cmake_minimum_required(VERSION 3.16)
project(medvetalkie VERSION 0.0.1 LANGUAGES C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

add_library(medvetalkie_common STATIC src/common/service.c src/common/state.c)
target_include_directories(medvetalkie_common PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_definitions(medvetalkie_common PUBLIC _POSIX_C_SOURCE=200809L)

if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(medvetalkie_common PRIVATE -Wall -Wextra -Wpedantic)
endif()

foreach(service IN ITEMS medvetalkied medvetalkie-bt medvetalkie-ui)
  add_executable(${service} src/${service}/main.c)
  target_link_libraries(${service} PRIVATE medvetalkie_common)
endforeach()

include(CTest)
if(BUILD_TESTING)
  add_executable(test_state tests/test_state.c)
  target_link_libraries(test_state PRIVATE medvetalkie_common)
  add_test(NAME state_matrix COMMAND test_state)
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
  target_link_libraries(medvetalkie-web PRIVATE ${CIVETWEB_LIBRARY})
  if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(medvetalkie-web PRIVATE -Wall -Wextra -Wpedantic)
  endif()
  if(BUILD_TESTING)
    add_test(NAME web_health
      COMMAND sh ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_web_health.sh $<TARGET_FILE:medvetalkie-web>)
  endif()
else()
  message(STATUS "CivetWeb not installed: medvetalkie-web target disabled")
endif()
