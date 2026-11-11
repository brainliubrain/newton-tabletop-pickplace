import os
import sys

import newton

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place", "assets")
urdf = os.path.join(ASSETS, "franka_emika_panda", "urdf", "fr3_franka_hand.urdf")
fb = newton.ModelBuilder()
fb.add_urdf(urdf, floating=False, joint_damping_mode="passive")
print("joints:", fb.joint_count, "bodies:", fb.body_count)
for i, (l, t) in enumerate(zip(fb.joint_label, fb.joint_type)):
    print(f"{i:3d} {str(t):20s} {l}")
print("body labels:", list(fb.body_label))
