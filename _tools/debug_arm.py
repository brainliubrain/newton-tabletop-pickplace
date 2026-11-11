import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
from env import HOME_Q, PickPlaceEnv  # noqa: E402

wp.init()
env = PickPlaceEnv()
m = env.model
print("joint_target_ke:", np.round(m.joint_target_ke.numpy(), 1))
print("joint_target_kd:", np.round(m.joint_target_kd.numpy(), 1))
print("joint_damp_mode?", [a for a in dir(m) if "mode" in a.lower() and "joint" in a.lower()])
if hasattr(m, "joint_target_mode"):
    print("joint_target_mode:", m.joint_target_mode.numpy())

poses = env.reset(seed=0)
hold = np.asarray(HOME_Q, dtype=np.float32)
for i in range(60):
    env.step(hold)
    if i % 5 == 0:
        jq = env.joint_q()
        err = np.round(np.asarray(hold[:9]) - jq[:9], 3)
        tcp = env.tcp_pose()[0]
        print(f"t={i:3d} joint_err={err}  tcp_z={tcp[2]:.3f}")
