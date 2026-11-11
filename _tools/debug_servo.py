"""Static servo test: command the bowl-grasp IK pose directly and watch tracking."""
import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
from agent import FrankaIK  # noqa: E402
from env import TCP_BODY, PickPlaceEnv, solve_home_q  # noqa: E402

wp.init()
env = PickPlaceEnv()
ik = FrankaIK(np.asarray(env.home_q, dtype=np.float32))
env.reset(seed=0)

TARGET = (0.496, -0.129, 0.410)
q_ik = ik.solve(np.array(TARGET), iterations=400)
print("IK solution:", np.round(q_ik[:7], 3), "grip:", q_ik[7:9])

target = np.asarray(q_ik[:9], dtype=np.float32)
target[7:9] = 0.04
for i in range(240):
    env.step(target)
    if i % 40 == 0:
        tcp = env.tcp_pose()[0]
        jq = env.joint_q()
        print(f"t={i:3d} sim_tcp={np.round(tcp, 3)}  sim_q={np.round(jq[:7], 3)}")
