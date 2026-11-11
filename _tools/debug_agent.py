"""Block4 self-check: run ONE episode with the scripted agent and report."""
import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
from agent import PickPlaceAgent  # noqa: E402
from env import PickPlaceEnv  # noqa: E402
from task import EpisodeJudge, TaskConfig  # noqa: E402

wp.init()
env = PickPlaceEnv()
agent = PickPlaceAgent(env)
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0

poses = env.reset(seed=seed)
print("spawns:", {k: (round(float(v.p[0]), 3), round(float(v.p[1]), 3)) for k, v in poses.items()})
agent.reset_episode({k: np.array([v.p[0], v.p[1], v.p[2]]) for k, v in poses.items()})

judge = EpisodeJudge(TaskConfig())
spawn_z = {"bowl": 0.40, "cup": 0.442}

last_phase = ""
for i in range(1500):
    jt = agent.act()
    env.step(jt)
    if agent.phase_name != last_phase:
        q = env.body_poses()
        tcp = q[env.tcp_idx, :3]
        bw = q[env.object_bodies["bowl"], :3]
        fl, fr = q[env.finger_idx[0], :3], q[env.finger_idx[1], :3]
        gap = float(np.linalg.norm(fl - fr))
        print(f"t={agent.frame:4d} phase={agent.phase_name:16s} tcp={np.round(tcp,3)} bowl={np.round(bw,3)} fingap={gap:.3f} grip={agent.current_grip:.3f}")
        last_phase = agent.phase_name
    q = env.body_poses()
    qd = env.body_vels()
    tcp_z = float(q[env.tcp_idx, 2])
    for name, b in env.object_bodies.items():
        lin = float(np.linalg.norm(qd[b, :3]))
        ang = float(np.linalg.norm(qd[b, 3:]))
        judge.observe(name, q[b], lin, ang, spawn_z[name], hands_off=bool(tcp_z > 0.50))
    if judge.success():
        print(f"SUCCESS at frame {agent.frame}")
        break

q = env.body_poses()
for name, b in env.object_bodies.items():
    print(f"{name}: final pos={np.round(q[b, :3], 3)} grasped={judge.was_grasped.get(name, False)} placed_streak={judge.in_tray_streak[name]}")
print("episode success:", judge.success(), "| agent finished:", agent.finished())
