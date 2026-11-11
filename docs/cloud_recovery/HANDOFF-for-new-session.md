# 交接提示词(粘贴到新 Devin 会话的第一条消息)

> 用法:在新账号的 Devin 会话里,先让它克隆仓库,然后把本导出目录 `files/` 里的文件按 `files/_index.txt` 的映射覆盖/添加到仓库对应路径(这些是上个会话未推送的最新工作成果),再把下面的内容发给它。

---

仓库:https://github.com/brainliubrain/newton-tabletop-pickplace(先 clone)

这是我面试光轮智能岗位的考题项目(IsaacLab 3.0 + Newton,托盘/碗/杯桌面抓放任务)。上一个 Devin 会话完成了大量分析和部分实现,因额度耗尽暂停,以下是完整交接:

## 上个会话已确认的 5 个硬伤(都有编译后模型/源码证据)

1. **接触参数推导是错的**(P4/P18 的核心论据):newton 实际调用 `convert_solref(ke, kd, 1.0, 1.0)`,timeconst = 2/kd = 4e-5 s,不是文档写的 0.04 s。它远小于 2·dt,被 MuJoCo 的 refsafe 钳到 2·dt —— 接触刚度实际由步长决定,ke 基本不起作用,之前的 ke/kd 扫描实际只扫了阻尼比。P18 "substeps=6 突破 ke 稳定极限" 的根因解释需要重做。
2. **机器人基座 link0 与底座圆柱穿透 37.5 mm**,加上 link0–地面 4 个接触:静止时 36 行约束里有 20 行是静态体对静态体的无效接触。
3. **rigid_gap 默认 0.1 m**:20 cm 内的几何对都生成候选接触(静止 44 个候选、仅 7 个有效)。P16 把 njmax/nconmax 调大是治标,这才是根因。
4. 按 README/AGENTS.md 的依赖清单全新安装跑不起来(缺 `pyarrow`)。
5. **碗的质量 0.238 kg = 实心圆柱 + 视觉网格重复计质量**,惯量是实心的不是空心碗。

## 上个会话的 7 项计划(中断时的进度)

1. 修复可复现性:pyarrow 依赖、requirements、CPU/Linux 路径、误导性 CUDA-graph 日志 —— **进行中(被打断)**
2. 物理探针(穿透深度/静置高度误差/步长收敛阶/能量漂移/求解器迭代数/速度钳触发)接入 bench.py —— **已写出 physics_probe.py,见附件**
3. 用探针数据重新推导接触 solref(P4)并重做 P18 substeps=6 根因
4. Infra 性能:rigid_gap、静态-静态基座接触、njmax/nconmax 收紧;配对种子 + held-out bench
5. 资产审计脚本(URDF vs menagerie MJCF vs 编译后模型)+ 碗质量重复计数修复 —— **已写出 asset_audit.py,见附件**
6. RSI 闭环:诊断→提案→配对评测→held-out 复核→接受/回滚日志 —— **已写出 rsi_loop.py,见附件**
7. 文档:PROBLEMS.md 新增条目 + 更正 P4/P18,STATE.md、README、AGENTS.md;最终以 PR 形式提交,不直接推 main

## 已确定的评测协议(必须遵守)

- 调参集:seeds 0–9,每配置 10 回合,配对种子 + 物理探针
- 任何要改默认值的结论,必须再用 `--episodes 10 --seed-base 10`(held-out seeds 10–19)复核后才采纳
- 3 回合冒烟只当冒烟用,不支持结论(swe2.0flash 模型的教训:P18 用 3 eps 冒烟下结论被推翻)
- 模型:SWE-2 Flash Max(Preview)切到 Lite 时额度耗尽;task.py 成功判据不动,求解器保持 MuJoCo-Warp
- ms/帧只有 CPU 数字,GPU 数字需要在 3060 上重跑一次 bench

## 中断时的现场(2026-11-11 19:51)

- 正在跑 bench 调参:日志在 `/home/ubuntu/logs/bench_tune.log`(11060 字节,seeds 0–9)
- 最新结果:`results/bench_20261111_193727.json`、`results/probe_rest_20261111_192429.json`(见附件)
- 因 out_of_quota 暂停,VM 未做最终提交;**附件 files/ 目录里有所有被改文件的最新快照**(映射见 files/_index.txt),请先把它们恢复到仓库里再继续,注意其中有对 `.venv` 里 newton solver_mujoco.py 的本地补丁(如适用)

## 继续的优先事项

1. 先 `git status`/`git diff` 确认仓库基线,恢复附件文件
2. 完成 #1(可复现性),然后跑通 bench + 物理探针
3. 用探针数据重做 P4/P18 根因(这是面试最核心的量化分析点)
4. 按 4/5/6 顺序推进,全程遵守上面的评测协议
5. 最后更新文档并开 PR

附件明细见 `README-导出说明.md`。
