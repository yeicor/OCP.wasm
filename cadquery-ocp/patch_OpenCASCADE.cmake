if(NOT DEFINED REAL_SOURCE_DIR)
  message(FATAL_ERROR "REAL_SOURCE_DIR must be defined")
endif()
if(NOT DEFINED REAL_BINARY_DIR)
  message(FATAL_ERROR "REAL_BINARY_DIR must be defined")
endif()
if(NOT DEFINED rapidjson_SOURCE_DIR)
  message(FATAL_ERROR "rapidjson_SOURCE_DIR must be defined")
endif()

file(GLOB_RECURSE cmake_files
  "${REAL_SOURCE_DIR}/CMakeLists.txt"
  "${REAL_SOURCE_DIR}/adm/cmake/*.cmake"
)

foreach(f IN LISTS cmake_files)
  file(READ "${f}" content)
  set(content_old "${content}")
  string(REPLACE "\${CMAKE_SOURCE_DIR}" "${REAL_SOURCE_DIR}" content "${content}")
  string(REPLACE "\$CMAKE_SOURCE_DIR" "${REAL_SOURCE_DIR}" content "${content}")
  string(REPLACE "\${CMAKE_BINARY_DIR}" "${REAL_BINARY_DIR}" content "${content}")
  string(REPLACE "\$CMAKE_BINARY_DIR" "${REAL_BINARY_DIR}" content "${content}")
  string(REGEX REPLACE "(OCCT_IS_PRODUCT_REQUIRED *\\(CSF_RapidJSON +CAN_USE_RAPIDJSON\\))\n *if" "\\1\nset(3RDPARTY_RAPIDJSON_INCLUDE_DIR \"${rapidjson_SOURCE_DIR}/include\")\nif" content "${content}")
  if(NOT content STREQUAL content_old)
    file(WRITE "${f}" "${content}")
    message(STATUS "Patched ${f}")
  endif()
endforeach()
