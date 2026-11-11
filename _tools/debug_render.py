"""Render grasp moments via CPU mj_data sync + mujoco.Renderer."""
import os
import sys

import numpy as np
import warp as wp
import mujoco
import mujoco_warp
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
from agent import PickPlaceAgent  # noqa: E402
from env import PickPlaceEnv  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames")
os.makedirs(OUT, exist_ok=True)

wp.init()
env = PickPlaceEnv()
agent = PickPlaceAgent(env)
poses = env.reset(seed=0)
agent.reset_episode({k: np.array([v.p[0], v.p[1], v.p[2]]) for k, v in poses.items()})

mj_model = env.solver.mj_model
mj_data = mujoco.MjData(mj_model)
renderer = mujoco.Renderer(mj_model, height=480, width=640)
cam = mujoco.MjvCamera()
cam.type = mujoco.mjtCamera.mjCAMERA_FREE
cam.lookat[:] = [0.35, -0.05, 0.42]
cam.distance = 0.9
cam.elevation = -18

opt = mujoco.MjvOption()
opt.flags[mujoco.mjtVisFlag.mjVIS_CONTACTPOINT] = True  # show contact points!


def snap(tag):
    mujoco_warp.get_data_into(mj_data, mj_model, env.solver.mjw_data, world_id=0)
    mujoco.mj_forward(mj_model, mj_data)
    for az, suffix in ((-90, "front"), (180, "side"), (-45, "iso")):
        cam.azimuth = az
        renderer.update_scene(mj_data, camera=cam, scene_option=opt)
        img = renderer.render()
        Image.fromarray(img).save(os.path.join(OUT, f"{tag}-{suffix}.png"))
    q = env.body_poses()
    b = env.object_bodies["bowl"]
    print(f"{tag}: bowl={np.round(q[b, :3], 3)} tcp={np.round(env.tcp_pose()[0], 3)} grip={agent.current_grip:.3f}")


SNAP_AT = {175: "1-descend-end", 274: "2-grasp-end", 305: "3-lift-mid", 335: "4-lift-end"}
for i in range(1500):
    env.step(agent.act())
    if i in SNAP_AT:
        snap(f"{SNAP_AT[i]}-{i}")
renderer.close()
