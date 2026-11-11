import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
from env import HOME_Q, PickPlaceEnv  # noqa: E402

wp.init()
env = PickPlaceEnv()
poses = env.reset(seed=0)
hold = np.asarray(HOME_Q, dtype=np.float32)
b = env.object_bodies["bowl"]
c = env.object_bodies["cup"]
print("bowl spawn:", np.round(env.state_0.body_q.numpy()[b, :3], 4))

for i in range(1, 121):
    env.step(hold)
    if i % 20 == 0:
        q = env.body_poses()
        print(f"t={i:3d} bowl={np.round(q[b, :3], 3)} cup_xy=({q[c,0]:.3f},{q[c,1]:.3f})")
        if i == 20:
            names = list(env.body_names)
            for j in range(14):
                print(f"    arm body {j:2d} {names[j]:22s} pos={np.round(q[j, :3], 3)}")
q = env.body_poses()
print("bowl final:", np.round(q[b, :3], 4))
