# Joint-space command for both arms and hands (from retargeting or a VLA policy).
# An empty array means "no command" for that group.
std_msgs/Header header
bool deadman              # operator enable switch / clutch held
float64[] left_arm        # 7 positions [rad], order of left_arm_controller joints
float64[] right_arm       # 7 positions [rad], order of right_arm_controller joints
float64[] left_hand       # 6 positions [rad], order of left_gripper_controller joints
float64[] right_hand      # 6 positions [rad], order of right_gripper_controller joints
