"""Scientific benchmark harness for physics/solver configuration sweeps.

Runs a grid of SceneConfig overrides IN-PROCESS (one env build per config,
episodes reuse fixed seeds) and reports success rate + timing with spread.
This is the "more scientific" counterpart to ad-hoc CLI sweeps:

  - identical seed set for every config (paired comparison)
  - per-episode wall time -> ms/frame mean +/- std
  - success counted with the SAME EpisodeJudge as run_task.py
  - results appended to results/bench_<UTC>.json + printed as a table

Usage:
  python bench.py --episodes 5 --seeds 0
  python bench.py --episodes 3 --grid solver_iters=8,15,25 ls_iters=12,20,30
  python bench.py --episodes 3 --preset contact      # built-in grids below
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
import time
from dataclasses import fields

import numpy as np
import warp as wp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent import PickPlaceAgent  # noqa: E402
from env import PickPlaceEnv, SceneConfig  # noqa: E402
from run_task import run_episode  # noqa: E402
from task import EpisodeJudge, TaskConfig  # noqa: E402

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

# fields that are safe/meaningful to sweep
SWEEPABLE = {
    f.name
    for f in fields(SceneConfig)
    if f.name
    in {
        "substeps",
        "contact_ke",
        "contact_kd",
        "solver_iterations",
        "ls_iterations",
        "njmax",
        "nconmax",
        "rigid_gap",
        "bowl_density",
        "cup_density",
    }
}

PRESETS = {
    "solver": {
        "solver_iterations": [8, 15, 25],
        "ls_iterations": [12, 20, 30],
    },
    "contact": {
        "contact_ke": [1.0e8, 2.5e8, 5.0e8],
        "contact_kd": [3.0e4, 5.0e4, 7.0e4],
    },
    "cadence": {"substeps": [8, 10, 12]},
    "buffers": {"njmax": [768, 1536], "nconmax": [384, 768]},
}


def parse_kv(kv: str) -> tuple[str, list]:
    name, _, vals = kv.partition("=")
    name = name.strip()
    if name not in SWEEPABLE:
        raise SystemExit(f"unknown/unsweepable field: {name} (allowed: {sorted(SWEEPABLE)})")
    out = []
    for v in vals.split(","):
        v = v.strip()
        out.append(float(v) if "." in v or "e" in v.lower() else int(v))
    return name, out


def grid_from(args) -> list[dict]:
    axes: dict[str, list] = {}
    for kv in args.grid or []:
        name, vals = parse_kv(kv)
        axes[name] = vals
    if args.preset:
        for name, vals in PRESETS[args.preset].items():
            axes.setdefault(name, vals)
    if not axes:
        axes = {"solver_iterations": [15], "ls_iterations": [20]}  # baseline point
    names = list(axes)
    configs = []
    for combo in itertools.product(*(axes[n] for n in names)):
        cfg = {n: v for n, v in zip(names, combo)}
        # keep int-typed fields ints
        for n in ("substeps", "solver_iterations", "ls_iterations", "njmax", "nconmax"):
            if n in cfg:
                cfg[n] = int(cfg[n])
        configs.append(cfg)
    return configs


def eval_config(scene_overrides: dict, episodes: int, seed_base: int, task_cfg: TaskConfig) -> dict:
    scene_cfg = SceneConfig(**scene_overrides)
    env = PickPlaceEnv(scene_cfg)
    agent = PickPlaceAgent(env)
    records = []
    t0 = time.time()
    try:
        for ep in range(episodes):
            judge = EpisodeJudge(task_cfg)
            rec = run_episode(env, agent, judge, task_cfg, seed=seed_base + ep)
            records.append(rec)
    finally:
        del env, agent
        import gc

        gc.collect()
    n_ok = sum(1 for r in records if r["outcome"] == "success")
    ms = np.array([r["ms_per_frame"] for r in records])
    frames = np.array([r["frames"] for r in records], dtype=float)
    agent_ms = float(np.mean([r.get("agent_ms_per_frame", 0.0) for r in records]))
    envstep_ms = float(np.mean([r.get("envstep_ms_per_frame", 0.0) for r in records]))
    # Wilson score interval for the success rate (small-sample honest bounds)
    z = 1.96
    p = n_ok / episodes
    denom = 1 + z * z / episodes
    center = (p + z * z / (2 * episodes)) / denom
    half = z * np.sqrt(p * (1 - p) / episodes + z * z / (4 * episodes * episodes)) / denom
    return {
        "config": scene_overrides,
        "episodes": episodes,
        "seeds": [seed_base + i for i in range(episodes)],
        "successes": n_ok,
        "success_rate": round(n_ok / episodes, 3),
        "success_rate_ci95": [round(float(center - half), 3), round(float(center + half), 3)],
        "ms_per_frame_mean": round(float(ms.mean()), 2),
        "ms_per_frame_std": round(float(ms.std()), 2),
        "frames_mean": round(float(frames.mean()), 1),
        "agent_ms_per_frame": round(agent_ms, 2),
        "envstep_ms_per_frame": round(envstep_ms, 2),
        "wall_time_s": round(time.time() - t0, 1),
        "per_episode": [
            {
                "seed": r["seed"],
                "outcome": r["outcome"],
                "frames": r["frames"],
                "ms_per_frame": r["ms_per_frame"],
                "agent_ms": r.get("agent_ms_per_frame"),
                "envstep_ms": r.get("envstep_ms_per_frame"),
            }
            for r in records
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--episodes", type=int, default=5)
    ap.add_argument("--seed-base", type=int, default=0)
    ap.add_argument("--grid", action="append", help="field=v1,v2,... (repeatable)")
    ap.add_argument("--preset", choices=sorted(PRESETS), default=None)
    args = ap.parse_args()

    wp.init()
    task_cfg = TaskConfig()
    configs = grid_from(args)
    print(f"[bench] {len(configs)} config(s) x {args.episodes} episodes, seeds {args.seed_base}..{args.seed_base + args.episodes - 1}")

    results = [eval_config(c, args.episodes, args.seed_base, task_cfg) for c in configs]

    # persist
    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = os.path.join(RESULTS_DIR, f"bench_{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"episodes": args.episodes, "seed_base": args.seed_base, "results": results}, f, indent=2)

    # table
    keys = sorted({k for r in results for k in r["config"]})
    header = ["config"] + keys + ["succ", "rate_ci95", "ms/f", "agent ms", "envstep ms", "frames", "wall_s"]
    print(" | ".join(header))
    print("-" * 100)
    for r in results:
        row = [json.dumps(r["config"], sort_keys=True)]
        row += [str(r["config"].get(k, "-")) for k in keys]
        row += [
            f"{r['successes']}/{r['episodes']}",
            str(r["success_rate_ci95"]),
            f"{r['ms_per_frame_mean']}±{r['ms_per_frame_std']}",
            str(r["agent_ms_per_frame"]),
            str(r["envstep_ms_per_frame"]),
            str(r["frames_mean"]),
            str(r["wall_time_s"]),
        ]
        print(" | ".join(row))
    print(f"[bench] results -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
