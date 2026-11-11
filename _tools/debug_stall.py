"""Dump IK-commanded vs sim joint state during the bowl grasp stall."""
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

for i in range(260):
    jt = agent.act()
    env.step(jt)
    if 170 <= i <= 240 and i % 10 == 0:
        ik_q = agent.ik.joint_q.numpy().reshape(-1)
        sim_q = env.joint_q()
        state = agent.ik.model.state()
        newton.eval_fk(agent.ik.model, agent.ik.joint_q.reshape(-1), wp.zeros(9, dtype=wp.float32), state)
        ik_tcp = state.body_q.numpy()[TCP_BODY, :3]
        sim_tcp = env.tcp_pose()[0]
        print(
            f"t={i:3d} {agent.phase_name:14s} cmd_target={np.round(agent.current_target, 3)} "
            f"ik_tcp={np.round(ik_tcp, 3)} sim_tcp={np.round(sim_tcp, 3)}"
        )
        print(
            f"      ik_q ={np.round(ik_q[:7], 2)}\n      sim_q={np.round(sim_q[:7], 2)}"
        )
