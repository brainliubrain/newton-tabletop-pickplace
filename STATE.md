# STATE — Newton kitless 桌面 pick-place(面试题)

## 任务(面试题原文要点)
- 基于 isaaclab3.0 + newton 物理引擎构建仿真 env:桌面 + 托盘 + 碗 + 杯,机械臂把碗和杯都放入托盘;机器人可用 isaaclab 内任意一个。
- 要求:1) 构建完整 task 和成功标准;2) 可用任意模型/agent 控制机器人完成任务。
- 本机约束:RTX 3060 6GB,已装 Isaac Sim 4.5。**走 kitless 路线**(pip 安装 newton 引擎本体,Newton/MuJoCo-Warp 求解器,无需 Isaac Sim)。

## 环境
- Windows + Git Bash;GPU RTX 3060 6GB(驱动 610.62,CUDA 13.3)。
- uv venv(Python 3.12)+ newton 1.7.0 + warp 1.19 + mujoco/mujoco-warp 3.15。
- 网络:pypi 走清华镜像;GitHub 网页不通但 raw/api 通 → 资产按 pinned SHA vendored 到 `newton_pick_place/assets/`(离线可复现)。

## 验收 gate(自动执行,见 `.zcode/gate.json`;stop hook 单命令限 120s)
1. `check_env.py` — 栈自检(CUDA/URDF/USD/GPU 步进)
2. `test_success.py` — 成功判据单测
3. `run_task.py --episodes 3 --no-video --min-success 0.66` — 冒烟评测(实测 ~100s)
   (10 回合全量评测 + 视频为展示产物,见 results/)

## 块状态
| 块 | 内容 | status | 证据 |
|----|------|--------|------|
| B0 | gate.json + STATE.md | verified | 本文件 + .zcode/gate.json |
| B1 | 安装 newton/warp/mujoco,验证 CUDA | verified | check_env 5 项 PASS |
| B2 | 桌面 env(托盘/碗/杯/FR3) | verified | 冒烟 PASS + 多 seed 稳定 |
| B3 | task + 成功判据 + 单测 | verified | test_success 6 组 PASS |
| B4 | 控制 agent(路标点+解析IK) | verified | 多 seed 抓放通过 |
| B5 | 多回合评测 + 视频 | verified | **10/10 = 100%**(results.json + demo_ep0.mp4,studio 实时渲染) |
| B6 | README + PROBLEMS.md | verified | 文档落盘,最终 gate 见下 |
| B7 | 场景去动画化:物理=渲染(真托盘/桌腿/FR3视觉/地面/材质) | verified | studio 帧检查 + 10/10 评测 |
| B8 | real2sim 管线(CLI+资产包+env接入+CoACD) | verified | tests/test_real2sim_e2e.py ALL PASS |
| B9 | sim2real 部署契约层(后端+Runner+安全包络) | verified | 同上第 4/5 步 |

## 最终 gate 结果
- check_env.py:PASS
- test_success.py:ALL PASS
- run_task.py --episodes 10 --min-success 0.66:SUCCESS RATE 10/10 = 100% → exit 0

## 关键问题记录
全部 12 个问题及定位/修复过程见 `newton_pick_place/docs/PROBLEMS.md`(接触参数反解、自由体状态权威、视觉网格幻影碰撞体、西瓜籽弹射、矩形防撞陷阱等)。

## 卡点记录
(无 — 全部解决)

## 2026-11-12 迭代:科学化评测 + solver 寻优
- 新增 `bench.py`(同进程配对种子网格评测,Wilson CI,ms/帧分解)+ `run_task.py` 物理参数 CLI 覆盖 + results.json 记录 physics 配置与 agent/envstep 分项耗时。
- 扫描结论(solver iters / cadence / contact ke·kd,见 results/bench_*.json):默认改 **substeps 10→8**(480Hz,held-out seeds 20/20 验证,-17% 墙钟);solver iters 15/20 保持;contact 2.5e8/5e4 保持(ke=5e8+kd=3e4 有超时失败)。
- 新发现 P18:substeps=6 在 held-out seeds 3/10 崩——cadence 稳定性悬崖,已写入 PROBLEMS.md。
## 2026-11-12 solver sweep 收官(local GPU, seeds 0-9 调参 + 10-19 held-out)
- 新默认: multiccd=1, filter_static_base=1, rigid_gap=0.02, substeps=8(维持)
- 关键证据: bench_20261111_220419/222748/224338/225146/230218.json, probe_rest_energy_convergence_20261111_224521.json, asset_audit.json(14 PASS/10 WARN/0 FAIL)
- P18 悬崖根因更正(P22): 单点接触流形而非 ke 极限; multiccd 后 substeps=6 也 10/10, 但精度权衡仍选 8
- njmax/nconmax 保持 1536/768(P21: 收紧无收益, 保留分解资产余量)
- asset_audit 修复: menagerie stl 补齐 + meshdir patch + link0/base 穿透修复(机器人抬升 37.5mm + IK 同步) + 碗质量 0.238->0.178kg

## 2026-10-13 RSI 闭环首跑(P23)
- `rsi_loop.py` 完整运行:tune 0-9 / held-out 10-19 / final 20-39,4 轮收敛
- 采纳:`substeps 8→7`(env.py 默认已改);拒绝:`njmax 512 / nconmax 256`(real2sim 余量盲区,人工否决)
- final test seeds 20-39: 20/20 vs 20/20, envstep 7.74→7.26ms, 穿透 0.80→0.92mm
- 证据: results/rsi/{journal.jsonl,REPORT.md,champion.json}

## 2026-10-13 RSI 第二轮:保真度旋钮(P24)
- rsi_loop 扩展: +contact_kd 阻尼比 / rigid_gap / 三个机器人保真度 preset, --tried 参数
- 8 轮收敛: ACCEPT contact_kd=3.2e4(穿透-33%)、frictionloss=menagerie、effort=hardware、rigid_gap=0.01;ROLLBACK armature=menagerie(滑移回退)、solver_iterations=12、nconmax=128
- final seeds 20-39: 20/20 vs 20/20, 穿透 0.92→0.602mm, envstep 7.16→6.76ms
- 采纳进 env.py 默认: CONTACT_KD=3.2e4, rigid_gap=0.01, frictionloss/effort=menagerie/hardware; armature/armature 保持 sim; buffers 不变
- asset_audit 修复 effort_limit 测量(jnt_actfrcrange): 22 PASS / 2 WARN / 0 FAIL

## 2026-10-13 REVIEW-e944ea7 修复
- rsi_loop 原生 --veto 支持;journal/REPORT/champion.json 三处对齐(proposed_champion vs adopted)
- 两轮历史 veto 回填:run1 njmax=512+nconmax=256, run2 njmax=512 → VETOED
- held-out bench 补足 10 eps(REVIEW #2): bench_20261113_070155.json 10/10, pen 0.605mm, envstep 6.66ms
