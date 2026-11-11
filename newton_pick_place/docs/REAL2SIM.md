# REAL2SIM / SIM2REAL 管线指南

本项目把「真世界 → 仿真 → 真世界」两个方向都做成了**留在仓库里的基础设施**。本文说明怎么用、边界在哪、上真机还缺什么。

---

## 1. real2sim:真实物体 → 仿真资产包

### 1.1 采集(不需要扫描仪)

| 方法 | 成本 | 适用 |
|------|------|------|
| 手机摄影测量(Polycam / Luma AI / Qlone) | 免费~低价,10 分钟 | 碗/杯/托盘这类中刚性物体;**透明杯需喷显像粉或哑光喷雾** |
| 卡尺 + 厨房秤 | 5 分钟 | 最小可行:关键尺寸 + 质量,程序化网格按测量参数生成 |
| CAD(制造商图纸) | 有图纸时 | 参数最准 |

**拍摄要点**:360° 覆盖、均匀光照、画面里放一把尺子或 ArUco 标定板(定比例)、透明物体喷哑光剂。

### 1.2 一条命令进仿真

```bash
.venv/Scripts/python.exe real2sim.py import-object \
    --name my_bowl --mesh scan_bowl.obj \
    --mass 0.25 --category bowl          # 质量=称的,密度由网格体积反推

.venv/Scripts/python.exe real2sim.py import-object \
    --name glass_cup --mesh scan_cup.obj --mass 0.30 --category cup --transparent

.venv/Scripts/python.exe real2sim.py preview --name my_bowl   # 生成 preview.png
.venv/Scripts/python.exe real2sim.py list
```

产出资产包 `assets/real2sim/<name>/`:

```
object.json       清单:质量/密度/摩擦/碰撞方案/包围盒/出生间隙/rgba(透明杯 alpha<1)
visual.obj        减面后的渲染网格(≤2 万面)
collision_###.obj CoACD 凸分解件(每个都是凸体,仿真直接用)
preview.png       独立渲染预览
```

**碰撞策略**:默认 `auto` = CoACD 凸分解(凹形物体如碗/托盘必需;凸分解件在 mujoco 中按凸包精确碰撞)。`--collision hull` 单凸包(快,凹形失真)。密度 = 质量/网格体积 → **仿真的惯性 = 真实物体的惯性**。

### 1.3 接入环境(一行)

```python
env = PickPlaceEnv(object_assets={"bowl": "assets/real2sim/my_bowl",
                                  "cup":  "assets/real2sim/glass_cup"})
```

- 物体出生点取原点在**底部中心**(导入时自动归一),出生高度按清单 `spawn_clearance_m`;
- 渲染层(studio.py)读取清单材质——**透明杯自动半透明**;
- 不传 `object_assets` 时保持程序化物体,全部既有回归不受影响。

### 1.4 摩擦标定(把 mu 从"拍的"变成"测的")

斜面法:物体放在可倾斜平面上,记录开始滑动的临界角 θ,mu = tan(θ)。手指-物体摩擦用夹持滑移临界力标定:夹住物体往上提,记录打滑时的加速度 a,mu ≥ (g+a)/(N/m)。

### 1.5 诚实的边界(当前)

1. **抓取策略是为合成碗设计的**(外径 5.5cm < 夹爪 8cm 开口)。真实汤碗 12–16cm,**rim-pinch(指尖沿碗沿内外壁挤压)策略待实现**——这是真实几何下的第一优先级,不是资产问题;
2. agent 读的是真值位姿;真实位姿感知(相机+估计器)是独立模块,接口在 sim2real 契约里已预留;
3. 视觉网格保真度只影响观感/未来感知,不影响当前物理。

端到端测试(合成扫描→资产包→环境加载→落桌稳定):
`tests/test_real2sim_e2e.py`

---

## 2. sim2real:部署契约(诚实版)

`sim2real.py` 定义的是**契约与适配器**,不是假装能跑真机的框架:

```
RobotBackend(ABC)         部署接口:60Hz 关节目标流 (9,) + 状态回读
├── NewtonSimBackend      真实 Newton 仿真作为后端(CI 全程验证)
├── MockArmBackend        运动学重放后端(离线测试 runner 机制)
└── FrankaRealBackend     真机适配器——刻意留桩,注明接线清单,无真机时拒绝运行
DeploymentRunner           限速 + 安全包络(力矩/速度/TCP 工作空间)+ 60Hz 节拍
```

**契约(已冻结)**:控制帧 60Hz、`(9,)` float32 = 7 关节位置目标(rad)+ 2 手指目标(m);状态回读 `joint_q/joint_qd/tcp_pose`。

**测试**:`tests/test_real2sim_e2e.py` 第 4/5 步通过 NewtonSimBackend 和 MockArmBackend 驱动 DeploymentRunner。

**上真机前必须补的三件事**(契约里已写明接线位置):
1. 60Hz→1kHz 中继:libfranka 反射环要求 1kHz,需要插值中继(franka_ros2 JointGroup 或 deoxfr3);
2. 感知模块:替换真值位姿读取(相机 + 物体位姿估计);
3. 系统辨识:真实接触参数(摩擦/刚度)按 1.4 的方法标定。

**已知的真实差异**(Runner 的速度包络会如实暴露):脚本策略的 PTP 跳转超过真实关节速度包络(2.6 rad/s),Runner 会限幅——真机上的轨迹会更慢,相位时长需要按限幅后的实际轨迹重排。

---

## 3. 资产格式策略(为什么不是全 USD)

| 资产 | 格式 | 理由 |
|------|------|------|
| FR3 机器人 | URDF(+menagerie OBJ 视觉网格) | Franka 原生格式;newton 官方示例同款路径,转换最成熟 |
| 杯子(合成) | USD | 来自 newton-assets,验证 newton 的 USD 读取路径 |
| 碗/托盘/桌 | 程序化生成 | 几何与 task.py 判据**同源参数化**——改一处,物理+判据联动 |
| real2sim 导入 | OBJ + JSON 清单 | 扫描产物天然是 mesh;物理参数必须人工标注(称重/测量) |

USD 的价值在完整 IsaacLab 3.0 栈(Isaac Sim 5.x,USD 强制);kitless 管线里所有格式最终都编译成同一批 shape,格式统一没有物理或渲染收益。
