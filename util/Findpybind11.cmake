# Findpybind11.cmake
# Locates pybind11 when already added via add_subdirectory in a parent
# scope (checkout_git_tag + add_subdirectory).

if(TARGET pybind11::module)
  set(pybind11_FOUND TRUE)
  # Query include dirs from existing target rather than re-searching
  if(TARGET pybind11::headers)
    get_target_property(_pybind11_include_dirs pybind11::headers
      INTERFACE_INCLUDE_DIRECTORIES)
    if(_pybind11_include_dirs)
      set(pybind11_INCLUDE_DIRS "${_pybind11_include_dirs}")
      set(pybind11_INCLUDE_DIR "${_pybind11_include_dirs}")
      set(PYBIND11_INCLUDE_DIR "${_pybind11_include_dirs}")
      set(PYBIND11_INCLUDE_DIRS "${_pybind11_include_dirs}")
    endif()
  endif()
  return()
endif()

if(NOT pybind11_FOUND)
  message(FATAL_ERROR "pybind11::module target not found. Ensure pybind11 is configured as a subdirectory before use.")
endif()
