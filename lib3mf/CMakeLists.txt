cmake_minimum_required(VERSION 3.24)
include(${CMAKE_CURRENT_LIST_DIR}/../util/common.cmake)

auto_ccache()
project(${SKBUILD_PROJECT_NAME} LANGUAGES C VERSION ${SKBUILD_PROJECT_VERSION})

set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set_property(GLOBAL PROPERTY TARGET_SUPPORTS_SHARED_LIBS TRUE)
configure_fetchcontent()
override_install()

set(LIB3MF_VERSION "2.4.1")
set(LIB3MF_SRC_DIR "${CMAKE_BINARY_DIR}/_deps/lib3mf-src")
checkout_git_tag(SRC "${LIB3MF_SRC_DIR}" URL "https://github.com/3MFConsortium/lib3mf.git" TAG "v${LIB3MF_VERSION}")
message(STATUS "${LIB3MF_SRC_DIR}")
execute_process(
  COMMAND "${CMAKE_COMMAND}" "-DREAL_SOURCE_DIR=${LIB3MF_SRC_DIR}" -P "${CMAKE_CURRENT_LIST_DIR}/patch.cmake"
  COMMAND_ERROR_IS_FATAL ANY)
set_timestamps("${LIB3MF_SRC_DIR}")

set(LIB3MF_BINARY_DIR "${CMAKE_BINARY_DIR}/_deps/lib3mf-build")
add_subdirectory("${LIB3MF_SRC_DIR}" "${LIB3MF_BINARY_DIR}")

if(EMSCRIPTEN)
  message(STATUS "Setting up extra wheel download and repacking pass")
  FetchContent_Declare(
    lib3mf-wheel-original
    URL "https://github.com/3MFConsortium/lib3mf/releases/download/v${LIB3MF_VERSION}/lib3mf-${LIB3MF_VERSION}-py3-none-manylinux2014_x86_64.whl"
  )
  FetchContent_MakeAvailable(lib3mf-wheel-original)
  FetchContent_GetProperties(lib3mf-wheel-original)
  set(WHEEL_CONTENTS_DIR "${CMAKE_CURRENT_BINARY_DIR}/lib3mf-wheel-contents")
  set(WHEEL_LIB3MF_DIR "${WHEEL_CONTENTS_DIR}/lib3mf")
  set(WHEEL_LIB3MF_PY "${WHEEL_LIB3MF_DIR}/Lib3MF.py")
  set(WHEEL_LIB3MF_PY_TMP "${WHEEL_LIB3MF_DIR}/Lib3MF.py.wasm.tmp")
  add_custom_command(
    DEPENDS lib3mf
    OUTPUT "${WHEEL_CONTENTS_DIR}"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${WHEEL_CONTENTS_DIR}"
    COMMAND /bin/sh -c "rm -r '${WHEEL_CONTENTS_DIR}/lib3mf' || true"
    COMMAND ${CMAKE_COMMAND} -E make_directory "${WHEEL_LIB3MF_DIR}"
    COMMAND /bin/sh -c "cp '${lib3mf-wheel-original_SOURCE_DIR}/lib3mf/'*.py '${WHEEL_LIB3MF_DIR}/'"
    COMMAND /bin/sh -c "sed -i 's/linux/emscripten/g;s/Linux/Emscripten/g' '${WHEEL_LIB3MF_DIR}/'*.py"
    COMMAND python3 "${CMAKE_CURRENT_LIST_DIR}/fix_lib3mf_wasm.py" "${WHEEL_LIB3MF_PY}" "${WHEEL_LIB3MF_PY_TMP}"
    COMMAND ${CMAKE_COMMAND} -E rename "${WHEEL_LIB3MF_PY_TMP}" "${WHEEL_LIB3MF_PY}"
    COMMAND /bin/sh -c "! grep -q 'lib3mf_getlibraryversion\\.argtypes = \\[ctypes\\.POINTER(ctypes\\.c_uint64)' '${WHEEL_LIB3MF_PY}'"
    COMMAND /bin/sh -c "cp '${LIB3MF_BINARY_DIR}/lib3mf.so' '${WHEEL_LIB3MF_DIR}/lib3mf.so'"
    COMMAND /bin/sh -c "[ -f '${LIB3MF_BINARY_DIR}/lib3mf.wasm.debug.wasm' ] && cp '${LIB3MF_BINARY_DIR}/lib3mf.wasm.debug.wasm' '${WHEEL_CONTENTS_DIR}/lib3mf/lib3mf.wasm.debug.wasm' || true"
    COMMAND /bin/sh -c "[ -f '${LIB3MF_BINARY_DIR}/lib3mf.so.map' ] && cp '${LIB3MF_BINARY_DIR}/lib3mf.so.map' '${WHEEL_CONTENTS_DIR}/lib3mf/lib3mf.so.map' || true"
    VERBATIM
  )
  add_custom_target(lib3mf-wheel-target ALL DEPENDS "${WHEEL_CONTENTS_DIR}")
  install(INSTALL_ME DIRECTORY "${WHEEL_CONTENTS_DIR}/" DESTINATION ".")
endif()
