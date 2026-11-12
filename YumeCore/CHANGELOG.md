# YumeCore 变更日志 (CHANGELOG.md)

所有针对 YumeCore 项目的重要架构重构与代码修改均记录于此。

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [1.0.0] - 2026-11-13

### Added
- Phase 8: PC 客户端适配与 CLI 增强。
  - `PC/host.py`: 使用 `SerialTransport` 替代裸 pyserial 读写；新增 `devices` 代理（`list`, `info`, `read`, `write`）与 `apps` 代理（`list`, `info`, `read`, `write`）；保持 `reboot()` 直连与原有 `led`, `auto`, `status`, `temp` 便捷方法。
  - `PC/interface.py`: CLI 新增通用 `devices`、`device`、`apps`、`app`、`ping`、`info` 命令；`auto on/off/set` 映射为应用代理调用；完整保留全部文件系统操作指令（`ls`, `cat`, `put`, `get`, `mkdir`, `rm`, `mv`）。
  - `tests/test_pc_host_and_interface.py`: 代理调用、直连重启与兼容层测试全部通过。
  - 全套单元与集成测试（共 27 项测试）100% 通过。

---

## [0.1.0-baseline] - 2026-11-13
- 现有系统基准版本。
- 包含已验证的 USB CDC 通信、文件系统远程管理、板载温度采样与阈值 LED 控制。
