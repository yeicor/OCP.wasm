cmake_minimum_required(VERSION 3.24)
project(OCP LANGUAGES CXX)

set(CMAKE_POSITION_INDEPENDENT_CODE ON)

include(FetchContent)
Set(FETCHCONTENT_QUIET FALSE)

# TODO: IPO/LTO makes required symbols dissappear?
if(CMAKE_BUILD_TYPE STREQUAL "Release")
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
  message(STATUS "Enabling emscripten hacks")
  # XXX: Avoid some final linking arguments assuming they are implicit
  list(APPEND CMAKE_CXX_IMPLICIT_LINK_LIBRARIES stubs c dlmalloc compiler_rt-legacysjlj c++-legacyexcept c++abi-legacyexcept unwind-legacyexcept c++abi-debug-legacyexcept)
  message(NOTICE "CMAKE_CXX_IMPLICIT_LINK_LIBRARIES=${CMAKE_CXX_IMPLICIT_LINK_LIBRARIES}")
  # XXX: Builds are broken, which means that automatic post-processing of -O2+ fails
  # Furthermore, pyodide defaults to O2 without a way to overwrite it from cmake, so ask the user to set it
  if(NOT CMAKE_EXE_LINKER_FLAGS MATCHES "-O1")
      message(FATAL_ERROR "Please set LDFLAGS=\"-O1\" before building with pyodide")
  endif()
endif()

function(install)
  if("${ARGV1}" STREQUAL "OCP")
    message(STATUS "XXX: Calling real install for: ${ARGV1}" )
    _install(${ARGV})
  else()
    message(STATUS "XXX: Skipping install of statically-linked dependency: ${ARGV1}")
  endif()
endfunction()

# ##### OCCT #####
set(BUILD_DOC_Overview OFF) 
set(BUILD_ADDITIONAL_TOOLKITS TKV3d) # TODO: For some reason this toolkit from the Visualization module is required from other modules
FetchContent_Declare(
  OpenCASCADE
  GIT_REPOSITORY "https://github.com/Open-Cascade-SAS/OCCT.git"
  GIT_TAG V7_8_1
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
  GIT_TAG v2.13.2
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
  GIT_REPOSITORY https://github.com/Tencent/rapidjson.git
  GIT_TAG v1.1.0
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
