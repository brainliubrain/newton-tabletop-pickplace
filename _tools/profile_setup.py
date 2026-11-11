import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
t0 = time.time()
import numpy as np
import warp as wp

wp.init()
t1 = time.time()
print(f"warp init: {t1 - t0:.1f}s")
import newton

t2 = time.time()
print(f"import newton: {t2 - t1:.1f}s")
from env import PickPlaceEnv, solve_home_q  # noqa: E402
from agent import PickPlaceAgent  # noqa: E402

t3 = time.time()
print(f"import modules: {t3 - t2:.1f}s")
h = solve_home_q()
t4 = time.time()
print(f"home IK (build+solve): {t4 - t3:.1f}s")
env = PickPlaceEnv()
t5 = time.time()
print(f"env build: {t5 - t4:.1f}s")
env.reset(seed=0)
t6 = time.time()
print(f"reset: {t6 - t5:.1f}s")
agent = PickPlaceAgent(env)
t7 = time.time()
print(f"agent IK build: {t7 - t6:.1f}s")
agent.reset_episode({"bowl": np.array([0.45, 0.0, 0.4]), "cup": np.array([0.42, 0.2, 0.44])})
for i in range(100):
    env.step(agent.act())
t8 = time.time()
print(f"agent reset+100 frames: {t8 - t7:.1f}s")
