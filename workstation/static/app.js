// YumeLab White Lab Workstation Controller & Integrated Terminal
const SFX_PRESETS_OPTIONS = [
  "click",
  "beep",
  "tone_up",
  "tone_down",
  "stark_boot",
  "alert",
  "victory",
  "mute",
];

const MORSE_MAP = {
  A: ".-", B: "-...", C: "-.-.", D: "-..", E: ".",
  F: "..-.", G: "--.", H: "....", I: "..", J: ".---",
  K: "-.-", L: ".-..", M: "--", N: "-.", O: "---",
  P: ".--.", Q: "--.-", R: ".-.", S: "...", T: "-",
  U: "..-", V: "...-", W: ".--", X: "-..-", Y: "-.--",
  Z: "--..",
  "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
  "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
  "?": "..--..", "/": "-..-.", "-": "-....-", ".": ".-.-.-", ",": "--..--",
  ":": "---...", "=": "-...-", "+": ".-.-.", "!": "-.-.--",
};

function textToMorse(text) {
  return (text || "")
    .toUpperCase()
    .split("")
    .map((ch) => (ch === " " ? "/" : MORSE_MAP[ch] || ""))
    .filter(Boolean)
    .join(" ");
}

const state = {
  simEditing: false,
  isRefreshing: false,
  modesCacheKey: "",
  sheetsCacheKey: "",
  authoritative: new Map(),
  queues: new Map(),
  globalSeq: 0,
  termHistory: [],
  termHistoryIdx: -1,
};

function enqueueMutation(key, targetValue, mutationFn) {
  state.globalSeq += 1;
  const mySeq = state.globalSeq;
  state.authoritative.set(key, { value: targetValue, seq: mySeq, timestamp: Date.now() });

  const prevPromise = state.queues.get(key) || Promise.resolve();
  const nextPromise = prevPromise
    .catch(() => {})
    .then(async () => {
      try {
        const res = await mutationFn();
        // 延时保留 authoritative 状态 2 秒，防止背景轮询返回滞后的旧快照导致按钮闪烁回弹
        setTimeout(() => {
          const current = state.authoritative.get(key);
          if (current && current.seq === mySeq) {
            state.authoritative.delete(key);
          }
        }, 2000);

        if (res && res.snapshot) {
          applyState(res.snapshot);
        }
      } catch (err) {
        console.error(`Mutation failed for ${key}:`, err);
        state.authoritative.delete(key);
        refreshState();
      }
    });

  state.queues.set(key, nextPromise);
}

function getAuthoritativeValue(key, fallbackVal) {
  if (state.authoritative.has(key)) {
    return state.authoritative.get(key).value;
  }
  return fallbackVal;
}

async function api(url, method = "GET", body = null) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== null) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  let data;
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    data = await res.json();
  } else {
    const rawText = await res.text();
    data = { detail: rawText || `HTTP ${res.status}` };
  }
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

function updateClock() {
  const now = new Date();
  document.getElementById("utcClock").textContent = now.toTimeString().slice(0, 8);
}
setInterval(updateClock, 1000);
updateClock();

function appendChat(role, text) {
  const log = document.getElementById("chatLog");
  const div = document.createElement("div");
  div.className = `msg-bubble ${role}`;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

/* Canvas Chart */
function renderChart(history) {
  const canvas = document.getElementById("telemetryChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  ctx.strokeStyle = "rgba(148, 163, 184, 0.25)";
  ctx.lineWidth = 1;
  for (let i = 1; i <= 3; i++) {
    const y = (h / 4) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }

  if (!history || history.length < 2) return;

  const drawSeries = (vals, minV, maxV, color) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    vals.forEach((v, idx) => {
      const x = (idx / (vals.length - 1)) * (w - 20) + 10;
      const ratio = Math.max(0, Math.min(1, (v - minV) / (maxV - minV)));
      const y = h - 12 - ratio * (h - 24);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  };

  const temps = history.map((p) => Number(p.temperature_c ?? 25));
  const lights = history.map((p) => Number(p.brightness_pct ?? 50));
  drawSeries(temps, 15, 60, "#d97706");
  drawSeries(lights, 0, 100, "#0284c7");
}

/* Mode Switches */
function renderModes(modes, activeMode) {
  const container = document.getElementById("modeButtons");
  const keys = Object.keys(modes || {});
  const cacheKey = keys.join("|");
  const currentMode = getAuthoritativeValue("mode", activeMode);

  if (state.modesCacheKey !== cacheKey) {
    container.innerHTML = "";
    keys.forEach((key) => {
      const meta = modes[key];
      const btn = document.createElement("button");
      btn.className = `mode-btn ${key === currentMode ? "active" : ""}`;
      btn.dataset.modeKey = key;
      btn.innerHTML = `<div class="m-title">${meta.label}</div><div class="m-desc">${meta.description}</div>`;
      btn.onclick = () => {
        container.querySelectorAll(".mode-btn").forEach((b) => {
          b.classList.toggle("active", b.dataset.modeKey === key);
        });
        document.getElementById("activeModeBadge").textContent = key.toUpperCase();
        enqueueMutation("mode", key, () => api("/api/mode", "POST", { mode: key }));
      };
      container.appendChild(btn);
    });
    state.modesCacheKey = cacheKey;
    return;
  }

  container.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.modeKey === currentMode);
  });
}

/* Instrument Rack Physical Controls Setup */
function setupInstrumentRack() {
  // Board LED Physical Rocker Switch
  const swLed = document.getElementById("swLedToggle");
  if (swLed) {
    swLed.addEventListener("click", () => {
      const current = getAuthoritativeValue("device:led:state", document.getElementById("kpiLed").textContent);
      const nextVal = current === "ON" ? "OFF" : "ON";
      swLed.classList.toggle("checked", nextVal === "ON");
      document.getElementById("kpiLed").textContent = nextVal;

      enqueueMutation("device:led:state", nextVal, () =>
        api("/api/devices/led/properties/state", "POST", { value: nextVal, sync_poll: true })
      );
    });
  }

  // Active Buzzer Alarm Burst
  document.getElementById("activeBuzzerBeepBtn")?.addEventListener("click", async () => {
    try {
      await api("/api/devices/actuator.buzzer.active/properties/beep", "POST", { value: 2, sync_poll: false });
      appendTerminalLine("Active buzzer alarm: 2 beeps triggered.", "res");
    } catch (err) {
      console.error(err);
    }
  });

  // Active Buzzer Morse Telegraph
  const morseInput = document.getElementById("morseInput");
  const morseSendBtn = document.getElementById("morseSendBtn");
  const morsePreview = document.getElementById("morsePreviewText");

  const updateMorsePreview = () => {
    if (morseInput && morsePreview) {
      morsePreview.textContent = textToMorse(morseInput.value) || "(无编码)";
    }
  };
  morseInput?.addEventListener("input", updateMorsePreview);
  updateMorsePreview();

  const sendMorse = async (text) => {
    const raw = (text || "").trim().toUpperCase();
    if (!raw) return;
    try {
      await api("/api/devices/actuator.buzzer.active/properties/morse", "POST", { value: raw, sync_poll: false });
      appendTerminalLine(`Morse transmitting: ${raw} [${textToMorse(raw)}]`, "res");
    } catch (err) {
      appendTerminalLine(`Morse error: ${err.message}`, "err");
    }
  };

  morseSendBtn?.addEventListener("click", () => sendMorse(morseInput?.value));
  morseInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendMorse(morseInput.value);
    }
  });

  document.querySelectorAll(".chip-btn.mini-chip[data-morse]").forEach((chip) => {
    chip.addEventListener("click", () => {
      const code = chip.dataset.morse;
      if (morseInput) {
        morseInput.value = code;
        updateMorsePreview();
      }
      sendMorse(code);
    });
  });

  // Desk Lamp PWM Fader
  const faderLamp = document.getElementById("faderLampRange");
  const faderLampVal = document.getElementById("faderLampVal");
  if (faderLamp && faderLampVal) {
    faderLamp.addEventListener("input", () => {
      faderLampVal.textContent = `${faderLamp.value} %`;
    });
    faderLamp.addEventListener("change", () => {
      const val = Number(faderLamp.value);
      // Temporarily pause auto ambient_light so manual duty stays
      api("/api/apps/ambient_light/properties/enabled", "POST", { value: false }).catch(() => {});
      enqueueMutation("device:actuator.desk_lamp:duty", val, () =>
        api("/api/devices/actuator.desk_lamp/properties/duty", "POST", { value: val, sync_poll: false })
      );
    });
  }

  // Thermal Threshold Fader
  const faderTherm = document.getElementById("faderThermalRange");
  const faderThermVal = document.getElementById("faderThermalVal");
  if (faderTherm && faderThermVal) {
    faderTherm.addEventListener("input", () => {
      faderThermVal.textContent = `${Number(faderTherm.value).toFixed(1)} °C`;
    });
    faderTherm.addEventListener("change", () => {
      const val = Number(faderTherm.value);
      enqueueMutation("app:thermal:threshold", val, () =>
        api("/api/apps/thermal/properties/threshold", "POST", { value: val })
      );
    });
  }

  // Buzzer Sheet Player Controls
  const playBtn = document.getElementById("playerPlayBtn");
  const pauseBtn = document.getElementById("playerPauseBtn");
  const stopBtn = document.getElementById("playerStopBtn");
  const sheetSel = document.getElementById("sheetSelect");

  playBtn?.addEventListener("click", async () => {
    const sheet = sheetSel?.value;
    if (!sheet) return;
    try {
      const res = await api("/api/piano/play", "POST", { sheet });
      if (res.snapshot) applyState(res.snapshot);
      appendTerminalLine(`Piano play: ${sheet}`, "res");
    } catch (err) {
      appendTerminalLine(`Piano error: ${err.message}`, "err");
    }
  });

  pauseBtn?.addEventListener("click", async () => {
    const badge = document.getElementById("playerStateBadge");
    const isPaused = badge?.textContent === "PAUSED";
    try {
      const res = await api(isPaused ? "/api/piano/resume" : "/api/piano/pause", "POST");
      if (res.snapshot) applyState(res.snapshot);
    } catch (err) {
      appendTerminalLine(`Piano error: ${err.message}`, "err");
    }
  });

  stopBtn?.addEventListener("click", async () => {
    try {
      const res = await api("/api/piano/stop", "POST");
      if (res.snapshot) applyState(res.snapshot);
    } catch (err) {
      appendTerminalLine(`Piano error: ${err.message}`, "err");
    }
  });
}

function renderSheets(sheets) {
  const select = document.getElementById("sheetSelect");
  if (!select) return;
  const key = (sheets || []).map((s) => s.id).join("|");
  if (state.sheetsCacheKey === key) return;
  state.sheetsCacheKey = key;

  const prev = select.value;
  select.innerHTML = "";
  if (!sheets || sheets.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "(暂无可用乐谱)";
    select.appendChild(opt);
    return;
  }
  sheets.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = `${s.title} (${s.bpm} BPM · ${s.notes}音符)`;
    select.appendChild(opt);
  });
  if (prev && sheets.some((s) => s.id === prev)) {
    select.value = prev;
  }
}

function renderPlayerStatus(player) {
  if (!player) return;
  const badge = document.getElementById("playerStateBadge");
  const titleEl = document.getElementById("playerNowTitle");
  const progEl = document.getElementById("playerProgressText");
  const barEl = document.getElementById("playerProgressBar");
  const pauseBtn = document.getElementById("playerPauseBtn");

  const st = player.state || "IDLE";
  if (badge) {
    badge.textContent = st;
    badge.classList.toggle("playing", st === "PLAYING");
    badge.classList.toggle("paused", st === "PAUSED");
  }
  if (pauseBtn) {
    pauseBtn.textContent = st === "PAUSED" ? "▶ 继续" : "⏸ 暂停";
  }
  if (titleEl) {
    titleEl.textContent = player.title ? `${player.title} (BPM=${player.bpm || 120})` : "待机中 · 请选择乐谱";
  }
  const cur = Number(player.progress || 0);
  const tot = Number(player.total || 0);
  if (progEl) progEl.textContent = `${cur} / ${tot}`;
  if (barEl) barEl.style.width = tot > 0 ? `${Math.round((cur / tot) * 100)}%` : "0%";
}

/* Micro Entities Updates */
function updateDevices(devices) {
  const container = document.getElementById("devicesContainer");
  const activeEl = document.activeElement;

  Object.values(devices || {}).forEach((dev) => {
    let card = container.querySelector(`[data-device-id="${CSS.escape(dev.id)}"]`);
    if (!card) {
      card = document.createElement("div");
      card.className = "kpi-box";
      card.dataset.deviceId = dev.id;
      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <span style="font-weight:700; font-size:0.86rem; color:var(--text-main);">${dev.id}</span>
          <span style="font-size:0.7rem; color:var(--text-muted);">${dev.type}</span>
        </div>
        <div class="entity-props" style="display:flex; flex-direction:column; gap:4px;"></div>
      `;
      container.appendChild(card);
    }

    const propsContainer = card.querySelector(".entity-props");
    Object.entries(dev.properties || {}).forEach(([prop, meta]) => {
      // 对无源蜂鸣器隐藏底层的 frequency，避免与应用层 tone 重复混淆
      if (dev.id === "actuator.buzzer.passive" && prop === "frequency") {
        return;
      }

      const rawVal = dev.values?.[prop];
      const lockKey = `device:${dev.id}:${prop}`;
      const effectiveVal = getAuthoritativeValue(lockKey, rawVal);
      const unit = meta.unit ? ` ${meta.unit}` : "";
      let row = propsContainer.querySelector(`[data-prop-name="${CSS.escape(prop)}"]`);

      if (!row) {
        row = document.createElement("div");
        row.dataset.propName = prop;
        row.style.cssText = "display:flex; justify-content:space-between; align-items:center; font-size:0.78rem; border-top:1px dashed rgba(148,163,184,0.25); padding-top:3px;";

        const left = document.createElement("span");
        left.className = "prop-label";
        row.appendChild(left);

        if (meta.writable && dev.id !== "led") {
          const ctrl = document.createElement("div");
          ctrl.style.display = "flex";
          ctrl.style.gap = "4px";
          ctrl.style.alignItems = "center";

          const propType = (meta.type || "").toLowerCase();
          const isStringProp = propType === "str" || propType === "string" || prop === "sfx" || prop === "state";

          let inp;
          if (prop === "sfx") {
            inp = document.createElement("select");
            inp.style.cssText = "width:98px; padding:2px 4px; font-size:0.75rem; border:1px solid var(--border); border-radius:4px; background:#fff;";
            SFX_PRESETS_OPTIONS.forEach((preset) => {
              const opt = document.createElement("option");
              opt.value = preset;
              opt.textContent = preset;
              inp.appendChild(opt);
            });
            if (effectiveVal && SFX_PRESETS_OPTIONS.includes(String(effectiveVal))) {
              inp.value = String(effectiveVal);
            }
          } else {
            inp = document.createElement("input");
            inp.type = isStringProp ? "text" : "number";
            inp.style.cssText = `${isStringProp ? "width:92px;" : "width:60px;"} padding:2px 4px; font-size:0.75rem; border:1px solid var(--border); border-radius:4px;`;
            if (isStringProp) {
              inp.placeholder = "文本值";
            } else if (prop === "tone") {
              inp.placeholder = "Hz";
            }
          }

          const btn = document.createElement("button");
          btn.className = "chip-btn";
          btn.textContent = "写";
          btn.style.padding = "2px 6px";
          btn.onclick = () => {
            let targetVal;
            if (inp.tagName === "SELECT" || isStringProp) {
              targetVal = String(inp.value).trim();
              if (!targetVal) return;
            } else {
              if (inp.value === "") return;
              targetVal = Number(inp.value);
              if (Number.isNaN(targetVal)) return;
            }
            enqueueMutation(lockKey, targetVal, () =>
              api(`/api/devices/${encodeURIComponent(dev.id)}/properties/${prop}`, "POST", { value: targetVal, sync_poll: true })
            );
          };
          ctrl.appendChild(inp);
          ctrl.appendChild(btn);

          // 为 tone 额外提供一键静音快捷键
          if (dev.id === "actuator.buzzer.passive" && prop === "tone") {
            const muteBtn = document.createElement("button");
            muteBtn.className = "chip-btn";
            muteBtn.textContent = "静音";
            muteBtn.style.padding = "2px 6px";
            muteBtn.onclick = () => {
              enqueueMutation(lockKey, 0, () =>
                api(`/api/devices/${encodeURIComponent(dev.id)}/properties/tone`, "POST", { value: 0, sync_poll: false })
              );
            };
            ctrl.appendChild(muteBtn);
          }

          row.appendChild(ctrl);
        }
        propsContainer.appendChild(row);
      }

      const labelEl = row.querySelector(".prop-label");
      if (labelEl) {
        if (dev.id === "actuator.buzzer.passive" && prop === "tone") {
          labelEl.textContent = `tone (音调): ${effectiveVal}${unit}`;
        } else {
          labelEl.textContent = `${prop}: ${effectiveVal}${unit}`;
        }
      }
    });
  });
}

function updateApps(apps) {
  const container = document.getElementById("appsContainer");
  Object.values(apps || {}).forEach((app) => {
    let card = container.querySelector(`[data-app-name="${CSS.escape(app.name)}"]`);
    if (!card) {
      card = document.createElement("div");
      card.className = "kpi-box";
      card.dataset.appName = app.name;
      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <span style="font-weight:700; font-size:0.86rem; color:var(--text-main);">${app.name}</span>
          <span style="font-size:0.7rem; color:var(--text-muted);">${app.description || ""}</span>
        </div>
        <div class="entity-props" style="display:flex; flex-direction:column; gap:4px;"></div>
      `;
      container.appendChild(card);
    }

    const propsContainer = card.querySelector(".entity-props");
    Object.entries(app.properties || {}).forEach(([prop, meta]) => {
      const rawVal = app.values?.[prop];
      const lockKey = `app:${app.name}:${prop}`;
      const effectiveVal = getAuthoritativeValue(lockKey, rawVal);
      const unit = meta.unit ? ` ${meta.unit}` : "";
      let row = propsContainer.querySelector(`[data-prop-name="${CSS.escape(prop)}"]`);

      if (!row) {
        row = document.createElement("div");
        row.dataset.propName = prop;
        row.style.cssText = "display:flex; justify-content:space-between; align-items:center; font-size:0.78rem; border-top:1px dashed rgba(148,163,184,0.25); padding-top:3px;";

        const left = document.createElement("span");
        left.className = "prop-label";
        row.appendChild(left);

        if (meta.writable) {
          const ctrl = document.createElement("div");
          ctrl.style.display = "flex";
          ctrl.style.gap = "4px";

          if (meta.type === "bool") {
            const btn = document.createElement("button");
            btn.className = "chip-btn";
            btn.style.padding = "2px 6px";
            btn.onclick = () => {
              const current = getAuthoritativeValue(lockKey, btn.dataset.currentBool === "true");
              const nextBool = !current;
              enqueueMutation(lockKey, nextBool, () =>
                api(`/api/apps/${encodeURIComponent(app.name)}/properties/${prop}`, "POST", { value: nextBool })
              );
            };
            ctrl.appendChild(btn);
          }
          row.appendChild(ctrl);
        }
        propsContainer.appendChild(row);
      }

      const labelEl = row.querySelector(".prop-label");
      if (labelEl) labelEl.textContent = `${prop}: ${effectiveVal}${unit}`;

      const boolBtn = row.querySelector(".chip-btn");
      if (boolBtn) {
        boolBtn.dataset.currentBool = String(effectiveVal);
        boolBtn.textContent = effectiveVal ? "停用" : "启用";
      }
    });
  });
}

function renderEvents(events) {
  const list = document.getElementById("eventList");
  const serialized = JSON.stringify(events || []);
  if (list.dataset.cache === serialized) return;
  list.dataset.cache = serialized;

  list.innerHTML = "";
  (events || []).forEach((ev) => {
    const div = document.createElement("div");
    div.className = "event-card";
    div.innerHTML = `
      <div class="ev-time">${ev.timestamp} · ${ev.source.toUpperCase()} // ${ev.kind}</div>
      <div style="margin-top:2px;">${ev.message}</div>
    `;
    list.appendChild(div);
  });
}

/* Master State Application */
function applyState(snap, history = null, events = null, modes = null, sheets = null) {
  const conn = snap.connection || {};
  const tel = snap.telemetry || {};

  const chip = document.getElementById("connChip");
  chip.classList.toggle("online", !!conn.connected);
  document.getElementById("connText").textContent = conn.connected
    ? `ONLINE (${conn.mode?.toUpperCase()})`
    : "OFFLINE";
  document.getElementById("nodeInfo").textContent =
    `${conn.port || "--"} // ${conn.node_info || "Waiting for hardware node..."}`;

  const activeMode = getAuthoritativeValue("mode", snap.workstation?.active_mode || "standard");
  document.getElementById("activeModeBadge").textContent = activeMode.toUpperCase();

  document.getElementById("kpiTemp").textContent = tel.temperature_c ?? "--";
  document.getElementById("kpiLight").textContent = tel.brightness_pct ?? "--";

  const effectiveLed = getAuthoritativeValue("device:led:state", tel.led_state ?? "--");
  document.getElementById("kpiLed").textContent = effectiveLed;
  const swLed = document.getElementById("swLedToggle");
  if (swLed) swLed.classList.toggle("checked", effectiveLed === "ON");

  const effectiveLamp = getAuthoritativeValue("device:actuator.desk_lamp:duty", tel.desk_lamp_duty ?? 0);
  document.getElementById("kpiLamp").textContent = effectiveLamp;
  const faderLamp = document.getElementById("faderLampRange");
  const faderLampVal = document.getElementById("faderLampVal");
  if (faderLamp && document.activeElement !== faderLamp) {
    faderLamp.value = effectiveLamp;
    if (faderLampVal) faderLampVal.textContent = `${effectiveLamp} %`;
  }

  const effectiveThermThresh = getAuthoritativeValue("app:thermal:threshold", snap.apps?.thermal?.values?.threshold ?? 45.0);
  const faderTherm = document.getElementById("faderThermalRange");
  const faderThermVal = document.getElementById("faderThermalVal");
  if (faderTherm && document.activeElement !== faderTherm) {
    faderTherm.value = effectiveThermThresh;
    if (faderThermVal) faderThermVal.textContent = `${Number(effectiveThermThresh).toFixed(1)} °C`;
  }

  const tempRatio = Math.max(0, Math.min(100, (((tel.temperature_c ?? 20) - 15) / 45) * 100));
  document.getElementById("barTemp").style.width = `${tempRatio}%`;
  document.getElementById("barLight").style.width = `${Math.max(0, Math.min(100, tel.brightness_pct ?? 0))}%`;

  const simPanel = document.getElementById("simPanel");
  if (simPanel) simPanel.style.display = conn.mode === "simulated" ? "block" : "none";

  if (history) renderChart(history);
  if (modes) renderModes(modes, activeMode);
  if (sheets) renderSheets(sheets);
  renderPlayerStatus(snap.player);
  updateDevices(snap.devices);
  updateApps(snap.apps);
  if (events) renderEvents(events);
}

async function refreshState() {
  if (state.isRefreshing) return;
  state.isRefreshing = true;

  try {
    const data = await api("/api/state");
    applyState(data.snapshot, data.history, data.events, data.modes, data.sheets);
  } catch (err) {
    console.error("Failed to refresh state:", err);
  } finally {
    state.isRefreshing = false;
  }
}

async function sendCommand(text) {
  if (!text.trim()) return;
  appendChat("user", text);
  try {
    const res = await api("/api/command", "POST", { text });
    appendChat("assistant", res.reply);
    if (res.snapshot) applyState(res.snapshot);
  } catch (err) {
    appendChat("assistant", `执行出错: ${err.message}`);
  }
}

/* Integrated Terminal Console Implementation */
function appendTerminalLine(text, kind = "res") {
  const out = document.getElementById("termOutput");
  if (!out) return;
  const line = document.createElement("div");
  line.className = `line ${kind}`;
  line.textContent = text;
  out.appendChild(line);
  out.scrollTop = out.scrollHeight;
}

function setupTerminalDrawer() {
  const drawer = document.getElementById("termDrawer");
  const bar = document.getElementById("termDrawerBar");
  const toggleBtn = document.getElementById("termToggleBtn");
  const input = document.getElementById("termInput");

  const toggleDrawer = () => {
    const isCollapsed = drawer.classList.contains("collapsed");
    drawer.classList.toggle("collapsed");
    toggleBtn.textContent = isCollapsed ? "▼ 折叠终端" : "▲ 展开终端 (CLI)";
    if (isCollapsed) input.focus();
  };

  bar.addEventListener("click", (e) => {
    if (e.target !== input) toggleDrawer();
  });

  const promptEl = document.querySelector(".term-prompt");

  input.addEventListener("keydown", async (e) => {
    if (e.key === "Enter") {
      const raw = input.value.trim();
      input.value = "";
      if (!raw) return;

      state.termHistory.push(raw);
      state.termHistoryIdx = state.termHistory.length;
      const currentCwd = promptEl ? promptEl.textContent : "YumeCore:/ $";
      appendTerminalLine(`${currentCwd} ${raw}`, "cmd");

      if (raw.toLowerCase() === "clear") {
        document.getElementById("termOutput").innerHTML = "";
        return;
      }

      try {
        const res = await api("/api/cli", "POST", { text: raw });
        if (res.output) {
          appendTerminalLine(res.output, res.ok ? "res" : "err");
        }
        if (res.cwd && promptEl) {
          promptEl.textContent = `YumeCore:${res.cwd} $`;
        }
        if (res.snapshot) {
          applyState(res.snapshot);
        }
      } catch (err) {
        appendTerminalLine(`Error: ${err.message}`, "err");
      }
    } else if (e.key === "Tab") {
      e.preventDefault();
      const current = input.value.trim();
      const candidates = ["help", "ping", "info", "devices", "device", "apps", "app", "auto", "piano", "ls", "cd", "pwd", "cat", "put", "get", "mkdir", "rm", "mv", "reboot", "send", "clear"];
      const match = candidates.find((c) => c.startsWith(current.toLowerCase()));
      if (match) input.value = match + " ";
    } else if (e.key === "ArrowUp") {
      if (state.termHistoryIdx > 0) {
        state.termHistoryIdx -= 1;
        input.value = state.termHistory[state.termHistoryIdx];
      }
    } else if (e.key === "ArrowDown") {
      if (state.termHistoryIdx < state.termHistory.length - 1) {
        state.termHistoryIdx += 1;
        input.value = state.termHistory[state.termHistoryIdx];
      } else {
        state.termHistoryIdx = state.termHistory.length;
        input.value = "";
      }
    }
  });
}

// Initial Wire-up
document.getElementById("cmdForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("cmdInput");
  const text = input.value;
  input.value = "";
  await sendCommand(text);
});

document.querySelectorAll(".chip-btn[data-cmd]").forEach((chip) => {
  chip.addEventListener("click", () => sendCommand(chip.dataset.cmd));
});

document.getElementById("refreshBtn")?.addEventListener("click", async () => {
  await api("/api/poll", "POST");
  await refreshState();
});

setupInstrumentRack();
setupTerminalDrawer();

appendChat("assistant", "米露莉安已就位～✨ 纯白实验室控制台与拟物乐器台已全部装载完成！点击琴键或音效垫，听听桌上的蜂鸣器唱歌吧～");
refreshState();
setInterval(refreshState, 1000);
