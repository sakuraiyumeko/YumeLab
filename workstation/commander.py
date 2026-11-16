"""
YumeLab Workstation Commander (Natural Language & Tool Dispatch Layer).

Provides unified structured tool capabilities over `WorkstationHub`,
plus a reliable bilingual natural-language intent parser so users can
command the workstation in Chinese or English out-of-the-box without
requiring external API keys (while also exposing OpenAI/Anthropic-style
JSON tool schemas for future LLM integration).
"""

import re
from typing import Any, Dict, List, Optional

from workstation.hub import SCENE_MODES, WorkstationHub


TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "get_workstation_status",
        "description": "获取当前工作站设备状态、传感器读数、应用配置与工作模式快照。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "write_device",
        "description": "控制指定硬件设备的可写属性，如 led.state (ON/OFF/TOGGLE) 或 actuator.desk_lamp.duty (0-100)。",
        "parameters": {
            "type": "object",
            "properties": {
                "device_id": {"type": "string"},
                "property": {"type": "string"},
                "value": {},
            },
            "required": ["device_id", "property", "value"],
        },
    },
    {
        "name": "write_app",
        "description": "修改自动化应用参数，如 thermal.threshold、thermal.enabled、ambient_light.dark_threshold、ambient_light.target_brightness。",
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {"type": "string"},
                "property": {"type": "string"},
                "value": {},
            },
            "required": ["app_name", "property", "value"],
        },
    },
    {
        "name": "switch_mode",
        "description": "切换工作站预设场景模式（standard / focus / night_bench / alert_cool）。",
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": list(SCENE_MODES.keys())},
            },
            "required": ["mode"],
        },
    },
    {
        "name": "set_simulation_env",
        "description": "在仿真模式下调整虚拟环境温度与光照，用于测试传感器联动效果。",
        "parameters": {
            "type": "object",
            "properties": {
                "temp_c": {"type": "number"},
                "light_pct": {"type": "number"},
                "auto_wave": {"type": "boolean"},
            },
        },
    },
]


class WorkstationCommander:
    """
    Executes structured workstation tools and natural-language commands.
    """

    def __init__(self, hub: WorkstationHub):
        self.hub = hub

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return TOOL_SCHEMAS

    def execute_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = arguments or {}
        if tool_name == "get_workstation_status":
            return {"ok": True, "tool": tool_name, "result": self.hub.get_snapshot()}
        elif tool_name == "write_device":
            res = self.hub.write_device(args["device_id"], args["property"], args["value"])
            return {"ok": True, "tool": tool_name, "result": res}
        elif tool_name == "write_app":
            res = self.hub.write_app(args["app_name"], args["property"], args["value"])
            return {"ok": True, "tool": tool_name, "result": res}
        elif tool_name == "switch_mode":
            snap = self.hub.apply_mode(args["mode"])
            return {"ok": True, "tool": tool_name, "result": snap}
        elif tool_name == "set_simulation_env":
            if not self.hub.simulate:
                return {
                    "ok": False,
                    "tool": tool_name,
                    "error": "NOT_SIMULATED",
                    "message": "当前工作站正连接着真实物理 Pico 节点，真实环境温度和光照由物理传感器采集，无法注入虚拟仿真参数哦！若要测试虚拟环境，启动时请加上 --simulate-only 参数。",
                }
            snap = self.hub.set_simulation_env(
                temp_c=args.get("temp_c"),
                light_pct=args.get("light_pct"),
                auto_wave=bool(args.get("auto_wave", False)),
            )
            return {"ok": True, "tool": tool_name, "result": snap}
        raise ValueError(f"未知工具: {tool_name}")

    def interpret_and_execute(self, command_text: str) -> Dict[str, Any]:
        """
        Parses natural language (Chinese / English) into tool calls and executes them.
        """
        text = (command_text or "").strip()
        if not text:
            return {"ok": False, "reply": "指令不能为空，试试说「查看当前状态」或「把台灯调到 80%」。", "actions": []}

        lower = text.lower()
        actions: List[Dict[str, Any]] = []
        replies: List[str] = []

        # 1. Mode switches
        if any(k in lower for k in ("专注模式", "focus mode", "工作模式", "focus")):
            res = self.execute_tool("switch_mode", {"mode": "focus"})
            actions.append({"tool": "switch_mode", "args": {"mode": "focus"}, "ok": True})
            replies.append("已切换至「专注工作模式」：补光目标亮度 80%，暗光触发阈值 55%，温控阈值 42°C。")
        elif any(k in lower for k in ("夜间模式", "焊接模式", "夜班", "night_bench", "night bench", "夜间电路")):
            res = self.execute_tool("switch_mode", {"mode": "night_bench"})
            actions.append({"tool": "switch_mode", "args": {"mode": "night_bench"}, "ok": True})
            replies.append("已切换至「夜间电路台模式」：补光目标亮度 95%，暗光触发阈值 70%，温控警戒 40°C。")
        elif any(k in lower for k in ("休眠", "静音模式", "全部关闭", "alert_cool", "sleep mode")):
            self.execute_tool("switch_mode", {"mode": "alert_cool"})
            actions.append({"tool": "switch_mode", "args": {"mode": "alert_cool"}, "ok": True})
            replies.append("已切换至「静音休眠模式」：已关闭自动联动与灯光输出，仅维持后台传感监控。")
        elif any(k in lower for k in ("标准模式", "默认模式", "恢复默认", "standard mode", "standard")):
            self.execute_tool("switch_mode", {"mode": "standard"})
            actions.append({"tool": "switch_mode", "args": {"mode": "standard"}, "ok": True})
            replies.append("已恢复「标准实验模式」。")

        # 2. Buzzer and Audio effects
        if any(k in lower for k in ("开机音", "启动音", "开机音乐", "stark boot", "boot sound")):
            self.execute_tool("write_device", {"device_id": "actuator.buzzer.passive", "property": "sfx", "value": "stark_boot"})
            actions.append({"tool": "write_device", "args": {"device_id": "actuator.buzzer.passive", "property": "sfx", "value": "stark_boot"}, "ok": True})
            replies.append("已播放「斯塔克战甲启动音效」🎵")
        elif any(k in lower for k in ("哔", "响一下", "蜂鸣", "警报音", "beep", "alert tone")):
            self.execute_tool("write_device", {"device_id": "actuator.buzzer.passive", "property": "sfx", "value": "alert"})
            actions.append({"tool": "write_device", "args": {"device_id": "actuator.buzzer.passive", "property": "sfx", "value": "alert"}, "ok": True})
            replies.append("无源蜂鸣器已拉响提示警报音效！")
        elif any(k in lower for k in ("静音", "别叫", "闭嘴", "mute", "stop sound")):
            self.execute_tool("write_device", {"device_id": "actuator.buzzer.passive", "property": "sfx", "value": "mute"})
            try:
                self.execute_tool("write_device", {"device_id": "actuator.buzzer.active", "property": "state", "value": "OFF"})
            except Exception:
                pass
            actions.append({"tool": "write_device", "args": {"device_id": "actuator.buzzer.passive", "property": "sfx", "value": "mute"}, "ok": True})
            replies.append("已静音所有蜂鸣器输出。")

        # 3. Desk lamp brightness / PWM duty
        lamp_duty_match = re.search(
            r"(?:台灯|桌面灯|补光|灯带|lamp|desk_lamp).*?(\d+(?:\.\d+)?)\s*%?",
            lower,
        )
        if lamp_duty_match and any(k in lower for k in ("调", "设", "亮", "duty", "set", "to", "成", "到")):
            duty = max(0.0, min(100.0, float(lamp_duty_match.group(1))))
            # If user explicitly controls lamp duty, pause ambient_light auto overwrite so manual value sticks
            self.execute_tool("write_app", {"app_name": "ambient_light", "property": "enabled", "value": False})
            self.execute_tool("write_device", {"device_id": "actuator.desk_lamp", "property": "duty", "value": duty})
            actions.append({"tool": "write_device", "args": {"device_id": "actuator.desk_lamp", "property": "duty", "value": duty}, "ok": True})
            replies.append(f"已手动将桌面补光灯亮度设置为 {duty:.0f}%（已暂挂自动光控以免被覆盖）。")
        elif any(k in lower for k in ("开台灯", "打开台灯", "打开补光", "开补光", "turn on lamp", "lamp on")):
            self.execute_tool("write_app", {"app_name": "ambient_light", "property": "enabled", "value": False})
            self.execute_tool("write_device", {"device_id": "actuator.desk_lamp", "property": "duty", "value": 80})
            actions.append({"tool": "write_device", "args": {"device_id": "actuator.desk_lamp", "property": "duty", "value": 80}, "ok": True})
            replies.append("已打开桌面补光灯（80% 亮度）。")
        elif any(k in lower for k in ("关台灯", "关闭台灯", "关补光", "关闭补光", "turn off lamp", "lamp off")):
            self.execute_tool("write_app", {"app_name": "ambient_light", "property": "enabled", "value": False})
            self.execute_tool("write_device", {"device_id": "actuator.desk_lamp", "property": "duty", "value": 0})
            actions.append({"tool": "write_device", "args": {"device_id": "actuator.desk_lamp", "property": "duty", "value": 0}, "ok": True})
            replies.append("已关闭桌面补光灯。")

        # 3. Board LED control
        if any(k in lower for k in ("打开led", "开led", "开灯", "led on", "点亮led", "打开指示灯")) and "台灯" not in lower:
            self.execute_tool("write_device", {"device_id": "led", "property": "state", "value": "ON"})
            actions.append({"tool": "write_device", "args": {"device_id": "led", "property": "state", "value": "ON"}, "ok": True})
            replies.append("已点亮板载 LED。")
        elif any(k in lower for k in ("关闭led", "关led", "关灯", "led off", "熄灭led", "关闭指示灯")) and "台灯" not in lower:
            self.execute_tool("write_device", {"device_id": "led", "property": "state", "value": "OFF"})
            actions.append({"tool": "write_device", "args": {"device_id": "led", "property": "state", "value": "OFF"}, "ok": True})
            replies.append("已熄灭板载 LED。")

        # 4. Thermal threshold & auto toggle
        temp_thresh_match = re.search(
            r"(?:温控|温度|报警|热|thermal).*?(?:阈值|threshold)?[^\d-]*(-?\d+(?:\.\d+)?)\s*(?:度|c|℃)?",
            lower,
        )
        if temp_thresh_match and any(k in lower for k in ("阈值", "改", "设", "调", "threshold", "set")) and "模拟" not in lower and "仿真" not in lower:
            thresh = float(temp_thresh_match.group(1))
            self.execute_tool("write_app", {"app_name": "thermal", "property": "threshold", "value": thresh})
            actions.append({"tool": "write_app", "args": {"app_name": "thermal", "property": "threshold", "value": thresh}, "ok": True})
            replies.append(f"已将温控报警阈值调整为 {thresh:.1f}°C。")

        if any(k in lower for k in ("开启自动光控", "打开自动光控", "开启光控", "启用光控", "auto light on")):
            self.execute_tool("write_app", {"app_name": "ambient_light", "property": "enabled", "value": True})
            actions.append({"tool": "write_app", "args": {"app_name": "ambient_light", "property": "enabled", "value": True}, "ok": True})
            replies.append("已启用自动光控补光应用。")
        elif any(k in lower for k in ("关闭自动光控", "停用光控", "关闭光控", "auto light off")):
            self.execute_tool("write_app", {"app_name": "ambient_light", "property": "enabled", "value": False})
            actions.append({"tool": "write_app", "args": {"app_name": "ambient_light", "property": "enabled", "value": False}, "ok": True})
            replies.append("已停用自动光控补光应用。")

        if any(k in lower for k in ("开启温控", "打开温控", "启用温控", "auto on")):
            self.execute_tool("write_app", {"app_name": "thermal", "property": "enabled", "value": True})
            actions.append({"tool": "write_app", "args": {"app_name": "thermal", "property": "enabled", "value": True}, "ok": True})
            replies.append("已启用温控自动联动。")
        elif any(k in lower for k in ("关闭温控", "停用温控", "auto off")):
            self.execute_tool("write_app", {"app_name": "thermal", "property": "enabled", "value": False})
            actions.append({"tool": "write_app", "args": {"app_name": "thermal", "property": "enabled", "value": False}, "ok": True})
            replies.append("已停用温控自动联动。")

        # 5. Simulation environment override
        if any(k in lower for k in ("模拟", "仿真", "sim", "环境")):
            sim_args: Dict[str, Any] = {}
            t_match = re.search(r"(?:温度|temp)[^\d-]*(-?\d+(?:\.\d+)?)", lower)
            l_match = re.search(r"(?:光照|亮度|light)[^\d]*(\d+(?:\.\d+)?)", lower)
            if "自动波动" in lower or "恢复波动" in lower or "wave" in lower:
                sim_args["auto_wave"] = True
            if t_match:
                sim_args["temp_c"] = float(t_match.group(1))
            if l_match:
                sim_args["light_pct"] = float(l_match.group(1))
            if sim_args:
                res = self.execute_tool("set_simulation_env", sim_args)
                if res.get("ok"):
                    actions.append({"tool": "set_simulation_env", "args": sim_args, "ok": True})
                    replies.append(f"已更新虚拟环境参数：{sim_args}。")
                else:
                    actions.append({"tool": "set_simulation_env", "args": sim_args, "ok": False, "error": res.get("message")})
                    replies.append(res.get("message", "当前连接的是真实硬件，无法注入虚拟环境参数。"))

        # 6. Status / sensor inquiry
        is_query = any(k in lower for k in ("状态", "多少", "温度", "光照", "亮度", "汇报", "报告", "status", "report", "情况", "看看"))
        if is_query or not actions:
            snap = self.hub.get_snapshot()
            tel = snap.get("telemetry", {})
            mode = snap.get("workstation", {}).get("active_mode")
            status_line = (
                f"当前模式 [{mode}] ｜ 温度: {tel.get('temperature_c')}°C ｜ "
                f"环境光: {tel.get('brightness_pct')}% ｜ 板载 LED: {tel.get('led_state')} ｜ "
                f"桌面补光灯: {tel.get('desk_lamp_duty')}%"
            )
            if not actions:
                actions.append({"tool": "get_workstation_status", "args": {}, "ok": True})
                if is_query:
                    replies.append(status_line)
                else:
                    replies.append(
                        "我暂时没完全识别你的具体操控意图，先给你汇报最新读数：\n"
                        + status_line
                        + "\n你可以试试：「切换到专注模式」「把台灯调到 75%」「把温控阈值设为 40 度」「模拟光照 20 温度 46」。"
                    )
            elif is_query:
                replies.append(status_line)

        self.hub.state_store.record_event(
            source="commander",
            kind="command",
            message=f"自然语言指令: {text}",
            detail={"actions": actions},
        )
        return {
            "ok": True,
            "input": text,
            "reply": "\n".join(replies),
            "actions": actions,
            "snapshot": self.hub.get_snapshot(),
        }
