if(NOT DEFINED REAL_SOURCE_DIR)
  message(FATAL_ERROR "REAL_SOURCE_DIR must be defined")
endif()

file(READ "${REAL_SOURCE_DIR}/CMakeLists.txt" content)

string(REGEX REPLACE "(option\\(RAPIDJSON_BUILD_(DOC|EXAMPLES|TESTS)[^)]*)ON\\)" "\\1OFF)"
                     content "${content}")

string(REGEX REPLACE "\n([ \t]*find_program\\(CCACHE_FOUND ccache\\).*endif\\(CCACHE_FOUND\\))" "\n#[[ \\1 ]]"
                     content "${content}")

file(WRITE "${REAL_SOURCE_DIR}/CMakeLists.txt" "${content}")
