if(NOT DEFINED REAL_SOURCE_DIR)
  message(FATAL_ERROR "REAL_SOURCE_DIR must be defined")
endif()
if(NOT DEFINED REAL_BINARY_DIR)
  message(FATAL_ERROR "REAL_BINARY_DIR must be defined")
endif()

file(GLOB_RECURSE cmake_files
  "${REAL_SOURCE_DIR}/CMakeLists.txt"
  "${REAL_SOURCE_DIR}/adm/cmake/*.cmake"
)

foreach(f IN LISTS cmake_files)
  file(READ "${f}" content)
  string(REPLACE "\${CMAKE_SOURCE_DIR}" "${REAL_SOURCE_DIR}" content "${content}")
  string(REPLACE "\$CMAKE_SOURCE_DIR" "${REAL_SOURCE_DIR}" content "${content}")
  string(REPLACE "\${CMAKE_BINARY_DIR}" "${REAL_BINARY_DIR}" content "${content}")
  string(REPLACE "\$CMAKE_BINARY_DIR" "${REAL_BINARY_DIR}" content "${content}")
  file(WRITE "${f}" "${content}")
endforeach()
