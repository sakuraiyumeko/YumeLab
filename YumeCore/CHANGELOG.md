# YumeCore 变更日志 (CHANGELOG.md)

所有针对 YumeCore 项目的重要架构重构与代码修改均记录于此。

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [Unreleased]

### Added
- Phase 1: 传输层分离。
  - `PICO/transport.py`: 封装 `Transport` 类，支持 `uselect.poll` 非阻塞轮询输入，行缓冲区限长 256 字节，带换行分帧与溢出检测，单次轮询限流保护主循环。
  - `PC/transport.py`: 封装 `SerialTransport` 类，管理串口生命周期、基于单调时钟的高精度超时行读取 `readline()` 与异常处理。
  - `tests/test_transport.py`: 编写并通过了传输层收发、超时与缓冲区溢出测试用例。

---

## [0.1.0-baseline] - 2026-11-13
- 现有系统基准版本。
- 包含已验证的 USB CDC 通信、文件系统远程管理、板载温度采样与阈值 LED 控制。
