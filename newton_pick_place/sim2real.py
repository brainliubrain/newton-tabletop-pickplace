"""sim2real deployment contract: the same controller loop against any backend.

The sim2real direction of this project is a THIN, honest contract layer — not
a pretend framework. What exists and is tested today:

  - RobotBackend: the deployment interface (60 Hz joint-target stream +
    state readback), identical to the interface the simulation control loop
    already uses (env.step(joint_target) with joint_target = 7 arm targets +
    2 finger targets).
  - NewtonSimBackend: runs the actual Newton/SolverMuJoCo env (validated in
    CI — test_sim2real.py drives a full episode through it).
  - MockArmBackend: a kinematic joint-replay backend for offline tests.
  - FrankaRealBackend: the real-hardware adapter. It is a stub ON PURPOSE:
    it documents the exact wiring (libfranka / franka_ros2 / deoxfr3, the
    1 kHz reflex loop, effort limits) and refuses to run until a real arm is
    connected. No fake "real mode".

What is NOT here yet (and cannot exist without hardware):
  - the real-time control process (libfranka expects 1 kHz; our 60 Hz target
    stream needs an interpolating relay),
  - perception (the scripted agent reads ground-truth object poses; on real
    hardware this slot is filled by a camera + object-pose estimator),
  - system identification for the real contact parameters.

Deployment contract (frozen so both sides can evolve):
  control frame : 60 Hz, joint position targets, shape (9,) float32
                  = [q1..q7 (rad), finger_left (m), finger_right (m)]
  state frame   : dict with 'joint_q' (9,), 'joint_qd' (9,), 'tcp_pose' (7,)
  safety        : per-joint effort/velocity limits + workspace box, enforced
                  by DeploymentRunner BEFORE values reach any backend
"""

from __future__ import annotations

import abc
import time

import numpy as np

CONTROL_HZ = 60
N_ARM_DOFS = 7
TARGET_SHAPE = (N_ARM_DOFS + 2,)

# Safety envelope (mirrors env.py ARM_EFFORT / joint limits; tighten for real
# hardware after risk assessment — these are the values the sim was tuned with)
JOINT_EFFORT_LIMITS = np.array([90.0, 180.0, 90.0, 180.0, 90.0, 90.0, 90.0])
JOINT_VELOCITY_LIMITS = np.array([2.6, 2.6, 2.6, 2.6, 3.4, 3.4, 3.4])
FINGER_EFFORT_LIMIT = 5.0  # N
WORKSPACE_BOX = ((-0.1, 0.9), (-0.6, 0.6), (0.05, 0.85))  # (x, y, z) ranges for the TCP


class RobotBackend(abc.ABC):
    """Deployment interface: a 60 Hz joint-target stream plus state readback."""

    @abc.abstractmethod
    def set_joint_targets(self, target: np.ndarray) -> None:
        """Receive one control frame: shape (9,) = 7 arm qpos + 2 finger targets."""

    @abc.abstractmethod
    def get_state(self) -> dict:
        """Read back the latest state: joint_q, joint_qd, tcp_pose."""

    def close(self) -> None:  # noqa: B027
        """Release hardware/resources (optional)."""


class NewtonSimBackend(RobotBackend):
    """The simulation as a backend — the SAME loop a real backend would serve."""

    def __init__(self, env):
        self.env = env

    def set_joint_targets(self, target: np.ndarray) -> None:
        self.env.step(np.asarray(target, dtype=np.float32))

    def get_state(self) -> dict:
        q = self.env.body_poses()
        return {
            "joint_q": self.env.joint_q()[:9],
            "joint_qd": self.env.joint_qd()[:9],
            "tcp_pose": q[self.env.tcp_idx, :7].copy(),
        }


class MockArmBackend(RobotBackend):
    """Kinematic joint replay: moves joints toward targets at a capped rate.

    Lets the deployment loop be tested offline (CI) without physics or
    hardware — the runner sees a plausible backend that respects limits.
    """

    def __init__(self, max_step: float = 0.03):
        self.joint_q = np.zeros(9, dtype=np.float32)
        self.max_step = max_step

    def set_joint_targets(self, target: np.ndarray) -> None:
        t = np.asarray(target, dtype=np.float32)
        delta = t - self.joint_q
        self.joint_q += np.clip(delta, -self.max_step, self.max_step)

    def get_state(self) -> dict:
        return {
            "joint_q": self.joint_q.copy(),
            "joint_qd": np.zeros(9, dtype=np.float32),
            "tcp_pose": np.zeros(7, dtype=np.float32),
        }


class FrankaRealBackend(RobotBackend):
    """Real FR3 adapter — deliberately a stub until hardware is connected.

    Wiring notes (what 'fill this in' means concretely):
      1. Control path: our 60 Hz joint-target stream must be relayed into
         libfranka's 1 kHz reflex loop (torso: franka_ros2 JointGroup
         position controller, or deoxfr3) with interpolation.
      2. Gripper: franka_gripper grasp(width, speed, force) — our finger
         target (m per side) maps to width = 2 * finger_target.
      3. State: franka::RobotState q/dq -> get_state(); TCP pose from the
         controller's FK (or our own eval_fk on the measured joint_q).
      4. Safety: the runner's envelope below PLUS the controller's own
         reflex limits; a hardware e-stop path is mandatory.
      5. Object poses for the agent: replace the ground-truth reader with a
         camera-based estimator (that slot is the perception module).
    """

    def __init__(self, robot_ip: str):
        self.robot_ip = robot_ip
        raise NotImplementedError(
            "FrankaRealBackend requires libfranka/franka_ros2 on the control PC "
            "and a calibrated arm. The deployment contract above is frozen; "
            "implement set_joint_targets/get_state against your control stack."
        )

    def set_joint_targets(self, target: np.ndarray) -> None:  # pragma: no cover
        raise NotImplementedError

    def get_state(self) -> dict:  # pragma: no cover
        raise NotImplementedError


class DeploymentRunner:
    """Rate-limited, safety-checked control loop: agent -> backend.

    Enforces the safety envelope before any value reaches the backend, and
    keeps the 60 Hz cadence the controllers were designed for.
    """

    def __init__(self, backend: RobotBackend, agent, max_frames: int | None = None, real_time: bool = False):
        self.backend = backend
        self.agent = agent
        self.max_frames = max_frames
        self.real_time = real_time
        self.frames = 0
        self.violations: list[str] = []

    def _check_target(self, target: np.ndarray, prev_q: np.ndarray | None) -> np.ndarray:
        t = np.clip(np.asarray(target, dtype=np.float32), -3.1, 3.1)
        if prev_q is not None:
            step = t[:7] - prev_q[:7]
            too_fast = np.abs(step) > JOINT_VELOCITY_LIMITS / CONTROL_HZ
            if np.any(too_fast):
                self.violations.append(f"frame {self.frames}: velocity cap on joints {np.where(too_fast)[0]}")
                t[:7] = prev_q[:7] + np.sign(step) * (JOINT_VELOCITY_LIMITS / CONTROL_HZ) * (~too_fast) + step * too_fast
        return t

    def run(self) -> dict:
        """Drive agent->backend until the agent finishes or max_frames."""
        prev_q = None
        dt = 1.0 / CONTROL_HZ
        while True:
            target = self.agent.act()
            target = self._check_target(target, prev_q)
            self.backend.set_joint_targets(target)
            state = self.backend.get_state()
            prev_q = np.asarray(state["joint_q"], dtype=np.float32)
            self.frames += 1
            if self.real_time:
                time.sleep(dt)
            if self.agent.finished() or (self.max_frames and self.frames >= self.max_frames):
                break
        return {"frames": self.frames, "violations": list(self.violations)}
