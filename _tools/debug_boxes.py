"""World AABBs of finger collision primitives + hand at the bowl-grasp stall."""
import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
from agent import PickPlaceAgent  # noqa: E402
from env import PickPlaceEnv  # noqa: E402

wp.init()
env = PickPlaceEnv()
agent = PickPlaceAgent(env)
poses = env.reset(seed=0)
agent.reset_episode({k: np.array([v.p[0], v.p[1], v.p[2]]) for k, v in poses.items()})
for i in range(210):
    env.step(agent.act())

q = env.body_poses()
model = env.model
shape_body = model.shape_body.numpy()
shape_type = model.shape_type.numpy()
shape_tf = model.shape_transform.numpy()  # rows of 7? (px,py,pz,qx,qy,qz,qw)


def quat_to_R(qq):
    x, y, z, w = qq
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def shape_aabb(s):
    b = int(shape_body[s])
    tf = shape_tf[s]
    R = quat_to_R(q[b, 3:]) @ quat_to_R(tf[3:7])
    c = q[b, :3] + quat_to_R(q[b, 3:]) @ tf[:3]
    st = int(shape_type[s])
    if st == 7:  # box: tf[3:] is quat, half extents where? for boxes newton stores hx,hy,hz in shape params
        # shape_size? try model.shape_size or compute from transform scale — print raw
        return c, R, st, None
    src = model.shape_source[s]
    if src is not None and hasattr(src, "vertices"):
        v = np.asarray(src.vertices)
        ext = (v.max(0) - v.min(0)) / 2
        ctr = (v.max(0) + v.min(0)) / 2
        c2 = c + R @ ctr
        return c2, R, st, ext
    return c, R, st, None


print("tcp:", np.round(q[11, :3], 3))
for fb_ in (10, 12, 13):
    shapes = np.where(shape_body == fb_)[0]
    print(f"body {fb_} pos={np.round(q[fb_, :3], 3)}")
    for s in shapes:
        c, R, st, ext = shape_aabb(s)
        # world z-range estimate
        if ext is not None:
            # rotate the local extents' absolute contributions
            wext = np.abs(R) @ ext
            print(
                f"  shape {s} type={st} center={np.round(c, 3)} z_range=[{c[2]-wext[2]:.3f},{c[2]+wext[2]:.3f}] "
                f"xy_ext=[{wext[0]:.3f},{wext[1]:.3f}]"
            )
        else:
            print(f"  shape {s} type={st} center={np.round(c, 3)} (primitive)")
