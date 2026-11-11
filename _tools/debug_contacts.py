"""Dump actual mujoco contacts during the stall via mjw_data (synced to mj_data)."""
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

# open-loop descent to the stall point (same as debug_openloop)
ik = FrankaIK(home)
start = np.array([0.496, -0.129, 0.55])
end = np.array([0.496, -0.129, 0.410])
for i in range(121):
    t = min(1.0, i / 120)
    tgt = start * (1 - t) + end * t
    ik.joint_q.assign(home.reshape(1, -1))
    q = ik.solve(tgt, iterations=400)
    jt = np.asarray(q[:9], dtype=np.float32)
    jt[7:9] = 0.04
    env.step(jt)

tcp = env.tcp_pose()[0]
print("stalled tcp:", np.round(tcp, 3))

s = env.solver
d = s.mj_data
names = [l for l in dir(d) if not l.startswith("_")]
print("mj_data type:", type(d))
if hasattr(d, "ncon"):
    print("ncon:", d.ncon)
    geoms = {}
    for i in range(min(d.ncon, 40)):
        c = d.contact[i]
        g1, g2 = int(c.geom[0]), int(c.geom[1])
        dist = float(c.dist)
        geoms.setdefault((g1, g2), []).append(dist)
    m = s.mj_model
    for (g1, g2), dists in geoms.items():
        n1 = m.geom(g1).name or f"geom{g1}"
        n2 = m.geom(g2).name or f"geom{g2}"
        print(f"contact {n1} <-> {n2}: n={len(dists)} dist={np.round(min(dists), 4)}")
else:
    print("no ncon field:", [n for n in names if "con" in n][:12])
