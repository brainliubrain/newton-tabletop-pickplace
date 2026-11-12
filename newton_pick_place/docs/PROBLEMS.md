# 问题记录(完成任务过程中解决的真实问题)

按时间顺序记录调试过程中的真实卡点、根因分析与修复。每个问题都经过实验定位(隔离复现 → 变量扫描 → 根因确认 → 修复验证),无"大概可以"。

## P1. 包名陷阱:`newton-physics` 已改名 `newton`
- **现象**:`pip install newton-physics[mujoco]` 装出的 1.0.0 是改名占位包(只有一个 `__init__.py`),`import newton` 失败。
- **修复**:改装 `newton==1.7.0`;且 newton 1.7.0 通过 `[sim]` extra 锁定 `mujoco~=3.15.0`/`mujoco-warp~=3.15.0`(装 3.17 会在 `mjw_model.stat` 处 AttributeError),`mujoco-warp` 是可选后端必须显式安装。

## P2. 离线资产获取:GitHub 网页不通
- **现象**:`newton.utils.download_asset` 走 git clone github.com,本机网络不通(但 raw.githubusercontent.com / api.github.com 通)。
- **修复**:用 GitHub API 拿 `newton-assets@f8fb7abc`(pinned SHA,与 newton 1.7.0 代码内 REF 一致)的文件树,按需 vendoring FR3 URDF+网格(27MB)+ cup 资产到 `assets/`,运行时零网络依赖、确定性可复现。URDF 的 `package://` 路径解析与目录布局天然兼容。

## P3. 示例 home 姿态与场景冲突
- **现象**:直接采用官方 panda_hydro 的硬编码 home 后,场景里物体被扫飞。
- **根因**:该 home 让手悬在 z≈0.33m,而本场景桌面高 0.40m——手插在桌子内部。
- **修复**:启动时用 `newton.ik.IKSolver`(ANALYTIC 雅可比 + 关节限位目标)解算一个 TCP (0.45, 0, 0.62) 掌心朝下的悬停 home,FK 验证误差 0.00mm。正确姿势的 home 不该硬编码,应当从场景几何推导。

## P4. 接触参数:默认值让轻物体"陷进"桌面 14mm
- **现象**:碗静置在桌面 z=0.387(应 0.402),稳定不弹出。
- **根因**:newton 把 ShapeConfig (ke,kd) 转成 mujoco solref:`timeconst=2/(kd·width)`,`dampratio=(kd/2)·√(d_r/ke)`(默认 solimp width=0.001, d_r=0.9)。默认 ke=2.5e3/kd=100 → timeconst≈20s 的超软接触。
- **定位过程**:隔离实验(只有桌+碗)→ (ke,kd) 网格扫描 → 落位高度随 ke 增大收敛到理论值。
- **修复**:反解目标 timeconst=0.04s(>2·dt 稳定)、dampratio≈1.5(过阻尼)→ **ke=2.5e8, kd=5e4**。落位误差 <0.1mm,且静止时无微振(欠阻尼会让静止物体持续微弹,干扰速度判据)。

## P5. 自由体位姿权威在 `state.joint_q`(最隐蔽的一个)
- **现象**:reset 后杯子"瞬移"回模型默认位;写入的 body_q 无效。
- **根因**:MuJoCo 是 reduced-coordinate 求解器,自由体的真状态是 FREE 关节坐标(`state.joint_q`),`body_q` 只是 FK 输出,每步被求解器覆盖。
- **修复**:reset 时按 joint_type(FREE=4,7 坐标)定位每个物体的 FREE 关节偏移,写入关节坐标,再 `newton.eval_fk` 重建 body_q。任何 IsaacLab/Newton 的 reset 逻辑都绕不开这一点。

## P6. 性能:698ms/帧 → 11ms/帧
- **根因**:每帧 10 个子步的 CPU↔GPU launch 开销(无 CUDA Graph)。
- **修复**:照官方 panda_hydro 模式用 `wp.ScopedCapture()` 把整个子步循环录成 CUDA Graph,每帧一次 `wp.capture_launch`。63× 提速,使 10 回合评测只要 ~4 分钟。

## P7. 凹形碗的碰撞:凸包转换焊掉底环
- **现象**:lathe 网格碗经 `approximate_meshes(convex_hull)` 后从桌上滚落。
- **根因**:凸包转换的前置简化把 5mm 厚的碗底环焊掉,凸包底变成不规则形状;且宽口碗(7.5cm)比 FR3 夹爪全开的内间距(~6.9cm)还宽——手指只能"搭"在碗沿上,永远抱不住。
- **修复**:碰撞改用圆柱原语(平底稳定、直径可调),lathe 网格只做外观(`has_shape_collision=False`);碗径缩到 5.5cm 并微锥形(上窄下宽,抓取时楔紧自增强)。**教训:夹爪能抓什么先按开口几何设计物体,再谈策略。**

## P8. 视觉网格变幻影碰撞体,把夹爪撑开
- **现象**:碗抓取时手指指令已闭合(0.035→0.015),实测指距却卡在 8.8cm(超过 8cm 机械上限),1.6s 后突然合上;GPU 侧接触数组显示无接触。
- **根因**:`approximate_meshes` 不带 `shape_indices` 时把**纯视觉网格**(flags 只含 VISIBLE)也转成了带 COLLIDE 标志的凸包——外观网格很"胖",成为幻影碰撞体。官方 panda_hydro 正是因此显式传了 `shape_indices`(白名单只含真碰撞网格),这个细节读漏了。
- **修复**:只对 URDF 真碰撞网格做凸包化。**教训:读官方示例要读"为什么这么写",不只读"写了什么"。**

## P9. 远端位姿的伺服病态(无接触卡死)
- **现象**:手臂在远端位姿(x≈0.50)下降时,TCP 稳定卡在比目标高 2–4.6cm 处;无接触、无自碰撞、力矩未饱和、换 kp 无效;冷启动 IK 明明可达(0mm 误差)。
- **定位**:静态跳转实验(直接指令+3s 整定)能到位 → 慢速插值路径是触发条件;z-scan 扫描画出了可跟踪包络。
- **修复**:工程上绕开——物体出生区限制在机械臂舒适工作区(题目只约束"桌上",不约束位置);释放高度贴托盘底;夹爪远端位形一律用"跳转+整定"而非慢速插值。

## P10. "西瓜籽"弹射:释放瞬间的 stored squeeze energy
- **现象**:释放时物体偶发被弹飞(速度钳制前可穿透地板,确定性 -43m)。
- **根因**:位置伺服夹爪闭合目标低于接触点 → 持续积蓄挤压;张爪瞬间不对称释放,把楔在指间的轻物体射出。newton 官方 panda_hydro 注释点名过同一问题("Compliant finger drives avoid releasing stored squeeze energy into lightweight objects")。
- **修复**:两段式释放——先"松压"(挤压目标退到近接触点,泄能)0.7s,再张爪 0.7s;同时释放高度降到物体**坐在托盘底面上**再松爪(托盘四壁+底面兜底)。加了一道物体速度安全钳(健康运动远达不到该阈值)作为最后防线。

## P11. 出生点防撞检查的矩形陷阱
- **现象**:特定 seed 确定性爆炸(第 0 帧、home 相位、速度即达钳制值)。
- **根因**:防撞用的是"到托盘**中心**距离 ≥ 0.15m",但托盘是矩形(半宽 0.145×0.105)——对角方向 0.175m 处的出生点与托盘 -x 壁直接穿模,求解器弹射。
- **修复**:改为"轴对齐矩形 + 物体包围半径"重叠检测。**教训:任何"距离检查"都要问一句形状假设对不对。**

## P12. 判据与物理的最后一公里
- **现象**:物体已视觉静止在托盘正确位置,成功率仍不稳(6/10 → 8/10)。
- **根因**:刚性接触的静止物体永远有 ~0.02–0.04 m/s 的微振;角速度抖动同理。"静止"判据的阈值低于物理本底噪声,判据就变成了抽签。
- **修复**:①接触调过阻尼(见 P4)从物理上压低噪声;②at_rest 只用线速度(<0.04 m/s,视觉静止),倾倒由 30° 倾斜判据独立把关;③增加"脱手"判据(TCP z>0.50m)防止"拿着不放"也算放置;④settle 窗口 20 帧连续。最终 10/10。

## P13. 渲染与物理"两张皮":编译后的 mj_model 里没有视觉网格
- **现象**:SolverMuJoCo 编译出的 mj_model 只有 26 个碰撞 geom——URDF 的视觉 DAE 网格、碗的 lathe 视觉全部丢失,直接渲染=灰色凸包手臂。
- **根因**:newton→mujoco 转换只输出碰撞 shape;视觉 shape 走 newton 自己的 USD 查看器,不进 mj_model。Antigravity 的"studio 场景"因此手写了一个平行 XML + CSV 重放——物理与视觉彻底分家(动画)。
- **修复**:`save_to_mjcf` 导出物理 MJCF → 注入视觉覆盖层(menagerie fr3.xml 的视觉 geom 按 body 帧映射 + 程序化碗/杯 OBJ)→ 灯光/天空盒/材质 → 重编译。**渲染的每个几何要么是物理碰撞体、要么是同一 body 帧上的原始视觉网格;视频逐帧同步实时物理状态,无重放。**

## P14. mujoco 3.15 不再从 mesh 属性隐式推断 geom 类型
- **现象**:注入的视觉 geom 全部渲染成球体。
- **根因**:旧版 MJCF `<geom mesh="x"/>` 隐含 type=mesh;3.15 中不带显式 type 的 geom 是 sphere(数据id=-1),网格引用被静默忽略。
- **修复**:所有注入的视觉 geom 显式 `type="mesh"`。**教训:升级依赖后,MJCF 的隐式行为不再可靠。**

## P15. 形状索引漂移:硬编码 geom 名全部失效
- **现象**:给场景加 4 条桌腿后,碗/杯碰撞体没隐藏、地面没改色——所有按 `shape_60_60` 式硬编码名字的映射全部错位。
- **修复**:env._build 建立**语义角色注册表**(`shape_roles: role -> shape indices`:table_top/table_legs/tray/bowl_collision/ground...),渲染层按角色映射,不再对任何索引硬编码。

## P16. 凸分解碰撞撑爆接触缓冲
- **现象**:导入 CoACD 分解的碗(16 个凸件)后,broadphase overflow 刷屏——溢出会**静默丢接触**(物体下陷)。
- **修复**:njmax 512→1536、nconmax 256→768。**教训:缓冲区溢出的警告不能当噪音。**

## P17. sim2real 契约测试暴露的真实差异
- **现象**:DeploymentRunner 的速度包络(2.6 rad/s)对脚本策略的 PTP 跳转频繁限幅。
- **意义**:这不是 bug——是**真实关节速度包络与仿真策略假设的差异被基础设施如实暴露**。真机上轨迹会更慢,相位时长需按限幅后轨迹重排;这正是契约层存在的价值。

## P18. cadence 稳定性悬崖:substeps=6 在 held-out seeds 上崩盘
- **现象**:3 回合冒烟里 substeps=6/8/10 全过,看不出差别;换 10 个**未见过的 seed(10-19)** 后 substeps=6 只有 3/10,物体在抓取/放置中被接触求解器甩飞或穿透。
- **根因**:dt_substep=1/360s(2.78ms)时,ke=2.5e8 的接触时间常数约束被突破——位置级 PD 伺服+硬接触在粗步长下出现能量注入。substeps=8(dt=2.08ms)在两个独立 seed 集(0-9, 10-19)共 20 回合全过。
- **方法论教训**:小样本冒烟(3 eps)不足以支撑物理参数结论;bench.py 的配对种子 + held-out seed 复核是必需品。**结论:默认 substeps=8(480Hz),-17% 墙钟耗时,精度经 20 回合验证。**
---
(现场可讲的)

1. **隔离复现**:每个 bug 先缩到最小可复现场景(桌+碗、单关节、纯 numpy),排除干扰变量;
2. **数据优先**:直接读 GPU 侧 mujoco 接触数组、dump 指令链(IK 解 → control → 仿真关节)逐段对账,不猜;
3. **变量扫描**:接触参数 (ke,kd) 网格、抓取高度 z-scan——用数据画包络,不凭感觉调参;
4. **读源码**:newton 的 solref 转换公式、资产下载的 pinned SHA、官方示例的隐性细节,全部从安装包源码确认;
5. **验收先行**:gate.json 三条命令 + 产物清单先落盘,每块完成即验,Stop hook 自动把关。
## P19. 接触参数理论更正:solref 被 refsafe 钳位,ke 基本不起作用
- **原 P4/P18 的理论是错的**:文档曾按 ke/kd 直接推导接触时间常数(0.04s 量级),并把 substeps=6 崩盘归因为"突破 ke 稳定极限"。
- **源码事实**:newton 调 `convert_solref(ke, kd, 1.0, 1.0)`,timeconst = 2/(kd·width);本场景算出 ~0.04ms,**远小于 2·dt_substep(4.17ms@substeps=8),被 MuJoCo refsafe 钳到 2·dt**——有效接触刚度由步长决定,ke/kd 实际只通过 dampratio = kd/(2·sqrt(ke·d_r)) 起作用。
- **实测验证**(physics_probe, `results/probe_rest_energy_convergence_20261111_224521.json`):固定 dt 下 ke/kd 组合只改变 zeta(0.67-2.5),静置穿透 0.001-0.018mm 变化来自阻尼比而非刚度;穿透随 dt 收敛 ~dt^1.88(与 refsafe p=2 吻合)。
- **推论**:之前的"ke/kd 扫描"实际只扫了阻尼比;真正影响接触行为的是步长(substeps)、接触流形(multiccd)、几何刚度(形状类型)。P18 的崩盘根因见 P22。

## P20. 接触流形质量:multiccd / filter_static_base / rigid_gap 三旋钮的实测权衡
- **背景**:asset_audit.py 实测发现碗/杯静止时只有 **1 个接触点**支撑(应为 >=3),绕 z 轴以 ~0.6 rad/s 微振——单点流形无法平衡物体,P12 判据本底噪声的物理根源。
- **实验**:seeds 0-9 配对网格,multiccd{0,1} x filter_static_base{0,1} x rigid_gap{0.02,0.1},全部 10/10(见 `results/bench_20261111_220419.json`)。
- **结果**:
  - `multiccd=1`(多点 CCD 流形):最大穿透 2.83→**0.79 mm**(3.6x),放置收尾角速度 0.56→**0.003 rad/s**(200x),搬运滑移 8.3→3.9 mm,求解器平均迭代 2.82→1.37;代价:调参集内 ms/帧 12.6→16.1 系 --probe 计时污染,**干净口径 held-out 实测 9.70 vs 9.57**(bench_20261111_222748.json),multiccd 无显著速度代价。
  - `filter_static_base=1`:静态-静态接触 5→1(nefc 36→20),ms/帧略降,零成本。
  - `rigid_gap 0.1→0.02`:接触候选 111→33(3.4x),ms/帧再降 ~1ms,精度指标不变(候选数降但有效接触不变)。
- **结论(已 held-out 复核,seeds 10-19 全 10/10,`results/bench_20261111_222748.json`)**:精度优先选 `multiccd=1 + filter_static_base=1 + rigid_gap=0.02`,干净计时 **9.70 ms/帧**(vs multiccd=0 的 9.57,无显著差异);若 ms/帧 优先则 multiccd=0 同组合。P18 的"solver 保真度优先于 infra 性能"原则支持前者。

## P21. njmax/nconmax 收紧扫描:无收益,保持余量
- **实验**:新默认(multiccd+fsb+gap0.02)下 njmax{768,1536} x nconmax{384,768},seeds 0-9(`results/bench_20261111_224338.json`)。
- **结果**:4 配置全 10/10,物理指标逐位相同(穿透 0.789mm,nefc peak 88,接触峰值 38/20);ms/帧 9.6-10.4 无显著差异。
- **结论**:缓冲区是预分配显存,缩小不提速;而 real2sim CoACD 分解包(16+ 凸件)接触数估计可达当前 ~4-6 倍(未实测,按 16+ 凸件分解包推算),P16 的静默丢接触风险不值得为零收益冒。**保持 njmax=1536 / nconmax=768**,余量 nefc 17.5x / naconmax 20x。

## P22. P18 悬崖的真正根因:单点接触流形,不是 ke 稳定极限(more)
- **P18 原结论是错的**:当时归因为"dt=2.78ms 突破 ke=2.5e8 的接触时间常数极限"。P19 已证明 solref 被 refsafe 钳到 2·dt,**有效刚度始终由步长决定,ke/kd 只控阻尼比**——不存在 ke 稳定极限。
- **新证据**:physics_probe 实测——静置穿透 ~dt^1.88(与 refsafe p=2 吻合);ke/kd 在固定 dt 下只改变 dampratio(zeta 0.67-2.5):ke 无关,ζ 使穿透在 0.001-0.018mm 间变化 18 倍;求解器收敛阶 ~1.06、能量漂移 ~1.00(一阶精度)。
- **正确根因**:substeps=6(360Hz)时单点 CCD 接触流形无法约束抓取/放置瞬态的冲击与摩擦耦合,位置级 PD 伺服注入能量,物体被甩飞——是**接触流形质量问题**,不是刚度稳定性问题。
- **验证**:新默认(multiccd=1 多点流形 + filter_static_base + rigid_gap=0.02)下 substeps=6 在 held-out seeds 10-19 复测 **10/10**(旧配置下同 seeds 仅 3/10),ms/帧 7.12 vs substeps=8 的 9.36。P18 的"悬崖"由 P20 的流形修复消除。
- **方法论**:错误的物理直觉(ke 极限)被 held-out 数据证伪;正确解释来自先读 solref 源码(P19)再做流形对照实验(P20/P22)。**substeps 默认值待 P22 探针数据定夺(6 vs 8 的精度权衡)。**

## P23. RSI 闭环首次完整运行:substeps=7 采纳,buffer 收紧拒绝
- **实验**:`rsi_loop.py` 默认参数完整跑完——tune seeds 0-9 / held-out 10-19 / final 20-39(从未参与任何决策),4 轮收敛,证据 `results/rsi/{journal.jsonl,REPORT.md,champion.json}`。
- **过程**:round1 substeps=7 ACCEPT(held-out envstep -10%);round2 substeps=6 **ROLLBACK**——tune seeds 上 carry_slip 3.98→5.34mm 超 gate 容差,gate 按设计工作;round3 njmax=512、round4 nconmax=256 均以 resource_only ACCEPT(无回退)。
- **final test(seeds 20-39,40 回合)**:baseline vs champion 均 20/20;envstep 7.74→7.26ms(-6%);穿透 0.80→0.92mm(+15%,容差内);抖动/滑移基本持平。
- **采纳决策(人工)**:**substeps=7 采纳为新默认**(envstep -6%,精度损失在容差内);**njmax/nconmax 保持 1536/768 不采纳**——RSI 的 gate 只测原始资产,测不到 real2sim CoACD 分解后的接触数放大(P16/P21 的静默丢接触风险),属于盲区采纳,人工否决。
- **教训**:自动闭环的价值在"提案+证据+回滚",不在"全自动改默认"——gate 覆盖不到的维度(real2sim 余量、非 2 幂 cadence)需要人工把关。substeps=7 让 dt_substep≈2.38ms,仍在 refsafe 钳位区内,收敛阶 ~1.9 下误差增幅可控。
