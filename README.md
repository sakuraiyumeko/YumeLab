# YumeLab

YumeLab aims to build a modular, extensible hardware control platform.

Its goal is to provide a unified way to connect, manage, and control different hardware components, allowing them to work together as a flexible system.

Rather than building devices for a single purpose, YumeLab seeks to create a general-purpose foundation that can grow with new hardware, new capabilities, and new ideas.

## 快速启动工作站（纯软件仿真 / 真实 Pico 通用）

当前已实现无需物理硬件即可完整运行的纯软件工作站中枢与 HUD 仪表盘：

```bash
# 1. 启动工作站 HUD（默认运行内置模拟 Pico 节点）
python run_workstation.py --open-browser

# 2. 若已连接物理 Pico（例如 COM7），直接切换真实串口模式
python run_workstation.py --port COM7 --open-browser

# 3. 或者仅使用自然语言命令行交互
python run_workstation.py --cli
```

启动后访问 `http://127.0.0.1:8000/` 即可打开可视化控制台；运行时设备快照与事件流会自动保存在 `state/` 目录中。
