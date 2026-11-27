cmake_minimum_required(VERSION 3.16)
project(openarm_o6_description NONE)

find_package(ament_cmake REQUIRED)

# Upstream O6 URDF/meshes come from linker-bot/linkerhand-urdf (see ros2_ws/third_party.repos).
if(DEFINED ENV{LINKERHAND_URDF_DIR})
  set(_linkerhand_default "$ENV{LINKERHAND_URDF_DIR}")
else()
  set(_linkerhand_default "${CMAKE_CURRENT_SOURCE_DIR}/../../../third_party/linkerhand-urdf")
endif()
set(LINKERHAND_URDF_DIR "${_linkerhand_default}" CACHE PATH "Path to linkerhand-urdf checkout")

foreach(side left right)
  if(side STREQUAL "left")
    set(prefix lh)
  else()
    set(prefix rh)
  endif()
  set(src_dir "${LINKERHAND_URDF_DIR}/O6/${side}")
  set(src_urdf "${src_dir}/linkerhand_o6_${side}.urdf")
  if(NOT EXISTS "${src_urdf}")
    message(FATAL_ERROR "O6 URDF not found: ${src_urdf} (set LINKERHAND_URDF_DIR)")
  endif()
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${src_urdf}")

  file(READ "${src_urdf}" urdf)
  string(REPLACE "filename=\"meshes/" "filename=\"package://${PROJECT_NAME}/meshes/o6_${side}/" urdf "${urdf}")
  # Both hands define the same material names; urdfdom rejects duplicates in one model.
  string(REPLACE "material name=\"" "material name=\"${prefix}_" urdf "${urdf}")
  file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/urdf/linker_o6_${side}.urdf" "${urdf}")

  install(FILES "${CMAKE_CURRENT_BINARY_DIR}/urdf/linker_o6_${side}.urdf" DESTINATION share/${PROJECT_NAME}/urdf)
  install(DIRECTORY "${src_dir}/meshes/" DESTINATION share/${PROJECT_NAME}/meshes/o6_${side})
endforeach()

install(DIRECTORY config launch rviz urdf DESTINATION share/${PROJECT_NAME})

ament_package()
