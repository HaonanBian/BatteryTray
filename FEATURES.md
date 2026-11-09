# BatteryTray 功能介绍

> Windows 托盘电量显示工具 —— 让鼠标和耳机的电量一眼可见，不再靠猜。

![托盘图标](assets/batterytray.png)

## 一句话简介

BatteryTray 常驻在 Windows 系统托盘，用一个闪电图标实时显示你的**鼠标**和**蓝牙耳机**的剩余电量。不用装厂商驱动、不用开管理员权限、不占用任何可见窗口。

---

## 核心功能

### 1. 托盘图标：颜色即状态

托盘里只占一个小图标，颜色直接告诉你电量的紧迫程度，不需要点开任何窗口：

| 颜色 | 含义 |
|------|------|
| 🟢 绿色 | 电量 ≥ 60%，充足 |
| 🟠 橙色 | 电量 20–59%，中等 |
| 🔴 红色 | 电量 < 20%，该充电了 |
| 🔵 蓝色 | 正在充电 |
| ⚪ 灰色 | 设备离线 |

多设备同时在线时，图标上会出现**多根闪电**，代表每台设备的电量条。

### 2. 左键浮层：点一下就看完

- 左键点击托盘图标，弹出**无边框圆角浮层**
- 浮层里横向排列每台在线设备的**名称 + 环形电量**
- **点击别处自动收起**，不打断你正在做的事
- 离线设备**不会**出现在浮层里 —— 托盘保持清爽

### 3. 右键菜单：全部功能都在这

| 菜单项 | 作用 |
|--------|------|
| 查看电量 | 直接弹出浮层面板 |
| 打开主窗口 | 打开雷蛇风格深色主界面 |
| 立即刷新 | 不等轮询间隔，马上读一次电量 |
| 设置 | 打开设置窗口 |
| 开机自启 | 勾选后开机自动启动 |
| 打开启动文件夹 | 一键定位到自启快捷方式所在目录 |
| 退出 | 关闭程序 |

### 4. 主窗口：深色卡片式界面

- 雷蛇风格的**深色主题**，每台设备一张**卡片**
- 卡片上显示**环形电量表**、设备图标、连接状态
- 点击卡片右侧的 **✎** 图标可**自定义设备名称**（例如把 `Razer Viper V3 Pro Wired` 改成「我的毒蝰 V3」）
- 离线设备在这里显示「未连接」和 `--`，不会误报 100%
- 右下角「设置」按钮直达设置窗口

### 5. 设置窗口：可调项

| 选项 | 说明 |
|------|------|
| 显示的设备类型 | 鼠标 / 耳机 / 游戏手柄 / 键盘，逐项勾选 |
| 低电量提醒阈值（%） | 范围 1–100，达到时弹系统通知 |
| 启用低电量通知 | 关闭后不再弹通知 |
| 轮询间隔（秒） | 范围 15–3600 |
| 托盘图标显示所有设备的电量 | 关闭则只画电量最低的那台 |

保存后**立即生效**，并写入配置文件。

### 6. 单实例运行

基于命名互斥量实现。重复点击图标、重复启动程序都**不会堆叠多个实例**，托盘永远只有一个图标。

### 7. 开机自启

通过**启动文件夹快捷方式**实现（不写注册表、不装服务、不需要管理员权限）。托盘右键「打开启动文件夹」可以一键定位。

---

## 支持的设备

| 类型 | 说明 |
|------|------|
| 雷蛇无线鼠标 | 设备表共 **65 个型号**，transaction id 取自 OpenRazer 设备库 |
| 蓝牙耳机 | 通过 HFP 上报电量的设备（Sony、WH-CH720N 等） |
| 蓝牙手柄 / 键鼠 | 可在**设置窗口**里勾选开启 |

> 默认只显示**鼠标**和**耳机**，手柄和键盘需要在设置里手动打开。

---

## 技术亮点

### 雷蛇鼠标：免驱动的 HID 直读

雷蛇设备的电量通过 **HID feature report** 查询，协议沿用 OpenRazer 的 `struct razer_report`。整包 **91 字节**，返回值 0..255 的原始刻度，换算百分比即 `raw * 100 / 255`。

**关键实现细节**：Windows 的 `mouclass` 驱动在鼠标使用期间会持有独占锁，用读写方式打开设备会得到 `ERROR_ACCESS_DENIED`。必须用 `desired_access = 0` 打开句柄才能发送 feature report —— 这是 [`damianyoko/viper-tray`](https://github.com/damianyoko/viper-tray) 和 [`nuxencs/razertray`](https://github.com/nuxencs/razertray) 都采用的绕过方式。

毒蝰 V3 Pro 的设备 ID：USB 有线 `PID 0x00C0`，无线接收器 `PID 0x00C1`，transaction id 为 `0x1F`。

### 蓝牙耳机：未公开的 PnP 属性

Windows 蓝牙协议栈在收到耳机通过 HFP 上报的电量后，会把它写入一个未公开的设备属性：

```
DEVPKEY_Bluetooth_BatteryLevel
{104EA319-6EE2-4701-BD47-8DDBF425BBE5}, pid = 2
DEVPROP_TYPE_BYTE，值为 0..100
```

这个属性挂在设备的 **Hands-Free / 免提节点**上，不在设备主节点上。读取路径：`SetupDiGetClassDevsW` → `SetupDiEnumDeviceInfo` → `SetupDiGetDevicePropertyW`。

### 解决了「离线设备显示 100%」这个经典 bug

Windows 把电量写进设备节点后**不会清除**。耳机关机、超出范围之后，这个属性依然保留最后一次的读数 —— 表现就是耳机明明没连，却一直显示 100%。

BatteryTray 因此额外读取连接信号来判断设备是否真的可达：

| 来源 | 字段 | 含义 |
|------|------|------|
| PnP 属性 | `{83DA6326-97A6-4088-9453-A1923F573B29} 15` | `IsConnected`，蓝牙协议栈维护的连接标志 |
| 注册表 | `BTHPORT\Parameters\Devices\<地址>\LastSeen` | 协议栈最后一次听到该设备的时间 |

判定规则：

- 标志为**已连接** → 可达，直接显示电量
- 标志为**未连接**，但 `LastSeen` 在 **5 分钟内** → 设备刚刚还在，判定为可达
- 其余情况 → 判定为离线，界面显示「未连接」和 `--`，不显示电量条

> **踩过的坑**：最初用的是「电量上报时间戳」来判断可达性，结果断开的耳机照样显示 100%。原因是 **Windows 在设备断开的瞬间会再写一次电量属性**，把上报时间戳刷新到断开时刻（实测：注册表 `LastSeen` 是 `20:52:57`，而电量上报时间戳是 `20:53:01`，晚了 4 秒）。所以上报时间戳完全不能用来判断在线状态，只有协议栈的 `LastSeen` 才行。

### 设备类型的可靠判断

设备的**友好名称**往往说不清它是什么（`ROG KERIS WIRELESS AIMPOINT` 是鼠标，`Xbox Wireless Controller` 是手柄），所以分类以**蓝牙协议栈记录的 Class of Device** 为准：

| 来源 | 字段 | 判据 |
|------|------|------|
| HID 设备 | `LEAppearance` | 低 6 位是 HID 子类：`0x02` 鼠标、`0x01` 键盘、`0x03/0x04` 手柄 |
| 经典设备 | `COD` | 高 5 位大类 + 次 3 位小类：`0x04` 音频、`0x05` 外设 |

这些值存在注册表 `HKLM\SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices\<地址>` 下。名称只作为兜底。

---

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

---

## 已知限制

- 雷蛇无线设备必须保持接收器插着；鼠标休眠时读不到，此时保留上一次读数并显示离线
- 蓝牙耳机的电量由耳机主动上报，Windows 无法查询未上报的设备
- 蓝牙设备离线时不会显示电量（显示「未连接」）；重新开机后需要等耳机上报一次电量才会恢复
- 电量显示的是原始刻度换算值，实际可能有 ±2% 误差
- 雷蛇耳机（Kraken / BlackShark）使用独立的厂商协议，未纳入本版本

---

## 参考项目

- [openrazer/openrazer](https://github.com/openrazer/openrazer) —— 设备库与协议定义的事实标准
- [damianyoko/viper-tray](https://github.com/damianyoko/viper-tray) —— Rust 写的毒蝰 V3 Pro 托盘工具，本项目的 `desired_access=0` 绕过方案来自这里
- [nuxencs/razertray](https://github.com/nuxencs/razertray) —— 报告结构与 CRC 的实现参考，设备表也由此提取
- [Fan4Metal/mouse_tray](https://github.com/Fan4Metal/mouse_tray) —— 多厂商驱动的架构参考
- [fastfetch-cli/fastfetch](https://github.com/fastfetch-cli/fastfetch) —— 蓝牙电量属性读取的参考实现
- [yszyszysz233/2.4G-battery-viewer](https://github.com/yszyszysz233/2.4G-battery-viewer) —— Hands-Free 节点属性的关键说明
