"""Isolation test: does the lathe bowl settle correctly on a bare table box?"""
import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
import newton  # noqa: E402
from env import SceneConfig, bowl_profile, lathe_mesh  # noqa: E402

wp.init()
cfg = SceneConfig()

builder = newton.ModelBuilder()
builder.default_shape_cfg = newton.ModelBuilder.ShapeConfig(kh=1e11, gap=0.01)
builder.add_ground_plane()
builder.add_shape_box(
    body=-1, hx=cfg.table_half[0], hy=cfg.table_half[1], hz=cfg.table_half[2],
    xform=wp.transform(wp.vec3(*cfg.table_center), wp.quat_identity()),
)
mesh = lathe_mesh(bowl_profile(cfg))
b = builder.add_body(xform=wp.transform(wp.vec3(0.4955, -0.1289, cfg.table_top_z + 0.002), wp.quat_identity()), label="bowl")
builder.add_shape_mesh(body=b, mesh=mesh, cfg=newton.ModelBuilder.ShapeConfig(density=1500.0, mu=0.8))
builder.approximate_meshes(method="convex_hull", keep_visual_shapes=True)
model = builder.finalize()
print("bowl shapes:", [(s, model.shape_type.numpy()[s], model.shape_flags.numpy()[s]) for s in np.where(model.shape_body.numpy() == b)[0]])
print("ShapeFlags: COLLIDE_SHAPES =", int(newton.ShapeFlags.COLLIDE_SHAPES), " VISIBLE =", int(newton.ShapeFlags.VISIBLE))

s0, s1 = model.state(), model.state()
ctrl = model.control()
solver = newton.solvers.SolverMuJoCo(model, iterations=15, ls_iterations=20, njmax=128, nconmax=64)
for i in range(240):
    s0.clear_forces()
    solver.step(s0, s1, ctrl, None, 1.0 / 600)
    s0, s1 = s1, s0
wp.synchronize()
q = s0.body_q.numpy()
print("bowl final:", np.round(q[b, :3], 4), "quat:", np.round(q[b, 3:], 3))
qd = s0.body_qd.numpy()
print("bowl vel:", np.round(qd[b], 4))
