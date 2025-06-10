cmake_minimum_required(VERSION 3.24)
project(OCP LANGUAGES CXX)

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
set(CMAKE_C_FLAGS_DEBUG "-Og -g")
set(CMAKE_CXX_FLAGS_DEBUG "-Og -g")
set(CMAKE_LD_FLAGS_DEBUG "-Og -g -gsource-map=inline")
set(CMAKE_C_FLAGS_RELEASE "-O3")
set(CMAKE_CXX_FLAGS_RELEASE "-O3")
set(CMAKE_LD_FLAGS_RELEASE "-O3")

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

# XXX: I only want to install the final static build, not intermediate outputs
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

if(EMSCRIPTEN)
  set(PYWASMCROSS_ENV_FILE "${CMAKE_SOURCE_DIR}/.pyodide_build/pywasmcross_symlinks/pywasmcross_env.json")
  file(READ "${PYWASMCROSS_ENV_FILE}" PYWASMCROSS_ENV_CONTENTS)
  # XXX: https://github.com/llvm/llvm-project/issues/63183
  string(REPLACE "-fwasm-exceptions" "" PYWASMCROSS_ENV_CONTENTS "${PYWASMCROSS_ENV_CONTENTS}")
  # This lets the CMake build system override debug and optimization levels
  string(REPLACE "-O2" "" PYWASMCROSS_ENV_CONTENTS "${PYWASMCROSS_ENV_CONTENTS}")
  string(REPLACE "-g0" "" PYWASMCROSS_ENV_CONTENTS "${PYWASMCROSS_ENV_CONTENTS}")
  file(WRITE "${PYWASMCROSS_ENV_FILE}" "${PYWASMCROSS_ENV_CONTENTS}")
  message(STATUS "Patched pywasmcross_env.json")
  
  set(PYWASMCROSS_FILE "${CMAKE_SOURCE_DIR}/.pyodide_build/pywasmcross_symlinks/pywasmcross.py")
  file(READ "${PYWASMCROSS_FILE}" PYWASMCROSS_CONTENTS)
  # Force previous changes to take effect by ignoring the environment
  string(REPLACE "if \"PYWASMCROSS_ARGS\" in os.environ:" "if False:" PYWASMCROSS_CONTENTS "${PYWASMCROSS_CONTENTS}")
  # Force even harder ignoring wasm exceptions (see above)
  string(REPLACE "    return new_args" "    new_args = [a for a in new_args if a != '-fwasm-exceptions']\n    # print('Compiling args: ' + str(new_args), file=sys.stderr)\n\n    return new_args" PYWASMCROSS_CONTENTS "${PYWASMCROSS_CONTENTS}")
  file(WRITE "${PYWASMCROSS_FILE}" "${PYWASMCROSS_CONTENTS}")
  message(STATUS "Patched pywasmcross.py")
endif()

# ##### OCCT #####
set(BUILD_DOC_Overview OFF) 
set(BUILD_ADDITIONAL_TOOLKITS TKV3d) # TODO: For some reason this toolkit from the Visualization module is required from other modules
FetchContent_Declare(
  OpenCASCADE
  GIT_REPOSITORY "https://github.com/Open-Cascade-SAS/OCCT.git"
  GIT_TAG "V7_8_1"
  GIT_PROGRESS TRUE
  PATCH_COMMAND
    ${CMAKE_COMMAND}
    -DREAL_SOURCE_DIR=<SOURCE_DIR>
    -DREAL_BINARY_DIR=<BINARY_DIR>
    -P ${CMAKE_CURRENT_LIST_DIR}/patch_OpenCASCADE.cmake
  OVERRIDE_FIND_PACKAGE TRUE
)

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
    -P ${CMAKE_CURRENT_LIST_DIR}/patch_pybind11.cmake
  OVERRIDE_FIND_PACKAGE TRUE
)

# ##### rapidjson #####
FetchContent_Declare(
  rapidjson
  GIT_REPOSITORY "https://github.com/Tencent/rapidjson.git"
  GIT_TAG "v1.1.0"
  GIT_PROGRESS TRUE
  PATCH_COMMAND
    ${CMAKE_COMMAND}
    -DREAL_SOURCE_DIR=<SOURCE_DIR>
    -DREAL_BINARY_DIR=<BINARY_DIR>
    -P ${CMAKE_CURRENT_LIST_DIR}/patch_rapidjson.cmake
  OVERRIDE_FIND_PACKAGE TRUE
)

# Make dependencies available
FetchContent_MakeAvailable(OpenCASCADE pybind11 rapidjson)

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
    -P ${CMAKE_CURRENT_LIST_DIR}/patch_OCP.cmake
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

# Final wasm-opt --post-emscripten -O4 pass for release builds
if(EMSCRIPTEN AND NOT _IS_DEBUG)
  message(STATUS "Setting up extra optimization pass for release build")
  FetchContent_GetProperties(OCP)
  set(OPTIMIZED_DIR "${CMAKE_CURRENT_BINARY_DIR}/OCP-wasm-opt")
  file(MAKE_DIRECTORY "${OPTIMIZED_DIR}")
  add_custom_command(
    DEPENDS OCP
    OUTPUT "${OPTIMIZED_DIR}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${OPTIMIZED_DIR}"
    COMMAND ${CMAKE_COMMAND} -E env DEBUG=${_IS_DEBUG} PYTHONPATH=$ENV{PYTHONPATH}
            sh -c "SO_FILE=\"$(find ${OCP_BINARY_DIR} -name '*.so')\" wasm-opt --post-emscripten -O4 \"$SO_FILE\" \"${OPTIMIZED_DIR}/$(basename \"$SO_FILE\")\""
    VERBATIM
  )
  add_custom_target(OCP-wasm-opt-target ALL DEPENDS "${OPTIMIZED_DIR}")  # XXX: target required for custom command to happen?
  install(INSTALL_ME DIRECTORY "${OPTIMIZED_DIR}/" DESTINATION ".")
endif()



