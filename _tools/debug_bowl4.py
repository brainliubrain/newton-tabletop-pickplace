"""Bowl-on-table contact (ke, kd) grid scan: find params that rest ON the table top."""
import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
import newton  # noqa: E402
from env import SceneConfig, bowl_profile, lathe_mesh  # noqa: E402

wp.init()
cfg = SceneConfig()


def run(name, ke, kd, gap=0.0):
    builder = newton.ModelBuilder()
    builder.add_ground_plane()
    builder.add_shape_box(
        body=-1, hx=cfg.table_half[0], hy=cfg.table_half[1], hz=cfg.table_half[2],
        xform=wp.transform(wp.vec3(*cfg.table_center), wp.quat_identity()),
        cfg=newton.ModelBuilder.ShapeConfig(density=700.0, mu=0.6, ke=ke, kd=kd, gap=gap),
    )
    mesh = lathe_mesh(bowl_profile(cfg))
    b = builder.add_body(xform=wp.transform(wp.vec3(0.4955, -0.1289, cfg.table_top_z + 0.002), wp.quat_identity()), label="bowl")
    builder.add_shape_mesh(
        body=b, mesh=mesh,
        cfg=newton.ModelBuilder.ShapeConfig(density=1500.0, mu=0.8, ke=ke, kd=kd, gap=gap),
    )
    builder.approximate_meshes(method="convex_hull", keep_visual_shapes=True)
    model = builder.finalize()
    s0, s1 = model.state(), model.state()
    ctrl = model.control()
    solver = newton.solvers.SolverMuJoCo(model, iterations=15, ls_iterations=20, njmax=128, nconmax=64)
    for _ in range(240):
        s0.clear_forces()
        solver.step(s0, s1, ctrl, None, 1.0 / 600)
        s0, s1 = s1, s0
    wp.synchronize()
    q = s0.body_q.numpy()
    z = q[b, 2]
    verdict = "OK " if (np.isfinite(z) and 0.395 <= z <= 0.406) else "   "
    print(f"{verdict}{name:26s} final z={z:.4f}  xy=({q[b,0]:.3f},{q[b,1]:.3f})")


run("ke=0 kd=0 (mujoco default)", 0.0, 0.0)
for ke, kd in (
    (2.5e3, 100.0),      # library defaults -> baseline
    (2.5e5, 1e3),
    (2.5e5, 3e3),
    (2.5e6, 3e3),
    (2.5e6, 1e4),
    (2.5e7, 1e4),
    (2.5e7, 3e4),
    (2.5e8, 3e4),
    (2.5e8, 1e5),
    (9e9, 2e5),          # analytic: T=0.01s, zeta=1
    (2.25e9, 1e5),       # T=0.02s, zeta=1
):
    try:
        run(f"ke={ke:.1e} kd={kd:.0e}", ke, kd)
    except Exception as e:  # noqa: BLE001
        print(f"  ke={ke:.1e} kd={kd:.0e} FAILED: {e!r}")
