cmake_minimum_required(VERSION 3.24)
include(${CMAKE_CURRENT_LIST_DIR}/../util/common.cmake)

auto_ccache()
project(${SKBUILD_PROJECT_NAME} LANGUAGES C VERSION ${SKBUILD_PROJECT_VERSION})
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(DEPS_DIR "${CMAKE_BINARY_DIR}/_deps")
get_filename_component(DEPS_DIR "${DEPS_DIR}" ABSOLUTE)
string(REPLACE "\"" "" DEPS_DIR "${DEPS_DIR}")
message(STATUS "DEPS_DIR=${DEPS_DIR}")

# Set default debug and release flags
set(_IS_DEBUG OFF) # Useful for later
if (CMAKE_BUILD_TYPE STREQUAL "Debug")
  set(_IS_DEBUG ON)
endif()
message(STATUS "Is this a debug build? ${_IS_DEBUG}")

# IPO/LTO requires ~50GiB RAM+SWAP, which is not available on GitHub actions
option(ENABLE_IPO "Enable Interprocedural Optimization / Link Time Optimization (requires lots of RAM)" OFF)
if(NOT _IS_DEBUG AND ENABLE_IPO)
  include(CheckIPOSupported)
  check_ipo_supported(RESULT check_ipo_res)
  if(check_ipo_res)
    message(STATUS "Enabling interprocedural optimization globally (LTO)")
    cmake_policy(SET CMP0069 NEW)
    set(CMAKE_POLICY_DEFAULT_CMP0069 NEW)
    set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)
  endif()
endif()

if(EMSCRIPTEN)
  # XXX: The build tries to link the following libraries, so they must be available (they are cached by emscripten)
  message(STATUS "Prebuilding emscripten core dependencies")
  execute_process(
    COMMAND embuilder build libdlmalloc libcompiler_rt-legacysjlj libc++-legacyexcept libc++abi-legacyexcept libunwind-legacyexcept libc++abi-debug-legacyexcept freetype freetype-legacysjlj --pic
    RESULT_VARIABLE EMBUILD_RESULT
    OUTPUT_VARIABLE EMBUILD_OUTPUT
    ERROR_VARIABLE EMBUILD_ERROR
  )
  message(STATUS "embuilder output: ${EMBUILD_OUTPUT}")
  message(STATUS "embuilder error: ${EMBUILD_ERROR}")
  if(NOT EMBUILD_RESULT EQUAL 0)
    message(FATAL_ERROR "Failed to run embuilder build")
  endif()

  # XXX: Make a local link to the sysroot, since pyodide will just drop it if it falls under /src
  execute_process( # Find sysroot automatically
    COMMAND bash -c "emcc --cflags | grep -o -- '--sysroot=[^ ]*' | cut -d= -f2"
    OUTPUT_VARIABLE EMSCRIPTEN_SYSROOT
    OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE EMSCRIPTEN_SYSROOT_RESULT
  )
  if(NOT EMSCRIPTEN_SYSROOT_RESULT EQUAL 0)
    message(FATAL_ERROR "Failed to retrieve emscripten sysroot")
  endif()
  message(STATUS "EMSCRIPTEN_SYSROOT=${EMSCRIPTEN_SYSROOT}")
  if(NOT EXISTS "${CMAKE_CURRENT_BINARY_DIR}/.emscripten_sysroot")
    execute_process(
      COMMAND ${CMAKE_COMMAND} -E create_symlink "${EMSCRIPTEN_SYSROOT}" "${CMAKE_CURRENT_BINARY_DIR}/.emscripten_sysroot"
      RESULT_VARIABLE LINK_RESULT
    )
    if(NOT LINK_RESULT EQUAL 0)
      message(FATAL_ERROR "Failed to create symbolic link to emscripten sysroot")
    endif()
    message(STATUS "Created symbolic link to emscripten sysroot at ${CMAKE_CURRENT_BINARY_DIR}/.emscripten_sysroot")
  endif()
  # Save the real sysroot path for use later; EMSCRIPTEN_SYSROOT gets overwritten
  # with a symlink path (for pyodide compat) on the next line.
  set(_EMSCRIPTEN_SYSROOT_REAL "${EMSCRIPTEN_SYSROOT}")
  set(EMSCRIPTEN_SYSROOT "${CMAKE_CURRENT_BINARY_DIR}/.emscripten_sysroot")

  # XXX: Copy PIC freetype port libraries to the non-PIC library directory.
  # embuilder --pic only builds PIC variants (into the pic/ subdirectory), but the
  # pyodide/pywasmcross linker wrapper does not add pic/ to the library search path
  # for SIDE_MODULE builds. Since this build always produces a SIDE_MODULE (.so),
  # all static libraries linked must be PIC-compatible.
  #
  # Use the REAL sysroot path (not the .emscripten_sysroot symlink) to ensure the
  # file ends up in the actual emscripten cache where the linker searches for it.
  set(_PIC_LIB_DIR "${_EMSCRIPTEN_SYSROOT_REAL}/lib/wasm32-emscripten/pic")
  set(_NONPIC_LIB_DIR "${_EMSCRIPTEN_SYSROOT_REAL}/lib/wasm32-emscripten")
  foreach(_lib freetype freetype-legacysjlj)
    set(_pic_lib "${_PIC_LIB_DIR}/lib${_lib}.a")
    set(_nonpic_lib "${_NONPIC_LIB_DIR}/lib${_lib}.a")
    if(EXISTS "${_pic_lib}" AND NOT EXISTS "${_nonpic_lib}")
      execute_process(COMMAND ${CMAKE_COMMAND} -E copy "${_pic_lib}" "${_NONPIC_LIB_DIR}"
        RESULT_VARIABLE _copy_result
      )
      if(_copy_result EQUAL 0)
        message(STATUS "Copied PIC library: ${_pic_lib} -> ${_nonpic_lib}")
      else()
        message(FATAL_ERROR "Failed to copy ${_pic_lib} to ${_NONPIC_LIB_DIR}")
      endif()
      # Double-check the file actually exists at the destination
      if(NOT EXISTS "${_nonpic_lib}")
        message(FATAL_ERROR "PIC library copy verification failed for ${_nonpic_lib}")
      endif()
    elseif(NOT EXISTS "${_pic_lib}")
      message(WARNING "PIC library not found: ${_pic_lib} (embuilder may have failed)")
    endif()
  endforeach()
endif()

# XXX: I only want to install the final build, not intermediate outputs
function(install)
  if("${ARGV1}" STREQUAL "OCP" AND NOT EMSCRIPTEN)
    message(STATUS "XXX: Calling real install for: ${ARGV1}")
    _install(${ARGV})
  elseif("${ARGV0}" STREQUAL "INSTALL_ME")
    message(STATUS "XXX: Calling real install for: ${ARGV2}")
    list(SUBLIST ARGV 1 -1 rest_args)
    _install(${rest_args})
  else()
    message(STATUS "XXX: Skipping install for: ${ARGV1}")
  endif()
endfunction()

# ##### Pybind11 #####
set(PYBIND11_SRC "${DEPS_DIR}/pybind11-src")
set(PYBIND11_BIN "${DEPS_DIR}/pybind11-build")
set(PYBIND11_USE_CROSSCOMPILING ON)
checkout_git_tag(SRC "${PYBIND11_SRC}" URL "https://github.com/pybind/pybind11.git" TAG "v3.0.4")
execute_process(
  COMMAND ${CMAKE_COMMAND} "-DREAL_SOURCE_DIR=${PYBIND11_SRC}" "-DREAL_BINARY_DIR=${PYBIND11_BIN}"
    -P "${CMAKE_CURRENT_LIST_DIR}/patch_pybind11.cmake"
  COMMAND_ERROR_IS_FATAL ANY)
set_timestamps("${PYBIND11_SRC}")
add_subdirectory("${PYBIND11_SRC}" "${PYBIND11_BIN}")

# ##### rapidjson #####
set(RAPIDJSON_SRC "${DEPS_DIR}/rapidjson-src")
checkout_git_tag(SRC "${RAPIDJSON_SRC}" URL "https://github.com/Tencent/rapidjson.git" TAG "24b5e7a8b27f42fa16b96fc70aade9106cf7102f")
execute_process(
  COMMAND ${CMAKE_COMMAND} "-DREAL_SOURCE_DIR=${RAPIDJSON_SRC}" -P "${CMAKE_CURRENT_LIST_DIR}/patch_rapidjson.cmake"
  COMMAND_ERROR_IS_FATAL ANY)
set_timestamps("${RAPIDJSON_SRC}")
add_subdirectory("${RAPIDJSON_SRC}")

# ##### fmt #####
set(FMT_SRC "${DEPS_DIR}/fmt-src")
set(FMT_BIN "${DEPS_DIR}/fmt-build")
checkout_git_tag(SRC "${FMT_SRC}" URL "https://github.com/fmtlib/fmt.git" TAG "12.1.0")
set_timestamps("${FMT_SRC}")
# Disable tests/docs/install noise
set(FMT_DOC OFF CACHE BOOL "" FORCE)
set(FMT_TEST OFF CACHE BOOL "" FORCE)
set(FMT_INSTALL ON CACHE BOOL "" FORCE)
add_subdirectory("${FMT_SRC}" "${FMT_BIN}")

# ##### OCCT #####
set(OCCT_SRC "${DEPS_DIR}/OpenCASCADE-src")
set(OCCT_BIN "${DEPS_DIR}/OpenCASCADE-build")
set(BUILD_DOC_Overview OFF)
set(BUILD_ADDITIONAL_TOOLKITS TKV3d)
checkout_git_tag(SRC "${OCCT_SRC}" URL "https://github.com/Open-Cascade-SAS/OCCT.git" TAG "V7_9_3")
execute_process(
  COMMAND ${CMAKE_COMMAND} "-DREAL_SOURCE_DIR=${OCCT_SRC}" "-DREAL_BINARY_DIR=${OCCT_BIN}"
    "-Drapidjson_SOURCE_DIR=${RAPIDJSON_SRC}"
    "-Dfreetype_INCLUDE_DIR=${EMSCRIPTEN_SYSROOT}/include/freetype2"
    -P "${CMAKE_CURRENT_LIST_DIR}/patch_OpenCASCADE.cmake"
  COMMAND_ERROR_IS_FATAL ANY)
set_timestamps("${OCCT_SRC}")
set_timestamps("${EMSCRIPTEN_SYSROOT}")
add_subdirectory("${OCCT_SRC}" "${OCCT_BIN}")

# Retrieve required OpenCASCADE information
message(STATUS "opencascade_BINARY_DIR=${OCCT_BIN}")
include("${OCCT_SRC}/adm/cmake/occt_macros.cmake")
OCCT_MODULES_AND_TOOLKITS (MODULES "TOOLKITS" OCCT_MODULES)
set(BUILD_TOOLKITS)
foreach (OCCT_MODULE ${OCCT_MODULES})
  foreach (__TK ${${OCCT_MODULE}_TOOLKITS})
    if(TARGET ${__TK})
      list(APPEND BUILD_TOOLKITS ${__TK})
    endif()
  endforeach()
endforeach()
string(REPLACE ";" " " BUILD_TOOLKITS_C "${BUILD_TOOLKITS}")
message(STATUS "-DOpenCASCADE_LIBRARIES=\\\"${BUILD_TOOLKITS_C}\\\"")

# ##### OCP #####
list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_LIST_DIR}/../util") # Findpybind11.cmake
set(OCP_SRC "${DEPS_DIR}/OCP-src")
set(OCP_BIN "${DEPS_DIR}/OCP-build")
download_url(NAME OCP URL "https://github.com/CadQuery/OCP/releases/download/7.9.3.1/OCP_src_stubs_Linux.zip" DEST "${OCP_SRC}")

execute_process(
  COMMAND ${CMAKE_COMMAND} "-DREAL_SOURCE_DIR=${OCP_SRC}" "-DREAL_BINARY_DIR=${OCP_BIN}"
    "-DROOT_SOURCE_DIR=${CMAKE_SOURCE_DIR}"
    "-DOpenCASCADE_BINARY_DIR=${OCCT_BIN}"
    "-DOpenCASCADE_LIBRARIES=${BUILD_TOOLKITS_C}"
    "-Drapidjson_SOURCE_DIR=${RAPIDJSON_SRC}"
    -P "${CMAKE_CURRENT_LIST_DIR}/patch_OCP.cmake"
  COMMAND_ERROR_IS_FATAL ANY)
set_timestamps("${OCP_SRC}")
add_subdirectory("${OCP_SRC}" "${OCP_BIN}")

if(EMSCRIPTEN)
  # Get wasm opt version early to make sure it is available before the long build
  execute_process(
    COMMAND wasm-opt --version
    OUTPUT_VARIABLE WASM_OPT_VERSION
    OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE WASM_OPT_RESULT
  )
  if (NOT WASM_OPT_RESULT EQUAL 0)
    message(FATAL_ERROR "wasm-opt is not available but it is required for the build.")
  endif()
  message(STATUS "Setting up extra repair/optimization pass using ${WASM_OPT_VERSION}")
  string(CONCAT FLAGS "$ENV{LDFLAGS}" "${CMAKE_EXE_LINKER_FLAGS}")
  if(NOT FLAGS MATCHES "-O[01g]")
    message(FATAL_ERROR "LDFLAGS must contain -O0, -O1, or -Og.")
  endif()

  set(OPTIMIZED_DIR "${CMAKE_CURRENT_BINARY_DIR}/OCP-wasm-opt")
  file(REMOVE_RECURSE "${OPTIMIZED_DIR}") # Always re-do the optimization step to avoid issues
  add_custom_command(
    DEPENDS OCP
    OUTPUT "${OPTIMIZED_DIR}"
    COMMAND ${CMAKE_COMMAND} -E env DEBUG=${_IS_DEBUG} PYTHONPATH=$ENV{PYTHONPATH}
            python3 "${CMAKE_CURRENT_SOURCE_DIR}/repair_wasm.py" "${OCP_BIN}" "${OPTIMIZED_DIR}"
    VERBATIM
  )
  add_custom_target(OCP-wasm-opt-target ALL DEPENDS "${OPTIMIZED_DIR}")
  install(INSTALL_ME DIRECTORY "${OPTIMIZED_DIR}/" DESTINATION "." FILES_MATCHING PATTERN "*.so")
endif()
