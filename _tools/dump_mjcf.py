import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
import numpy as np
import warp as wp

wp.init()
import newton  # noqa: E402
from env import PickPlaceEnv  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "physics_model.xml")

env = PickPlaceEnv()
s = newton.solvers.SolverMuJoCo(
    env.model, iterations=15, ls_iterations=20, njmax=512, nconmax=256, save_to_mjcf=OUT
)
print("saved:", OUT, os.path.getsize(OUT), "bytes")

import mujoco  # noqa: E402

m = s.mj_model
print("ngeom:", m.ngeom, "nbody:", m.nbody, "nlight:", m.nlight)
for i in range(m.ngeom):
    name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, i) or "-"
    t = int(m.geom_type[i])
    print(f"geom {i:3d} body={mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, int(m.geom_bodyid[i])) or '-':18s} type={t} rgba={np.round(m.geom_rgba[i], 3)} name={name}")
