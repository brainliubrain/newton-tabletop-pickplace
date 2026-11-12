"""Asset / scene audit: what the solver ACTUALLY simulates vs what the assets say.

Compares three sources of truth:
  1. the vendored URDF (assets/franka_emika_panda/urdf/fr3_franka_hand.urdf)
  2. the vendored MuJoCo-Menagerie FR3 MJCF (assets/franka_fr3/fr3.xml), used
     as an independent reference for actuator/joint dynamics
  3. the compiled MuJoCo model that MuJoCo-Warp steps (env.solver.mj_model)
plus a short settle rollout to audit contacts (initial penetration, wasted
static-static constraints, contact-manifold size, rest-velocity noise floor).

Every check is PASS / WARN / FAIL with the measured and expected value, so a
config or asset regression shows up as a diff of results/asset_audit.json.

Usage:
  python asset_audit.py              # audit the default SceneConfig
  python asset_audit.py --strict     # exit 1 on any FAIL (CI gate)
  python asset_audit.py --set multiccd=0 --set rigid_gap=0.1   # audit another config
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

import numpy as np
import warp as wp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env import ARM_ARMATURE, ARM_EFFORT, ARM_KD, ARM_KE, BASE_BODY, FRANKA_URDF, PickPlaceEnv, SceneConfig  # noqa: E402
from physics_probe import effective_contact_params, immovable  # noqa: E402
from task import TaskConfig  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MENAGERIE_FR3 = os.path.join(HERE, "assets", "franka_fr3", "fr3.xml")
RESULTS_DIR = os.path.join(HERE, "results")


class Audit:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, check: str, verdict: str, measured, expected, note: str = ""):
        self.rows.append({"check": check, "verdict": verdict, "measured": measured, "expected": expected, "note": note})

    def counts(self) -> dict:
        return {v: sum(r["verdict"] == v for r in self.rows) for v in ("PASS", "WARN", "FAIL")}

    def print(self):
        for r in self.rows:
            print(f"[{r['verdict']:<4}] {r['check']}\n         measured: {r['measured']}\n         expected: {r['expected']}" + (f"\n         note: {r['note']}" if r["note"] else ""))


def _r(x, n=4):
    return [round(float(v), n) for v in np.atleast_1d(x)]


def parse_urdf(path: str) -> dict:
    root = ET.parse(path).getroot()
    masses = {}
    for link in root.findall("link"):
        mass = link.find("inertial/mass")
        if mass is not None:
            masses[link.get("name")] = float(mass.get("value"))
    joints = {}
    for joint in root.findall("joint"):
        lim = joint.find("limit")
        if joint.get("type") in ("revolute", "prismatic") and lim is not None:
            joints[joint.get("name")] = {k: float(lim.get(k)) for k in ("lower", "upper", "effort", "velocity")}
    return {"masses": masses, "joints": joints}


def audit_robot(a: Audit, env: PickPlaceEnv):
    import mujoco

    mj = env.solver.mj_model
    urdf = parse_urdf(FRANKA_URDF)
    arm_joints = [f"fr3_joint{i}" for i in range(1, 8)]

    # --- link masses: URDF -> compiled -------------------------------------
    body_mass = {mj.body(b).name.split("fr3_", 1)[-1]: float(mj.body_mass[b]) for b in range(mj.nbody)}
    links = [f"fr3_link{i}" for i in range(1, 8)]
    urdf_m = [urdf["masses"][link] for link in links]
    comp_m = [body_mass.get(link, float("nan")) for link in links]
    err = float(np.nanmax(np.abs(np.array(comp_m) / np.array(urdf_m) - 1.0)))
    a.add("robot.link_mass: compiled == URDF", "PASS" if err < 0.01 else "FAIL", _r(comp_m, 3), _r(urdf_m, 3), f"max rel err {err:.2e}")

    # --- inertia validity (all bodies with mass) ---------------------------
    bad = []
    for b in range(1, mj.nbody):
        i1, i2, i3 = sorted(float(v) for v in mj.body_inertia[b])
        if mj.body_mass[b] > 0 and (i1 <= 0 or i1 + i2 < i3 * (1 - 1e-6)):
            bad.append(mj.body(b).name)
    a.add("inertia: positive-definite + triangle inequality (all bodies)", "PASS" if not bad else "FAIL", bad or "all valid", "no violations")

    # --- joint limits / effort: URDF (hardware datasheet) -> compiled -------
    qadr = {mj.joint(j).name.split("fr3_", 1)[-1]: j for j in range(mj.njnt)}
    comp_rng = [mj.jnt_range[qadr[j]] for j in arm_joints if j in qadr]
    urdf_rng = [(urdf["joints"][j]["lower"], urdf["joints"][j]["upper"]) for j in arm_joints]
    ok = len(comp_rng) == 7 and np.allclose(comp_rng, urdf_rng, atol=1e-3)
    a.add("robot.joint_range: compiled == URDF", "PASS" if ok else "FAIL", [_r(r, 3) for r in comp_rng], [_r(r, 3) for r in urdf_rng])

    hw_effort = [urdf["joints"][j]["effort"] for j in arm_joints]
    # newton maps joint_effort_limit -> mj.jnt_actfrcrange (per-joint actuator
    # force range), NOT actuator_forcerange — read the compiled value.
    comp_effort = [float(mj.jnt_actfrcrange[qadr[j]][1]) for j in arm_joints if j in qadr]
    over = [round(s / h, 1) for s, h in zip(comp_effort, hw_effort)]
    a.add(
        "robot.effort_limit: sim <= hardware torque limit",
        "PASS" if comp_effort and max(over) <= 1.05 else "WARN",
        _r(comp_effort, 1),
        hw_effort,
        f"sim/hardware ratio per joint {over}: torque the real FR3 cannot produce is available in sim (sim2real gap); see probe 'arm_torque_peak_nm' for what the task actually uses",
    )
    hw_vel = [urdf["joints"][j]["velocity"] for j in arm_joints]
    a.add("robot.velocity_limit: hardware reference", "PASS", "not enforced by the solver (agent PTP profile + sim2real envelope enforce it)", hw_vel)

    # --- actuator/joint dynamics vs Menagerie reference ---------------------
    # fr3.xml declares meshdir="assets" (upstream layout); our vendored copy
    # keeps the .obj files next to the XML, so patch meshdir="." via a temp copy.
    with open(MENAGERIE_FR3, encoding="utf-8") as fh:
        xml = fh.read().replace('meshdir="assets"', 'meshdir="."')
    ref_xml = os.path.join(os.path.dirname(MENAGERIE_FR3), "_audit_fr3.xml")
    with open(ref_xml, "w", encoding="utf-8") as fh:
        fh.write(xml)
    ref = mujoco.MjModel.from_xml_path(ref_xml)
    ref_arm = [float(ref.dof_armature[ref.joint(j).dofadr[0]]) for j in arm_joints]
    ref_fl = [float(ref.dof_frictionloss[ref.joint(j).dofadr[0]]) for j in arm_joints]
    ref_kp = [float(ref.actuator_gainprm[i, 0]) for i in range(7)]
    ref_kv = [float(-ref.actuator_biasprm[i, 2]) for i in range(7)]
    comp_arm = [float(mj.dof_armature[mj.jnt_dofadr[qadr[j]]]) for j in arm_joints]
    comp_fl = [float(mj.dof_frictionloss[mj.jnt_dofadr[qadr[j]]]) for j in arm_joints]
    a.add("robot.armature vs Menagerie FR3", "PASS" if np.allclose(comp_arm, ref_arm, rtol=0.25) else "WARN", _r(comp_arm, 3), _r(ref_arm, 3), f"configured ARM_ARMATURE={ARM_ARMATURE}")
    a.add("robot.frictionloss vs Menagerie FR3", "PASS" if np.allclose(comp_fl, ref_fl, rtol=0.25) else "WARN", _r(comp_fl, 3), _r(ref_fl, 3), "joint dry friction is not modeled in the sim")
    a.add("robot.pd_gains vs Menagerie FR3 (kp, kv)", "PASS" if np.allclose(ARM_KE, ref_kp, rtol=0.5) else "WARN", {"kp": list(ARM_KE), "kv": list(ARM_KD)}, {"kp": ref_kp, "kv": ref_kv}, "design choice; affects tracking error and contact impulse")


def audit_objects(a: Audit, env: PickPlaceEnv):
    mj = env.solver.mj_model
    cfg = env.cfg
    model = env.model
    shape_body = model.shape_body.numpy()
    body_mass = model.body_mass.numpy()
    body_inertia = model.body_inertia.numpy()

    if "bowl" not in env.object_assets:
        r, h = cfg.bowl_rim_r, cfg.bowl_height
        m = float(body_mass[env.bowl_idx])
        m_collider = float(np.pi * r * r * h * cfg.bowl_density)
        a.add(
            "bowl.mass: single mass source (collision shape x bowl_density)",
            "PASS" if abs(m / m_collider - 1.0) < 0.02 else "WARN",
            f"{m:.4f} kg",
            f"{m_collider:.4f} kg",
            f"{(m - m_collider) * 1e3:+.1f} g comes from other shapes on the body (a visual-only mesh with non-zero density is counted as mass)",
        )
        izz = float(body_inertia[env.bowl_idx].reshape(3, 3)[2, 2])
        izz_solid = 0.5 * m * r * r
        a.add("bowl.inertia_zz vs solid cylinder of the same mass", "PASS", f"{izz:.3e} kg m^2", f"solid {izz_solid:.3e}; thin shell {m * r * r:.3e}", "a real bowl is a shell: its yaw inertia lies between these")
        vis = [s for s in env.shape_roles.get("bowl_visual", [])]
        if vis:
            v = np.asarray(model.shape_source[vis[0]].vertices)
            r_vis = float(np.linalg.norm(v[:, :2], axis=1).max())
            a.add("bowl.collision_radius vs visual radius", "PASS" if abs(r_vis - r) < 2e-3 else "WARN", f"collision {r * 1e3:.1f} mm", f"visual {r_vis * 1e3:.1f} mm", "collision is a solid cylinder: the bowl cavity is not physical (nothing can be placed inside it)")

    # every dynamic object: mass plausibility + friction
    for name, b in env.object_bodies.items():
        shapes = [int(s) for s in np.nonzero(shape_body == b)[0]]
        mus = sorted({round(float(model.shape_material_mu.numpy()[s]), 3) for s in shapes})
        a.add(f"{name}.mass / friction", "PASS" if 0.02 < body_mass[b] < 1.0 else "WARN", f"{float(body_mass[b]):.4f} kg, mu={mus}", "0.02-1.0 kg (graspable by a 5 N/finger gripper)")

    del mj


def audit_scene(a: Audit, env: PickPlaceEnv, task_cfg: TaskConfig):
    mj = env.solver.mj_model
    d = env.solver.mjw_data
    cfg = env.cfg

    # --- solver options actually integrated ----------------------------------
    g = [float(v) for v in mj.opt.gravity]
    a.add("scene.gravity (z-up, SI)", "PASS" if np.allclose(g, [0, 0, -9.81], atol=0.01) else "FAIL", g, [0, 0, -9.81])
    ts = float(env.solver.mjw_model.opt.timestep.numpy()[0])
    env.reset(seed=0)
    hold = np.asarray(env.home_q, dtype=np.float32)
    env.step(hold)
    ts = float(env.solver.mjw_model.opt.timestep.numpy()[0])
    a.add("solver.timestep integrated == SceneConfig.dt_substep", "PASS" if abs(ts - cfg.dt_substep) < 1e-9 else "FAIL", f"{ts * 1e3:.5f} ms", f"{cfg.dt_substep * 1e3:.5f} ms")

    eff = effective_contact_params(cfg.contact_ke, cfg.contact_kd, cfg.dt_substep)
    a.add(
        "contact.solref: requested time constant is honored",
        "WARN" if eff["refsafe_clamped"] else "PASS",
        f"requested timeconst {eff['timeconst_requested_s'] * 1e3:.3f} ms -> effective {eff['timeconst_effective_s'] * 1e3:.3f} ms (dampratio {eff['dampratio']:.2f})",
        f">= 2*dt = {2 * cfg.dt_substep * 1e3:.3f} ms",
        "refsafe clamps it: contact stiffness is set by the timestep; ke/kd only act through dampratio = kd / (2 sqrt(ke))" if eff["refsafe_clamped"] else "",
    )

    # --- settle rollout: contacts ---------------------------------------------
    rest_lin = {n: 0.0 for n in env.object_bodies}
    rest_ang = {n: 0.0 for n in env.object_bodies}
    start = {n: env.body_poses()[b, :3].copy() for n, b in env.object_bodies.items()}
    for f in range(180):
        env.step(hold)
        if f == 60:
            start = {n: env.body_poses()[b, :3].copy() for n, b in env.object_bodies.items()}
        if f >= 60:
            for n, b in env.object_bodies.items():
                qd = env.body_vels()[b]
                rest_lin[n] = max(rest_lin[n], float(np.linalg.norm(qd[:3])))
                rest_ang[n] = max(rest_ang[n], float(np.linalg.norm(qd[3:])))
    drift = {n: float(np.linalg.norm(env.body_poses()[b, :3] - start[n])) for n, b in env.object_bodies.items()}

    n = int(d.nacon.numpy()[0])
    geom = d.contact.geom.numpy()[:n]
    dist = d.contact.dist.numpy()[:n]
    efc = d.contact.efc_address.numpy()[:n].reshape(n, -1)[:, 0]
    active = efc >= 0
    body_of = lambda g_: int(mj.geom_bodyid[g_])  # noqa: E731
    label = lambda g_: f"{mj.body(body_of(g_)).name}/{mj.geom(g_).name}"  # noqa: E731

    deep = [(label(g1), label(g2), round(float(-dist[i]) * 1e3, 2)) for i, (g1, g2) in enumerate(geom) if active[i] and dist[i] < -1e-3]
    a.add("scene.initial_penetration: no resting contact deeper than 1 mm", "PASS" if not deep else "FAIL", deep or "none", "none", "overlapping static geometry is solved as a contact every substep" if deep else "")

    wasted = [i for i, (g1, g2) in enumerate(geom) if active[i] and immovable(mj, body_of(g1)) and immovable(mj, body_of(g2))]
    nefc = int(d.nefc.numpy()[0])
    a.add(
        "scene.static_static_contacts: no constraints between immovable bodies",
        "PASS" if not wasted else "WARN",
        f"{len(wasted)} contact(s) of {int(active.sum())} active; {nefc} constraint rows total",
        "0",
        "the fixed base link is exported as a mocap body, so base<->stand/ground pairs are not auto-filtered" if wasted else "",
    )

    ratio = n / max(int(active.sum()), 1)
    a.add(
        "contact.candidates vs active (detection gap sizing)",
        "PASS" if ratio <= 3.0 else "WARN",
        f"{n} candidates / {int(active.sum())} active = {ratio:.1f}x (rigid_gap={cfg.rigid_gap} m)",
        "<= 3x",
        "every candidate costs narrowphase work and a contact-buffer slot" if ratio > 3.0 else "",
    )
    a.add("contact.buffers: headroom at rest", "PASS", f"nefc {nefc}/{int(d.njmax)} ({int(d.njmax) / max(nefc, 1):.0f}x), contacts {n}/{int(d.naconmax)} ({int(d.naconmax) / max(n, 1):.0f}x)", "peak usage during the task is reported by `bench.py --probe`")

    for name, b in env.object_bodies.items():
        mb = mj.body(name).id
        mine = [i for i, (g1, g2) in enumerate(geom) if active[i] and mb in (body_of(g1), body_of(g2))]
        pen = max((float(-dist[i]) for i in mine), default=0.0)
        a.add(
            f"{name}.rest_contact_manifold: >= 3 support points on a flat surface",
            "PASS" if len(mine) >= 3 else "WARN",
            f"{len(mine)} contact point(s), max penetration {pen * 1e3:.3f} mm",
            ">= 3",
            "a 1-point manifold cannot balance the object: the point orbits the rim and the body wobbles/creeps" if len(mine) < 3 else "",
        )
        floor = task_cfg.settle_lin_speed
        a.add(
            f"{name}.rest_velocity_noise: far below the judge's at-rest threshold",
            "PASS" if rest_lin[name] < 0.1 * floor else "WARN",
            f"lin {rest_lin[name] * 1e3:.3f} mm/s, ang {rest_ang[name]:.4f} rad/s, creep {drift[name] * 1e3:.3f} mm in 2 s",
            f"< {0.1 * floor * 1e3:.1f} mm/s (10% of the {floor} m/s gate)",
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true", help="exit 1 if any check FAILs")
    ap.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE", help="SceneConfig override (repeatable)")
    ap.add_argument("--out", default=os.path.join(RESULTS_DIR, "asset_audit.json"))
    args = ap.parse_args()

    overrides = {}
    defaults = SceneConfig()
    for kv in args.set:
        k, _, v = kv.partition("=")
        cur = getattr(defaults, k)
        overrides[k] = (v.lower() in ("1", "true")) if isinstance(cur, bool) else type(cur)(float(v))

    wp.init()
    wp.config.quiet = True
    env = PickPlaceEnv(SceneConfig(**overrides))
    a = Audit()
    audit_robot(a, env)
    audit_objects(a, env)
    audit_scene(a, env, TaskConfig())
    a.print()
    counts = a.counts()
    print(f"\nASSET AUDIT: {counts['PASS']} PASS, {counts['WARN']} WARN, {counts['FAIL']} FAIL (overrides: {overrides or 'none'})")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"device": str(wp.get_device()), "overrides": overrides, "counts": counts, "checks": a.rows}, f, indent=2, ensure_ascii=False)
    print(f"[audit] results -> {args.out}")
    return 1 if (args.strict and counts["FAIL"]) else 0


if __name__ == "__main__":
    sys.exit(main())
