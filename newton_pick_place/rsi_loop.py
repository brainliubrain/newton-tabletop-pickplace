"""Closed-loop self-improvement of the simulation config (RSI for the sim infra).

    diagnose -> propose -> paired evaluation -> held-out verification -> accept / roll back

One round:
  1. DIAGNOSE  the champion config from its measured physics metrics
               (physics_probe.SolverProbe via bench.eval_config(probe=True)).
  2. PROPOSE   one SceneConfig change. Each proposal is tied to the metric that
               triggered it, so the journal records WHY a change was tried.
  3. EVALUATE  the candidate on the TUNE seeds, paired with the champion.
  4. GATE      task success must not drop, no physics metric may regress beyond
               tolerance, and at least one metric must improve beyond noise.
  5. VERIFY    repeat the gate on HELD-OUT seeds the proposer never saw.
  6. ACCEPT (candidate becomes champion) or ROLL BACK. Either way the round is
     appended to results/rsi/journal.jsonl with all numbers.

After the loop, the original baseline and the final champion are compared on a
FINAL seed set touched by nothing else (held-out seeds are reused every round,
so they are a validation set, not a test set).

The loop only searches SceneConfig (physics/infra). task.py is never touched:
the success criteria are the fixed objective, not a tunable.

Usage:
  python rsi_loop.py                       # tune 0-9, held-out 10-19, final 20-39
  python rsi_loop.py --rounds 3 --episodes 5 --final-episodes 0   # quick look
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field

import numpy as np
import warp as wp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import eval_config, wilson_ci95  # noqa: E402
from env import SceneConfig  # noqa: E402
from task import TaskConfig  # noqa: E402

RSI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "rsi")

GAP_LADDER = (0.1, 0.03, 0.01)
SUBSTEP_FLOOR = 6
BUFFER_SAFETY = 4.0  # keep >= 4x the peak usage seen on tune seeds

# metric -> (relative tolerance, absolute tolerance); lower is better for all
NO_REGRESS = {
    "max_object_penetration_mm": (0.25, 0.05),
    "carry_slip_mm_max": (0.25, 0.3),
    "final_lin_speed_max_mps": (0.25, 0.002),
    "final_ang_speed_max_radps": (0.25, 0.02),
    "envstep_ms_per_frame": (0.03, 0.0),
}
IMPROVE_FRACTION = {
    "max_object_penetration_mm": 0.20,
    "carry_slip_mm_max": 0.20,
    "final_lin_speed_max_mps": 0.20,
    "final_ang_speed_max_radps": 0.20,
    "envstep_ms_per_frame": 0.03,
}


@dataclass
class Proposal:
    name: str
    overrides: dict
    trigger: str  # the measured symptom that motivated it
    hypothesis: str  # what should improve if the diagnosis is right
    resource_only: bool = False  # buffer right-sizing: accepted on "no regression" alone
    extra: dict = field(default_factory=dict)


def _metrics(result: dict) -> dict:
    """Flatten a bench.eval_config result into the scalar metrics the gate uses."""
    p = result["physics"]
    return {
        "successes": result["successes"],
        "episodes": result["episodes"],
        "success_ci95": result["success_rate_ci95"],
        "envstep_ms_per_frame": result["envstep_ms_per_frame"],
        "agent_ms_per_frame": result["agent_ms_per_frame"],
        "max_object_penetration_mm": p["max_object_penetration_mm"],
        "carry_slip_mm_max": p["carry_slip_mm_max"] or 0.0,
        "final_lin_speed_max_mps": p["final_lin_speed_max_mps"],
        "final_ang_speed_max_radps": p["final_ang_speed_max_radps"],
        "velocity_clamp_events": p["velocity_clamp_events"],
        "solver_cap_hit_frac": p["solver_cap_hit_frac"],
        "solver_niter_mean": p["solver_niter_mean"],
        "solver_niter_max": p["solver_niter_max"],
        "nefc_peak": p["nefc_peak"],
        "contact_candidates_peak": p["contact_candidates_peak"],
        "contacts_active_peak": p["contacts_active_peak"],
        "static_static_contacts_peak": p["static_static_contacts_peak"],
    }


def _pow2_at_least(x: float) -> int:
    return int(2 ** int(np.ceil(np.log2(max(x, 16)))))


def diagnose(cfg: SceneConfig, m: dict, tried: set[str]) -> list[Proposal]:
    """Map measured symptoms of the champion to candidate changes, most fundamental first."""
    out: list[Proposal] = []

    def add(p: Proposal):
        if p.name not in tried:
            out.append(p)

    # 1. contact-generation fidelity
    if not cfg.multiccd and (m["final_ang_speed_max_radps"] > 0.1 or m["final_lin_speed_max_mps"] > 0.004):
        add(
            Proposal(
                "multiccd=on",
                {"multiccd": True},
                f"objects 'at rest' in the tray still move: lin {m['final_lin_speed_max_mps']} m/s, ang {m['final_ang_speed_max_radps']} rad/s",
                "flat convex-vs-box contacts get 1 CCD point per pair, which cannot balance a body; a multi-point manifold removes the wobble",
            )
        )
    # 2. wasted constraints
    if not cfg.filter_static_base and m["static_static_contacts_peak"] > 0:
        add(
            Proposal(
                "filter_static_base=on",
                {"filter_static_base": True},
                f"{m['static_static_contacts_peak']} active contacts between immovable bodies",
                "fewer constraint rows per substep at identical dynamics",
            )
        )
    # 3. over-wide contact detection
    ratio = m["contact_candidates_peak"] / max(m["contacts_active_peak"], 1)
    lower_gaps = [g for g in GAP_LADDER if g < cfg.rigid_gap - 1e-9]
    if ratio > 3.0 and lower_gaps:
        g = lower_gaps[0]
        add(
            Proposal(
                f"rigid_gap={g}",
                {"rigid_gap": g},
                f"{m['contact_candidates_peak']} contact candidates for {m['contacts_active_peak']} active ({ratio:.1f}x) at rigid_gap={cfg.rigid_gap}",
                "narrowphase processes fewer far-apart pairs; dynamics unchanged because those pairs never produced a constraint",
            )
        )
    # 3b. contact damping ratio: P19 showed ke/kd only set zeta; current
    # zeta~1.58 is over-critical — try near-critical damping
    if cfg.contact_kd == 5.0e4:
        add(
            Proposal(
                "contact_kd=3.2e4",
                {"contact_kd": 3.2e4},
                f"damping ratio zeta~1.58 (over-critical) at ke={cfg.contact_ke}, kd={cfg.contact_kd}",
                "near-critical damping (zeta~1.0) may cut contact ringing -> less penetration/slip",
            )
        )
    # 3c. robot fidelity presets — the asset_audit WARN items. These are
    # sim2real-fidelity changes, not speed changes: accept on no-regression.
    if cfg.arm_inertia_model != "menagerie":
        add(
            Proposal(
                "arm_inertia_model=menagerie",
                {"arm_inertia_model": "menagerie"},
                "audit WARN robot.armature: sim 0.1 vs Menagerie [0.195x4, 0.074x3]",
                "rotor inertia matching the reference FR3; adopt if dynamics don't regress",
                resource_only=True,
            )
        )
    if cfg.arm_frictionloss_model != "menagerie":
        add(
            Proposal(
                "arm_frictionloss_model=menagerie",
                {"arm_frictionloss_model": "menagerie"},
                "audit WARN robot.frictionloss: joint dry friction not modeled (Menagerie 0.25-1.14)",
                "real FR3 joints have dry friction; adopt if tracking/grasp don't regress",
                resource_only=True,
            )
        )
    if cfg.arm_effort_model != "hardware":
        add(
            Proposal(
                "arm_effort_model=hardware",
                {"arm_effort_model": "hardware"},
                "audit WARN robot.effort_limit: sim allows up to 7.5x the hardware torque (wrist joints)",
                "clamp to the real FR3 torque envelope for sim2real honesty; adopt if the task still passes",
                resource_only=True,
            )
        )
    # 3d. narrower contact detection gap: fewer narrowphase candidates
    if m["contact_candidates_peak"] > 30 and cfg.rigid_gap > 0.011:
        g = cfg.rigid_gap / 2
        add(
            Proposal(
                f"rigid_gap={g}",
                {"rigid_gap": g},
                f"{m['contact_candidates_peak']} contact candidates at rigid_gap={cfg.rigid_gap}",
                "halving the detection gap shrinks the narrowphase set; active contacts unchanged",
            )
        )
    # 4. solver work budget
    if m["solver_cap_hit_frac"] == 0.0 and m["solver_niter_max"] * 2 < cfg.solver_iterations:
        it = max(2 * m["solver_niter_max"], 4)
        add(
            Proposal(
                f"solver_iterations={it}",
                {"solver_iterations": it},
                f"Newton solver used at most {m['solver_niter_max']} of {cfg.solver_iterations} iterations (mean {m['solver_niter_mean']})",
                "the iteration cap is a fixed-size loop on the GPU graph; a tighter cap with 2x margin costs less",
            )
        )
    # 5. cadence (known cliff: P18) — the gate, not the proposer, decides
    if cfg.substeps > SUBSTEP_FLOOR and m["velocity_clamp_events"] == 0:
        s = cfg.substeps - 1
        add(
            Proposal(
                f"substeps={s}",
                {"substeps": s},
                f"no clamp events and penetration {m['max_object_penetration_mm']} mm at substeps={cfg.substeps}",
                "one fewer solver step per frame if contact quality holds",
            )
        )
    # 6. buffer right-sizing (memory; matters for many parallel worlds)
    njmax = _pow2_at_least(BUFFER_SAFETY * m["nefc_peak"])
    if njmax < cfg.njmax:
        add(Proposal(f"njmax={njmax}", {"njmax": njmax}, f"constraint rows peak {m['nefc_peak']} of njmax={cfg.njmax}", f"{BUFFER_SAFETY:.0f}x headroom is enough", resource_only=True))
    nconmax = _pow2_at_least(BUFFER_SAFETY * m["contact_candidates_peak"])
    if nconmax < cfg.nconmax:
        add(Proposal(f"nconmax={nconmax}", {"nconmax": nconmax}, f"contact candidates peak {m['contact_candidates_peak']} of nconmax={cfg.nconmax}", f"{BUFFER_SAFETY:.0f}x headroom is enough", resource_only=True))
    return out


def gate(champ: dict, cand: dict, resource_only: bool = False) -> tuple[bool, list[str], list[str]]:
    """Return (passed, regressions, improvements) for candidate vs champion on the SAME seeds."""
    regress, improve = [], []
    if cand["successes"] < champ["successes"]:
        regress.append(f"success {champ['successes']} -> {cand['successes']}")
    elif cand["successes"] > champ["successes"]:
        improve.append(f"success {champ['successes']} -> {cand['successes']}")
    if cand["velocity_clamp_events"] > champ["velocity_clamp_events"]:
        regress.append(f"velocity clamp events {champ['velocity_clamp_events']} -> {cand['velocity_clamp_events']}")
    if cand["solver_cap_hit_frac"] > champ["solver_cap_hit_frac"] + 0.01:
        regress.append(f"solver cap hit {champ['solver_cap_hit_frac']:.2%} -> {cand['solver_cap_hit_frac']:.2%}")
    for key, (rel, absolute) in NO_REGRESS.items():
        if cand[key] > champ[key] * (1 + rel) + absolute:
            regress.append(f"{key} {champ[key]} -> {cand[key]}")
    for key, frac in IMPROVE_FRACTION.items():
        if champ[key] > 0 and cand[key] < champ[key] * (1 - frac):
            improve.append(f"{key} {champ[key]} -> {cand[key]} ({(cand[key] / champ[key] - 1):+.0%})")
    passed = not regress and (bool(improve) or resource_only)
    return passed, regress, improve


class Evaluator:
    def __init__(self, episodes: int, task_cfg: TaskConfig):
        self.episodes = episodes
        self.task_cfg = task_cfg
        self.cache: dict[tuple, dict] = {}

    def __call__(self, overrides: dict, seed_base: int, episodes: int | None = None) -> dict:
        n = episodes or self.episodes
        key = (json.dumps(overrides, sort_keys=True), seed_base, n)
        if key not in self.cache:
            t0 = time.time()
            self.cache[key] = eval_config(dict(overrides), n, seed_base, self.task_cfg, probe=True)
            r = self.cache[key]
            print(f"    eval {key[0]} seeds {seed_base}..{seed_base + n - 1}: {r['successes']}/{n}, envstep {r['envstep_ms_per_frame']} ms ({time.time() - t0:.0f}s)", flush=True)
        return self.cache[key]


def write_report(path: str, meta: dict, rounds: list[dict], final: dict | None):
    lines = ["# RSI loop report", "", f"device: `{meta['device']}` | tune seeds {meta['tune']} | held-out seeds {meta['holdout']} | final seeds {meta['final']}", ""]
    lines += ["| round | proposal | trigger | tune: success / gate | held-out: success / gate | verdict |", "|---|---|---|---|---|---|"]
    for r in rounds:
        t, h = r["tune"], r.get("holdout")
        tune_s = f"{t['candidate']['successes']}/{t['candidate']['episodes']} (champ {t['champion']['successes']}); " + ("; ".join(t["improvements"] + [f"REGRESS {x}" for x in t["regressions"]]) or "no change")
        hold_s = "not run" if h is None else f"{h['candidate']['successes']}/{h['candidate']['episodes']} (champ {h['champion']['successes']}); " + ("; ".join(h["improvements"] + [f"REGRESS {x}" for x in h["regressions"]]) or "no change")
        lines.append(f"| {r['round']} | `{r['proposal']['name']}` | {r['proposal']['trigger']} | {tune_s} | {hold_s} | **{r['verdict']}** |")
    lines += ["", f"champion overrides vs SceneConfig defaults at loop start: `{json.dumps(meta['champion'], sort_keys=True)}`", ""]
    if final:
        b, c = final["baseline"], final["champion"]
        lines += [f"## Final test on untouched seeds {meta['final']}", "", "| metric | baseline | champion |", "|---|---|---|"]
        lines.append(f"| success (Wilson 95%) | {b['successes']}/{b['episodes']} {b['success_ci95']} | {c['successes']}/{c['episodes']} {c['success_ci95']} |")
        for key in ("envstep_ms_per_frame", "agent_ms_per_frame", "max_object_penetration_mm", "carry_slip_mm_max", "final_lin_speed_max_mps", "final_ang_speed_max_radps", "velocity_clamp_events", "solver_niter_mean", "solver_cap_hit_frac", "nefc_peak", "contact_candidates_peak", "static_static_contacts_peak"):
            lines.append(f"| {key} | {b[key]} | {c[key]} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--tune-base", type=int, default=0)
    ap.add_argument("--holdout-base", type=int, default=10)
    ap.add_argument("--final-base", type=int, default=20)
    ap.add_argument("--final-episodes", type=int, default=20, help="0 skips the final test")
    ap.add_argument("--start", default="{}", help="JSON SceneConfig overrides to start from (default: SceneConfig defaults)")
    ap.add_argument("--tried", default="", help="comma-separated proposal names already explored (pre-marked as tried)")
    args = ap.parse_args()

    wp.init()
    wp.config.quiet = True
    os.makedirs(RSI_DIR, exist_ok=True)
    journal_path = os.path.join(RSI_DIR, "journal.jsonl")
    open(journal_path, "w").close()
    evaluate = Evaluator(args.episodes, TaskConfig())
    baseline = json.loads(args.start)
    champion = dict(baseline)
    tried: set[str] = {t for t in args.tried.split(",") if t}
    rounds: list[dict] = []
    meta = {
        "device": str(wp.get_device()),
        "tune": f"{args.tune_base}-{args.tune_base + args.episodes - 1}",
        "holdout": f"{args.holdout_base}-{args.holdout_base + args.episodes - 1}",
        "final": f"{args.final_base}-{args.final_base + args.final_episodes - 1}" if args.final_episodes else "skipped",
    }

    for rnd in range(1, args.rounds + 1):
        champ_tune = _metrics(evaluate(champion, args.tune_base))
        proposals = diagnose(SceneConfig(**champion), champ_tune, tried)
        if not proposals:
            print(f"[rsi] round {rnd}: no untried proposal fires -> converged")
            break
        prop = proposals[0]
        tried.add(prop.name)
        candidate = {**champion, **prop.overrides}
        print(f"[rsi] round {rnd}: propose {prop.name}  <- {prop.trigger}", flush=True)

        cand_tune = _metrics(evaluate(candidate, args.tune_base))
        ok, regress, improve = gate(champ_tune, cand_tune, prop.resource_only)
        entry = {
            "round": rnd,
            "proposal": asdict(prop),
            "champion_before": dict(champion),
            "tune": {"champion": champ_tune, "candidate": cand_tune, "regressions": regress, "improvements": improve, "passed": ok},
        }
        if ok:
            champ_hold = _metrics(evaluate(champion, args.holdout_base))
            cand_hold = _metrics(evaluate(candidate, args.holdout_base))
            # held-out only has to confirm "no regression": the improvement was established on tune seeds
            ok_h, regress_h, improve_h = gate(champ_hold, cand_hold, resource_only=True)
            entry["holdout"] = {"champion": champ_hold, "candidate": cand_hold, "regressions": regress_h, "improvements": improve_h, "passed": ok_h}
            ok = ok_h
        entry["verdict"] = "ACCEPT" if ok else ("ROLLBACK (held-out)" if "holdout" in entry else "ROLLBACK (tune)")
        if ok:
            champion = candidate
        entry["champion_after"] = dict(champion)
        rounds.append(entry)
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"[rsi] round {rnd}: {entry['verdict']}  improvements={improve}  regressions={regress + entry.get('holdout', {}).get('regressions', [])}", flush=True)

    meta["champion"] = champion
    final = None
    if args.final_episodes and champion != baseline:
        print(f"[rsi] final test on untouched seeds {meta['final']}", flush=True)
        final = {
            "baseline": _metrics(evaluate(baseline, args.final_base, args.final_episodes)),
            "champion": _metrics(evaluate(champion, args.final_base, args.final_episodes)),
        }
        for k in ("baseline", "champion"):
            final[k]["success_ci95"] = list(wilson_ci95(final[k]["successes"], final[k]["episodes"]))
    with open(os.path.join(RSI_DIR, "champion.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "baseline": baseline, "champion": champion, "final_test": final}, f, indent=2)
    write_report(os.path.join(RSI_DIR, "REPORT.md"), meta, rounds, final)
    accepted = [r["proposal"]["name"] for r in rounds if r["verdict"] == "ACCEPT"]
    print(f"[rsi] {len(rounds)} round(s), accepted: {accepted or 'none'}")
    print(f"[rsi] champion overrides: {json.dumps(champion, sort_keys=True)}")
    print(f"[rsi] journal -> {journal_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
