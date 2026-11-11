"""Why doesn't the judge count placed streaks at the end?"""
import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
from agent import PickPlaceAgent  # noqa: E402
from env import PickPlaceEnv  # noqa: E402
from task import EpisodeJudge, TaskConfig, at_rest, object_in_tray  # noqa: E402

wp.init()
env = PickPlaceEnv()
agent = PickPlaceAgent(env)
poses = env.reset(seed=0)
agent.reset_episode({k: np.array([v.p[0], v.p[1], v.p[2]]) for k, v in poses.items()})
judge = EpisodeJudge(TaskConfig())
spawn_z = {"bowl": 0.40, "cup": 0.442}

for i in range(1700):
    env.step(agent.act())
    q = env.body_poses()
    qd = env.body_vels()
    tcp_z = float(q[env.tcp_idx, 2])
    for name, b in env.object_bodies.items():
        judge.observe(name, q[b], float(np.linalg.norm(qd[b, :3])), float(np.linalg.norm(qd[b, 3:])), spawn_z[name])
    if judge.success():
        print(f"SUCCESS at frame {i}")
        break

q = env.body_poses()
qd = env.body_vels()
for name, b in env.object_bodies.items():
    pose = q[b]
    lin, ang = float(np.linalg.norm(qd[b, :3])), float(np.linalg.norm(qd[b, 3:]))
    in_tray = object_in_tray(pose, TaskConfig())
    rest = at_rest(lin, ang, TaskConfig())
    up_z = 1 - 2 * (pose[3] ** 2 + pose[4] ** 2)
    print(
        f"{name}: pos={np.round(pose[:3], 4)} quat={np.round(pose[3:], 3)} up_z={up_z:.3f} "
        f"lin={lin:.4f} ang={ang:.4f} in_tray={in_tray} at_rest={rest} streak={judge.in_tray_streak[name]}"
    )
