"""
YumeLab Workstation Launcher.

Run the full pure-software workstation (Simulated Pico + PC Hub + HUD + Commander):
    python run_workstation.py

Or connect to a physical Pico on serial port COM7:
    python run_workstation.py --port COM7

Or run an interactive natural-language CLI session without starting HTTP server:
    python run_workstation.py --cli
"""

import argparse
import threading
import webbrowser

import uvicorn

from workstation.commander import WorkstationCommander
from workstation.hub import WorkstationHub
from workstation.server import create_app


def run_cli(hub: WorkstationHub) -> None:
    commander = WorkstationCommander(hub)
    hub.start()
    print("YumeLab Workstation Commander CLI (输入 'exit' 退出)")
    try:
        while True:
            try:
                line = input("YumeLab> ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line.lower() in ("exit", "quit"):
                break
            res = commander.interpret_and_execute(line)
            print(res["reply"])
    finally:
        hub.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="YumeLab Modular Workstation Launcher")
    parser.add_argument("--port", default=None, help="Serial port (e.g. COM7). Auto-detects COM7 if connected.")
    parser.add_argument("--simulate-only", action="store_true", help="Force pure-software simulation even if physical Pico is plugged in")
    parser.add_argument("--host", default="127.0.0.1", help="HUD web server bind host (default: 127.0.0.1)")
    parser.add_argument("--http-port", type=int, default=8000, help="HUD web server port (default: 8000)")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Hub polling interval in seconds")
    parser.add_argument("--open-browser", action="store_true", help="Automatically open HUD in browser")
    parser.add_argument("--cli", action="store_true", help="Run interactive natural-language CLI instead of web server")
    args = parser.parse_args()

    simulate = args.port is None and not args.port
    # Auto-detect COM7 or any active Pico serial device if not specified
    target_port = args.port
    if target_port is None and not args.simulate_only:
        # Check if COM7 or Pico device exists
        try:
            import serial.tools.list_ports
            ports = [p.device for p in serial.tools.list_ports.comports()]
            if "COM7" in ports:
                target_port = "COM7"
                simulate = False
        except Exception:
            pass

    if args.simulate_only:
        simulate = True
        target_port = None
    if args.cli:
        hub = WorkstationHub(port=target_port, simulate=simulate, poll_interval=args.poll_interval)
        run_cli(hub)
        return

    app = create_app(port=target_port, simulate=simulate, poll_interval=args.poll_interval)
    if args.open_browser:
        url = f"http://{args.host}:{args.http_port}/"
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=args.host, port=args.http_port, log_level="info")


if __name__ == "__main__":
    main()
