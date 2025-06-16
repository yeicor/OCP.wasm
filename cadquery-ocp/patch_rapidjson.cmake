if(NOT DEFINED REAL_SOURCE_DIR)
  message(FATAL_ERROR "REAL_SOURCE_DIR must be defined")
endif()

file(READ "${REAL_SOURCE_DIR}/CMakeLists.txt" content)
set(content_old "${content}")

string(REGEX REPLACE "(option\\(RAPIDJSON_BUILD_(DOC|EXAMPLES|TESTS)[^)]*)ON\\)" "\\1OFF)"
                     content "${content}")

string(REGEX REPLACE "\n([ \t]*find_program\\(CCACHE_FOUND ccache\\).*endif\\(CCACHE_FOUND\\))" "\n#[[ \\1 ]]\ncmake_policy(SET CMP0175 OLD) # Hide warning due to old library dependency"
                     content "${content}")
                     
if(NOT content STREQUAL content_old)
  file(WRITE "${REAL_SOURCE_DIR}/CMakeLists.txt" "${content}")
  message(STATUS "Patched CMakeLists.txt")
endif()
