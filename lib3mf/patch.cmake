if(NOT DEFINED REAL_SOURCE_DIR)
  message(FATAL_ERROR "REAL_SOURCE_DIR must be defined")
endif()



set(FILE "${REAL_SOURCE_DIR}/CMakeLists.txt")
file(READ "${FILE}" CONTENTS)
set(NEW_CONTENTS "${CONTENTS}")

# Patch 1: Insert after "# Shared library"
string(REPLACE "# Shared library\nadd_library" "# Shared library\nset_property(GLOBAL PROPERTY TARGET_SUPPORTS_SHARED_LIBS TRUE)\nadd_library" NEW_CONTENTS "${NEW_CONTENTS}")

# Patch 2: Replace COMMAND line
string(REPLACE "COMMAND ${CMAKE_COMMAND}"
              "COMMAND /usr/bin/env \"CFLAGS=$CMAKE_C_FLAGS\" emcmake ${CMAKE_COMMAND}"
              NEW_CONTENTS "${NEW_CONTENTS}")

# Patch 3: Remove OUTPUT_QUIET
string(REPLACE "OUTPUT_QUIET" "" NEW_CONTENTS "${NEW_CONTENTS}")

# Patch 4: Do NOT strip binaries
string(REPLACE "LINK_FLAGS -s" "LINK_FLAGS" NEW_CONTENTS "${NEW_CONTENTS}")

if(NOT "${CONTENTS}" STREQUAL "${NEW_CONTENTS}")
    file(WRITE "${FILE}" "${NEW_CONTENTS}")
    message(STATUS "Patched: ${FILE}")
else()
    message(STATUS "No changes made to: ${FILE}")
endif()



set(FILE "${REAL_SOURCE_DIR}/submodules/libzip/cmake-config.h.in")
file(READ "${FILE}" CONTENTS)
set(NEW_CONTENTS "${CONTENTS}")

# Match and comment lines
string(REGEX REPLACE "#cmakedefine[ \t]+[A-Za-z0-9_]*_S\n" "// &" NEW_CONTENTS "${NEW_CONTENTS}")
string(REGEX REPLACE "#cmakedefine[ \t]+HAVE_ARC4RANDOM\n" "// &" NEW_CONTENTS "${NEW_CONTENTS}")
string(REGEX REPLACE "#cmakedefine[ \t]+HAVE_CLONEFILE\n" "// &" NEW_CONTENTS "${NEW_CONTENTS}")

# Only write if changed
if(NOT "${CONTENTS}" STREQUAL "${NEW_CONTENTS}")
    file(WRITE "${FILE}" "${NEW_CONTENTS}")
    message(STATUS "Patched: ${FILE}")
else()
    message(STATUS "No changes made to: ${FILE}")
endif()


