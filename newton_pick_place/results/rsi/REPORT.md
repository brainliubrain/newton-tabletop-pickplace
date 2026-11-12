# RSI loop report

device: `cuda:0` | tune seeds 0-9 | held-out seeds 10-19 | final seeds 20-39

| round | proposal | trigger | tune: success / gate | held-out: success / gate | verdict |
|---|---|---|---|---|---|
| 1 | `contact_kd=3.2e4` | damping ratio zeta~1.58 (over-critical) at ke=250000000.0, kd=50000.0 | 10/10 (champ 10); max_object_penetration_mm 0.907 -> 0.624 (-31%) | 10/10 (champ 10); max_object_penetration_mm 0.907 -> 0.611 (-33%) | **ACCEPT** |
| 2 | `arm_inertia_model=menagerie` | audit WARN robot.armature: sim 0.1 vs Menagerie [0.195x4, 0.074x3] | 10/10 (champ 10); no change | 10/10 (champ 10); REGRESS carry_slip_mm_max 4.284 -> 5.855 | **ROLLBACK (held-out)** |
| 3 | `arm_frictionloss_model=menagerie` | audit WARN robot.frictionloss: joint dry friction not modeled (Menagerie 0.25-1.14) | 10/10 (champ 10); no change | 10/10 (champ 10); no change | **ACCEPT** |
| 4 | `arm_effort_model=hardware` | audit WARN robot.effort_limit: sim allows up to 7.5x the hardware torque (wrist joints) | 10/10 (champ 10); no change | 10/10 (champ 10); no change | **ACCEPT** |
| 5 | `rigid_gap=0.01` | 38 contact candidates at rigid_gap=0.02 | 10/10 (champ 10); envstep_ms_per_frame 7.17 -> 6.85 (-4%) | 10/10 (champ 10); envstep_ms_per_frame 7.23 -> 6.79 (-6%) | **ACCEPT** |
| 6 | `solver_iterations=12` | Newton solver used at most 6 of 15 iterations (mean 1.29) | 10/10 (champ 10); no change | not run | **ROLLBACK (tune)** |
| 7 | `njmax=512` | constraint rows peak 88 of njmax=1536 | 10/10 (champ 10); no change | 10/10 (champ 10); no change | **ACCEPT** |
| 8 | `nconmax=128` | contact candidates peak 29 of nconmax=768 | 10/10 (champ 10); REGRESS envstep_ms_per_frame 6.88 -> 7.15 | not run | **ROLLBACK (tune)** |

champion overrides vs SceneConfig defaults at loop start: `{"arm_effort_model": "hardware", "arm_frictionloss_model": "menagerie", "contact_kd": 32000.0, "njmax": 512, "rigid_gap": 0.01}`

## Final test on untouched seeds 20-39

| metric | baseline | champion |
|---|---|---|
| success (Wilson 95%) | 20/20 [0.839, 1.0] | 20/20 [0.839, 1.0] |
| envstep_ms_per_frame | 7.16 | 6.76 |
| agent_ms_per_frame | 1.43 | 1.42 |
| max_object_penetration_mm | 0.92 | 0.602 |
| carry_slip_mm_max | 4.068 | 4.184 |
| final_lin_speed_max_mps | 8e-05 | 8e-05 |
| final_ang_speed_max_radps | 0.0033 | 0.0035 |
| velocity_clamp_events | 0 | 0 |
| solver_niter_mean | 1.32 | 1.28 |
| solver_cap_hit_frac | 0.0 | 0.0 |
| nefc_peak | 88 | 88 |
| contact_candidates_peak | 36 | 29 |
| static_static_contacts_peak | 0 | 0 |
