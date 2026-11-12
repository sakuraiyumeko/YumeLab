# YumeCore 变更日志 (CHANGELOG.md)

所有针对 YumeCore 项目的重要架构重构与代码修改均记录于此。

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [Unreleased]

### Added
- Phase 3: 硬件隔离与资源管理。
  - `PICO/hardware.py`: 重构为纯粹的 `HardwareManager`，提供引脚占用追踪与冲突检测机制（`claim_pin` / `release_pin`）。
  - 严格隔离 RP2040 内部温度传感器 ADC(4) 与物理引脚（`create_internal_temp_adc` 不占用 GPIO 4）。
  - 移除非硬件职责的 `Device` 抽象、`Hardware` 设备集合与协议分发代码。
  - `tests/test_hardware.py`: 单元测试引脚冲突、释放与 ADC4/GPIO4 隔离特性全部通过。

---

## [0.1.0-baseline] - 2026-11-13
- 现有系统基准版本。
- 包含已验证的 USB CDC 通信、文件系统远程管理、板载温度采样与阈值 LED 控制。
