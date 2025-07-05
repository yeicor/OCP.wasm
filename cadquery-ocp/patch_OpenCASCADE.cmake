if(NOT DEFINED REAL_SOURCE_DIR)
  message(FATAL_ERROR "REAL_SOURCE_DIR must be defined")
endif()
if(NOT DEFINED REAL_BINARY_DIR)
  message(FATAL_ERROR "REAL_BINARY_DIR must be defined")
endif()
if(NOT DEFINED rapidjson_SOURCE_DIR)
  message(FATAL_ERROR "rapidjson_SOURCE_DIR must be defined")
endif()
if(NOT DEFINED freetype_SOURCE_DIR)
  message(FATAL_ERROR "freetype_SOURCE_DIR must be defined")
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
  string(REGEX REPLACE "(# define CSF variable)\n(OCCT_INCLUDE_CMAKE_FILE)" "\\1\n\
  set(3RDPARTY_RAPIDJSON_INCLUDE_DIR \"${rapidjson_SOURCE_DIR}/include\")\n\
  set(3RDPARTY_FREETYPE_INCLUDE_DIR_ft2build \"${freetype_SOURCE_DIR}/include\")\n\
  set(3RDPARTY_FREETYPE_INCLUDE_DIR_freetype2 \"${freetype_SOURCE_DIR}/include\")\n\
  \\2" content "${content}")
  if(NOT content STREQUAL content_old)
    file(WRITE "${f}" "${content}")
    message(STATUS "Patched ${f}")
  endif()
endforeach()

# ----- Patch StdPrs_BrepFont.cxx -----
set(stdprs_brepfont_cxx "${REAL_SOURCE_DIR}/src/StdPrs/StdPrs_BRepFont.cxx")
file(READ "${stdprs_brepfont_cxx}" content)
set(content_old "${content}")
string(REPLACE "const char* aTags" "const auto aTags" content "${content}")
if(NOT content STREQUAL content_old)
  file(WRITE "${stdprs_brepfont_cxx}" "${content}")
  message(STATUS "Patched StdPrs_BRepFont.cxx")
endif()
