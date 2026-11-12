# YumeCore 变更日志 (CHANGELOG.md)

所有针对 YumeCore 项目的重要架构重构与代码修改均记录于此。

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [Unreleased]

### Added
- Phase 2: 协议层重构与解耦。
  - `PICO/protocol.py` & `PC/protocol.py`: 彻底移除 `COMMANDS` 白名单硬编码，协议只负责 `ID CMD [ARGS...]` 帧格式解析与响应封装，版本升级为 `1.0`。
  - 增加通用命令常量（`CMD_DEVICE_*`, `CMD_APP_*`），不限制未知扩展命令。
  - `tests/test_protocol.py`: 全面测试任意命令编解码、参数提取与错误处理，100% 通过。

---

## [0.1.0-baseline] - 2026-11-13
- 现有系统基准版本。
- 包含已验证的 USB CDC 通信、文件系统远程管理、板载温度采样与阈值 LED 控制。
