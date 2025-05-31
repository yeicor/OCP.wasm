if(NOT DEFINED REAL_SOURCE_DIR)
  message(FATAL_ERROR "REAL_SOURCE_DIR must be defined")
endif()

set(target_file "${REAL_SOURCE_DIR}/include/pybind11/detail/common.h")

# XXX: Replace the specific static_assert line with a commented version
file(READ "${target_file}" content)
string(REGEX REPLACE
  "[ \t]+(static_assert\\(sizeof\\(IntType\\) <= sizeof\\(ssize_t\\),[^\n]*\\);)"
  "/*\\1*/" content "${content}"
)
file(WRITE "${target_file}" "${content}")
