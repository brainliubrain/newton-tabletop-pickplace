"""Block2 self-check: multi-seed reset stability — objects settle on the table, no NaN."""
import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
from env import PickPlaceEnv  # noqa: E402

wp.init()
env = PickPlaceEnv()
hold = np.asarray(env.home_q, dtype=np.float32)
ok = True
for seed in range(5):
    poses = env.reset(seed=seed)
    for _ in range(90):  # 1.5 s settle
        env.step(hold)
    q = env.body_poses()
    for name, b in env.object_bodies.items():
        p = q[b, :3]
        on_table = 0.36 < p[2] < 0.46 and 0.28 < p[0] < 1.02 and abs(p[1]) < 0.52
        finite = np.all(np.isfinite(q))
        print(
            f"seed={seed} {name:4s} pos={np.round(p, 3)} on_table={on_table} finite={finite} "
            f"spawn=({poses[name].p[0]:.2f},{poses[name].p[1]:.2f})"
        )
        ok &= on_table and finite
    # arm must still hold near home
    tcp = q[env.tcp_idx, :3]
    err = np.linalg.norm(tcp - np.array([0.45, 0.0, 0.62]))
    print(f"seed={seed} tcp={np.round(tcp, 3)} home_err={err:.3f}")
    ok &= err < 0.05
print("SEED STABILITY:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
