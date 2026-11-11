import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
from env import HOME_Q, PickPlaceEnv  # noqa: E402

wp.init()
env = PickPlaceEnv()
print("model.joint_q:", np.round(np.asarray(env.model.joint_q.numpy()), 3))
print("state_0.joint_q is None:", env.state_0.joint_q is None)
poses = env.reset(seed=0)
print("after reset: state_0.joint_q is None:", env.state_0.joint_q is None)
if env.state_0.joint_q is not None:
    print("after reset: state_0.joint_q:", np.round(env.state_0.joint_q.numpy(), 3))
print("hold target :", np.round(np.asarray(HOME_Q), 3))
hold = np.asarray(HOME_Q, dtype=np.float32)
env.step(hold)
if env.state_0.joint_q is not None:
    print("after 1 step: state_0.joint_q:", np.round(env.state_0.joint_q.numpy(), 3))
