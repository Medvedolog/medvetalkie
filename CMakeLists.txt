cmake_minimum_required(VERSION 3.16)
project(medvetalkie VERSION 0.0.1 LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

add_library(medvetalkie_common STATIC src/common/service.c src/common/state.c src/common/ipc.c)
target_include_directories(medvetalkie_common PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_definitions(medvetalkie_common PUBLIC _POSIX_C_SOURCE=200809L)

if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(medvetalkie_common PRIVATE -Wall -Wextra -Wpedantic)
endif()

find_package(Threads REQUIRED)
find_package(SQLite3 REQUIRED)
find_package(PkgConfig REQUIRED)
pkg_check_modules(DBUS1 REQUIRED IMPORTED_TARGET dbus-1)
find_path(JSONC_INCLUDE_DIR NAMES json-c/json.h)
find_library(JSONC_LIBRARY NAMES json-c)
if(NOT JSONC_INCLUDE_DIR OR NOT JSONC_LIBRARY)
  message(FATAL_ERROR "API Core Alpha requires libjson-c-dev")
endif()

foreach(service IN ITEMS medvetalkied medvetalkie-bt medvetalkie-ui)
  add_executable(${service} src/${service}/main.c)
  target_link_libraries(${service} PRIVATE medvetalkie_common)
endforeach()
target_sources(medvetalkied PRIVATE
  src/common/settings.c
  src/medvetalkied/settings_api.c
  src/medvetalkied/bt_inventory.c
  src/medvetalkied/bt_bluez.c)
target_include_directories(medvetalkied PRIVATE ${JSONC_INCLUDE_DIR})
target_link_libraries(medvetalkied PRIVATE ${JSONC_LIBRARY} SQLite::SQLite3 Threads::Threads PkgConfig::DBUS1)
# Explicit local startup bridge to the independently tested Bjorni script.
# Does not install/autostart the hardware renderer.
add_executable(medvetalkie-display-runner src/medvetalkie-display-runner/main.c)
target_include_directories(medvetalkie-display-runner PRIVATE ${JSONC_INCLUDE_DIR})
target_link_libraries(medvetalkie-display-runner PRIVATE medvetalkie_common ${JSONC_LIBRARY})


include(CTest)
if(BUILD_TESTING)
  add_executable(test_state tests/test_state.c)
  target_link_libraries(test_state PRIVATE medvetalkie_common)
  add_test(NAME state_matrix COMMAND test_state)
  find_package(Python3 COMPONENTS Interpreter REQUIRED)
  add_test(NAME core_ipc_protocol
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_core_ipc.py
            $<TARGET_FILE:medvetalkied>)
  set_tests_properties(core_ipc_protocol PROPERTIES TIMEOUT 15)
  add_test(NAME settings_sqlite
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_settings_api.py
            $<TARGET_FILE:medvetalkied>)
  set_tests_properties(settings_sqlite PROPERTIES TIMEOUT 25)
  add_test(NAME bt_inventory_sysfs
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_bt_inventory.py
            $<TARGET_FILE:medvetalkied>)
  set_tests_properties(bt_inventory_sysfs PROPERTIES TIMEOUT 15)
  add_executable(test_bluez_parser tests/test_bluez_parser.c
    src/medvetalkied/bt_bluez.c)
  target_include_directories(test_bluez_parser PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src/medvetalkied ${JSONC_INCLUDE_DIR})
  target_link_libraries(test_bluez_parser PRIVATE PkgConfig::DBUS1 ${JSONC_LIBRARY})
  add_test(NAME bluez_dbus_parser COMMAND test_bluez_parser)
  set_tests_properties(bluez_dbus_parser PROPERTIES TIMEOUT 10)
  add_test(NAME display_runner_bridge
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_display_runner.py
            $<TARGET_FILE:medvetalkied> $<TARGET_FILE:medvetalkie-display-runner>)
  set_tests_properties(display_runner_bridge PROPERTIES TIMEOUT 15)
endif()

# Read-only diagnostic binary; deliberately does not bind USB device roles.
add_executable(medvetalkie-usb-inventory src/diagnostics/usb_inventory.c)
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(medvetalkie-usb-inventory PRIVATE -Wall -Wextra -Wpedantic)
endif()

if(BUILD_TESTING)
  add_test(NAME usb_inventory_fixture
    COMMAND sh ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_usb_inventory.sh $<TARGET_FILE:medvetalkie-usb-inventory>)
endif()

# Isolated Web Alpha is built only when CivetWeb headers/library are installed.
find_path(CIVETWEB_INCLUDE_DIR NAMES civetweb.h)
find_library(CIVETWEB_LIBRARY NAMES civetweb)
if(CIVETWEB_INCLUDE_DIR AND CIVETWEB_LIBRARY)
  add_executable(medvetalkie-web src/medvetalkie-web/main.c)
  target_include_directories(medvetalkie-web PRIVATE ${CIVETWEB_INCLUDE_DIR})
  target_link_libraries(medvetalkie-web PRIVATE medvetalkie_common ${CIVETWEB_LIBRARY})
  if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(medvetalkie-web PRIVATE -Wall -Wextra -Wpedantic)
  endif()
  if(BUILD_TESTING)
    add_test(NAME web_health
      COMMAND sh ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_web_health.sh $<TARGET_FILE:medvetalkie-web> $<TARGET_FILE:medvetalkied>)
    set_tests_properties(web_health PROPERTIES TIMEOUT 15)
  endif()
else()
  message(STATUS "CivetWeb not installed: medvetalkie-web target disabled")
endif()
