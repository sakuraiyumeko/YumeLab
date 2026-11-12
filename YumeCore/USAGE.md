# YumeCore 操作与使用手册

本文档详细说明 YumeCore 控制系统的硬件部署、PC 端交互操作、Python SDK 开发以及新增设备与扩展应用的开发方法。

---

## 目录

1. [系统简介与架构](#1-系统简介与架构)
2. [Pico 固件与代码部署](#2-pico-固件与代码部署)
3. [PC 端交互式 CLI 使用指南](#3-pc-端交互式-cli-使用指南)
4. [Python SDK 编程指南](#4-python-sdk-编程指南)
5. [系统扩展开发指南](#5-系统扩展开发指南)
   - [5.1 如何新增一个硬件外设/传感器](#51-如何新增一个硬件外设传感器)
   - [5.2 如何新增一个控制应用逻辑](#52-如何新增一个控制应用逻辑)
6. [常见问题与排错 (FAQ)](#6-常见问题与排错-faq)

---

## 1. 系统简介与架构

YumeCore 是专为 Raspberry Pi Pico（RP2040）与 PC 之间打造的低耦合、高扩展性硬件控制与远程管理平台。系统通过 USB CDC（虚拟串口）进行通信，分层如下：

```
PC 端 (Python 3)               Pico 端 (MicroPython)
┌──────────────────────┐       ┌──────────────────────┐
│ interface.py (CLI)   │       │ applications/        │
│ host.py (YumeCore)   │       │ controller.py        │
│ transport.py (Serial)│ <===> │ services (dev/app/fs)│
│ protocol.py          │  CDC  │ devices / sensors    │
└──────────────────────┘       │ hardware & transport │
                               └──────────────────────┘
```

- **核心原则**：新增设备或控制逻辑，**无需修改协议核心、PC 核心或主循环入口**。
- **通信模式**：文本协议帧 `ID COMMAND [ARGS...]\n`，结构化数据采用 JSON 传输。

---

## 2. Pico 固件与代码部署

### 2.1 准备工作
- Raspberry Pi Pico / Pico W 已刷入官方 MicroPython 固件（RP2040）。
- PC 上已安装 Python 3.8+ 及串口依赖库 `pyserial`：
  ```bash
  pip install pyserial
  ```

### 2.2 上传代码到 Pico
将 `YumeLab/YumeCore/PICO/` 目录下的所有文件原样上传到 Pico 的根目录（`/`）。

需上传的文件与目录树：
```text
/
├── main.py              # 系统主入口
├── transport.py         # CDC 传输层
├── protocol.py          # 协议编解码
├── hardware.py          # 硬件管理器
├── devices.py           # 设备抽象与注册表
├── sensors.py           # 传感器设备集合
├── actuators.py         # 执行器设备集合
├── events.py            # 进程内事件总线
├── device_service.py    # 通用设备服务
├── app_service.py       # 通用应用服务
├── controller.py        # 任务调度与运行时
├── filesystem.py        # 远程文件系统服务
├── boot.py              # 启动日志
└── applications/        # 应用逻辑目录
    ├── __init__.py
    └── thermal.py       # 虚拟温感按钮应用
```

**推荐上传方式**：
- **方式 A（VS Code MicroPico 插件）**：在 VS Code 中打开项目，通过 MicroPico 扩展的 `Upload project to Pico` 一键同步。
- **方式 B（mpremote 命令行）**：
  ```bash
  pip install mpremote
  mpremote connect COM7 fs cp -r PICO/* :
  ```
- **方式 C（Thonny IDE）**：打开 Thonny，连接 Pico，将 `PICO` 目录下的文件拖入 Pico 设备文件树中。

上传完成后，重新插拔 Pico 或发送软复位，Pico 即可自动运行 `main.py`。

---

## 3. PC 端交互式 CLI 使用指南

### 3.1 启动命令行终端
在 PC 终端中进入 `YumeLab/YumeCore/PC` 目录：

```bash
cd YumeLab/YumeCore/PC
python interface.py
```

> **注意**：如果你的 Pico 占用的不是默认的 `COM7`（Windows）或 `/dev/ttyACM0`（Linux/Mac），请先打开 `PC/interface.py`，将顶部的 `PORT = "COM7"` 修改为你的实际串口号，或在创建 `PicoInterface(port)` 时指定。

启动成功后，将看到交互提示符：
```text
YumeCore Pico Control & Filesystem Interface
Type 'help' for commands.

Pico:/ $ 
```

---

### 3.2 常用命令一览

#### 1. 基础系统指令
- **测试连通性**：
  ```text
  Pico:/ $ ping
  PONG
  ```
- **查看主控信息**：
  ```text
  Pico:/ $ info
  MACHINE=Raspberry Pi Pico with RP2040 RELEASE=1.20.0
  ```
- **远程复位 Pico**：
  ```text
  Pico:/ $ reboot
  Rebooting Pico...
  Disconnected.
  ```

#### 2. 通用设备管理指令 (`devices` & `device`)
新增的设备通过统一的指令族访问，无需修改任何代码：

- **列出所有已注册设备**：
  ```text
  Pico:/ $ devices
  DEVICE ID              TYPE                 PROPERTIES
  -----------------------------------------------------------------
  led                    led                  state
  sensor.temperature     temperature_sensor   value, raw
  ```
- **查看指定设备详情与能力**：
  ```text
  Pico:/ $ device info sensor.temperature
  {
    "id": "sensor.temperature",
    "type": "temperature_sensor",
    "properties": {
      "value": { "readable": true, "writable": false, "unit": "C" },
      "raw": { "readable": true, "writable": false, "unit": "u16" }
    }
  }
  ```
- **读取设备属性**：
  ```text
  Pico:/ $ device read sensor.temperature value
  sensor.temperature.value = 28.52

  Pico:/ $ device read led state
  led.state = OFF
  ```
- **写入/控制设备属性**：
  ```text
  Pico:/ $ device write led state ON
  led.state -> ON

  Pico:/ $ device write led state TOGGLE
  led.state -> OFF
  ```

#### 3. 通用应用管理指令 (`apps` & `app`)
所有运行在 Pico 上的业务控制应用均可通过此指令族动态读取和调整参数：

- **列出所有运行中的应用**：
  ```text
  Pico:/ $ apps
  APP NAME        DESCRIPTION                    PROPERTIES
  ---------------------------------------------------------------------------
  thermal         Temperature threshold virtua   enabled, threshold, hysteresis, debounce_ms, state, last_temp
  ```
- **读取应用配置与状态**：
  ```text
  Pico:/ $ app read thermal threshold
  thermal.threshold = 45.0

  Pico:/ $ app read thermal state
  thermal.state = RELEASED
  ```
- **修改应用参数（动态调优）**：
  ```text
  Pico:/ $ app write thermal threshold 50.0
  thermal.threshold -> 50.0

  Pico:/ $ app write thermal enabled false
  thermal.enabled -> False
  ```

#### 4. 便捷温控指令（向后兼容别名）
系统保留了习惯的快捷温控指令：
- `auto on`：开启温度阈值自动联动 LED。
- `auto off`：关闭温度自动联动。
- `auto set 48.5`：设置温控阈值为 48.5 ℃。

#### 5. 远程文件系统管理指令
支持在 PC 端远程维护 Pico 内部 Flash 上的文件，便于热更新代码：
- `ls [path]`：列出目录内容。
- `cd <path>`：切换当前工作路径。
- `pwd`：打印当前远程目录路径。
- `cat <file>`：在终端输出远程文本文件内容。
- `put <local_path> [remote_path]`：上传本地文件至 Pico。
- `get <remote_path> [local_path]`：下载 Pico 上的文件到本地。
- `mkdir <path>`：在 Pico 上创建目录。
- `rm <path>`：删除 Pico 上的文件。
- `mv <src> <dst>`：重命名或移动文件。

#### 6. 协议裸命令发送 (`send`)
用于低层调试或扩展调试：
```text
Pico:/ $ send PING
PONG

Pico:/ $ send DEVICE_READ led state
{"device": "led", "property": "state", "value": "OFF"}
```

---

## 4. Python SDK 编程指南

你可以将 `PC/host.py` 作为 Python 库导入到你自己的自动化脚本、数据采集工程或图形界面应用中。

### 示例：自动化温度监控与数据记录脚本
```python
import time
from host import YumeCore

# 连接 Pico (通过 with 语句自动管理连接与关闭)
with YumeCore(port="COM7", timeout=2.0) as core:
    print("连接成功，Pico 系统信息:", core.info())

    # 1. 检查设备列表
    devices = core.devices.list()
    print("当前已注册设备:", [d["id"] for d in devices])

    # 2. 读取板载温度传感器
    current_temp = core.devices.read("sensor.temperature", "value")
    print(f"当前板载温度: {current_temp} ℃")

    # 3. 控制 LED 闪烁
    for _ in range(3):
        core.devices.write("led", "state", "ON")
        time.sleep(0.5)
        core.devices.write("led", "state", "OFF")
        time.sleep(0.5)

    # 4. 动态配置温控应用参数
    core.apps.write("thermal", "threshold", 42.0)
    print("温控阈值已调整为:", core.apps.read("thermal", "threshold"))
```

---

## 5. 系统扩展开发指南

YumeCore 最大的设计亮点是**插件化与开闭原则**。新增传感器或业务逻辑，无需触碰底层通信与调度。

### 5.1 如何新增一个硬件外设/传感器

假设你要接入一个光敏传感器（LDR，连接在 GPIO 26 / ADC0 引脚上）：

1. **编写设备类**（在 `sensors.py` 或你自建的模块中）：
   ```python
   from devices import Device

   class LightSensor(Device):
       device_id = "sensor.light"
       device_type = "light_sensor"

       def __init__(self, hardware, pin=26):
           self.hardware = hardware
           self.pin = pin
           self.properties = {
               "raw": {"readable": True, "writable": False, "unit": "u16"},
               "level": {"readable": True, "writable": False, "unit": "%"}
           }
           # 向硬件管理器申请 ADC 资源（自动检测引脚冲突）
           self._adc = hardware.create_adc(pin, owner=self.device_id)
           self._raw = 0

       def update(self):
           """周期采样由 Controller 统一调度"""
           self._raw = self._adc.read_u16()

       def read(self, property_name):
           if property_name == "raw":
               return self._raw
           elif property_name == "level":
               return round((self._raw / 65535) * 100, 1)
           raise ValueError("UNKNOWN_PROPERTY: " + property_name)

       def deinit(self):
           self.hardware.release_pin(self.pin)
   ```

2. **在 `main.py` 装配阶段注册该设备**：
   ```python
   # main.py 的 main() 函数中：
   light_sensor = LightSensor(hardware, pin=26)
   registry.register(light_sensor)
   ```

3. **完成！**
   无需修改协议文件或 PC 代码，在 PC 端运行 `interface.py`：
   - 输入 `devices` 会立即看到 `sensor.light`。
   - 输入 `device read sensor.light level` 即可直接读取光照百分比！

---

### 5.2 如何新增一个控制应用逻辑

假设你要编写一个“暗光自动开灯”的应用（`DarkLightController`）：

1. **编写应用类**（在 `applications/dark_light.py`）：
   ```python
   class DarkLightApp:
       def __init__(self, light_sensor, led_actuator, threshold_level=30.0):
           self.name = "dark_light"
           self.description = "Auto turn on light when environment is dark"
           self.sensor = light_sensor
           self.led = led_actuator
           self.threshold = threshold_level
           self.enabled = True

           self.properties = {
               "enabled": {"readable": True, "writable": True, "type": "bool"},
               "threshold": {"readable": True, "writable": True, "type": "float"}
           }

       def update(self):
           """Controller 会持续周期调用该函数"""
           if not self.enabled:
               return
           level = self.sensor.read("level")
           if level < self.threshold:
               self.led.write("state", "ON")
           else:
               self.led.write("state", "OFF")

       def info(self):
           return {"name": self.name, "description": self.description, "properties": self.properties}

       def read(self, prop):
           if prop == "enabled": return self.enabled
           if prop == "threshold": return self.threshold
           raise ValueError("UNKNOWN_PROPERTY")

       def write(self, prop, val):
           if prop == "enabled":
               self.enabled = str(val).lower() in ("true", "1", "on")
               return self.enabled
           if prop == "threshold":
               self.threshold = float(val)
               return self.threshold
           raise ValueError("UNKNOWN_PROPERTY")
   ```

2. **在 `main.py` 中注册应用**：
   ```python
   dark_app = DarkLightApp(light_sensor, led)
   app_service.register_app(dark_app)
   controller.register_app(dark_app)
   ```

3. **PC 端立即可用**：
   - 输入 `apps` 会显示 `dark_light`。
   - 输入 `app write dark_light threshold 20.0` 即可实时配置阈值！

---

## 6. 常见问题与排错 (FAQ)

### Q1: 运行 `interface.py` 报错 `could not open port 'COM7'`？
- **原因**：Pico 占用的串口号与配置不符，或者串口被其他软件（如 Thonny、VS Code 串口监视器、PuTTY）独占。
- **排错步骤**：
  1. 在设备管理器中确认“USB 串行设备”的实际 COM 端口。
  2. 关闭所有可能占用该端口的窗口（Thonny 必须断开连接或关闭）。
  3. 修改 `PC/interface.py` 中的 `PORT` 变量后重新运行。

### Q2: 为什么输入命令后提示 `TimeoutError: No response for request`？
- **原因**：Pico 端未正确运行 `main.py`，或者正在处于 REPL 阻塞状态。
- **排错步骤**：
  1. 按一下 Pico 的复位或重新插拔 USB。
  2. 确认 `main.py` 及相关解耦模块已全部上传到 Pico 根目录下。
  3. 检查是否有未经捕获的启动异常。

### Q3: 新增引脚分配报错 `PIN_CONFLICT: Pin X already claimed by Y`？
- **原因**：`HardwareManager` 具备引脚防重占互斥机制，说明引脚 `X` 已经被其他外设（如已占用的 PWM 或输入）持有。
- **解决方式**：检查硬件接线，更换为未被占用的空闲 GPIO 引脚。
