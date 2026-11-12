# YumeCore 变更日志 (CHANGELOG.md)

所有针对 YumeCore 项目的重要架构重构与代码修改均记录于此。

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [Unreleased]

### Added
- Phase 6: 应用层抽象、Thermal 迁移与 AppService。
  - `PICO/applications/thermal.py`: 实现 `ThermalButton` 应用，订阅温度变化事件，实现阈值比较、滞回（hysteresis）与去抖（debounce），可选直驱 LED 执行器或发布应用事件。
  - `PICO/app_service.py`: 实现通用应用服务层，支持 `APP_LIST`、`APP_INFO`、`APP_READ`、`APP_WRITE`，并向后兼容 `AUTO`、`AUTO_SET`、`TEMP` 命令。
  - `tests/test_applications.py`: 滞回、阈值触发与 AppService 通用配置测试全部通过。

---

## [0.1.0-baseline] - 2026-11-13
- 现有系统基准版本。
- 包含已验证的 USB CDC 通信、文件系统远程管理、板载温度采样与阈值 LED 控制。
