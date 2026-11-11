"""Open-loop descent replay with cold-start IK each frame (isolates warm-start IK)."""
import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
from agent import FrankaIK  # noqa: E402
from env import TCP_BODY, PickPlaceEnv, solve_home_q  # noqa: E402

wp.init()
env = PickPlaceEnv()
home = np.asarray(env.home_q, dtype=np.float32)
env.reset(seed=0)

ik_fresh = FrankaIK(home)
N = 120
start = np.array([0.496, -0.129, 0.55])
end = np.array([0.496, -0.129, 0.410])
for i in range(N + 60):
    t = min(1.0, i / N)
    tgt = start * (1 - t) + end * t
    ik_fresh.joint_q.assign(home.reshape(1, -1))  # cold start every frame
    q = ik_fresh.solve(tgt, iterations=400)
    jt = np.asarray(q[:9], dtype=np.float32)
    jt[7:9] = 0.04
    env.step(jt)
    if i % 20 == 0:
        tcp = env.tcp_pose()[0]
        print(f"t={i:3d} tgt_z={tgt[2]:.3f} sim_tcp={np.round(tcp, 3)}")
