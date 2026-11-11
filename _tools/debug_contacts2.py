"""Read REAL contacts from the GPU mujoco-warp data at the stall."""
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

tcp = env.tcp_pose()[0]
print("stalled tcp:", np.round(tcp, 3))

d = env.solver.mjw_data
m = env.solver.mj_model
geom_names = [m.geom(i).name or f"geom{i}" for i in range(m.ngeom)]

# mujoco-warp stores contacts in fixed-size arrays; ncon tells how many are live
for attr in ("ncon", "nefc"):
    if hasattr(d, attr):
        arr = getattr(d, attr)
        try:
            print(attr, "=", np.asarray(arr.numpy()).ravel()[:4])
        except Exception as e:  # noqa: BLE001
            print(attr, "read fail", e)

con = d.contact
# contact fields in mujoco-warp: geom is (ncon_max, 2) int array, dist (ncon_max,)
try:
    geom = np.asarray(con.geom.numpy())
    dist = np.asarray(con.dist.numpy())
    ncon = int(np.asarray(d.ncon.numpy()).ravel()[0]) if hasattr(d, "ncon") else len(dist)
    print(f"ncon={ncon}")
    active = [(int(g[0]), int(g[1]), float(dd)) for g, dd in zip(geom[:ncon], dist[:ncon])]
    for g1, g2, dd in active[:30]:
        n1 = geom_names[g1] if g1 < len(geom_names) else f"g{g1}"
        n2 = geom_names[g2] if g2 < len(geom_names) else f"g{g2}"
        print(f"  {n1} <-> {n2}: dist={dd:+.4f}")
except Exception as e:  # noqa: BLE001
    print("contact read fail:", repr(e))
    print("contact attrs:", [a for a in dir(con) if not a.startswith("_")][:20])
