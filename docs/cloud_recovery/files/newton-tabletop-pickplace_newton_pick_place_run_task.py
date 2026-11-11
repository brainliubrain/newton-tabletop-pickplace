                float(judge.was_grasped["cup"]),
                float(judge.was_placed["cup"]),
            )
            bridge.record_step(
                step=i,
                t=float(env.sim_time),
                phase=phase_id,
                subtask=subtask_id,
                tip_xyz=tcp_pos,
                obj_xyz=cur_obj_xyz,
                dest_xyz=cur_dest_xyz,
                grip=float(action_target[7]),
                arm_j=env.arm_joint_q(),
                arm_jd=env.arm_joint_qd(),
                finger_gap=float(env.finger_gap()),
                tip_q=tcp_rot,
                bowl_q=q[bowl_b, 3:7],
                cup_q=q[cup_b, 3:7],
                gates=gates,
                success=float(is_success),
                bowl_xyz=q[bowl_b, :3],
                cup_xyz=q[cup_b, :3],
            )

        if collect_lerobot:
            lerobot_buffers["states"].append(np.hstack([env.arm_joint_q(), [env.finger_gap()]]))
            lerobot_buffers["actions"].append(action_target[:8].copy())
            lerobot_buffers["ee_poses"].append(np.hstack([tcp_pos, tcp_rot]))
            lerobot_buffers["objects"].append(np.hstack([q[bowl_b, :7], q[cup_b, :7]]))
            lerobot_buffers["subtasks"].append(subtask_id)
            lerobot_buffers["phases"].append(phase_id)
            lerobot_buffers["timestamps"].append(float(env.sim_time))

        if is_success:
            outcome, success_frame = "success", i
            break

        if recorder is not None and i % 2 == 0:
            recorder(
                i,
                hud={
                    "t": float(env.sim_time),
                    "phase": cur_phase_name,
                    "gap": float(env.finger_gap()),
                    "ee": tuple(float(v) for v in tcp_pos),
                    "success": False,
                },
            )

    q = env.body_poses()
    if recorder is not None:
        recorder(
            frames,
            hud={
                "t": float(env.sim_time),
                "phase": agent.phase_name,
                "gap": float(env.finger_gap()),
                "ee": tuple(float(v) for v in env.tcp_pose()[0]),
                "success": judge.success(),
            },
        )
    record = {
        "seed": seed,
        "outcome": outcome,
        "success_frame": success_frame,
        "frames": frames,
        "wall_s": round(time.time() - t_ep0, 2),
        "ms_per_frame": round(1000.0 * (time.time() - t_ep0) / max(frames, 1), 2),
        "agent_ms_per_frame": round(1000.0 * t_agent / max(frames, 1), 2),
        "envstep_ms_per_frame": round(1000.0 * t_envstep / max(frames, 1), 2),
        "grasped": dict(judge.was_grasped),
        "final_poses": {
            name: [round(float(v), 4) for v in q[b, :7]]
            for name, b in env.object_bodies.items()
        },
        "spawn_poses": {
            name: [round(float(v.p[0]), 4), round(float(v.p[1]), 4)] for name, v in poses.items()
        },
    }

    if collect_lerobot:
        record["lerobot_data"] = {
            k: np.array(v, dtype=np.float32 if k not in ("subtasks", "phases") else np.int64)
            for k, v in lerobot_buffers.items()
        }

    return record
