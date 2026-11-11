import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
import numpy as np
import warp as wp

wp.init()
from env import PickPlaceEnv  # noqa: E402

env = PickPlaceEnv()
env.reset(seed=0)
hold = np.asarray(env.home_q, dtype=np.float32)
for _ in range(30):
    env.step(hold)

from studio import StudioRenderer, build_studio_mjcf  # noqa: E402
from PIL import Image  # noqa: E402

xml_path = build_studio_mjcf(env)
import mujoco  # noqa: E402

model = mujoco.MjModel.from_xml_path(xml_path)
data = mujoco.MjData(model)
qpos = env.solver.mjw_data.qpos.numpy()[0][: model.nq]
data.qpos[:] = qpos
mujoco.mj_forward(model, data)

out_dir = os.path.dirname(os.path.abspath(__file__))
for groups in ([True, True, True, False], [False, True, False, False], [True, False, False, False]):
    r = mujoco.Renderer(model, height=720, width=1280)
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = [0.42, 0.02, 0.42]
    cam.distance = 1.30
    cam.azimuth = -130
    cam.elevation = -24
    opt = mujoco.MjvOption()
    for gi, on in enumerate(groups):
        opt.geomgroup[gi] = on
    r.update_scene(data, camera=cam, scene_option=opt)
    img = r.render()
    name = "all" if groups == [True, True, True, False] else ("g2" if groups[1] else "g0")
    Image.fromarray(img).save(os.path.join(out_dir, f"group_{name}.png"))
    r.close()
print("saved group_all/g2/g0")
