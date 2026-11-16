## BatteryTray 1.2.0

Windows 托盘电量显示工具 —— 让鼠标、键盘和耳机的电量一眼可见。

### 下载

| 版本 | 文件 |
|------|------|
| 安装版（推荐） | `BatteryTray-Setup-1.2.0.exe` — 带安装向导、开始菜单快捷方式和卸载程序 |
| 便携版 | `BatteryTray-1.2.0-portable.zip` — 解压即用 |
| 单文件版 | `BatteryTray-1.2.0.exe` — 双击即运行，免安装 |

### 新增：二十多种厂商协议

从 GitHub 上的开源项目（`HeyOkay/HaloBattery`、`seerge/g-helper`、`435311382/Volt`、`mammadow/keychron-battery-tray`、`LORQAQ/mchose-tray` 等）里整理并验证了二十多种厂商的电量协议，全部加进 `batterytray/drivers/vendor2.py`：

| 协议族 | 覆盖的品牌 | 报文特征 |
|--------|-----------|---------|
| Compx 17 字节 | ATK / VXE / VGN / Pulsar / Scyrox / 达尔优 / G-Wolves / Zaopin | `08 04` 开头，17 字节求和等于 `0x55` |
| AULA 20 字节 | AULA / LEOBOG / 狼蛛 / 凌豹 / 迈从 / Incott | `13` 开头，末字节是前面字节的低位和 |
| Keychron | Keychron M5 / M6 / M7 | 厂商页 `0xFFC1`，`B3 06` 查询，第 20 字节是电量 |
| Pulsar XS-1 | Pulsar | 65 字节 feature 帧，双字节校验和 |
| MCHOSE | MCHOSE 鼠标 / 耳机 | 载荷逐位取反，`0x06` 设备信息命令 |
| Lamzu | Lamzu | 65 字节 feature 报告 |
| Ninjutso | Ninjutso / NINX | 32 字节 Nordic feature 报告 |
| Bloody | A4Tech Bloody | `80 FF 00` 命令，回复 `06 56` |
| HyperX | Cloud Alpha / III 无线耳机 | `21 FF 05` 输出报告 |
| SteelSeries | Arctis / Nova / GameBuds | `00 20`（Nova）与各家命令表 |
| 雷柏 | Rapoo 2.4G 无线系列 | 接收器主动推送 `07` 状态包 |
| Attack Shark | Attack Shark 无线鼠标 | 接收器主动推送，电量按 10% 步进 |
| Lofree | Lofree Hyzen 键盘 | `0xFF1C:0x92` 上的三段式事务 |
| NZXT | NZXT Lift Elite 无线鼠标 | `0xFFCA:0x0001`，`4E` 开头的 64 字节帧 |
| ASUS ROG 键盘 | Falchion / Azoth / Strix Scope II 96 / Strix Flare II / Claymore II / TUF K3 / TX 98 | `12 01` 电量查询 |
| ASUS ROG Omni | ROG Omni Receiver | 先读配对列表，再按键盘通道查询 |
| HID 标准电池页 | 通用 | usage page `0x06` / usage `0x20` 兜底 |

### 新增：ASUS ROG 键盘

- **Falchion（幻灵）系列** —— 百分比在**第 11 字节**（第 6 字节是 0–10 的档位刻度）
- **Azoth / Azoth Extreme（魔剑 / 魔剑 Extreme）**
- **Strix Scope II 96 / Strix Flare II**
- **Claymore II（棱剑 II）**
- **TUF Gaming K3 / TX 98**
- **ROG Omni Receiver** —— 先用 `01 A0 00 00` 读配对列表拿到键盘名字，键盘本身再走 `0xFF00` 的 Report ID `0x02`

### 新增：型号名称库

`batterytray/drivers/devices.py` 维护了一套 VID/PID → 友好名称的映射，托盘图标上显示的是「Lofree Hyzen 无线键盘」而不是 `USB Composite Device`。

### 修复

- **Windows 有时会在 HID 回复前面补一个 Report ID** —— ROG 键盘的电量偏移解析现在会先看头两字节判断基准位置，带 Report ID 和不带 Report ID 的回包都能正确读出电量
- **休眠的键盘不会被当成 0%** —— 没有回应就跳过，不会误报

### 功能

- **雷蛇鼠标免驱动读取** — 直接通过 USB HID feature report 读取电量
- **多品牌电量** — 罗技、ATK/VXE/VGN、Endgame、VAXEE、Nordic、ROG、雷蛇，以及新增的二十多种厂商协议
- **颜色即状态** — 绿 ≥60% / 橙 20–59% / 红 <20% / 蓝=充电中 / 灰=离线
- **左键浮层 / 右键菜单 / 低电量通知 / 自定义设备名 / 开机自启**
- **正确识别离线设备** — 不会把缓存的旧电量当成当前电量

### 系统要求

- Windows 10 / 11
- 无线接收器需要保持插着
- 蓝牙耳机需主动上报电量（HFP）
- 键盘默认不显示，需要在设置里勾选「键盘」

### 已知限制

- 新增品牌目前只读取电量，DPI / 回报率 / 改键仍只对雷蛇和 ROG 月刃开放
- 部分键盘（如 Lofree、Keychron）休眠时不响应查询，按一下键盘再刷新即可
- 罗技蓝牙 BLE 直连不走 HID++，由 Windows 蓝牙属性读取
- 电量为原始刻度换算值，实际可能有 ±2% 误差
- 蓝牙设备离线时显示「未连接」，重新开机后需等设备上报一次电量才恢复

📖 完整功能介绍见仓库 [FEATURES.md](https://github.com/HaonanBian/BatteryTray/blob/main/FEATURES.md)
