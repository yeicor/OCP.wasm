if(NOT DEFINED REAL_SOURCE_DIR)
  message(FATAL_ERROR "REAL_SOURCE_DIR must be defined")
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
  string(TOLOWER "${f}" f_lower)
  if(f_lower MATCHES "vtk")
    list(APPEND vtk_and_opengl_sources "${f}")
  endif()
  if(f_lower MATCHES "opengl")
    list(APPEND vtk_and_opengl_sources "${f}")
  endif()
endforeach()

foreach(f IN LISTS vtk_and_opengl_sources)
  file(REMOVE "${f}")
endforeach()

# ----- Modify OCP.cpp -----
set(ocp_cpp "${REAL_SOURCE_DIR}/OCP.cpp")
file(READ "${ocp_cpp}" content)
string(REGEX REPLACE "(\n)([^/\n]+register_[^\n]*([vV][tT][kK]|OpenGl)[^\n]*)" "\\1/*\\2*/" content "${content}")
file(WRITE "${ocp_cpp}" "${content}")

# ----- Modify OSD.cpp -----
# Do not expose OSD_OpenFile as FILE* is not safely bindable in Emscripten (or even desktop platforms in many cases) via pybind11 because of the incomplete _IO_FILE type and RTTI (typeid) issues.
set(osd_cpp "${REAL_SOURCE_DIR}/OSD.cpp")
file(READ "${osd_cpp}" osd_content)
string(REGEX REPLACE "([ \t])(m\\.def\\(\"OSD_OpenFile\",[^;]*;)" "\\1/*\\2*/" osd_content "${osd_content}")
file(WRITE "${osd_cpp}" "${osd_content}")

# ----- Patch CMakeLists.txt -----
message(STATUS "OpenCASCADE_LIBRARIES=${OpenCASCADE_LIBRARIES}")
set(OCP_CMAKE "${REAL_SOURCE_DIR}/CMakeLists.txt")
file(READ "${OCP_CMAKE}" content)
string(REGEX REPLACE "\n([ \t]*find_package[ \t]*\\([^)]*(VTK|Python)[^)]*\\))" "\n#[[ \\1 ]]" content "${content}")
string(REGEX REPLACE "([ \t]+)(VTK::[^ )]*)" "\\1#[[\\2]]" content "${content}")
string(REGEX REPLACE "([ \t]+)(INTERPROCEDURAL_OPTIMIZATION[ \t]+FALSE)" "\\1#[[\\2]]" content "${content}")
string(REGEX REPLACE "(target_include_directories\\([ \t]?[^ )]+[ \t]?[^ )]+[ \t]?[^ )]+[ \t]?)+\\)" "\\1 \"${OpenCASCADE_BINARY_DIR}/include/opencascade\" \"${rapidjson_SOURCE_DIR}/include\")" content "${content}")
string(REGEX REPLACE "(target_link_libraries\\([ \t]?[^ )]+[ \t]?[^ )]+[ \t]?[^ )]+[ \t]?)\\)" "\\1 ${OpenCASCADE_LIBRARIES})" content "${content}")
string(REGEX REPLACE "SET\\(PYTHON_SP_DIR \\\"site-packages\\\"" "SET(PYTHON_SP_DIR \".\"" content "${content}")
string(REGEX REPLACE "\n\n([ \t]*install\\( *TARGETS +OCP)" "\nif(EMSCRIPTEN)\n  add_custom_command(TARGET OCP POST_BUILD COMMAND ${CMAKE_COMMAND} -E env \"PYTHONPATH=$ENV{PYTHONPATH}\" python3 \"${ROOT_SOURCE_DIR}/repair_and_optimize_wasm.py\" \"\$<TARGET_FILE:OCP>\")\nendif()\n\\1" content "${content}")
file(WRITE "${OCP_CMAKE}" "${content}")
