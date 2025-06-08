if(NOT DEFINED REAL_SOURCE_DIR)
  message(FATAL_ERROR "REAL_SOURCE_DIR must be defined")
endif()

set(target_file "${REAL_SOURCE_DIR}/include/pybind11/detail/common.h")

file(READ "${target_file}" content)
set(content_old "${content}")

# XXX: Replace the specific static_assert line with a commented version
string(REGEX REPLACE
  "[ \t]+(static_assert\\(sizeof\\(IntType\\) <= sizeof\\(ssize_t\\),[^\n]*\\);)"
  "/*\\1*/" content "${content}"
)
file(WRITE "${target_file}" "${content}")

if(NOT content STREQUAL content_old)
  file(WRITE "${target_file}" "${content}")
  message(STATUS "Patched ${target_file}")
else() # XXX: Not the first time, ensure the timestamp is kept to an old value to use the cached compiled objects!
  message(STATUS "XXX: Forcing ${target_file} to have old timestamp...")
  if(UNIX)
    execute_process(COMMAND touch -t 202201011230.55 "${target_file}")
  elseif(WIN32)
    execute_process(COMMAND powershell -Command "(Get-Item '${target_file}').LastWriteTime = '01 January 2022 12:30:55'")
  else()
      message(WARNING "Timestamp modification not supported on this platform.")
  endif()
endif()
