# YumeCore 变更日志 (CHANGELOG.md)

所有针对 YumeCore 项目的重要架构重构与代码修改均记录于此。

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [Unreleased]

### Added
- Phase 4: 设备层抽象与 DeviceService。
  - `PICO/devices.py`: 定义 `Device` 基类（统一声明 `id`、`type`、`properties`，标准化 `info/read/write/update/deinit`）与 `DeviceRegistry`。
  - `PICO/sensors.py`: 实现 `TemperatureSensor`（基于内部 ADC4 采样与温标转换）、`AnalogSensor`、`DigitalInputSensor`。
  - `PICO/actuators.py`: 实现 `LED`（支持 ON/OFF/TOGGLE 状态控制）、`DigitalOutput`、`PWMOutput`。
  - `PICO/device_service.py`: 专门处理 `DEVICE_LIST`、`DEVICE_INFO`、`DEVICE_READ`、`DEVICE_WRITE` 通用设备请求，并兼容原有 `STATUS`、`LED`、`HW_*` 命令。
  - `tests/test_devices.py`: 设备注册、传感器读取、执行器写入及 DeviceService 协议分发测试全部通过。

---

## [0.1.0-baseline] - 2026-11-13
- 现有系统基准版本。
- 包含已验证的 USB CDC 通信、文件系统远程管理、板载温度采样与阈值 LED 控制。
