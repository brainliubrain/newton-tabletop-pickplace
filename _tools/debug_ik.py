"""Probe IK reachability of the bowl/cup grasp poses; print joint values vs limits."""
import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
import newton  # noqa: E402
from agent import FrankaIK  # noqa: E402
from env import TCP_BODY, solve_home_q  # noqa: E402

wp.init()
home = np.asarray(solve_home_q(), dtype=np.float32)
ik = FrankaIK(home)

targets = {
    "bowl grasp (0.496,-0.129,0.417)": (0.496, -0.129, 0.417),
    "bowl hover (0.496,-0.129,0.55)": (0.496, -0.129, 0.55),
    "cup grasp (0.402,0.175,0.435)": (0.402, 0.175, 0.435),
    "slot lower (0.56,0.02,0.46)": (0.56, 0.02, 0.46),
}

lo = ik.model.joint_limit_lower.numpy()
hi = ik.model.joint_limit_upper.numpy()
print("arm joint limits (rad):")
for j in range(7):
    print(f"  j{j+1}: [{lo[j]:+.2f}, {hi[j]:+.2f}]")

for name, tgt in targets.items():
    ik.joint_q.assign(home.reshape(1, -1))  # reset seed each time
    q = None
    for it in range(1, 301):
        q = ik.solve(tgt, iterations=1)
    # forward kinematics the solution
    state = ik.model.state()
    newton.eval_fk(ik.model, ik.joint_q.reshape(-1), wp.zeros(ik.model.joint_coord_count, dtype=wp.float32), state)
    tcp = state.body_q.numpy()[TCP_BODY, :3]
    err = np.linalg.norm(tcp - np.array(tgt))
    js = " ".join(f"{v:+.2f}" for v in q[:7])
    at_lim = ["LIM!" if abs(q[j] - lo[j]) < 0.05 or abs(q[j] - hi[j]) < 0.05 else "" for j in range(7)]
    print(f"{name}: tcp={np.round(tcp,3)} err={err*1000:.0f}mm iters=300")
    print(f"   q=[{js}] at_limit={at_lim}")
