# Shared utilities for OCP.wasm builds

# Setup ccache if available as compiler launcher
macro(auto_ccache)
  option(AUTO_CCACHE "Use ccache to speed up rebuilds" ON)
  find_program(CCACHE_PROGRAM ccache)
  if(CCACHE_PROGRAM AND ${AUTO_CCACHE})
    message(STATUS "Found ccache at ${CCACHE_PROGRAM}, will use as compiler launcher")
    set(CMAKE_C_COMPILER_LAUNCHER "${CCACHE_PROGRAM}" CACHE STRING "C compiler launcher" FORCE)
    set(CMAKE_CXX_COMPILER_LAUNCHER "${CCACHE_PROGRAM}" CACHE STRING "C++ compiler launcher" FORCE)
  else()
    set(CMAKE_C_COMPILER_LAUNCHER "" CACHE STRING "C compiler launcher" FORCE)
    set(CMAKE_CXX_COMPILER_LAUNCHER "" CACHE STRING "C++ compiler launcher" FORCE)
  endif()
endmacro()

# Configure FetchContent with project-standard settings
macro(configure_fetchcontent)
  include(FetchContent)
  set(FETCHCONTENT_QUIET FALSE)
  set(FETCHCONTENT_FULLY_DISCONNECTED FALSE)
  # Don't re-validate git info when cached downloads already exist
  set(FETCHCONTENT_UPDATES_DISCONNECTED TRUE)
endmacro()

# Override install() to only install targets explicitly marked with INSTALL_ME
macro(override_install)
  function(install)
    if("${ARGV0}" STREQUAL "INSTALL_ME")
      message(STATUS "XXX: Calling real install for: ${ARGV2}")
      list(SUBLIST ARGV 1 -1 rest_args)
      _install(${rest_args})
    else()
      message(STATUS "XXX: Skipping install for: ${ARGV1}")
    endif()
  endfunction()
endmacro()

# Set file timestamps to git commit time for reproducible builds.
# Requires _FORCE_OLD_SOURCES env var; otherwise a no-op.
function(set_timestamps SOURCE_DIR)
  if(DEFINED ENV{_FORCE_OLD_SOURCES})
    find_program(PYTHON3 python3 REQUIRED)
    execute_process(
      COMMAND "${PYTHON3}" "${CMAKE_SOURCE_DIR}/../util/set_timestamps.py" "${SOURCE_DIR}"
      COMMAND_ERROR_IS_FATAL ANY)
  endif()
endfunction()

# Idempotently fetch a specific git tag with --depth 1 and check it out.
# Creates a local tag ref so subsequent runs are a no-op.
# Optional: apply a CMake script patch after checkout.
function(checkout_git_tag)
  cmake_parse_arguments(PARSE_ARGV 0 _ "" "SRC;URL;TAG;PATCH" "")
  get_filename_component(__SRC "${__SRC}" ABSOLUTE)
  if(NOT EXISTS "${__SRC}/.git")
    execute_process(COMMAND git clone --depth 1 --recurse-submodules
      "${__URL}" "${__SRC}" COMMAND_ERROR_IS_FATAL ANY)
  endif()
  execute_process(
    COMMAND bash -c "
      set -ex
      if ! git rev-parse --verify refs/tags/\"${__TAG}\" >/dev/null 2>&1 ||
         [ \"\$(git rev-parse HEAD)\" != \"\$(git rev-parse refs/tags/\"${__TAG}\")\" ]; then
        git reset --hard
        git clean -fdx
        git fetch --depth 1 origin \"${__TAG}\"
        git checkout FETCH_HEAD
        git tag -f \"${__TAG}\" FETCH_HEAD
        git submodule update --init --recursive --depth 1 --force
      fi
    "
    WORKING_DIRECTORY "${__SRC}"
    COMMAND_ERROR_IS_FATAL ANY)
endfunction()

# Download and extract a URL archive idempotently into DEST.
# Skips the download if DEST exists and a stamp file matches the URL.
# Handles single top-level directory stripping (like FetchContent).
# Sets ${__NAME}_SOURCE_DIR = DEST in the caller scope.
function(download_url)
  cmake_parse_arguments(PARSE_ARGV 0 _ "" "NAME;URL;DEST" "")
  get_filename_component(__DEST "${__DEST}" ABSOLUTE)
  set(stamp_file "${CMAKE_BINARY_DIR}/_deps/${__NAME}.stamp")
  set(cached_stamp "")
  if(EXISTS "${stamp_file}")
    file(STRINGS "${stamp_file}" cached_stamp)
  endif()
  if("${__URL}" STREQUAL "${cached_stamp}" AND EXISTS "${__DEST}")
    set(${__NAME}_SOURCE_DIR "${__DEST}" PARENT_SCOPE)
    return()
  endif()
  message(STATUS "Downloading ${__NAME}...")
  file(REMOVE_RECURSE "${__DEST}")
  file(MAKE_DIRECTORY "${__DEST}")
  set(archive "${CMAKE_BINARY_DIR}/_deps/${__NAME}.dl")
  file(DOWNLOAD "${__URL}" "${archive}" SHOW_PROGRESS)
  file(ARCHIVE_EXTRACT INPUT "${archive}" DESTINATION ${__DEST})
  file(REMOVE "${archive}")
  # Strip single top-level directory (mimics FetchContent behavior)
  file(GLOB top_entries "${__DEST}/*")
  list(LENGTH top_entries n)
  if(n EQUAL 1)
    list(GET top_entries 0 single)
    if(IS_DIRECTORY "${single}")
      file(GLOB children "${single}/*")
      foreach(child ${children})
        get_filename_component(base "${child}" NAME)
        file(RENAME "${child}" "${__DEST}/${base}")
      endforeach()
      file(REMOVE_RECURSE "${single}")
    endif()
  endif()
  file(WRITE "${stamp_file}" "${__URL}")
  set(${__NAME}_SOURCE_DIR "${__DEST}" PARENT_SCOPE)
endfunction()
