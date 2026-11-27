cmake_minimum_required(VERSION 3.16)
project(teleop_safety LANGUAGES CXX)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()
add_compile_options(-Wall -Wextra -Wpedantic)

find_package(ament_cmake REQUIRED)
find_package(kdl_parser REQUIRED)
find_package(orocos_kdl_vendor REQUIRED)
find_package(orocos_kdl REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(std_srvs REQUIRED)
find_package(teleop_msgs REQUIRED)
find_package(urdf REQUIRED)

add_executable(safety_monitor_node src/safety_monitor_node.cpp)
target_include_directories(safety_monitor_node PRIVATE include)
target_link_libraries(safety_monitor_node
  kdl_parser::kdl_parser
  orocos-kdl
  rclcpp::rclcpp
  ${sensor_msgs_TARGETS}
  ${std_msgs_TARGETS}
  ${std_srvs_TARGETS}
  ${teleop_msgs_TARGETS}
  urdf::urdf)

install(TARGETS safety_monitor_node DESTINATION lib/${PROJECT_NAME})
install(PROGRAMS scripts/safety_test.py DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY config DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_limits test/test_limits.cpp)
  target_include_directories(test_limits PRIVATE include)
endif()

ament_package()
