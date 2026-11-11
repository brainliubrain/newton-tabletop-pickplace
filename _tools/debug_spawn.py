import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
from env import PickPlaceEnv  # noqa: E402

wp.init()
env = PickPlaceEnv()
for seed in (4, 1, 0):
    poses = env.reset(seed=seed)
    sp = {k: (round(float(v.p[0]), 3), round(float(v.p[1]), 3)) for k, v in poses.items()}
    q = env.body_poses()
    b0 = {k: np.round(q[b, :3], 3).tolist() for k, b in env.object_bodies.items()}
    print(f"seed={seed} spawns={sp}")
    print(f"   frame0={b0}")
