# RSI loop report

device: `cuda:0` | tune seeds 0-9 | held-out seeds 10-19 | final seeds 20-39

| round | proposal | trigger | tune: success / gate | held-out: success / gate | verdict |
|---|---|---|---|---|---|
| 1 | `substeps=7` | no clamp events and penetration 0.789 mm at substeps=8 | 10/10 (champ 10); envstep_ms_per_frame 7.48 -> 6.91 (-8%) | 10/10 (champ 10); envstep_ms_per_frame 7.99 -> 7.23 (-10%) | **ACCEPT** |
| 2 | `substeps=6` | no clamp events and penetration 0.907 mm at substeps=7 | 10/10 (champ 10); envstep_ms_per_frame 6.91 -> 6.19 (-10%); REGRESS carry_slip_mm_max 3.98 -> 5.339 | not run | **ROLLBACK (tune)** |
| 3 | `njmax=512` | constraint rows peak 88 of njmax=1536 | 10/10 (champ 10); no change | 10/10 (champ 10); envstep_ms_per_frame 7.23 -> 6.8 (-6%) | **ACCEPT** |
| 4 | `nconmax=256` | contact candidates peak 38 of nconmax=768 | 10/10 (champ 10); no change | 10/10 (champ 10); no change | **ACCEPT** |

champion overrides vs SceneConfig defaults at loop start: `{"nconmax": 256, "njmax": 512, "substeps": 7}`

## Final test on untouched seeds 20-39

| metric | baseline | champion |
|---|---|---|
| success (Wilson 95%) | 20/20 [0.839, 1.0] | 20/20 [0.839, 1.0] |
| envstep_ms_per_frame | 7.74 | 7.26 |
| agent_ms_per_frame | 0.94 | 1.39 |
| max_object_penetration_mm | 0.8 | 0.92 |
| carry_slip_mm_max | 4.014 | 4.068 |
| final_lin_speed_max_mps | 8e-05 | 8e-05 |
| final_ang_speed_max_radps | 0.0034 | 0.0035 |
| velocity_clamp_events | 0 | 0 |
| solver_niter_mean | 1.3 | 1.31 |
| solver_cap_hit_frac | 0.0 | 0.0 |
| nefc_peak | 88 | 88 |
| contact_candidates_peak | 36 | 36 |
| static_static_contacts_peak | 0 | 0 |
