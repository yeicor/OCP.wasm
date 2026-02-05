if(NOT DEFINED REAL_SOURCE_DIR)
  message(FATAL_ERROR "REAL_SOURCE_DIR must be defined")
endif()
if(NOT DEFINED OpenCASCADE_LIBRARIES)
  message(FATAL_ERROR "OpenCASCADE_LIBRARIES must be defined")
endif()
if(NOT DEFINED OpenCASCADE_BINARY_DIR)
  message(FATAL_ERROR "OpenCASCADE_BINARY_DIR must be defined")
endif()
if(NOT DEFINED rapidjson_SOURCE_DIR)
  message(FATAL_ERROR "OpenCASCADE_BINARY_DIR must be defined")
endif()

# ----- Remove vtk-related files (case-insensitive) -----
file(GLOB_RECURSE all_sources
  "${REAL_SOURCE_DIR}/*.cpp"
  "${REAL_SOURCE_DIR}/*.cxx"
  "${REAL_SOURCE_DIR}/*.h"
  "${REAL_SOURCE_DIR}/*.hpp"
)

set(vtk_and_opengl_sources "")
foreach(f IN LISTS all_sources)
  get_filename_component(fname "${f}" NAME)
  string(TOLOWER "${fname}" fname_lower)
  if(fname_lower MATCHES "vtk")
    list(APPEND vtk_and_opengl_sources "${f}")
  endif()
  if(fname_lower MATCHES "opengl")
    list(APPEND vtk_and_opengl_sources "${f}")
  endif()
endforeach()

foreach(f IN LISTS vtk_and_opengl_sources)
  file(REMOVE "${f}")
endforeach()

# ----- Modify OCP.cpp -----
set(ocp_cpp "${REAL_SOURCE_DIR}/OCP.cpp")
file(READ "${ocp_cpp}" content)
set(content_old "${content}")
string(REGEX REPLACE "(\n)([^/\n]+register_[^\n]*([vV][tT][kK]|OpenGl)[^\n]*)" "\\1/*\\2*/" content "${content}")
if(NOT content STREQUAL content_old)
  file(WRITE "${ocp_cpp}" "${content}")
  message(STATUS "Patched OCP.cpp")
endif()

# ----- Modify OSD.cpp -----
# Do not expose OSD_OpenFile as FILE* is not safely bindable in Emscripten (or even desktop platforms in many cases) via pybind11 because of the incomplete _IO_FILE type and RTTI (typeid) issues.
set(osd_cpp "${REAL_SOURCE_DIR}/OSD.cpp")
file(READ "${osd_cpp}" content)
set(content_old "${content}")
string(REGEX REPLACE "([ \t])(m\\.def\\(\"OSD_OpenFile\",[^;]*;)" "\\1/*\\2*/" content "${content}")
if(NOT content STREQUAL content_old)
  file(WRITE "${osd_cpp}" "${content}")
  message(STATUS "Patched OSD.cpp")
endif()

# ----- Patch CMakeLists.txt -----
message(STATUS "OpenCASCADE_LIBRARIES=${OpenCASCADE_LIBRARIES}")
set(OCP_CMAKE "${REAL_SOURCE_DIR}/CMakeLists.txt")
file(READ "${OCP_CMAKE}" content)
set(content_old "${content}")
string(REGEX REPLACE "\n([ \t]*find_package[ \t]*\\([^)]*(VTK|Python)[^)]*\\))" "\n#[[ \\1 ]]" content "${content}")
string(REGEX REPLACE "([ \t]+)(VTK::[^ )]*)" "\\1#[[\\2]]" content "${content}")
string(REGEX REPLACE "([ \t]+)(INTERPROCEDURAL_OPTIMIZATION[ \t]+FALSE)" "\\1#[[\\2]]" content "${content}")
string(REGEX REPLACE "(target_include_directories\\([ \t]?[^ )]+[ \t]?[^ )]+[ \t]?[^ )]+[ \t]?)+\\)" "\\1 \"${OpenCASCADE_BINARY_DIR}/include/opencascade\" \"${rapidjson_SOURCE_DIR}/include\")" content "${content}")
string(REGEX REPLACE "(\ntarget_link_libraries\\([ \t]?[^ )]+[ \t]?[^ )]+[ \t]?[^ )]+[ \t]?)\\)" "\\1 ${OpenCASCADE_LIBRARIES} freetype)" content "${content}")
string(REGEX REPLACE "SET\\(PYTHON_SP_DIR \\\"site-packages\\\"" "SET(PYTHON_SP_DIR \".\"" content "${content}")
if(NOT content MATCHES ".*SKBUILD_SOABI.*")
    string(APPEND content "\nset_property(TARGET OCP PROPERTY SUFFIX \".\${SKBUILD_SOABI}\${CMAKE_SHARED_MODULE_SUFFIX}\")")
endif()
if(NOT content STREQUAL content_old)
  file(WRITE "${OCP_CMAKE}" "${content}")
  message(STATUS "Patched CMakeLists.txt")
endif()
