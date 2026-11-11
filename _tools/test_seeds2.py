"""Multi-seed episode reliability check for the full task."""
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
cfg = TaskConfig()

seeds = [int(s) for s in sys.argv[1:]] or list(range(5))
wins = 0
for seed in seeds:
    poses = env.reset(seed=seed)
    agent.reset_episode({k: np.array([v.p[0], v.p[1], v.p[2]]) for k, v in poses.items()})
    judge = EpisodeJudge(cfg)
    spawn_z = {"bowl": 0.40, "cup": 0.442}
    outcome = "timeout"
    spiked = False
    for i in range(cfg.episode_frames):
        env.step(agent.act())
        q = env.body_poses()
        qd = env.body_vels()
        tcp_z = float(q[env.tcp_idx, 2])
        if not spiked:
            v = float(np.linalg.norm(qd[env.object_bodies["bowl"], :3]))
            if v > 0.5 or not np.all(np.isfinite(q[env.object_bodies["bowl"]])):
                spiked = True
                print(
                    f"  SPIKE@{i} phase={agent.phase_name} v={v:.2f} bowl={np.round(q[env.object_bodies['bowl'], :3], 3)} "
                    f"tcp={np.round(env.tcp_pose()[0], 3)} grip={agent.current_grip:.3f}"
                )
        for name, b in env.object_bodies.items():
            judge.observe(
                name,
                q[b],
                float(np.linalg.norm(qd[b, :3])),
                float(np.linalg.norm(qd[b, 3:])),
                spawn_z[name],
                hands_off=bool(tcp_z > 0.50),
            )
        if judge.success():
            outcome = f"success@{i}"
            break
    ok = judge.success()
    wins += ok
    q = env.body_poses()
    bp = q[env.object_bodies["bowl"], :3]
    cp = q[env.object_bodies["cup"], :3]
    print(
        f"seed={seed}: {outcome}  bowl=({bp[0]:.3f},{bp[1]:.3f},{bp[2]:.3f}) cup=({cp[0]:.3f},{cp[1]:.3f},{cp[2]:.3f}) "
        f"grasped={judge.was_grasped}"
    )
print(f"RESULTS: {wins}/{len(seeds)}")
