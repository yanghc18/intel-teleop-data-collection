cmake_minimum_required(VERSION 3.16)
project(openarm_o6_bringup NONE)

find_package(ament_cmake REQUIRED)

install(DIRECTORY config launch DESTINATION share/${PROJECT_NAME})
install(PROGRAMS scripts/go_ready.py DESTINATION lib/${PROJECT_NAME})

ament_package()
