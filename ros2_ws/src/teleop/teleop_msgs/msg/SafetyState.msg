uint8 STATE_ACTIVE=0      # commands are forwarded (limited)
uint8 STATE_HOLD=1        # no fresh command / deadman released / fault: outputs frozen
uint8 STATE_ESTOP=2       # latched until /emergency_stop is false and ~/reset is called

std_msgs/Header header
uint8 state
string reason
bool estop
bool deadman
float64 command_age       # [s] since the last /teleop_action, -1 if none received
string[] faulted_groups   # groups whose joint_states are stale
string[] limited_groups   # groups limited (position / velocity / workspace) in the last cycle
