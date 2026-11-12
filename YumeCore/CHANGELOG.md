# YumeCore 变更日志 (CHANGELOG.md)

所有针对 YumeCore 项目的重要架构重构与代码修改均记录于此。

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [Unreleased]

### Added
- Phase 5: 事件总线系统。
  - `PICO/events.py`: 实现进程内发布/订阅事件总线 `EventBus`，支持多订阅者分发与异常隔离。
  - `TemperatureSensor` 接入 `EventBus`：带死区判定，在温度变化时自动发布 `sensor.temperature.changed` 事件。
  - `tests/test_events.py`: 包含多订阅者测试、异常隔离测试及温感事件集成测试，全部通过。

---

## [0.1.0-baseline] - 2026-11-13
- 现有系统基准版本。
- 包含已验证的 USB CDC 通信、文件系统远程管理、板载温度采样与阈值 LED 控制。
