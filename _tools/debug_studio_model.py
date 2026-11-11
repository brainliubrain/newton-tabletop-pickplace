import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
import numpy as np
import warp as wp

wp.init()
from env import PickPlaceEnv  # noqa: E402

env = PickPlaceEnv()
from studio import build_studio_mjcf  # noqa: E402
import mujoco  # noqa: E402

xml_path = build_studio_mjcf(env)
m = mujoco.MjModel.from_xml_path(xml_path)
print("ngeom:", m.ngeom, "nmesh:", m.nmesh, "nmat:", m.nmat, "nlight:", m.nlight)
g2 = [i for i in range(m.ngeom) if m.geom_group[i] == 2]
print("group2 geoms:", len(g2))
for i in g2[:6]:
    mid = int(m.geom_matid[i])
    mat = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_MATERIAL, mid) if mid >= 0 else "-"
    print(
        f"  geom {i} body={mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, int(m.geom_bodyid[i]))} "
        f"mesh={mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_MESH, int(m.geom_dataid[i]))} mat={mat} "
        f"pos={np.round(m.geom_pos[i], 3)}"
    )
print("mesh verts:", [int(m.mesh_vertnum[i]) for i in range(min(m.nmesh, 40))])
