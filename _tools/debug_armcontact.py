"""At the far-pose stall: list arm <-> table/tray contacts from GPU mjw_data."""
import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
from agent import PickPlaceAgent  # noqa: E402
from env import PickPlaceEnv  # noqa: E402

wp.init()
env = PickPlaceEnv()
agent = PickPlaceAgent(env)
poses = env.reset(seed=0)
agent.reset_episode({k: np.array([v.p[0], v.p[1], v.p[2]]) for k, v in poses.items()})
for i in range(210):
    env.step(agent.act())

print("tcp:", np.round(env.tcp_pose()[0], 3))
d = env.solver.mjw_data
m = env.solver.mj_model
shape_body = env.model.shape_body.numpy()
body_names = list(env.model.body_label)

geom = np.asarray(d.contact.geom.numpy())  # (nacon_max, 2)
dist = np.asarray(d.contact.dist.numpy()).ravel()
nacon = int(np.asarray(d.nacon.numpy()).ravel()[0])
print(f"nacon={nacon}")
STATIC = {-1}
seen = []
for i in range(min(nacon, len(dist))):
    g1, g2 = int(geom[i, 0]), int(geom[i, 1])
    dd = float(dist[i])
    if g1 < 0 or g2 < 0:
        continue
    s1, s2 = g1, g2
    b1, b2 = int(shape_body[s1]), int(shape_body[s2])
    # arm bodies are 0..13; static = -1 (table/tray/ground); objects 14,15
    arm_involved = (0 <= b1 <= 13 and b2 in (-1, 14, 15)) or (0 <= b2 <= 13 and b1 in (-1, 14, 15))
    if arm_involved and dd < 0.02:
        n1 = body_names[b1] if b1 >= 0 else "STATIC"
        n2 = body_names[b2] if b2 >= 0 else "STATIC"
        seen.append((f"{n1} <-> {n2}", dd, s1, s2))
for s in sorted(seen, key=lambda t: t[1])[:20]:
    print(f"  {s[0]}: dist={s[1] * 1000:.1f}mm  shapes=({s[2]},{s[3]})")
