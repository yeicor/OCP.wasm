cmake_minimum_required(VERSION 3.24)
project(${SKBUILD_PROJECT_NAME} LANGUAGES C VERSION ${SKBUILD_PROJECT_VERSION})

set(CMAKE_POSITION_INDEPENDENT_CODE ON)

include(FetchContent)
Set(FETCHCONTENT_QUIET FALSE)

option(AUTO_CCACHE "Use ccache to speed up rebuilds" ON)
find_program(CCACHE_PROGRAM ccache)
if(CCACHE_PROGRAM AND ${AUTO_CCACHE})
  message(STATUS "Using ${CCACHE_PROGRAM} as compiler launcher")
  set(CMAKE_C_COMPILER_LAUNCHER "${CCACHE_PROGRAM}")
  set(CMAKE_CXX_COMPILER_LAUNCHER "${CCACHE_PROGRAM}")
endif()


# Set default debug and release flags
set(_IS_DEBUG OFF) # Useful for later
if (CMAKE_BUILD_TYPE STREQUAL "Debug")
    set(_IS_DEBUG ON)
endif()
message(STATUS "Is this a debug build? ${_IS_DEBUG}")
# XXX: The following is overwritten by pyodide during build, so moved to main.yml as environment vars
# set(CMAKE_C_FLAGS_DEBUG "-Og -g -gsource-map=inline" CACHE STRING "Flags used by the compiler" FORCE)
# set(CMAKE_CXX_FLAGS_DEBUG "-Og -g -gsource-map=inline" CACHE STRING "Flags used by the compiler" FORCE)
# set(CMAKE_C_FLAGS_RELEASE "-O3" CACHE STRING "Flags used by the compiler" FORCE)
# set(CMAKE_CXX_FLAGS_RELEASE "-O3" CACHE STRING "Flags used by the compiler" FORCE)

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

# XXX: I only want to install the final build, not intermediate outputs
function(install)
  # XXX: This may ignore installation of some system files required for some operations? But its mostly docs and static libraries...
  if("${ARGV1}" STREQUAL "OCP" AND (_IS_DEBUG OR NOT EMSCRIPTEN))
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
set(PYBIND11_USE_CROSSCOMPILING ON) # Will enable this if it is actually used (e.g. emscripten)
FetchContent_Declare(
  pybind11
  GIT_REPOSITORY "https://github.com/pybind/pybind11.git"
  GIT_TAG "v2.13.6"
  GIT_PROGRESS TRUE
  PATCH_COMMAND
    ${CMAKE_COMMAND}
    -DREAL_SOURCE_DIR=<SOURCE_DIR>
    -DREAL_BINARY_DIR=<BINARY_DIR>
    -P ${CMAKE_CURRENT_LIST_DIR}/patch_pybind11.cmake &&
    "${CMAKE_COMMAND}" -E env PYTHONPATH=$ENV{PYTHONPATH} python3 "${CMAKE_SOURCE_DIR}/../util/set_timestamps.py" "<SOURCE_DIR>" # XXX: Better caching!
  OVERRIDE_FIND_PACKAGE
)

# ##### rapidjson #####
FetchContent_Declare(
  rapidjson
  GIT_REPOSITORY "https://github.com/Tencent/rapidjson.git"
  GIT_TAG "24b5e7a8b27f42fa16b96fc70aade9106cf7102f"  # They do not make new releases for some reason...
  GIT_PROGRESS TRUE
  PATCH_COMMAND
    ${CMAKE_COMMAND}
    -DREAL_SOURCE_DIR=<SOURCE_DIR>
    -DREAL_BINARY_DIR=<BINARY_DIR>
    -P ${CMAKE_CURRENT_LIST_DIR}/patch_rapidjson.cmake &&
    "${CMAKE_COMMAND}" -E env PYTHONPATH=$ENV{PYTHONPATH} python3 "${CMAKE_SOURCE_DIR}/../util/set_timestamps.py" "<SOURCE_DIR>" # XXX: Better caching!
  OVERRIDE_FIND_PACKAGE
)

# ##### FreeType #####
FetchContent_Declare(
  freetype
  URL "https://download.savannah.gnu.org/releases/freetype/freetype-2.13.2.tar.gz"
  PATCH_COMMAND "${CMAKE_COMMAND}" -E env PYTHONPATH=$ENV{PYTHONPATH} python3 "${CMAKE_SOURCE_DIR}/../util/set_timestamps.py" "<SOURCE_DIR>" # XXX: Better caching!
  OVERRIDE_FIND_PACKAGE
)

# Make dependencies available
FetchContent_MakeAvailable(pybind11 rapidjson freetype)

# ##### OCCT #####
set(BUILD_DOC_Overview OFF) 
set(BUILD_ADDITIONAL_TOOLKITS TKV3d) # For some reason this toolkit from the Visualization module is required from other modules...
FetchContent_Declare(
  OpenCASCADE
  GIT_REPOSITORY "https://github.com/Open-Cascade-SAS/OCCT.git"
  GIT_TAG "V7_8_1"
  GIT_PROGRESS TRUE
  PATCH_COMMAND
    ${CMAKE_COMMAND}
    -DREAL_SOURCE_DIR=<SOURCE_DIR>
    -DREAL_BINARY_DIR=<BINARY_DIR>
    -Drapidjson_SOURCE_DIR=${rapidjson_SOURCE_DIR}
    -Dfreetype_SOURCE_DIR=${freetype_SOURCE_DIR}
    -P ${CMAKE_CURRENT_LIST_DIR}/patch_OpenCASCADE.cmake &&
    "${CMAKE_COMMAND}" -E env PYTHONPATH=$ENV{PYTHONPATH} python3 "${CMAKE_SOURCE_DIR}/../util/set_timestamps.py" "<SOURCE_DIR>" # XXX: Better caching!
  OVERRIDE_FIND_PACKAGE
)
FetchContent_MakeAvailable(OpenCASCADE)

# Retrieve required OpenCASCADE information
FetchContent_GetProperties(OpenCASCADE)
message(STATUS "opencascade_BINARY_DIR=${opencascade_BINARY_DIR}")
# The following fragment is partially extracted from OpenCASCADE
include("${opencascade_SOURCE_DIR}/adm/cmake/occt_macros.cmake")
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
FetchContent_Declare(
  OCP
  URL "https://github.com/CadQuery/OCP/releases/download/7.8.1.2/OCP_src_stubs_ubuntu-20.04.zip"
  PATCH_COMMAND
    ${CMAKE_COMMAND}
    -DREAL_SOURCE_DIR=<SOURCE_DIR>
    -DREAL_BINARY_DIR=<BINARY_DIR>
    -DROOT_SOURCE_DIR=${CMAKE_SOURCE_DIR}
    -DOpenCASCADE_BINARY_DIR=${opencascade_BINARY_DIR}
    -DOpenCASCADE_LIBRARIES=${BUILD_TOOLKITS_C}
    -Drapidjson_SOURCE_DIR=${rapidjson_SOURCE_DIR}
    -Dfreetype_BINARY_DIR=${freetype_BINARY_DIR}
    -P ${CMAKE_CURRENT_LIST_DIR}/patch_OCP.cmake &&
    "${CMAKE_COMMAND}" -E env PYTHONPATH=$ENV{PYTHONPATH} python3 "${CMAKE_SOURCE_DIR}/../util/set_timestamps.py" "<SOURCE_DIR>" # XXX: Better caching!
)

# Make main target available
FetchContent_MakeAvailable(OCP)

# The build tries to link the following libraries, so they must be available (they are cached by emscripten)
if(EMSCRIPTEN)
  message(STATUS "Prebuilding emscripten core dependencies")
  execute_process(
    COMMAND embuilder build libdlmalloc libcompiler_rt-legacysjlj libc++-legacyexcept libc++abi-legacyexcept libunwind-legacyexcept libc++abi-debug-legacyexcept --pic
    RESULT_VARIABLE EMBUILD_RESULT
  )
  if(NOT EMBUILD_RESULT EQUAL 0)
      message(FATAL_ERROR "Failed to run embuilder")
  endif()
endif()

if(EMSCRIPTEN)
  message(STATUS "Setting up extra repair/optimization pass")
  # XXX: All builds hit this issue: https://github.com/llvm/llvm-project/issues/63183
  # As a hacky workaround, replace all invalid instructions (usually very few) with unreachable opcodes
  # This also requires linking with an optimization level <= 1, otherwise internal linker validation
  # during optimization would fail. Note that optimization is still invoked manually after the file is "repaired".
  string(CONCAT FLAGS "$ENV{LDFLAGS}" "${CMAKE_EXE_LINKER_FLAGS}")
  if(NOT FLAGS MATCHES "-O[01g]")
    message(FATAL_ERROR "LDFLAGS must contain -O0, -O1, or -Og. See comment above this error.")
  endif()
  FetchContent_GetProperties(OCP)
  set(OPTIMIZED_DIR "${CMAKE_CURRENT_BINARY_DIR}/OCP-wasm-opt")
  file(MAKE_DIRECTORY "${OPTIMIZED_DIR}")
  add_custom_command(
    DEPENDS OCP
    OUTPUT "${OPTIMIZED_DIR}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${OPTIMIZED_DIR}"
    COMMAND ${CMAKE_COMMAND} -E env DEBUG=${_IS_DEBUG} PYTHONPATH=$ENV{PYTHONPATH}
            python3 "${CMAKE_CURRENT_SOURCE_DIR}/repair_wasm.py" "${OCP_BINARY_DIR}" "${OPTIMIZED_DIR}"
    VERBATIM
  )
  add_custom_target(OCP-wasm-opt-target ALL DEPENDS "${OPTIMIZED_DIR}")
  install(INSTALL_ME DIRECTORY "${OPTIMIZED_DIR}/" DESTINATION ".")
endif()



