# RSI loop report

device: `cuda:0` | tune seeds 0-4 | held-out seeds 10-14 | final seeds skipped

| round | proposal | trigger | tune: success / gate | held-out: success / gate | verdict |
|---|---|---|---|---|---|
| 1 | `solver_iterations=14` | Newton solver used at most 7 of 15 iterations (mean 1.29) | 5/5 (champ 5); no change | not run | **ROLLBACK (tune)** |
| 2 | `substeps=7` | no clamp events and penetration 0.751 mm at substeps=8 | 5/5 (champ 5); envstep_ms_per_frame 7.48 -> 6.72 (-10%) | 5/5 (champ 5); envstep_ms_per_frame 7.72 -> 6.87 (-11%) | **ACCEPT** |
| 3 | `solver_iterations=12` | Newton solver used at most 6 of 15 iterations (mean 1.34) | 5/5 (champ 5); no change | not run | **ROLLBACK (tune)** |

champion overrides vs SceneConfig defaults at loop start: `{"substeps": 7}`

