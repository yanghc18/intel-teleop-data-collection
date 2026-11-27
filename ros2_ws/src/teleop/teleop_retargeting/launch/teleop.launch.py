"""Teleop chain in the LXD teleop container: retargeting (+ fake operator inputs when no devices)."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    share = FindPackageShare('teleop_retargeting')
    return LaunchDescription([
        DeclareLaunchArgument('fake_operator', default_value='false',
                              description='Publish simulated Pico/Manus/deadman inputs.'),
        Node(package='teleop_retargeting', executable='retarget_node', output='screen',
             parameters=[PathJoinSubstitution([share, 'config', 'retarget.yaml']),
                         {'hand_map_file': PathJoinSubstitution([share, 'config', 'hand_map.yaml'])}]),
        Node(package='teleop_retargeting', executable='fake_operator', output='screen',
             condition=IfCondition(LaunchConfiguration('fake_operator'))),
    ])
