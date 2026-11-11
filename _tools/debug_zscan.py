"""Z-scan: command static grasp poses at the bowl xy, measure steady-state tcp."""
import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
from agent import FrankaIK  # noqa: E402
from env import PickPlaceEnv  # noqa: E402

wp.init()
env = PickPlaceEnv()
home = np.asarray(env.home_q, dtype=np.float32)

for z_cmd in (0.50, 0.47, 0.45, 0.43, 0.41, 0.39, 0.37):
    env.reset(seed=0)
    ik = FrankaIK(home)
    q = ik.solve((0.496, -0.129, z_cmd), iterations=500, cold=True)
    # measure achieved IK tcp
    import newton
    state = ik.model.state()
    newton.eval_fk(ik.model, ik.joint_q.reshape(-1), wp.zeros(9, dtype=wp.float32), state)
    ik_tcp = state.body_q.numpy()[11, :3]
    jt = np.asarray(q[:9], dtype=np.float32)
    jt[7:9] = 0.04
    for _ in range(180):  # 3 s settle
        env.step(jt)
    tcp = env.tcp_pose()[0]
    err = tcp[2] - ik_tcp[2]
    print(
        f"cmd_z={z_cmd:.3f} ik_tcp_z={ik_tcp[2]:.3f} sim_tcp=({tcp[0]:.3f},{tcp[1]:.3f},{tcp[2]:.3f}) "
        f"z_err={err * 1000:+.0f}mm"
    )
