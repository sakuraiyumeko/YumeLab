# YumeCore 重构任务清单 (AGENT_TASK.md)

本文档定义 YumeCore 架构解耦与协议重构的分阶段任务清单与验收标准。

---

## 阶段规划概览

- [x] **Phase 0: 断点续作与版本控制初始化**
  - [x] 在 `YumeCore` 初始化 Git 仓库与 `.gitignore`
  - [x] 创建 `AGENT_TASK.md`、`AGENT_PROGRESS.md`、`CHANGELOG.md`
  - [x] 建立 baseline commit

- [x] **Phase 1: 传输层分离 (Transport Layer)**
  - [x] 实现 `PICO/transport.py`（非阻塞 poll、行缓冲、防溢出）
  - [x] 实现 `PC/transport.py`（串口包装、单调时钟超时控制）
  - [x] 验证基本字符串收发与超时处理

- [x] **Phase 2: 协议层重构 (Protocol Layer)**
  - [x] 重构 `PICO/protocol.py`（移除 COMMANDS 白名单，保留格式解析）
  - [x] 重构 `PC/protocol.py`（同步命令常量定义，移除命令校验）
  - [x] 验证 PING / INFO / FS_* 请求打包与解包

- [x] **Phase 3: 硬件资源隔离 (Hardware Layer)**
  - [x] 重构 `PICO/hardware.py`
  - [x] 实现 `HardwareManager`：GPIO 引脚占用追踪与互斥检查
  - [x] 严格隔离 RP2040 内部 ADC(4) 与外部 GPIO ADC（GPIO 26-28 = ADC 0-2）
  - [x] 移除 `hardware.py` 内的 `Device` 基类和设备实现

- [x] **Phase 4: 设备层抽象与 DeviceService**
  - [x] 实现 `PICO/devices.py`（`Device` 基类、`DeviceRegistry` 注册表）
  - [x] 实现 `PICO/sensors.py`（`TemperatureSensor`、`AnalogSensor`、`DigitalInputSensor`）
  - [x] 实现 `PICO/actuators.py`（`LED`、`DigitalOutput`、`PWMOutput`）
  - [x] 实现 `PICO/device_service.py`（处理 `DEVICE_LIST`、`DEVICE_INFO`、`DEVICE_READ`、`DEVICE_WRITE`）
  - [x] 单元/功能验证：设备注册、读写与列表查询

- [x] **Phase 5: 事件总线系统 (Event System)**
  - [x] 实现 `PICO/events.py`（`EventBus` 发布/订阅）
  - [x] 实现单个订阅者异常隔离机制
  - [x] 接入 `TemperatureSensor`：在温度采样变化时发布 `sensor.temperature.changed`

- [ ] **Phase 6: 应用层抽象与 AppService**
  - [ ] 创建 `PICO/applications/__init__.py`
  - [ ] 实现 `PICO/applications/thermal.py`（`ThermalButton`：订阅温度事件，滞回与去抖）
  - [ ] 实现 `PICO/app_service.py`（处理 `APP_LIST`、`APP_INFO`、`APP_READ`、`APP_WRITE`）
  - [ ] 验证应用通用读写配置与温度触发逻辑

- [ ] **Phase 7: Controller 调度纯化与 main.py 重组**
  - [ ] 重构 `PICO/controller.py`（仅负责周期任务调度、设备轮询更新与应用更新）
  - [ ] 重构 `PICO/main.py`（组装各层组件，实现公平调度主循环）
  - [ ] 确保主循环持续调用 `controller.tick()`，限流每轮处理 1 条串口消息
  - [ ] 验证无串口通信饥饿，文件系统与 REBOOT 正常

- [ ] **Phase 8: PC 客户端适配与 CLI 增强**
  - [ ] 重构 `PC/host.py`（接入 `transport.py`，新增 `devices` 与 `apps` 代理）
  - [ ] 重构 `PC/interface.py`（新增通用 `device` 与 `app` 指令族，保留 `auto` 别名）
  - [ ] 验证 PC 与 Pico 整体协同通信

---

## 20 项验收标准核对表

1. [ ] PC 与 Pico 间 USB CDC 正常通信，无乱码。
2. [ ] 协议移除 COMMANDS 白名单后，任意合法格式命令解析正常。
3. [ ] PING、INFO 返回正确响应。
4. [ ] REBOOT 直连命令正常工作，软复位前响应先输出。
5. [ ] 文件系统全套功能（ls/cat/put/get/mkdir/rm/mv）100% 保持兼容。
6. [ ] 硬件层严格隔离 RP2040 内部 ADC(4) 与外部 GPIO ADC。
7. [ ] 同一 GPIO 引脚被二次注册时被拦截并报错。
8. [ ] 设备可通过统一接口注册到 DeviceRegistry。
9. [ ] DEVICE_LIST 返回系统中已注册的所有设备信息。
10. [ ] DEVICE_READ 可正确读取板载温度和 LED 状态。
11. [ ] DEVICE_WRITE 可直接控制 LED 亮灭。
12. [ ] EventBus 支持多订阅者，单个异常不扩散。
13. [ ] TemperatureSensor 采样后在温度变化时发布事件。
14. [ ] ThermalButton 仅通过订阅事件获取温度并决策。
15. [ ] APP_LIST / APP_INFO / APP_READ / APP_WRITE 支持应用动态配置。
16. [ ] 原 auto on/off/set 通过别名继续生效。
17. [ ] Controller 不包含任何具体硬件引用或业务分支代码。
18. [ ] 主循环中持续执行 controller.tick()，高速通信下任务不饥饿。
19. [ ] 新增设备类与新应用无需修改 main.py 或 protocol.py。
20. [ ] 各 Phase 结束具备清晰变更记录与对应 Git commit。
