# BatteryTray

Windows 托盘电量显示工具 —— 在系统托盘里查看**鼠标**和**耳机**的电量。

- 直接通过 USB HID 读取 **雷蛇毒蝰 V3 Pro** 电量，**不需要装雷蛇 Synapse**，不需要内核驱动，不需要管理员权限
- 通过 Windows 蓝牙协议栈读取**蓝牙耳机**电量
- **托盘图标是闪电标志**，颜色按电量变化：绿色 ≥60%、橙色 20–59%、红色 <20%、充电时蓝色、离线时灰色
- **左键点击托盘图标**弹出无边框浮层，一眼看完所有设备电量；点别处自动收起，不打断工作
- **右键菜单**：查看电量 / 打开主窗口 / 立即刷新 / 设置 / 开机自启 / 打开启动文件夹 / 退出
- **主窗口**为雷蛇风格深色界面（卡片 + 环形电量），支持**自定义设备名称**
- **单实例运行**（命名互斥量），重复点击托盘不会堆叠

![托盘图标](assets/batterytray.png)

## 快速开始

直接运行打包好的单文件程序：

```
dist\BatteryTray.exe
```

把它放到一个**固定目录**（例如 `C:\Tools\BatteryTray\`），然后在托盘图标上右键勾选 **Start with Windows** 即可开机自启。

快捷方式放在：

```
%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\BatteryTray.lnk
```

托盘右键菜单里的 **「打开启动文件夹」** 可以直接打开这个目录。开机自启失败时，多半是快捷方式指向的 exe 被移动或改名了 —— 重新勾选一次即可。

## 从源码运行

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run.py
```

## 打包

```bash
.venv\Scripts\python -m PyInstaller --noconfirm --clean BatteryTray.spec
```

产物在 `dist\BatteryTray.exe`，约 15 MB。

## 工作原理

### 雷蛇鼠标：HID Feature Report

雷蛇设备的电量通过 HID feature report 查询，协议沿用 OpenRazer 的 `struct razer_report`：

| 偏移 | 字段 |
|------|------|
| 0 | 状态（`0x01` busy，`0x02` 成功） |
| 1 | transaction id |
| 5 | data size |
| 6 | command class |
| 7 | command id |
| 8–87 | 参数 |
| 88 | CRC（字节 2..87 的异或） |

电量查询命令为 `command class 0x07`（power）+ `command id 0x80`（battery level），返回值是 0..255 的原始刻度，换算成百分比即 `raw * 100 / 255`。充电状态用 `command id 0x84`。

线路上 feature report 前面多一个 HID report id，所以整包是 **91 字节**，上表所有偏移都要 +1。

**关键实现细节**：Windows 的 `mouclass` 驱动在鼠标使用期间会持有独占锁，用读写方式打开设备会得到 `ERROR_ACCESS_DENIED`。必须用 `desired_access = 0` 打开句柄才能发送 feature report —— 这是 `damianyoko/viper-tray` 和 `nuxencs/razertray` 都采用的绕过方式。

毒蝰 V3 Pro 的设备 ID：USB 有线 `PID 0x00C0`，无线接收器 `PID 0x00C1`，transaction id 为 `0x1F`。

### 蓝牙耳机：未公开的 PnP 属性

Windows 蓝牙协议栈在收到耳机通过 HFP 上报的电量后，会把它写入一个未公开的设备属性：

```
DEVPKEY_Bluetooth_BatteryLevel
{104EA319-6EE2-4701-BD47-8DDBF425BBE5}, pid = 2
DEVPROP_TYPE_BYTE，值为 0..100
```

**注意**：这个属性挂在设备的 **Hands-Free / 免提节点**上，不在设备主节点上。属性由驱动在收到上报时写入，耳机没连接或不上报电量时该属性不存在。

读取路径：`SetupDiGetClassDevsW` → `SetupDiEnumDeviceInfo` → `SetupDiGetDevicePropertyW`。

#### 离线设备的假电量（已修复）

Windows 把电量写进设备节点后**不会清除**。耳机关机、超出范围之后，这个属性依然保留最后一次的读数，程序每轮轮询都会读到它 —— 表现就是耳机明明没连，却一直显示 100%。

驱动因此额外读取连接信号来判断设备是否真的可达：

| 来源 | 字段 | 含义 |
|------|------|------|
| PnP 属性 | `{83DA6326-97A6-4088-9453-A1923F573B29} 15` | `IsConnected`，蓝牙协议栈维护的连接标志 |
| 注册表 | `BTHPORT\Parameters\Devices\<地址>\LastSeen` | 协议栈最后一次听到该设备的时间 |

判定规则：

- 标志为**已连接** → 可达，直接显示电量
- 标志为**未连接**，但 `LastSeen` 在 **5 分钟内** → 设备刚刚还在，判定为可达
- 其余情况 → 判定为离线，界面显示「未连接」和 `--`，不显示电量条

> **踩过的坑**：最初用的是「电量上报时间戳」来判断可达性，结果断开的耳机照样显示 100%。原因是 **Windows 在设备断开的瞬间会再写一次电量属性**，把上报时间戳刷新到断开时刻（实测：注册表 `LastSeen` 是 `20:52:57`，而电量上报时间戳是 `20:53:01`，晚了 4 秒）。所以上报时间戳完全不能用来判断在线状态，只有协议栈的 `LastSeen` 才行。

注意属性存储的类型标记和 SDK 头文件里的 `DEVPROP_TYPE_*` 不一致：布尔是 `0x11`、字符串是 `0x12`，读错类型会拿到原始 blob 而不是值。

#### 未连接设备的显示位置

离线设备只在**主窗口**出现，托盘弹出面板、托盘图标和悬停提示里都看不到它们。这样托盘保持清爽，只有真正能读���电量的设备才占位置。

| 位置 | 显示内容 |
|------|---------|
| 托盘弹出面板 | 仅已连接设备 |
| 托盘图标 | 仅已连接设备（多设备时一��闪电） |
| 托盘悬停提示 | 仅已连接设备 |
| 主窗口 | 全部设备，离线的显示「未连接」 |

## 支持的设备

| 类型 | 说明 |
|------|------|
| 雷蛇无线鼠标 | 设备表共 65 个型号，transaction id 取自 OpenRazer 设备库 |
| 蓝牙耳机 | 通过 HFP 上报电量的设备（Sony、WH-CH720N 等） |
| 蓝牙手柄 / 键鼠 | 可在**设置窗口**里勾选开启 |

默认只显示鼠标和耳机，手柄和键盘要在设置里打开。

### 设备类型是怎么判断的

设备的**友好名称**往往说不清它是什么（`ROG KERIS WIRELESS AIMPOINT` 是鼠标，`Xbox Wireless Controller` 是手柄），所以分类以**蓝牙协议栈记录的 Class of Device** 为准：

| 来源 | 字段 | 判据 |
|------|------|------|
| HID 设备 | `LEAppearance` | 低 6 位是 HID 子类：`0x02` 鼠标、`0x01` 键盘、`0x03/0x04` 手柄 |
| 经典设备 | `COD` | 高 5 位大类 + 次 3 位小类：`0x04` 音频、`0x05` 外设 |

这些值存在注册表 `HKLM\SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices\<地址>` 下。名称只作为兜底。

## 设置窗口

在**主窗口**右下角点「设置」，或**右键托盘图标**选「设置」，可以改：

| 选项 | 说明 |
|------|------|
| 显示的设备类型 | 鼠标 / 耳机 / 游戏手柄 / 键盘，逐项勾选 |
| 低电量提醒阈值（%） | 电量低于或等于该值时弹通知，范围 1–100 |
| 启用低电量通知 | 关闭后不再弹系统通知 |
| 轮询间隔（秒） | 范围 15–3600 |
| 托盘图标显示所有设备的电量 | 关闭则只画电量最低的那台 |

保存后立即生效并写入配置文件。

## 配置

配置文件：`%APPDATA%\BatteryTray\config.json`

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `poll_interval` | 60 | 轮询间隔（秒），最小 15 |
| `enabled_kinds` | `null` | 要显示的设备类型；`null` 表示默认（鼠标+耳机），空数组表示全部关闭 |
| `include_other_peripherals` | false | 旧开关，与 `enabled_kinds` 保持同步 |
| `show_every_device` | true | 多设备时是否每个都画一根电量条 |
| `low_battery_threshold` | 20 | 低电量提醒阈值（%） |
| `notify_low_battery` | true | 是否弹出系统通知 |
| `devices` | `[]` | 设备名白名单，空表示自动检测 |
| `custom_names` | `{}` | 自定义设备名称，键是设备原始名，值是显示名 |

最新一次读数同时写到 `%APPDATA%\BatteryTray\status.txt`，方便排查。

## 自定义设备名称

在**主窗口**里点击设备卡片右侧的 ✎ 图标即可改名（回车保存，Esc 取消）；在**托盘浮层**里右键设备那一行，选择「重命名设备」会弹出对话框。

名称保存在 `custom_names` 里，重启后依然生效。要恢复默认名称，在改名框里清空内容即可。

```json
{
  "custom_names": {
    "Razer Viper V3 Pro Wired": "我的毒蝰 V3",
    "WH-CH720N Hands-Free AG": "降噪耳机"
  }
}
```

## 项目结构

```
batterytray/
├── app.py            # 托盘主程序、菜单、轮询循环
├── icon.py           # 闪电图标绘制
├── window.py         # 雷蛇风格主窗口
├── quickpanel.py     # 托盘浮层（含全局鼠标钩子自动收起）
├── renamedialog.py   # 重命名对话框
├── settingsdialog.py # 设置窗口（设备类型、阈值、轮询间隔）
├── dpi.py            # Per-Monitor DPI 感知与缩放
├── config.py         # 配置读写
├── autostart.py      # 开机自启（启动文件夹快捷方式）
├── singleton.py      # 单实例互斥量
└── drivers/
    ├── razer.py      # 雷蛇 HID feature report
    └── bluetooth.py  # 蓝牙 PnP 电量属性
```

## 测试

```bash
.venv\Scripts\python -m pytest verify_all.py -q
```

90 个用例，覆盖协议编解码、CRC、图标渲染、配置读写、设备筛选与去重、Class of Device 分类、离线设备的电量屏蔽、离线设备的显示位置、设置窗口、重命名、单实例、开机自启和轮询循环。其中几个用例会直接读取你机器上真实连接的设备。

## 已知限制

- 雷蛇无线设备必须保持接收器插着；鼠标休眠时读不到，此时保留上一次读数并显示离线
- 蓝牙耳机的电量由耳机主动上报，Windows 无法查询未上报的设备
- 蓝牙设备离线时不会显示电量（显示「未连接」）；重新开机后需要等耳机上报一次电量才会恢复
- 电量显示的是原始刻度换算值，实际可能有 ±2% 误差
- 雷蛇耳机（Kraken / BlackShark）使用独立的厂商协议，未纳入本版本

## 参考项目

- [openrazer/openrazer](https://github.com/openrazer/openrazer) —— 设备库与协议定义的事实标准
- [damianyoko/viper-tray](https://github.com/damianyoko/viper-tray) —— Rust 写的毒蝰 V3 Pro 托盘工具，本项目的 `desired_access=0` 绕过方案来自这里
- [nuxencs/razertray](https://github.com/nuxencs/razertray) —— 报告结构与 CRC 的实现参考，设备表也由此提取
- [Fan4Metal/mouse_tray](https://github.com/Fan4Metal/mouse_tray) —— 多厂商驱动的架构参考
- [fastfetch-cli/fastfetch](https://github.com/fastfetch-cli/fastfetch) —— 蓝牙电量属性读取的参考实现
- [yszyszysz233/2.4G-battery-viewer](https://github.com/yszyszysz233/2.4G-battery-viewer) —— Hands-Free 节点属性的关键说明
