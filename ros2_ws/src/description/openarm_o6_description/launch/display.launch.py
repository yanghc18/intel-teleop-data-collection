"""Preview the OpenARM + O6 URDF with joint_state_publisher_gui (no ros2_control)."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg = FindPackageShare('openarm_o6_description')
    robot_description = ParameterValue(
        Command([FindExecutable(name='xacro'), ' ',
                 PathJoinSubstitution([pkg, 'urdf', 'openarm_o6.urdf.xacro'])]),
        value_type=str)
    gui = LaunchConfiguration('gui')

    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true',
                              description='Start joint_state_publisher_gui and RViz.'),
        Node(package='robot_state_publisher', executable='robot_state_publisher',
             parameters=[{'robot_description': robot_description}]),
        Node(package='joint_state_publisher_gui', executable='joint_state_publisher_gui',
             condition=IfCondition(gui)),
        Node(package='joint_state_publisher', executable='joint_state_publisher',
             condition=UnlessCondition(gui)),
        Node(package='rviz2', executable='rviz2',
             arguments=['-d', PathJoinSubstitution([pkg, 'rviz', 'openarm_o6.rviz'])],
             condition=IfCondition(gui)),
    ])
