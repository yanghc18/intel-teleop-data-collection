# Finger data of one glove (Manus ergonomics), consumed by hand retargeting.
std_msgs/Header header
string side               # "left" | "right"
string[] joint_names      # e.g. ThumbMCPSpread, IndexMCPStretch, ...
float64[] joint_angles    # [rad], same order as joint_names
