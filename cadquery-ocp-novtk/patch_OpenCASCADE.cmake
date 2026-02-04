if(NOT DEFINED REAL_SOURCE_DIR)
  message(FATAL_ERROR "REAL_SOURCE_DIR must be defined")
endif()
if(NOT DEFINED REAL_BINARY_DIR)
  message(FATAL_ERROR "REAL_BINARY_DIR must be defined")
endif()
if(NOT DEFINED rapidjson_SOURCE_DIR)
  message(FATAL_ERROR "rapidjson_SOURCE_DIR must be defined")
endif()
if(NOT DEFINED freetype_INCLUDE_DIR)
  message(FATAL_ERROR "freetype_INCLUDE_DIR must be defined")
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
  set(3RDPARTY_FREETYPE_INCLUDE_DIR_ft2build \"${freetype_INCLUDE_DIR}\")\n\
  set(3RDPARTY_FREETYPE_INCLUDE_DIR_freetype2 \"${freetype_INCLUDE_DIR}\")\n\
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

# ----- Patch TKMath/PACKAGES -----
set(tkmath_packages "${REAL_SOURCE_DIR}/src/TKMath/PACKAGES")
file(READ "${tkmath_packages}" content)
set(content_old "${content}")
# Ensure Expr is present (forgotten in 7.9.2?)
string(FIND "${content}" "\nExpr\n" _has_expr)
if(_has_expr EQUAL -1)
  string(APPEND content "\nExpr")
endif()
# Ensure ExprIntrp is present (forgotten in 7.9.2?)
string(FIND "${content}" "\nExprIntrp\n" _has_exprintrp)
if(_has_exprintrp EQUAL -1)
  string(APPEND content "\nExprIntrp")
endif()
if(NOT content STREQUAL content_old)
  file(WRITE "${tkmath_packages}" "${content}")
  message(STATUS "Patched TKMath/PACKAGES to include Expr and ExprIntrp")
endif()
