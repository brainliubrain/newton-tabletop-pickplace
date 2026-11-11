import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
import newton

from env import HOME_Q, PickPlaceEnv  # noqa: E402

wp.init()
env = PickPlaceEnv()
poses = env.reset(seed=0)
hold = np.asarray(HOME_Q, dtype=np.float32)

b = env.object_bodies["bowl"]
c = env.object_bodies["cup"]
print("bowl spawn:", np.round(env.state_0.body_q.numpy()[b, :3], 4))
print("cup spawn:", np.round(env.state_0.body_q.numpy()[c, :3], 4))

for i in range(1, 121):
    env.step(hold)
    if i % 20 == 0:
        q = env.body_poses()
        print(
            f"t={i:3d}  bowl xy z = {np.round(q[b, :3], 4)}  |  cup z = {q[c, 2]:.4f}"
        )

# inspect shape types on the bowl body after hull conversion
model = env.model
shape_body = model.shape_body.numpy()
shape_type = model.shape_type.numpy()
bowl_shapes = np.where(shape_body == b)[0]
print("bowl shapes:", bowl_shapes, "types:", shape_type[bowl_shapes])
table_shapes = np.where(shape_body == -1)[0]
print("static shapes:", table_shapes, "types:", shape_type[table_shapes])
