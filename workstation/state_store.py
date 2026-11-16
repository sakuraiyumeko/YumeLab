"""
YumeLab State Store.
Manages persistent workstation snapshots, telemetry time-series history,
event logs, and workstation scene modes inside the `state/` directory.
"""

import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional


DEFAULT_STATE_DIR = Path(__file__).resolve().parent.parent / "state"


def utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StateStore:
    """
    Thread-safe manager for workstation state snapshots and recent telemetry.
    Writes atomic JSON snapshots into `state/snapshot.json` and recent events
    into `state/events.jsonl` while keeping bounded ring buffers in memory.
    """

    def __init__(
        self,
        state_dir: Optional[Path] = None,
        history_limit: int = 120,
        event_limit: int = 80,
    ):
        self.state_dir = Path(state_dir) if state_dir is not None else DEFAULT_STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.snapshot_file = self.state_dir / "snapshot.json"
        self.events_file = self.state_dir / "events.jsonl"
        self.config_file = self.state_dir / "workstation_config.json"

        self._lock = threading.RLock()
        self._history: Deque[Dict[str, Any]] = deque(maxlen=history_limit)
        self._events: Deque[Dict[str, Any]] = deque(maxlen=event_limit)

        self._snapshot: Dict[str, Any] = {
            "timestamp": utc_iso_now(),
            "connection": {
                "connected": False,
                "mode": "uninitialized",
                "port": None,
                "node_info": None,
                "last_error": None,
            },
            "workstation": {
                "active_mode": "standard",
                "available_modes": ["standard", "focus", "night_bench", "alert_cool"],
            },
            "devices": {},
            "apps": {},
            "telemetry": {
                "temperature_c": None,
                "brightness_pct": None,
                "led_state": None,
                "desk_lamp_duty": None,
            },
        }
        self._load_persisted_config()

    def _load_persisted_config(self) -> None:
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                if "active_mode" in data:
                    self._snapshot["workstation"]["active_mode"] = data["active_mode"]
            except Exception:
                pass

    def save_config(self, config: Dict[str, Any]) -> None:
        with self._lock:
            tmp = self.config_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.config_file)

    def update_snapshot(
        self,
        connection: Optional[Dict[str, Any]] = None,
        devices: Optional[Dict[str, Any]] = None,
        apps: Optional[Dict[str, Any]] = None,
        telemetry: Optional[Dict[str, Any]] = None,
        active_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            self._snapshot["timestamp"] = utc_iso_now()
            if connection is not None:
                self._snapshot["connection"].update(connection)
            if devices is not None:
                self._snapshot["devices"] = devices
            if apps is not None:
                self._snapshot["apps"] = apps
            if telemetry is not None:
                self._snapshot["telemetry"].update(telemetry)
                self._history.append({
                    "timestamp": self._snapshot["timestamp"],
                    "epoch_ms": int(time.time() * 1000),
                    **self._snapshot["telemetry"],
                })
            if active_mode is not None:
                self._snapshot["workstation"]["active_mode"] = active_mode
                self.save_config({"active_mode": active_mode})

            self._persist_snapshot_unlocked()
            return self.get_snapshot()

    def _persist_snapshot_unlocked(self) -> None:
        payload = {
            **self._snapshot,
            "history_count": len(self._history),
        }
        tmp = self.snapshot_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.snapshot_file)

    def record_event(self, source: str, kind: str, message: str, detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        entry = {
            "timestamp": utc_iso_now(),
            "source": source,
            "kind": kind,
            "message": message,
            "detail": detail or {},
        }
        with self._lock:
            self._events.appendleft(entry)
            try:
                with self.events_file.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception:
                pass
        return entry

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._snapshot))

    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._history)
            if limit is not None and limit > 0:
                return items[-limit:]
            return items

    def get_events(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._events)[:limit]
