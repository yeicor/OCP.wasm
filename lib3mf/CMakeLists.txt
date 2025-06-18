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

# XXX: I only want to install the final build, not intermediate outputs
function(install)
  if("${ARGV0}" STREQUAL "INSTALL_ME")
    message(STATUS "XXX: Calling real install for: ${ARGV2}")
    list(SUBLIST ARGV 1 -1 rest_args)
    _install(${rest_args})
  else()
    message(STATUS "XXX: Skipping install for: ${ARGV1}")
  endif()
endfunction()

FetchContent_Declare(
  lib3mf
  GIT_REPOSITORY "https://github.com/3MFConsortium/lib3mf.git"
  GIT_TAG "v2.4.1"
  GIT_PROGRESS TRUE
  PATCH_COMMAND "${CMAKE_COMMAND}" "-DREAL_SOURCE_DIR=<SOURCE_DIR>" -P "${CMAKE_CURRENT_LIST_DIR}/patch.cmake"
  COMMAND /bin/sh -c "if [ ! -z \"$_FORCE_OLD_SOURCES\" ]; then find <SOURCE_DIR> -type f -exec touch -t 200001010000.00 {} +; fi" # XXX: Better caching!
  OVERRIDE_FIND_PACKAGE TRUE
)

FetchContent_MakeAvailable(lib3mf)

if(EMSCRIPTEN)
  message(STATUS "Setting up extra wheel download and repacking pass")

  FetchContent_Declare(
    lib3mf-wheel-original
    URL "https://github.com/3MFConsortium/lib3mf/releases/download/v2.4.1/lib3mf-2.4.1-py3-none-manylinux2014_x86_64.whl"
  )
  FetchContent_MakeAvailable(lib3mf-wheel-original)

  FetchContent_GetProperties(lib3mf lib3mf-wheel-original)
  set(WHEEL_CONTENTS_DIR "${CMAKE_CURRENT_BINARY_DIR}/lib3mf-wheel-contents")
  add_custom_command(
    DEPENDS lib3mf
    OUTPUT "${WHEEL_CONTENTS_DIR}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${WHEEL_CONTENTS_DIR}"
    COMMAND /bin/sh -c "rm -r '${WHEEL_CONTENTS_DIR}/lib3mf' || true"
    COMMAND /bin/sh -c "rm -r '${WHEEL_CONTENTS_DIR}/py_lib3mf' || true"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${WHEEL_CONTENTS_DIR}/lib3mf"
    COMMAND /bin/sh -c "cp '${lib3mf-wheel-original_SOURCE_DIR}/lib3mf/'*.py '${WHEEL_CONTENTS_DIR}/lib3mf/'"
    COMMAND /bin/sh -c "sed -i 's/linux/emscripten/g;s/Linux/Emscripten/g' '${WHEEL_CONTENTS_DIR}/lib3mf/'*.py"
    COMMAND /bin/sh -c "cp '${lib3mf_BINARY_DIR}/lib3mf.so' '${WHEEL_CONTENTS_DIR}/lib3mf/lib3mf.so'"
    COMMAND /bin/sh -c "cp -r '${WHEEL_CONTENTS_DIR}/lib3mf' '${WHEEL_CONTENTS_DIR}/py_lib3mf'" # XXX: Support old import by duplicating data
    VERBATIM
  )
  add_custom_target(lib3mf-wheel-target ALL DEPENDS "${WHEEL_CONTENTS_DIR}")
  install(INSTALL_ME DIRECTORY "${WHEEL_CONTENTS_DIR}/" DESTINATION ".")
endif()



