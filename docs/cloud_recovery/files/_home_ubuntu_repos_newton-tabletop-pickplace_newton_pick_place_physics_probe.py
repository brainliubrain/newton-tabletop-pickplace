"""Quantitative solver/contact probe for the MuJoCo-Warp backend.

Two uses:

1. ``SolverProbe`` — attach to a running PickPlaceEnv and sample the solver
   state once per control frame (active contacts, penetration depth per
   contact-pair class, solver iterations actually used, constraint-buffer
   headroom, grasp slip). ``bench.py --probe`` aggregates these per config, so
   a sweep reports continuous physics metrics instead of only task success.

2. CLI minimal repros (no agent, seconds each):
     python physics_probe.py rest         # rest penetration vs dt and vs ke/kd
     python physics_probe.py energy       # free-flight energy drift vs dt
     python physics_probe.py convergence  # arm PD step response vs dt (order)
     python physics_probe.py all

Sampling note: the probe reads the state after the LAST substep of each 60 Hz
frame (the substep loop is one captured graph), so per-substep transients
between frames are not observed; peaks are lower bounds.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import warp as wp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
GRAVITY = 9.81
SETTLE_WINDOW = 20  # frames; mirrors TaskConfig.settle_frames


def effective_contact_params(ke: float, kd: float, dt: float, dmax: float = 0.95) -> dict:
    """Contact reference the solver actually uses for a newton (ke, kd) shape.

    newton 1.7 compiles shape gains with ``convert_solref(ke, kd, 1.0, 1.0)``:
    timeconst = 2/kd, dampratio = kd / (2*sqrt(ke)). MuJoCo's refsafe then
    clamps timeconst to >= 2*dt, so for stiff gains the reference stiffness is
    set by the TIMESTEP, not by ke (k = 1/(dmax^2 tc^2 zeta^2), b = 2/(dmax tc)).
    """
    tc_req = 2.0 / kd
    zeta = kd / (2.0 * np.sqrt(ke))
    tc = max(tc_req, 2.0 * dt)
    return {
        "timeconst_requested_s": tc_req,
        "timeconst_effective_s": tc,
        "refsafe_clamped": bool(tc_req < 2.0 * dt),
        "dampratio": float(zeta),
        "k_ref": float(1.0 / (dmax**2 * tc**2 * zeta**2)),
        "b_ref": float(2.0 / (dmax * tc)),
    }


def immovable(mj, body: int) -> bool:
    """True if the body has no DOF anywhere up its kinematic chain (world, fixed base, ...)."""
    while body > 0:
        if mj.body_dofnum[body] > 0:
            return False
        body = int(mj.body_parentid[body])
    return True


class SolverProbe:
    """Per-frame sampler of MuJoCo-Warp contact/solver state for one env."""

    def __init__(self, env):
        self.env = env
        self.solver = env.solver
        self.data = env.solver.mjw_data
        mj = env.solver.mj_model
        self.iter_cap = int(mj.opt.iterations)
        self.njmax = int(self.data.njmax)
        self.naconmax = int(self.data.naconmax)
        role_of_shape = {s: role for role, shapes in env.shape_roles.items() for s in shapes}
        self.geom_role: list[str] = []
        for g in range(mj.ngeom):
            body = mj.body(mj.geom_bodyid[g]).name
            name = mj.geom(g).name
            shape = int(name.split("_")[-1]) if name.split("_")[-1].isdigit() else -1
            if body in ("bowl", "cup"):
                role = body
            elif "finger" in body:
                role = "finger"
            elif body.startswith("fr3"):
                role = "robot"
            else:
                role = role_of_shape.get(shape, "static")
            self.geom_role.append(role)
        self.geom_static = np.array([immovable(mj, int(mj.geom_bodyid[g])) for g in range(mj.ngeom)])
        self.reset()

    def reset(self):
        self.frames = 0
        self.max_pen: dict[str, float] = {}
        self.niter: list[int] = []
        self.nefc_peak = 0
        self.ncand_peak = 0
        self.nactive_peak = 0
        self.nactive_sum = 0
        self.static_static_peak = 0
        self.obj_speed_peak = {n: 0.0 for n in self.env.object_bodies}
        self._tail = {n: [] for n in self.env.object_bodies}  # (lin, ang) speed, last SETTLE_WINDOW frames
        self.arm_torque_peak = np.zeros(7)
        self._carry: dict[str, list] = {n: [] for n in self.env.object_bodies}

    def sample(self, phase: str = ""):
        d = self.data
        n = int(d.nacon.numpy()[0])
        self.frames += 1
        self.ncand_peak = max(self.ncand_peak, n)
        self.nefc_peak = max(self.nefc_peak, int(d.nefc.numpy()[0]))
        self.niter.append(int(d.solver_niter.numpy()[0]))
        n_active = 0
        if n:
            dist = d.contact.dist.numpy()[:n]
            geom = d.contact.geom.numpy()[:n]
            efc = d.contact.efc_address.numpy()[:n]
            active = (efc.reshape(n, -1)[:, 0] >= 0) & (dist < 0.0)
            has_row = efc.reshape(n, -1)[:, 0] >= 0
            n_active = int(np.count_nonzero(has_row))
            wasted = has_row & self.geom_static[geom[:, 0]] & self.geom_static[geom[:, 1]]
            self.static_static_peak = max(self.static_static_peak, int(np.count_nonzero(wasted)))
            for i in np.nonzero(active)[0]:
                key = "|".join(sorted((self.geom_role[geom[i, 0]], self.geom_role[geom[i, 1]])))
                pen = float(-dist[i])
                if pen > self.max_pen.get(key, 0.0):
                    self.max_pen[key] = pen
        self.nactive_peak = max(self.nactive_peak, n_active)
        self.nactive_sum += n_active
        self.arm_torque_peak = np.maximum(self.arm_torque_peak, np.abs(d.qfrc_actuator.numpy()[0, :7]))
        q, qd = self.env.body_poses(), self.env.body_vels()
        tcp = q[self.env.tcp_idx, :3]
        for name, b in self.env.object_bodies.items():
            lin, ang = float(np.linalg.norm(qd[b, :3])), float(np.linalg.norm(qd[b, 3:]))
            self.obj_speed_peak[name] = max(self.obj_speed_peak[name], lin)
            tail = self._tail[name]
            tail.append((lin, ang))
            if len(tail) > SETTLE_WINDOW:
                tail.pop(0)
            if phase == f"{name}:move":
                self._carry[name].append(q[b, :3] - tcp)

    def summary(self) -> dict:
        niter = np.asarray(self.niter or [0])
        dynamic = {k: v for k, v in self.max_pen.items() if "bowl" in k or "cup" in k}
        slip = {}
        for name, rel in self._carry.items():
            if len(rel) > 1:
                rel = np.asarray(rel)
                slip[name] = float(np.linalg.norm(rel.max(axis=0) - rel.min(axis=0)))
        return {
            "frames": self.frames,
            "max_penetration_mm": {k: round(v * 1e3, 3) for k, v in sorted(self.max_pen.items())},
            "max_object_penetration_mm": round(max(dynamic.values(), default=0.0) * 1e3, 3),
            "solver_niter_mean": round(float(niter.mean()), 2),
            "solver_niter_max": int(niter.max()),
            "solver_iter_cap": self.iter_cap,
            "solver_cap_hit_frac": round(float(np.mean(niter >= self.iter_cap)), 4),
            "nefc_peak": self.nefc_peak,
            "njmax": self.njmax,
            "njmax_headroom_x": round(self.njmax / max(self.nefc_peak, 1), 1),
            "contact_candidates_peak": self.ncand_peak,
            "contacts_active_peak": self.nactive_peak,
            "contacts_active_mean": round(self.nactive_sum / max(self.frames, 1), 2),
            "static_static_contacts_peak": self.static_static_peak,
            "naconmax": self.naconmax,
            "naconmax_headroom_x": round(self.naconmax / max(self.ncand_peak, 1), 1),
            "object_speed_peak_mps": {k: round(v, 3) for k, v in self.obj_speed_peak.items()},
            "carry_slip_mm": {k: round(v * 1e3, 3) for k, v in slip.items()},
            # speeds over the episode's last SETTLE_WINDOW frames (= the judge's settle window on success)
            "final_lin_speed_max_mps": {k: round(max(v[0] for v in t), 5) for k, t in self._tail.items() if t},
            "final_ang_speed_max_radps": {k: round(max(v[1] for v in t), 4) for k, t in self._tail.items() if t},
            "arm_torque_peak_nm": [round(float(v), 1) for v in self.arm_torque_peak],
            "velocity_clamp_events": int(getattr(self.env, "clamp_events", 0)),
        }


# --------------------------------------------------------------------------- #
# minimal repros
# --------------------------------------------------------------------------- #
def _make_env(**overrides):
    from env import PickPlaceEnv, SceneConfig

    return PickPlaceEnv(SceneConfig(**overrides))


def _loglog_slope(x, y) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = (x > 0) & (y > 0)
    return float(np.polyfit(np.log(x[ok]), np.log(y[ok]), 1)[0]) if ok.sum() >= 2 else float("nan")


def exp_rest(substeps_list=(4, 6, 8, 12, 16, 24), gains=((1.0e8, 5.0e4), (2.5e8, 5.0e4), (5.0e8, 3.0e4), (2.5e6, 5.0e3), (1.0e4, 1.0e2))):
    """Objects resting on the table: penetration + residual speed vs dt and vs (ke, kd)."""
    rows = []

    def run(**ov):
        env = _make_env(**ov)
        probe = SolverProbe(env)
        env.reset(seed=0)
        hold = np.asarray(env.home_q, dtype=np.float32)
        speeds = {n: [] for n in env.object_bodies}
        for f in range(150):
            env.step(hold)
            if f >= 90:  # last 1 s: rest window
                probe.sample()
                for n, b in env.object_bodies.items():
                    speeds[n].append(float(np.linalg.norm(env.body_vels()[b, :3])))
        s = probe.summary()
        q = env.body_poses()
        cfg = env.cfg
        row = {
            "substeps": cfg.substeps,
            "dt_ms": round(cfg.dt_substep * 1e3, 4),
            "contact_ke": cfg.contact_ke,
            "contact_kd": cfg.contact_kd,
            **{k: v for k, v in effective_contact_params(cfg.contact_ke, cfg.contact_kd, cfg.dt_substep).items()},
            "bowl_pen_mm": s["max_penetration_mm"].get("bowl|table_top", 0.0),
            "cup_pen_mm": s["max_penetration_mm"].get("cup|table_top", 0.0),
            "bowl_rest_height_err_mm": round((float(q[env.bowl_idx, 2]) - env.bowl_zmin - cfg.table_top_z) * 1e3, 3),
            "cup_rest_height_err_mm": round((float(q[env.cup_idx, 2]) + env.cup_zmin - cfg.table_top_z) * 1e3, 3),
            "bowl_rest_speed_mps": round(float(np.max(speeds["bowl"])), 5),
            "cup_rest_speed_mps": round(float(np.max(speeds["cup"])), 5),
            "solver_niter_mean": s["solver_niter_mean"],
        }
        rows.append(row)
        print(
            f"  substeps={row['substeps']:>2} dt={row['dt_ms']:.3f}ms ke={row['contact_ke']:.1e} kd={row['contact_kd']:.1e} "
            f"tc_eff={row['timeconst_effective_s'] * 1e3:.3f}ms zeta={row['dampratio']:.2f} | "
            f"pen bowl={row['bowl_pen_mm']:.4f} cup={row['cup_pen_mm']:.4f} mm | "
            f"rest speed bowl={row['bowl_rest_speed_mps']:.4f} cup={row['cup_rest_speed_mps']:.4f} m/s",
            flush=True,
        )
        return row

    print("[rest] A) dt sweep at default gains")
    dt_rows = [run(substeps=s) for s in substeps_list]
    print("[rest] B) gain sweep at default dt")
    gain_rows = [run(contact_ke=ke, contact_kd=kd) for ke, kd in gains]
    dts = [r["dt_ms"] for r in dt_rows]
    out = {
        "dt_sweep": dt_rows,
        "gain_sweep": gain_rows,
        "penetration_vs_dt_loglog_slope": {
            "bowl": round(_loglog_slope(dts, [r["bowl_pen_mm"] for r in dt_rows]), 2),
            "cup": round(_loglog_slope(dts, [r["cup_pen_mm"] for r in dt_rows]), 2),
        },
    }
    print(f"[rest] penetration ~ dt^p, fitted p = {out['penetration_vs_dt_loglog_slope']} (refsafe predicts 2)")
    return out


def _mechanical_energy(env, body: int) -> float:
    m = float(env.model.body_mass.numpy()[body])
    inertia = env.model.body_inertia.numpy()[body].reshape(3, 3)
    com = env.model.body_com.numpy()[body]
    q, qd = env.state_0.body_q.numpy()[body], env.state_0.body_qd.numpy()[body]
    x, y, z, w = q[3:7]
    rot = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    com_w = q[:3] + rot @ com
    v, w_ = qd[:3], qd[3:6]
    i_w = rot @ inertia @ rot.T
    return 0.5 * m * float(v @ v) + 0.5 * float(w_ @ i_w @ w_) + m * GRAVITY * float(com_w[2])


def exp_energy(substeps_list=(2, 4, 8, 16, 32)):
    """Free flight (no contacts) of the cup with spin: relative mechanical-energy drift vs dt."""
    rows = []
    for s in substeps_list:
        env = _make_env(substeps=s)
        env.reset(seed=0)
        off = env.free_joint_offsets["cup"]
        jq = env.state_0.joint_q.numpy()
        jq[off : off + 3] = [0.45, 0.6, 1.6]  # high above the scene, clear of the arm
        env.state_0.joint_q.assign(jq)
        jqd = env.state_0.joint_qd.numpy()
        d0 = 9 + 6  # 9 robot dofs + 6 bowl dofs -> cup free-joint dofs
        jqd[d0 : d0 + 6] = [0.3, -0.2, 1.0, 6.0, 4.0, 2.0]
        env.state_0.joint_qd.assign(jqd)
        import newton

        newton.eval_fk(env.model, env.state_0.joint_q, env.state_0.joint_qd, env.state_0)
        env.state_1.joint_q.assign(env.state_0.joint_q.numpy())
        env.state_1.joint_qd.assign(env.state_0.joint_qd.numpy())
        hold = np.asarray(env.home_q, dtype=np.float32)
        e0 = _mechanical_energy(env, env.cup_idx)
        drift = 0.0
        for _ in range(24):  # 0.4 s of flight
            # bypass the velocity safety clamp: step the solver directly
            env.control.joint_target_q.assign(hold)
            env._simulate() if env._graph is None else wp.capture_launch(env._graph)
            drift = max(drift, abs(_mechanical_energy(env, env.cup_idx) - e0))
        rows.append({"substeps": s, "dt_ms": round(env.cfg.dt_substep * 1e3, 4), "e0_J": round(e0, 6), "max_abs_drift_J": float(drift), "rel_drift": float(drift / abs(e0))})
        print(f"  substeps={s:>2} dt={rows[-1]['dt_ms']:.3f}ms  E0={e0:.4f} J  max|dE|={drift:.3e} J  rel={rows[-1]['rel_drift']:.3e}", flush=True)
    slope = _loglog_slope([r["dt_ms"] for r in rows], [r["max_abs_drift_J"] for r in rows])
    print(f"[energy] drift ~ dt^p, fitted p = {slope:.2f}")
    return {"rows": rows, "drift_vs_dt_loglog_slope": round(slope, 2)}


def exp_convergence(substeps_list=(2, 4, 6, 8, 12, 16), ref_substeps=64):
    """Arm PD step response in free space: joint trajectory error vs dt against a fine reference."""

    def traj(s):
        env = _make_env(substeps=s)
        env.reset(seed=0)
        target = np.asarray(env.home_q, dtype=np.float32).copy()
        target[:7] += np.array([0.25, 0.15, -0.2, 0.2, 0.2, -0.2, 0.3], dtype=np.float32)
        out = []
        for _ in range(60):  # 1 s
            env.step(target)
            out.append(env.joint_q()[:7].copy())
        return np.asarray(out), env.cfg.dt_substep

    ref, _ = traj(ref_substeps)
    rows = []
    for s in substeps_list:
        q, dt = traj(s)
        err = float(np.sqrt(np.mean((q - ref) ** 2)))
        rows.append({"substeps": s, "dt_ms": round(dt * 1e3, 4), "rms_joint_err_rad": err, "max_joint_err_rad": float(np.abs(q - ref).max())})
        print(f"  substeps={s:>2} dt={dt * 1e3:.3f}ms  rms err={err:.3e} rad  max={rows[-1]['max_joint_err_rad']:.3e} rad", flush=True)
    slope = _loglog_slope([r["dt_ms"] for r in rows], [r["rms_joint_err_rad"] for r in rows])
    print(f"[convergence] error ~ dt^p, fitted p = {slope:.2f} (reference: substeps={ref_substeps})")
    return {"reference_substeps": ref_substeps, "rows": rows, "error_vs_dt_loglog_slope": round(slope, 2)}


EXPERIMENTS = {"rest": exp_rest, "energy": exp_energy, "convergence": exp_convergence}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("experiment", choices=[*EXPERIMENTS, "all"])
    args = ap.parse_args()
    wp.init()
    wp.config.quiet = True
    names = list(EXPERIMENTS) if args.experiment == "all" else [args.experiment]
    out = {"device": str(wp.get_device()), "experiments": {}}
    for name in names:
        print(f"=== {name} ===", flush=True)
        out["experiments"][name] = EXPERIMENTS[name]()
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"probe_{'_'.join(names)}_{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"[probe] results -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
