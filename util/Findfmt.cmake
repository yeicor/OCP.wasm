# Findfmt.cmake
# Locates fmt when already added via add_subdirectory in a parent
# scope (checkout_git_tag + add_subdirectory).

if(TARGET fmt::fmt)
  set(fmt_FOUND TRUE)

  # Query include dirs from existing target rather than re-searching
  get_target_property(_fmt_include_dirs fmt::fmt
    INTERFACE_INCLUDE_DIRECTORIES)

  if(_fmt_include_dirs)
    set(fmt_INCLUDE_DIRS "${_fmt_include_dirs}")
    set(fmt_INCLUDE_DIR "${_fmt_include_dirs}")
    set(FMT_INCLUDE_DIR "${_fmt_include_dirs}")
    set(FMT_INCLUDE_DIRS "${_fmt_include_dirs}")
  endif()

  return()
endif()

# Header-only fallback
if(TARGET fmt::fmt-header-only)
  set(fmt_FOUND TRUE)

  get_target_property(_fmt_include_dirs fmt::fmt-header-only
    INTERFACE_INCLUDE_DIRECTORIES)

  if(_fmt_include_dirs)
    set(fmt_INCLUDE_DIRS "${_fmt_include_dirs}")
    set(fmt_INCLUDE_DIR "${_fmt_include_dirs}")
    set(FMT_INCLUDE_DIR "${_fmt_include_dirs}")
    set(FMT_INCLUDE_DIRS "${_fmt_include_dirs}")
  endif()

  return()
endif()

if(NOT fmt_FOUND)
  message(FATAL_ERROR
    "fmt target not found. Ensure fmt is configured as a subdirectory before use.")
endif()
