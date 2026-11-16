"""
YumeLab Workstation Hub (PC Central Coordinator).

Connects to either a physical Pico via YumeCore `SerialTransport` or the
pure-software `SimulatedPicoNode`, continuously polls device/app states into
`StateStore` (`state/snapshot.json`), manages workstation scene modes, and
dispatches commands safely across threads.
"""

import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


PC_DIR = Path(__file__).resolve().parent.parent / "YumeCore" / "PC"
if str(PC_DIR) not in sys.path:
    sys.path.insert(0, str(PC_DIR))

from host import YumeCore  # noqa: E402
from workstation.sim_pico import SimulatedPicoNode, SimulatedTransport  # noqa: E402
from workstation.state_store import StateStore  # noqa: E402


SCENE_MODES: Dict[str, Dict[str, Any]] = {
    "standard": {
        "label": "标准实验模式",
        "description": "保持温度报警与环境光自动联动处于默认平衡态",
        "apps": {
            "thermal": {"enabled": True, "threshold": 45.0},
            "ambient_light": {"enabled": True, "dark_threshold": 35.0, "target_brightness": 60.0},
        },
        "devices": {"led": {"state": "OFF"}},
    },
    "focus": {
        "label": "专注工作模式",
        "description": "柔和补光常备（亮度 80%），提高暗光触发阈值并保持热警戒",
        "apps": {
            "thermal": {"enabled": True, "threshold": 42.0},
            "ambient_light": {"enabled": True, "dark_threshold": 55.0, "target_brightness": 80.0},
        },
    },
    "night_bench": {
        "label": "夜间电路台模式",
        "description": "适合夜间焊接与调试：高亮度工作台照明，温和指示灯",
        "apps": {
            "thermal": {"enabled": True, "threshold": 40.0},
            "ambient_light": {"enabled": True, "dark_threshold": 70.0, "target_brightness": 95.0},
        },
    },
    "alert_cool": {
        "label": "静音休眠模式",
        "description": "关闭自动补光与温控外设输出，仅保留后台传感器采样监控",
        "apps": {
            "thermal": {"enabled": False},
            "ambient_light": {"enabled": False},
        },
        "devices": {"led": {"state": "OFF"}, "actuator.desk_lamp": {"duty": 0}},
    },
}


class WorkstationHub:
    """
    Central PC coordinator for YumeLab.
    Thread-safe wrapper over `YumeCore` + background telemetry polling + `StateStore`.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        simulate: bool = True,
        poll_interval: float = 1.0,
        state_dir: Optional[Path] = None,
        sim_node: Optional[SimulatedPicoNode] = None,
    ):
        self.port = port
        self.simulate = simulate
        self.poll_interval = max(0.2, float(poll_interval))
        self.state_store = StateStore(state_dir=state_dir)

        self._io_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None

        self.sim_node: Optional[SimulatedPicoNode] = sim_node
        self.core: Optional[YumeCore] = None
        self._node_info: Optional[str] = None

    def connect(self) -> Dict[str, Any]:
        with self._io_lock:
            if self.core is not None:
                try:
                    self.core.close()
                except Exception:
                    pass
                self.core = None

            if self.simulate or not self.port:
                self.simulate = True
                if self.sim_node is None:
                    self.sim_node = SimulatedPicoNode()
                transport = SimulatedTransport(self.sim_node)
                self.core = YumeCore(transport=transport, timeout=2.0)
                mode_name = "simulated"
                port_label = "SIM-PICO-01"
            else:
                self.core = YumeCore(port=self.port, timeout=2.0)
                mode_name = "serial"
                port_label = self.port

            self._node_info = self.core.info()
            self.state_store.update_snapshot(
                connection={
                    "connected": True,
                    "mode": mode_name,
                    "port": port_label,
                    "node_info": self._node_info,
                    "last_error": None,
                }
            )
            self.state_store.record_event(
                source="hub",
                kind="connection",
                message=f"已连接到节点 ({port_label})",
                detail={"mode": mode_name, "info": self._node_info},
            )
            return self.poll_once()

    def start(self) -> None:
        if self.core is None:
            self.connect()
        if self._poll_thread is not None and self._poll_thread.is_alive():
            return
        self._stop_event.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            name="YumeLabHubPoller",
            daemon=True,
        )
        self._poll_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=2.5)
            self._poll_thread = None
        with self._io_lock:
            if self.core is not None:
                try:
                    self.core.close()
                except Exception:
                    pass
                self.core = None
            self.state_store.update_snapshot(connection={"connected": False})

    def _poll_loop(self) -> None:
        while not self._stop_event.wait(self.poll_interval):
            try:
                self.poll_once()
            except Exception as exc:
                self.state_store.update_snapshot(
                    connection={"connected": False, "last_error": str(exc)}
                )
                self.state_store.record_event("hub", "error", f"轮询异常: {exc}")

    def poll_once(self) -> Dict[str, Any]:
        with self._io_lock:
            if self.core is None:
                raise RuntimeError("Hub is not connected")

            raw_devices = self.core.devices.list()
            devices_map: Dict[str, Any] = {}
            for dev in raw_devices:
                dev_id = dev["id"]
                values: Dict[str, Any] = {}
                for prop_name, prop_meta in dev.get("properties", {}).items():
                    if prop_meta.get("readable", False):
                        values[prop_name] = self.core.devices.read(dev_id, prop_name)
                devices_map[dev_id] = {
                    **dev,
                    "values": values,
                }

            raw_apps = self.core.apps.list()
            apps_map: Dict[str, Any] = {}
            for app in raw_apps:
                app_name = app["name"]
                values = {}
                for prop_name, prop_meta in app.get("properties", {}).items():
                    if prop_meta.get("readable", False):
                        values[prop_name] = self.core.apps.read(app_name, prop_name)
                apps_map[app_name] = {
                    **app,
                    "values": values,
                }

            telemetry = {
                "temperature_c": devices_map.get("sensor.temperature", {}).get("values", {}).get("value"),
                "brightness_pct": devices_map.get("sensor.light", {}).get("values", {}).get("brightness"),
                "led_state": devices_map.get("led", {}).get("values", {}).get("state"),
                "desk_lamp_duty": devices_map.get("actuator.desk_lamp", {}).get("values", {}).get("duty"),
            }

            return self.state_store.update_snapshot(
                connection={"connected": True, "last_error": None},
                devices=devices_map,
                apps=apps_map,
                telemetry=telemetry,
            )

    def write_device(self, device_id: str, property_name: str, value: Any) -> Dict[str, Any]:
        with self._io_lock:
            if self.core is None:
                raise RuntimeError("Hub is not connected")
            new_val = self.core.devices.write(device_id, property_name, value)
            self.state_store.record_event(
                source="device",
                kind="write",
                message=f"设备 {device_id}.{property_name} -> {new_val}",
                detail={"device_id": device_id, "property": property_name, "value": new_val},
            )
            snapshot = self.poll_once()
            return {"device": device_id, "property": property_name, "value": new_val, "snapshot": snapshot}

    def write_app(self, app_name: str, property_name: str, value: Any) -> Dict[str, Any]:
        with self._io_lock:
            if self.core is None:
                raise RuntimeError("Hub is not connected")
            new_val = self.core.apps.write(app_name, property_name, value)
            self.state_store.record_event(
                source="app",
                kind="write",
                message=f"应用 {app_name}.{property_name} -> {new_val}",
                detail={"app": app_name, "property": property_name, "value": new_val},
            )
            snapshot = self.poll_once()
            return {"app": app_name, "property": property_name, "value": new_val, "snapshot": snapshot}

    def apply_mode(self, mode_name: str) -> Dict[str, Any]:
        if mode_name not in SCENE_MODES:
            raise ValueError(f"未知工作模式: {mode_name}")

        preset = SCENE_MODES[mode_name]
        with self._io_lock:
            if self.core is None:
                raise RuntimeError("Hub is not connected")

            for app_name, props in preset.get("apps", {}).items():
                for prop_name, prop_val in props.items():
                    try:
                        self.core.apps.write(app_name, prop_name, prop_val)
                    except Exception:
                        pass

            for dev_id, props in preset.get("devices", {}).items():
                for prop_name, prop_val in props.items():
                    try:
                        self.core.devices.write(dev_id, prop_name, prop_val)
                    except Exception:
                        pass

            self.state_store.update_snapshot(active_mode=mode_name)
            self.state_store.record_event(
                source="mode",
                kind="switch",
                message=f"切换工作模式至「{preset['label']}」({mode_name})",
                detail={"mode": mode_name},
            )
            return self.poll_once()

    def set_simulation_env(
        self,
        temp_c: Optional[float] = None,
        light_pct: Optional[float] = None,
        auto_wave: bool = False,
    ) -> Dict[str, Any]:
        if not self.simulate or self.sim_node is None:
            raise RuntimeError("当前不是仿真模式，无法注入虚拟环境参数")
        with self._io_lock:
            env = self.sim_node.set_environment(temp_c=temp_c, light_pct=light_pct, auto_wave=auto_wave)
            self.state_store.record_event(
                source="simulator",
                kind="env",
                message=f"仿真环境更新: 温度={env['ambient_temp_c']}°C, 光照={env['ambient_light_pct']}%",
                detail={"auto_wave": auto_wave, **env},
            )
            return self.poll_once()

    def get_snapshot(self) -> Dict[str, Any]:
        return self.state_store.get_snapshot()

    def get_history(self, limit: int = 60) -> List[Dict[str, Any]]:
        return self.state_store.get_history(limit=limit)

    def get_events(self, limit: int = 30) -> List[Dict[str, Any]]:
        return self.state_store.get_events(limit=limit)

    def get_modes(self) -> Dict[str, Dict[str, Any]]:
        return SCENE_MODES
