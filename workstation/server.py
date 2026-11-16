"""
YumeLab Workstation Web Server (FastAPI + Uvicorn + Stark-style HUD).

Exposes REST APIs and serves the real-time HUD dashboard from `workstation/static/`.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from workstation.cli_bridge import WebCLIBridge
from workstation.commander import WorkstationCommander
from workstation.hub import WorkstationHub


STATIC_DIR = Path(__file__).resolve().parent / "static"


class DeviceWriteRequest(BaseModel):
    value: Any
    sync_poll: bool = True


class AppWriteRequest(BaseModel):
    value: Any


class ModeSwitchRequest(BaseModel):
    mode: str


class SimEnvRequest(BaseModel):
    temp_c: Optional[float] = None
    light_pct: Optional[float] = None
    auto_wave: bool = False


class CommandRequest(BaseModel):
    text: str


class ToolExecuteRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any] = {}


class PianoPlayRequest(BaseModel):
    sheet: str


def create_app(
    hub: Optional[WorkstationHub] = None,
    port: Optional[str] = None,
    simulate: bool = True,
    poll_interval: float = 1.0,
) -> FastAPI:
    owned_hub = hub is None
    active_hub = hub or WorkstationHub(port=port, simulate=simulate, poll_interval=poll_interval)
    commander = WorkstationCommander(active_hub)
    cli_bridge = WebCLIBridge(active_hub)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if owned_hub:
            active_hub.start()
        elif active_hub.core is None:
            active_hub.connect()
        try:
            yield
        finally:
            if owned_hub:
                active_hub.stop()

    app = FastAPI(title="YumeLab Workstation HUD API", version="1.0.0", lifespan=lifespan)
    app.state.hub = active_hub
    app.state.commander = commander

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="HUD frontend not found")
        return FileResponse(str(index_path))

    @app.get("/api/health")
    def health():
        snap = active_hub.get_snapshot()
        return {"ok": True, "connection": snap.get("connection")}

    @app.get("/api/state")
    def get_state():
        return {
            "snapshot": active_hub.get_snapshot(),
            "history": active_hub.get_history(limit=60),
            "events": active_hub.get_events(limit=25),
            "modes": active_hub.get_modes(),
            "sheets": active_hub.get_piano_sheets(),
        }

    @app.post("/api/poll")
    def force_poll():
        try:
            return {"ok": True, "snapshot": active_hub.poll_once()}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/devices/{device_id}/properties/{prop_name}")
    def write_device_prop(device_id: str, prop_name: str, body: DeviceWriteRequest):
        try:
            return active_hub.write_device(device_id, prop_name, body.value, sync_poll=body.sync_poll)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/apps/{app_name}/properties/{prop_name}")
    def write_app_prop(app_name: str, prop_name: str, body: AppWriteRequest):
        try:
            return active_hub.write_app(app_name, prop_name, body.value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/mode")
    def switch_mode(body: ModeSwitchRequest):
        try:
            snapshot = active_hub.apply_mode(body.mode)
            return {"ok": True, "snapshot": snapshot}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/sim/env")
    def update_sim_env(body: SimEnvRequest):
        try:
            snapshot = active_hub.set_simulation_env(
                temp_c=body.temp_c,
                light_pct=body.light_pct,
                auto_wave=body.auto_wave,
            )
            return {"ok": True, "snapshot": snapshot}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/tools")
    def list_tools():
        return {"tools": commander.get_tool_schemas()}

    @app.post("/api/tools/execute")
    def execute_tool(body: ToolExecuteRequest):
        try:
            return commander.execute_tool(body.tool, body.arguments)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/command")
    def natural_language_command(body: CommandRequest):
        return commander.interpret_and_execute(body.text)

    @app.post("/api/cli")
    def terminal_command(body: CommandRequest):
        return cli_bridge.execute_line(body.text)

    @app.get("/api/piano/sheets")
    def list_piano_sheets():
        return {
            "sheets": active_hub.get_piano_sheets(),
            "player": active_hub.get_piano_status(),
        }

    @app.post("/api/piano/play")
    def play_piano_sheet(body: PianoPlayRequest):
        try:
            return active_hub.play_piano_sheet(body.sheet)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/piano/pause")
    def pause_piano():
        try:
            return active_hub.pause_piano()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/piano/resume")
    def resume_piano():
        try:
            return active_hub.resume_piano()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    @app.post("/api/piano/stop")
    def stop_piano():
        try:
            return active_hub.stop_piano()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return app
