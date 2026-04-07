# TactileGear

全能型主动式力反馈外设平台 — 将高扭矩 FFB 硬件转化为多形态赛车虚拟外设。

## 功能

- **H 档模式** — 支持民用 6+R (左上/右下倒档)、保时捷 7+R、卡车 18 速排布，含物理力反馈墙、重力突破、打齿惩罚
- **序列档模式** — X 轴弹簧锁死，Y 轴换挡 + 高频震动 + 触底反弹
- **手刹模式** — Y 轴 → vJoy RY 轴，指数级液压阻力模拟
- **自动挡 PRND 模式** — 多段限位器，P 档驻车棘爪模拟
- **全局按钮映射** — 固定 32 按钮 vJoy 设备，模式切换零冲突
- **100Hz 物理循环** — 独立线程实时力反馈计算
- **紧急安全机制** — `Ctrl+C` / 异常退出自动释放电机力矩
- **GUI 控制面板** — CustomTkinter 赛车风格界面，参数精调 + 配置持久化

## 系统要求

- Windows 10/11
- Python 3.10+
- [vJoy](https://sourceforge.net/projects/vjoystick/) 驱动 (已安装并启用至少 1 个设备，配置 32 按钮 + 6 轴)
- 力反馈摇杆设备 (如 Moza AB6 底座)

## 安装

```bash
git clone https://github.com/gusc2013C/TactileGear.git
cd TactileGear
pip install -r requirements.txt
```

依赖仅两个：`PySDL3` 和 `customtkinter`。vJoy 通过 ctypes 直接调用系统 DLL，无需额外安装 pyvjoy。

## 运行

```bash
python main.py
```

## 项目结构

```
TactileGear/
├── main.py                          # 入口
├── requirements.txt
├── config/
│   ├── default_layouts.json         # 4 种 H 档排布定义
│   ├── default_profile.json         # 工厂默认参数
│   └── button_map.json              # vJoy 按钮映射文档
├── src/
│   ├── core/                        # 枚举、事件总线、配置管理
│   ├── hardware/                    # SDL3/ctypes-vJoy/SimHub 硬件封装
│   ├── state/                       # 4 种模式控制器
│   ├── physics/                     # 力曲线、档位几何、FFB 效果引擎
│   ├── engine/                      # 100Hz 物理主循环
│   └── gui/                         # CustomTkinter 界面
└── tests/
```

## vJoy 按钮映射

| 按钮 | H 档 | 序列档 | 自动挡 | 卡车 |
|------|------|--------|--------|------|
| 1-7  | 1-7 档 | | | 1-6 档 |
| 8    | 8 档 | | | |
| 9    | 倒档 | | | |
| 10   | 空挡 | | | |
| 11   | | 升档 | | |
| 12   | | 降档 | | |
| 13-17| | | P/R/N/D/S | |
| 18   | | | | Range |
| 19   | | | | Splitter |
| RY 轴| | | 手刹 (0-32767) | |

## 配置

排布定义在 `config/default_layouts.json`，可调参数通过 GUI 精调并保存为 `config/profiles.json`。

支持 SimHub 遥测 (UDP 20777) 获取离合器状态，实现打齿惩罚。未连接时默认离合器踩下 (安全)。

## License

[GPL-3.0](LICENSE)
