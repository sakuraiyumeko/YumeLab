// YumeLab White Lab Workstation Controller & Integrated Terminal
const state = {
  simEditing: false,
  isRefreshing: false,
  modesCacheKey: "",
  authoritative: new Map(),
  queues: new Map(),
  globalSeq: 0,
  termHistory: [],
  termHistoryIdx: -1,
};

function enqueueMutation(key, targetValue, mutationFn) {
  state.globalSeq += 1;
  const mySeq = state.globalSeq;
  state.authoritative.set(key, { value: targetValue, seq: mySeq });

  const prevPromise = state.queues.get(key) || Promise.resolve();
  const nextPromise = prevPromise
    .catch(() => {})
    .then(async () => {
      try {
        const res = await mutationFn();
        const current = state.authoritative.get(key);
        if (current && current.seq === mySeq) {
          state.authoritative.delete(key);
          if (res && res.snapshot) applyState(res.snapshot);
        }
      } catch (err) {
        console.error(`Mutation failed for ${key}:`, err);
        const current = state.authoritative.get(key);
        if (current && current.seq === mySeq) {
          state.authoritative.delete(key);
          refreshState();
        }
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
  // SFX Drum Pads
  document.querySelectorAll(".pad-btn[data-sfx]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const sfx = btn.dataset.sfx;
      btn.classList.add("playing");
      setTimeout(() => btn.classList.remove("playing"), 200);
      try {
        await api("/api/devices/actuator.buzzer.passive/properties/sfx", "POST", { value: sfx });
        appendTerminalLine(`SFX trigger: ${sfx}`, "res");
      } catch (err) {
        console.error("SFX error:", err);
      }
    });
  });

  // Passive Buzzer Mute
  document.getElementById("buzzerMuteBtn")?.addEventListener("click", async () => {
    try {
      await api("/api/devices/actuator.buzzer.passive/properties/sfx", "POST", { value: "mute" });
      appendTerminalLine("Buzzer muted.", "res");
    } catch (err) {
      console.error(err);
    }
  });

  // Piano Keys (C5 to C6)
  document.querySelectorAll(".piano-key").forEach((key) => {
    key.addEventListener("click", async () => {
      const freq = Number(key.dataset.freq);
      key.classList.add("playing");
      setTimeout(() => key.classList.remove("playing"), 180);
      try {
        await api("/api/devices/actuator.buzzer.passive/properties/tone", "POST", { value: freq });
        appendTerminalLine(`Tone played: ${freq} Hz`, "res");
        // Auto-silence after note release
        setTimeout(() => {
          api("/api/devices/actuator.buzzer.passive/properties/tone", "POST", { value: 0 }).catch(() => {});
        }, 180);
      } catch (err) {
        console.error("Piano tone error:", err);
      }
    });
  });

  // Board LED Physical Rocker Switch
  const swLed = document.getElementById("swLedToggle");
  if (swLed) {
    swLed.addEventListener("click", () => {
      const isChecked = swLed.classList.contains("checked");
      const nextVal = isChecked ? "OFF" : "ON";
      swLed.classList.toggle("checked", nextVal === "ON");
      document.getElementById("kpiLed").textContent = nextVal;

      enqueueMutation("device:led:state", nextVal, () =>
        api("/api/devices/led/properties/state", "POST", { value: nextVal })
      );
    });
  }

  // Active Buzzer Alarm Burst
  document.getElementById("activeBuzzerBeepBtn")?.addEventListener("click", async () => {
    try {
      await api("/api/devices/actuator.buzzer.active/properties/beep", "POST", { value: 2 });
      appendTerminalLine("Active buzzer alarm: 2 beeps triggered.", "res");
    } catch (err) {
      console.error(err);
    }
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
        api("/api/devices/actuator.desk_lamp/properties/duty", "POST", { value: val })
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

          const inp = document.createElement("input");
          inp.type = "number";
          inp.style.cssText = "width:60px; padding:2px 4px; font-size:0.75rem; border:1px solid var(--border); border-radius:4px;";
          const btn = document.createElement("button");
          btn.className = "chip-btn";
          btn.textContent = "写";
          btn.style.padding = "2px 6px";
          btn.onclick = () => {
            const targetVal = Number(inp.value);
            enqueueMutation(lockKey, targetVal, () =>
              api(`/api/devices/${encodeURIComponent(dev.id)}/properties/${prop}`, "POST", { value: targetVal })
            );
          };
          ctrl.appendChild(inp);
          ctrl.appendChild(btn);
          row.appendChild(ctrl);
        }
        propsContainer.appendChild(row);
      }

      const labelEl = row.querySelector(".prop-label");
      if (labelEl) labelEl.textContent = `${prop}: ${effectiveVal}${unit}`;
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
function applyState(snap, history = null, events = null, modes = null) {
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
  updateDevices(snap.devices);
  updateApps(snap.apps);
  if (events) renderEvents(events);
}

async function refreshState() {
  if (state.isRefreshing) return;
  state.isRefreshing = true;

  try {
    const data = await api("/api/state");
    applyState(data.snapshot, data.history, data.events, data.modes);
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
      const candidates = ["help", "ping", "info", "devices", "device", "apps", "app", "auto", "ls", "cd", "pwd", "cat", "put", "get", "mkdir", "rm", "mv", "reboot", "send", "clear"];
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
setInterval(refreshState, 500);
