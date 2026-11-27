"""Host ros2_control bringup: bimanual OpenARM 2.0 + Linker O6 hands."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import (
    Command, EqualsSubstitution, FindExecutable, LaunchConfiguration, PathJoinSubstitution)
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare

BROADCASTERS = [
    'left_arm_state_broadcaster', 'right_arm_state_broadcaster',
    'left_hand_state_broadcaster', 'right_hand_state_broadcaster',
]
TRAJECTORY_CONTROLLERS = [
    'left_arm_trajectory_controller', 'right_arm_trajectory_controller',
    'left_hand_trajectory_controller', 'right_hand_trajectory_controller',
]
FORWARD_CONTROLLERS = [
    'left_arm_controller', 'right_arm_controller',
    'left_gripper_controller', 'right_gripper_controller',
]
XACRO_ARGS = [
    ('use_mock_hardware', 'true', 'Use mock_components/GenericSystem for the arms.'),
    ('use_mock_hands', LaunchConfiguration('use_mock_hardware'),
     'Use mock_components/GenericSystem for the O6 hands (defaults to use_mock_hardware).'),
    ('right_arm_can_interface', 'arm_r', 'CAN interface of the right OpenARM.'),
    ('left_arm_can_interface', 'arm_l', 'CAN interface of the left OpenARM.'),
    ('arm_can_fd', 'false', 'Use CAN-FD for the arms (Anvil candleLight adapters: classic CAN).'),
    ('right_hand_can_interface', 'hand_r', 'CAN interface of the right O6 hand.'),
    ('left_hand_can_interface', 'hand_l', 'CAN interface of the left O6 hand.'),
]


def generate_launch_description():
    description_pkg = FindPackageShare('openarm_o6_description')
    xacro_cmd = [FindExecutable(name='xacro'), ' ',
                 PathJoinSubstitution([description_pkg, 'urdf', 'openarm_o6.urdf.xacro'])]
    for name, _, _ in XACRO_ARGS:
        xacro_cmd += [f' {name}:=', LaunchConfiguration(name)]
    robot_description = {'robot_description': ParameterValue(Command(xacro_cmd), value_type=str)}
    controllers = PathJoinSubstitution(
        [FindPackageShare('openarm_o6_bringup'), 'config', 'controllers.yaml'])
    teleop = EqualsSubstitution(LaunchConfiguration('mode'), 'teleop')

    def spawner(names, condition=None, inactive=False):
        return Node(package='controller_manager', executable='spawner',
                    arguments=names + (['--inactive'] if inactive else []), condition=condition)

    return LaunchDescription(
        [DeclareLaunchArgument(n, default_value=d, description=h) for n, d, h in XACRO_ARGS] + [
            DeclareLaunchArgument('rviz', default_value='false', description='Start RViz.'),
            DeclareLaunchArgument(
                'mode', default_value='manual', choices=['manual', 'teleop'],
                description='manual: trajectory controllers active; '
                            'teleop: forward controllers fed by teleop_safety.'),
            Node(package='robot_state_publisher', executable='robot_state_publisher',
                 parameters=[robot_description], output='screen'),
            Node(package='controller_manager', executable='ros2_control_node',
                 parameters=[controllers],
                 remappings=[('~/robot_description', '/robot_description')],
                 output='screen'),
            spawner(BROADCASTERS),
            spawner(TRAJECTORY_CONTROLLERS, UnlessCondition(teleop)),
            spawner(FORWARD_CONTROLLERS, UnlessCondition(teleop), inactive=True),
            spawner(FORWARD_CONTROLLERS, IfCondition(teleop)),
            spawner(TRAJECTORY_CONTROLLERS, IfCondition(teleop), inactive=True),
            Node(package='teleop_safety', executable='safety_monitor_node', output='screen',
                 parameters=[PathJoinSubstitution(
                     [FindPackageShare('teleop_safety'), 'config', 'safety.yaml'])],
                 condition=IfCondition(teleop)),
            Node(package='rviz2', executable='rviz2',
                 arguments=['-d', PathJoinSubstitution([description_pkg, 'rviz', 'openarm_o6.rviz'])],
                 condition=IfCondition(LaunchConfiguration('rviz'))),
        ])
