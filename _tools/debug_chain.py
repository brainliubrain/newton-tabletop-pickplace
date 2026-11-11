"""Full command-chain dump during the bowl grasp hold."""
import os
import sys

import numpy as np
import warp as wp

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "newton_pick_place"))
import newton  # noqa: E402
from agent import PickPlaceAgent  # noqa: E402
from env import TCP_BODY, PickPlaceEnv  # noqa: E402

wp.init()
env = PickPlaceEnv()
agent = PickPlaceAgent(env)
poses = env.reset(seed=0)
agent.reset_episode({k: np.array([v.p[0], v.p[1], v.p[2]]) for k, v in poses.items()})

for i in range(230):
    jt = agent.act()
    env.step(jt)
    if i in (100, 150, 180, 200, 220, 225, 228):
        ik_q = agent.ik.joint_q.numpy().reshape(-1)
        state = agent.ik.model.state()
        newton.eval_fk(agent.ik.model, agent.ik.joint_q.reshape(-1), wp.zeros(9, dtype=wp.float32), state)
        ik_tcp = state.body_q.numpy()[TCP_BODY, :3]
        ctrl = env.control.joint_target_q.numpy()
        sim_q = env.joint_q()
        sim_tcp = env.tcp_pose()[0]
        print(f"--- t={i} phase={agent.phase_name}")
        print(f"  ik_tcp={np.round(ik_tcp, 3)}  ctrl_recv={np.round(ctrl[:9], 3)}")
        print(f"  sim_tcp={np.round(sim_tcp, 3)}")
        print(f"  ik_q ={np.round(ik_q[:7], 3)}")
        print(f"  sim_q={np.round(sim_q[:7], 3)}")
        print(f"  ctrl-sim qerr={np.round(ctrl[:7] - sim_q[:7], 3)}")
