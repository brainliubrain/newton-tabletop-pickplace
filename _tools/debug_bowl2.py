import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
import newton  # noqa: E402
from env import HOME_Q, PickPlaceEnv, bowl_profile, lathe_mesh  # noqa: E402

wp.init()
env = PickPlaceEnv()
model = env.model
shape_body = model.shape_body.numpy()
shape_type = model.shape_type.numpy()
b = env.object_bodies["bowl"]

for s in np.where(shape_body == b)[0]:
    src = model.shape_source[s]
    label = getattr(src, "label", None) or type(src).__name__
    if hasattr(src, "vertices"):
        v = src.vertices
        print(f"shape {s} type={shape_type[s]} {type(src).__name__} bbox_min={np.round(v.min(0), 4)} bbox_max={np.round(v.max(0), 4)} nverts={len(v)}")
    else:
        print(f"shape {s} type={shape_type[s]} {type(src).__name__}")

# raw lathe mesh bbox for reference
m = lathe_mesh(bowl_profile(env.cfg))
print("raw lathe bbox_min=", np.round(m.vertices.min(0), 4), "max=", np.round(m.vertices.max(0), 4))

# settle and report final bowl pose
poses = env.reset(seed=0)
print("bowl spawn:", np.round(env.state_0.body_q.numpy()[b, :3], 4))
hold = np.asarray(HOME_Q, dtype=np.float32)
for _ in range(120):
    env.step(hold)
q = env.body_poses()
print("bowl final:", np.round(q[b, :3], 4), "quat:", np.round(q[b, 3:], 3))
print("bowl mass props: check inertia")
body_mass = model.body_mass.numpy()
print("body masses:", {k: round(float(body_mass[v]), 3) for k, v in env.object_bodies.items()})
