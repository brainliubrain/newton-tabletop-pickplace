"""At the bowl-grasp stall: where are the finger collision shapes vs the bowl?"""
import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
import newton  # noqa: E402
from agent import PickPlaceAgent  # noqa: E402
from env import PickPlaceEnv  # noqa: E402

wp.init()
env = PickPlaceEnv()
agent = PickPlaceAgent(env)
poses = env.reset(seed=0)
agent.reset_episode({k: np.array([v.p[0], v.p[1], v.p[2]]) for k, v in poses.items()})

for i in range(176):
    jt = agent.act()
    env.step(jt)

q = env.body_poses()
model = env.model
shape_body = model.shape_body.numpy()
shape_type = model.shape_type.numpy()

def aabb_of_shape(s, body_q_row):
    src = model.shape_source[s]
    v = src.vertices
    tf = model.shape_transform.numpy()[s]  # (7,) local xform? check layout
    print(f"    shape {s} type={shape_type[s]} nverts={len(v)} local_tf={np.round(tf, 3)}")

def rot_mat(quat_wxyz):
    # warp quat convention in body_q: (qx,qy,qz,qw)? verify: identity = [0,0,0,1] -> w last
    x, y, z, w = quat_wxyz
    R = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    return R

print("bowl cylinder AABB:")
b = env.object_bodies["bowl"]
s_bowl = [s for s in np.where(shape_body == b)[0]][0]
tf = model.shape_transform.numpy()[s_bowl]
R = rot_mat(q[b, 3:])
c = q[b, :3] + R @ tf[:3]
print(f"    center={np.round(c,3)} half={np.round(tf[3:] if len(tf)>6 else tf[3:6],3)}")

for fi, fb_ in enumerate((12, 13)):
    shapes = np.where(shape_body == fb_)[0]
    print(f"finger body {fb_} pos={np.round(q[fb_, :3], 3)} quat={np.round(q[fb_, 3:], 3)}")
    for s in shapes:
        src = model.shape_source[s]
        if src is None or not hasattr(src, "vertices"):
            print(f"    shape {s}: primitive type={shape_type[s]}")
            continue
        v = np.asarray(src.vertices)
        tf = model.shape_transform.numpy()[s]
        R = rot_mat(q[fb_, 3:])
        c = q[fb_, :3] + R @ tf[:3]
        # crude world aabb of the mesh around its center (ignoring rotation of the mesh itself)
        ext = (v.max(0) - v.min(0)) / 2
        print(f"    shape {s} type={shape_type[s]} world_center~{np.round(c,3)} half_extents~{np.round(ext,4)}")

print("hand body pos:", np.round(q[10, :3], 3))
print("tcp body pos:", np.round(q[11, :3], 3))
