# AGENTS.md — Optimization Charter for Cloud Agents

This repo is the canonical codebase for a robotics-simulation interview demo:
**tabletop pick-place — Franka FR3 puts a bowl AND a cup into a tray**, built on
the kitless Newton engine (newton 1.7.0 + MuJoCo-Warp solver on CUDA),
IsaacLab-3.0-isomorphic task/task-judge/agent layering. No Isaac Sim required.

Read `STATE.md` (block status + gate), `newton_pick_place/docs/PROBLEMS.md`
(18 documented failure modes), and `newton_pick_place/README.md` first.

## Objective

Improve the **simulation Infra / Solver** quality of this demo. In priority
order:

1. **Solver fidelity & stability**: contact behavior, penetration depth, rest
   height error, energy drift, timestep convergence. Quantify, don't guess.
2. **Infra performance**: ms/frame wall time (currently ~10.6 ms: env.step
   ~9.4 ms + agent IK ~1.2 ms + judge ~0.1 ms on RTX 3060 6GB).
3. **Task robustness**: success rate on randomized spawn poses must not regress.

## Hard constraints (do NOT break)

- `task.py` success criteria are FROZEN — they define the task. Improvements
  must come from physics/infra, not by loosening the judge.
- Evaluation protocol: paired seeds. `bench.py` runs identical seed sets for
  every config; claims require **held-out seeds** (e.g. tune on 0-9, verify on
  10-19) — see PROBLEMS.md P18 for why 3-episode smoke is insufficient.
- Assets are vendored and offline-reproducible; do not add network downloads.
- Keep the kitless architecture (no Isaac Sim dependency).

## How to verify (the gate)

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/Scripts/python.exe --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    "newton==1.7.0" "mujoco==3.15.*" "mujoco-warp==3.15.*" \
    pycollada resolve-robotics-uri-py "usd-core<26.9" newton-usd-schemas \
    scipy trimesh fast-simplification imageio imageio-ffmpeg

cd newton_pick_place
../.venv/Scripts/python.exe test_success.py            # unit tests, no sim
../.venv/Scripts/python.exe run_task.py --episodes 3 --no-video --min-success 0.66
../.venv/Scripts/python.exe bench.py --episodes 10 --grid substeps=8,10
```

GPU note: designed for a single ~6GB CUDA GPU; kernels are Warp-cached.

## Known landscape (from completed sweeps — do not redo blindly)

| Knob | Swept | Verdict |
|------|-------|---------|
| solver_iterations / ls_iterations | 8/15/25 × 12/20/30 | 15/20 kept; 8 hits iteration cap |
| contact_ke / contact_kd | 1e8–5e8 / 3e4–7e4 | 2.5e8/5e4 kept; 5e8+3e4 had a timeout |
| substeps | 6/7/8/10/12 | **7 adopted via rsi_loop** (P23: 20/20 on untouched seeds 20-39, envstep -6%); 6 collapses on held-out seeds (P18) |

Open directions worth investigating:

- Quantitative contact metrics: measure actual penetration depth / rest-height
  error across ke/kd instead of binary task success.
- `mu` (friction) and density sweeps; per-material contact params.
- Solver warm-start (`solver.reset` semantics), njmax/nconmax headroom under
  real2sim decomposed collisions (P16).
- Agent-side: IK iteration budget vs control latency; waypoint timing.
- CUDA graph coverage: are agent IK solves inside or outside the graph?

## Definition of done for any change

1. `test_success.py` all green.
2. `run_task.py --episodes 3 --no-video` passes.
3. Paired-seed `bench.py` comparison vs baseline on the SAME seeds, plus a
   held-out seed set — report success rate + Wilson CI + ms/frame breakdown.
4. Update `docs/PROBLEMS.md` (new P-number) and `STATE.md` with evidence.
