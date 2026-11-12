# YumeCore 变更日志 (CHANGELOG.md)

所有针对 YumeCore 项目的重要架构重构与代码修改均记录于此。

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [Unreleased]

### Added
- Phase 7: Controller 调度纯化与 main.py 重组。
  - `PICO/controller.py`: 彻底移除硬件与业务逻辑，专职负责周期任务调度、设备 `update()` 与应用生命周期管理。
  - `PICO/main.py`: 实现公平主循环调度（限流单轮最多处理 1 条串口输入，无条件持续调用 `controller.tick()`，彻底避免高频通信饿死控制任务），组装 `CommandDispatcher` 负责协议路由。
  - `tests/test_controller_and_main.py`: 调度器与指令分发器集成测试全部通过。

---

## [0.1.0-baseline] - 2026-11-13
- 现有系统基准版本。
- 包含已验证的 USB CDC 通信、文件系统远程管理、板载温度采样与阈值 LED 控制。
