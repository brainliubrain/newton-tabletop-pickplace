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
for _ in range(60):
    env.step(hold)

from studio import StudioRenderer  # noqa: E402

r = StudioRenderer(env)
frame = r.render_frame(env, hud={"t": 1.0, "phase": "home", "gap": 0.08, "ee": tuple(env.tcp_pose()[0]), "success": False})
from PIL import Image

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "studio_test.png")
Image.fromarray(frame).save(out)
print("saved:", out)
r.close()
