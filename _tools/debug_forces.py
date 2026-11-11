"""Compare ctrl vs qpos vs qvel vs actuator force at the stall; check saturation."""
import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
from agent import FrankaIK  # noqa: E402
from env import PickPlaceEnv, solve_home_q  # noqa: E402

wp.init()
env = PickPlaceEnv()
home = np.asarray(env.home_q, dtype=np.float32)
env.reset(seed=0)

ik = FrankaIK(home)
start = np.array([0.496, -0.129, 0.55])
end = np.array([0.496, -0.129, 0.410])
for i in range(181):
    t = min(1.0, i / 120)
    tgt = start * (1 - t) + end * t
    ik.joint_q.assign(home.reshape(1, -1))
    q = ik.solve(tgt, iterations=400)
    jt = np.asarray(q[:9], dtype=np.float32)
    jt[7:9] = 0.04
    env.step(jt)

print("final commanded q:", np.round(ik.joint_q.numpy().reshape(-1)[:7], 4))
ctrl = env.control.joint_target_q.numpy()
print("env control recv  :", np.round(ctrl[:7], 4))
d = env.solver.mj_data
m = env.solver.mj_model
qpos = np.asarray(d.qpos)[:m.nq] if hasattr(d, "qpos") else None
print("mj ctrl  :", np.round(np.asarray(d.ctrl), 2))
print("mj qvel  :", np.round(np.asarray(d.qvel)[:14], 3))
print("mj actuator_force:", np.round(np.asarray(d.actuator_force), 1))
jq = env.joint_q()
print("sim joint_q:", np.round(jq[:7], 4))
print("sim joint_qd:", np.round(env.state_0.joint_qd.numpy()[:7], 3))
print("tcp:", np.round(env.tcp_pose()[0], 3))
# effort limits per DOF as seen by mujoco
print("mj actuator_ctrlrange:", np.round(np.asarray(m.actuator_ctrlrange)[:9], 2) if m.na else "n/a")
