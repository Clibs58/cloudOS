// Color palette for processes in Gantt chart and table
const PROCESS_COLORS = [
  { bg: "#3b82f6", border: "#60a5fa" }, // Blue
  { bg: "#10b981", border: "#34d399" }, // Emerald
  { bg: "#8b5cf6", border: "#a78bfa" }, // Purple
  { bg: "#f59e0b", border: "#fbbf24" }, // Amber
  { bg: "#ec4899", border: "#f472b6" }, // Pink
  { bg: "#06b6d4", border: "#22d3ee" }, // Cyan
  { bg: "#f97316", border: "#fb923c" }, // Orange
  { bg: "#6366f1", border: "#818cf8" }, // Indigo
];

function getProcessColor(pid) {
  const idx = Math.abs(Number(pid) - 1) % PROCESS_COLORS.length;
  return PROCESS_COLORS[idx];
}

const RESOURCES = [
  { key: "cpu", label: "CPU", unit: "cores" },
  { key: "ram_gb", label: "RAM", unit: "GB" },
  { key: "gpu", label: "GPU", unit: "units" },
  { key: "storage_gb", label: "Storage", unit: "GB" },
];

let currentState = null;
let autoPlayInterval = null;
let autoPlaySpeed = 600;

// Escape HTML utility
function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// Render Resource Usage Overview
function renderBars(data) {
  const el = document.getElementById("resource-bars");
  if (!el || !data.capacity || !data.used) return;

  el.innerHTML = RESOURCES.map((r) => {
    const cap = data.capacity[r.key] || 1;
    const used = data.used[r.key] || 0;
    const pct = Math.min(100, Math.round((used / cap) * 100));
    const isHigh = pct >= 75 && pct < 90;
    const isCrit = pct >= 90;
    const fillClass = isCrit ? "bar-crit" : isHigh ? "bar-high" : "";
    const unit = r.unit ? ` ${r.unit}` : "";
    const display = `${used} / ${cap}${unit} (${pct}%)`;

    return `
      <div class="bar-row">
        <span class="bar-label">${r.label}</span>
        <div class="bar-track">
          <div class="bar-fill ${fillClass}" style="width: ${pct}%"></div>
        </div>
        <span class="bar-value mono">${display}</span>
      </div>`;
  }).join("");
}

// Render Header & Top Status Badges
function renderHeaderStatus(data) {
  document.getElementById("tick-val").textContent = `t=${data.tick}`;
  const schedLabel = data.scheduler === "Round Robin" ? `Round Robin (q=${data.quantum || 2})` : data.scheduler;
  document.getElementById("scheduler-badge").textContent = schedLabel;
  document.getElementById("cores-badge").textContent = `${data.active_cores || 1} Core${data.active_cores > 1 ? "s" : ""}`;

  // Deadlock Badge
  const dlBadge = document.getElementById("deadlock-badge");
  const alertBanner = document.getElementById("deadlock-alert");
  if (data.deadlock_detected) {
    dlBadge.textContent = "💀 DEADLOCKED";
    dlBadge.className = "pill-val badge-bad";
    alertBanner.classList.remove("hidden");
    const dlPids = (data.deadlocked_pids || []).join(", ");
    document.getElementById("deadlock-msg").textContent =
      `Processes (${dlPids}) are in circular hold-and-wait deadlock with Banker's avoidance disabled!`;
  } else if (!data.deadlock_safe) {
    dlBadge.textContent = "⚠ UNSAFE";
    dlBadge.className = "pill-val badge-bad";
    alertBanner.classList.add("hidden");
  } else {
    dlBadge.textContent = "✓ SAFE";
    dlBadge.className = "pill-val badge-safe";
    alertBanner.classList.add("hidden");
  }

  // Banker's Avoidance Badge
  const avoidBadge = document.getElementById("avoidance-badge");
  const avoidToggleBtn = document.getElementById("btn-toggle-avoidance");
  const avoidToggleText = document.getElementById("avoidance-toggle-text");
  if (data.deadlock_avoidance) {
    avoidBadge.textContent = "SHIELD ON";
    avoidBadge.className = "pill-val badge-active";
    avoidToggleBtn.className = "btn-toggle active";
    avoidToggleText.textContent = "ON (Safe)";
  } else {
    avoidBadge.textContent = "DISABLED";
    avoidBadge.className = "pill-val badge-disabled";
    avoidToggleBtn.className = "btn-toggle disabled-mode";
    avoidToggleText.textContent = "OFF (Greedy)";
  }

  // Memory Status Badge
  const memBadge = document.getElementById("memory-badge");
  const ms = data.memory_status;
  memBadge.textContent = ms;
  memBadge.className = ms === "NORMAL" ? "pill-val badge-safe" : ms === "CRITICAL" ? "pill-val badge-bad" : "pill-val badge-disabled";
}

// Render Performance Metrics Cards (Image 1, #1)
function renderMetrics(data) {
  const m = data.metrics || {};
  document.getElementById("metric-avg-wait").innerHTML = `${m.avg_waiting_time ?? 0.0} <span class="unit">ticks</span>`;
  document.getElementById("metric-avg-turnaround").innerHTML = `${m.avg_turnaround_time ?? 0.0} <span class="unit">ticks</span>`;
  document.getElementById("metric-avg-response").innerHTML = `${m.avg_response_time ?? 0.0} <span class="unit">ticks</span>`;

  const util = m.cpu_utilization ?? 0.0;
  document.getElementById("metric-cpu-util").textContent = `${util}%`;
  document.getElementById("metric-cpu-bar").style.width = `${Math.min(100, util)}%`;

  document.getElementById("metric-throughput").innerHTML = `${m.throughput ?? 0.0} <span class="unit">proc/t</span>`;
  document.getElementById("metric-completed-ratio").textContent = `${m.completed_count ?? 0} of ${m.total_count ?? 0} finished`;

  // Safe Path Ticker
  const safePathEl = document.getElementById("metric-safe-path");
  if (data.safe_sequence_names && data.safe_sequence_names.length) {
    safePathEl.textContent = data.safe_sequence_names.join(" ➔ ");
    safePathEl.style.color = "var(--accent-emerald)";
  } else if (!data.deadlock_safe) {
    safePathEl.textContent = "No Safe Sequence (Unsafe State)";
    safePathEl.style.color = "var(--accent-rose)";
  } else {
    safePathEl.textContent = "All Workloads Finished";
    safePathEl.style.color = "var(--text-muted)";
  }
}

// Render Interactive Gantt Chart Timeline (Image 1, #2 & Multi-Core Image 2, #7)
function renderGantt(data) {
  const container = document.getElementById("gantt-chart");
  const legendEl = document.getElementById("gantt-legend");
  const coreCountEl = document.getElementById("gantt-core-count");
  const gantt = data.gantt || [];
  const numCores = data.active_cores || 1;

  coreCountEl.textContent = `${numCores} Core${numCores > 1 ? "s" : ""} Lane${numCores > 1 ? "s" : ""}`;

  // Unique processes in gantt for legend
  const procMap = new Map();
  gantt.forEach((g) => {
    if (g.pid && !procMap.has(g.pid)) {
      procMap.set(g.pid, g.name);
    }
  });

  legendEl.innerHTML = Array.from(procMap.entries()).map(([pid, name]) => {
    const col = getProcessColor(pid);
    return `
      <div class="legend-item">
        <span class="legend-color" style="background:${col.bg}; border:1px solid ${col.border}"></span>
        <span>P${pid}: ${escapeHtml(name)}</span>
      </div>`;
  }).join("") + `
    <div class="legend-item">
      <span class="legend-color" style="background:#222; border:1px dashed #555"></span>
      <span>IDLE</span>
    </div>`;

  if (!gantt.length) {
    container.innerHTML = `<div class="gantt-empty">Run simulation ticks to populate the CPU execution timeline...</div>`;
    return;
  }

  // Group gantt entries by core
  const coreLanes = Array.from({ length: numCores }, () => []);
  gantt.forEach((entry) => {
    const c = entry.core || 0;
    if (c < numCores) {
      coreLanes[c].push(entry);
    }
  });

  // Calculate global ticks span for axis ruler
  const allTicks = (coreLanes[0] || []).map((e) => e.tick);
  const minTick = allTicks.length ? Math.min(...allTicks) : 1;
  const maxTick = allTicks.length ? Math.max(...allTicks) : 1;

  // Render lanes
  let lanesHtml = coreLanes.map((lane, cIdx) => {
    // Compress consecutive identical ticks into blocks
    const blocks = [];
    lane.forEach((entry) => {
      const last = blocks[blocks.length - 1];
      if (last && last.pid === entry.pid) {
        last.duration += 1;
        last.endTick = entry.tick;
      } else {
        blocks.push({
          pid: entry.pid,
          name: entry.name,
          startTick: entry.tick,
          endTick: entry.tick,
          duration: 1,
        });
      }
    });

    const blocksHtml = blocks.map((b) => {
      const widthPx = b.duration * 26;
      if (!b.pid) {
        return `
          <div class="gantt-block gantt-idle-block" style="width: ${widthPx}px" title="Core ${cIdx} IDLE (t=${b.startTick}-${b.endTick})">
            IDLE
          </div>`;
      }
      const col = getProcessColor(b.pid);
      return `
        <div class="gantt-block" style="width: ${widthPx}px; background:${col.bg}; border-color:${col.border}" title="Core ${cIdx}: P${b.pid} (${escapeHtml(b.name)}) | t=${b.startTick}-${b.endTick} (${b.duration} ticks)">
          P${b.pid}
        </div>`;
    }).join("");

    return `
      <div class="gantt-core-lane">
        <div class="gantt-core-label mono">Core ${cIdx}</div>
        <div class="gantt-blocks-wrap">${blocksHtml}</div>
      </div>`;
  }).join("");

  // Append ruler axis
  let rulerCells = "";
  for (let t = minTick; t <= maxTick; t++) {
    rulerCells += `<div class="gantt-tick-cell" style="width: 26px">t=${t}</div>`;
  }
  lanesHtml += `<div class="gantt-axis-ticks">${rulerCells}</div>`;

  container.innerHTML = lanesHtml;

  // Auto-scroll timeline to end
  const scrollWrap = document.getElementById("gantt-scroll-wrap");
  if (scrollWrap) {
    scrollWrap.scrollLeft = scrollWrap.scrollWidth;
  }
}


// Render Processes Table
function renderProcesses(processes, currentTick) {
  const body = document.getElementById("process-body");
  const pidSelect = document.getElementById("req-pid-select");

  if (!processes || !processes.length) {
    body.innerHTML = `<tr><td colspan="10" style="text-align:center; color:var(--text-dim); padding:1.5rem">No active processes in simulation</td></tr>`;
    pidSelect.innerHTML = `<option value="">No processes</option>`;
    return;
  }

  // Populate Request PID dropdown
  const activeProcs = processes.filter((p) => p.status !== "TERMINATED");
  pidSelect.innerHTML = activeProcs.map((p) => `<option value="${p.pid}">P${p.pid}: ${escapeHtml(p.name)}</option>`).join("");

  body.innerHTML = processes.map((p) => {
    let statusClass = "status-waiting";
    let statusLabel = p.status;

    if (p.status === "RUNNING") statusClass = "status-running";
    else if (p.status === "READY") statusClass = "status-ready";
    else if (p.status === "TERMINATED") statusClass = "status-terminated";
    else if (p.wait_reason === "io") {
      statusClass = "status-waiting";
      statusLabel = `WAITING (I/O ${p.io_remaining}t)`;
    } else {
      statusClass = "status-waiting";
      statusLabel = "WAITING (Res)";
    }

    const col = getProcessColor(p.pid);
    const prioDisplay = p.priority !== p.base_priority
      ? `<span class="prio-aged" title="Priority aged from ${p.base_priority}">${p.priority} ★</span>`
      : `${p.priority}`;

    const respDisplay = p.response_time !== null ? `${p.response_time}t` : "—";
    const turnDisplay = p.turnaround_time !== null ? `${p.turnaround_time}t` : "—";

    return `
      <tr>
        <td class="mono">
          <span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${col.bg}; margin-right:4px"></span>
          P${p.pid}
        </td>
        <td><strong>${escapeHtml(p.name)}</strong></td>
        <td class="mono">${prioDisplay}</td>
        <td class="mono" style="font-size:11px">
          [CPU:${p.cpu}/${p.max_cpu}, RAM:${p.ram_gb}/${p.max_ram_gb}G, GPU:${p.gpu}/${p.max_gpu}]
        </td>
        <td class="mono">${p.remaining_burst}/${p.burst_time}</td>
        <td class="mono">${p.waiting_ticks}t</td>
        <td class="mono">${turnDisplay}</td>
        <td class="mono">${respDisplay}</td>
        <td><span class="status-badge ${statusClass}">${statusLabel}</span></td>
        <td>
          <div class="row-actions">
            ${p.status !== "TERMINATED" ? `
              <button type="button" class="btn btn-sm btn-req-row" data-pid="${p.pid}" title="Quick Request Resources">+ Req</button>
              <button type="button" class="btn btn-sm btn-io-row" data-pid="${p.pid}" title="Simulate 3-tick I/O Burst">⚡ I/O</button>
            ` : `<span style="color:var(--text-dim)">—</span>`}
          </div>
        </td>
      </tr>`;

  }).join("");

  // Attach row actions
  body.querySelectorAll(".btn-req-row").forEach((btn) => {
    btn.addEventListener("click", () => {
      pidSelect.value = btn.dataset.pid;
      document.getElementById("req-cpu").focus();
    });
  });

  body.querySelectorAll(".btn-io-row").forEach((btn) => {
    btn.addEventListener("click", () => {
      api("/api/process/io", {
        method: "POST",
        body: JSON.stringify({ pid: Number(btn.dataset.pid), duration: 3 }),
      });
    });
  });
}

// Render Banker's Lab
function renderBanker(data) {
  const safeBadge = document.getElementById("banker-safe-status");
  const seqText = document.getElementById("banker-seq-text");

  if (data.deadlock_detected) {
    safeBadge.textContent = "DEADLOCK DETECTED";
    safeBadge.className = "badge-bad";
    seqText.textContent = "None (Deadlocked)";
    seqText.style.color = "var(--accent-rose)";
  } else if (!data.deadlock_safe) {
    safeBadge.textContent = "UNSAFE (No Safe Sequence)";
    safeBadge.className = "badge-bad";
    seqText.textContent = "UNSAFE: All sequences risk circular wait";
    seqText.style.color = "var(--accent-rose)";
  } else {
    safeBadge.textContent = "SAFE (Guaranteed Avoidance)";
    safeBadge.className = "badge-safe";
    const names = data.safe_sequence_names || [];
    seqText.textContent = names.length ? names.join(" ➔ ") : "All completed";
    seqText.style.color = "var(--accent-emerald)";
  }
}

// Render Memory Management & Paging (Image 3, #11)
function renderPaging(data) {
  const p = data.paging_stats || {};
  document.getElementById("p-hits").textContent = p.page_hits ?? 0;
  document.getElementById("p-faults").textContent = p.page_faults ?? 0;
  document.getElementById("p-hit-ratio").textContent = `${p.hit_ratio ?? 0}%`;
  document.getElementById("p-fault-ratio").textContent = `${p.fault_ratio ?? 0}%`;

  const evictEl = document.getElementById("p-eviction-note");
  if (p.last_eviction) {
    evictEl.textContent = p.last_eviction;
  }

  const framesGrid = document.getElementById("memory-frames-grid");
  const frames = p.frames || [];
  framesGrid.innerHTML = frames.map((f) => {
    if (f.is_free) {
      return `
        <div class="memory-frame-card">
          <span class="frame-id-tag">Frame ${f.frame_id}</span>
          <div class="frame-content frame-free">[ Free ]</div>
          <div class="frame-meta mono">Ready</div>
        </div>`;
    }
    const col = getProcessColor(f.pid);
    return `
      <div class="memory-frame-card" style="border-color:${col.border}">
        <span class="frame-id-tag">Frame ${f.frame_id}</span>
        <div class="frame-content frame-occupied">P${f.pid}: Page ${f.page_num}</div>
        <div class="frame-meta mono">${escapeHtml(f.process_name)} (t=${f.last_accessed_tick})</div>
      </div>`;
  }).join("");
}

// Render Event Log
function renderLog(data) {
  const logEl = document.getElementById("event-log");
  const log = data.log || [];
  logEl.textContent = log.slice(-35).join("\n") || "(no simulation events yet)";
  logEl.scrollTop = logEl.scrollHeight;
}

// Central State Application
function applyState(data) {
  currentState = data;
  renderHeaderStatus(data);
  renderBars(data);
  renderMetrics(data);
  renderGantt(data);
  renderProcesses(data.processes, data.tick);
  renderBanker(data);
  renderPaging(data);
  renderLog(data);

  // Sync inputs
  if (data.scheduler) {
    const sel = document.getElementById("engine-scheduler-select");
    if (sel) sel.value = data.scheduler;
  }
  if (data.quantum !== undefined) {
    const qInput = document.getElementById("engine-quantum-val");
    if (qInput) qInput.value = data.quantum;
  }
  if (data.active_cores) {
    const sel = document.getElementById("active-cores-select");
    if (sel) sel.value = String(data.active_cores);
  }
  const agingCb = document.getElementById("aging-toggle-cb");
  if (agingCb) agingCb.checked = !!data.aging_enabled;
}

// API Fetch Helper
async function api(path, options = {}) {
  try {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const data = await res.json();
    if (!res.ok) {
      if (data.error) {
        showFeedback(data.error, true);
      }
    }
    applyState(data);
    return data;
  } catch (err) {
    console.error("API Error:", err);
  }
}

function showFeedback(msg, isError = false) {
  const fb = document.getElementById("request-feedback");
  if (!fb) return;
  fb.textContent = msg;
  fb.className = `feedback-msg ${isError ? "feedback-err" : "feedback-ok"}`;
  fb.classList.remove("hidden");
  setTimeout(() => fb.classList.add("hidden"), 5000);
}

// Playback Control Handlers
document.getElementById("btn-step-forward").addEventListener("click", () => {
  api("/api/step", { method: "POST", body: "{}" });
});

document.getElementById("btn-step-back").addEventListener("click", () => {
  api("/api/step_back", { method: "POST", body: "{}" });
});

document.getElementById("btn-run-5").addEventListener("click", () => {
  api("/api/run", { method: "POST", body: JSON.stringify({ ticks: 5 }) });
});

document.getElementById("btn-run-20").addEventListener("click", () => {
  api("/api/run", { method: "POST", body: JSON.stringify({ ticks: 20 }) });
});

document.getElementById("btn-reload-demo").addEventListener("click", () => {
  api("/api/demo", { method: "POST", body: "{}" });
});

document.getElementById("btn-reset-all").addEventListener("click", () => {
  api("/api/reset", { method: "POST", body: "{}" });
});

// Auto-Play Toggle
const playBtn = document.getElementById("btn-auto-play");
playBtn.addEventListener("click", () => {
  if (autoPlayInterval) {
    clearInterval(autoPlayInterval);
    autoPlayInterval = null;
    playBtn.textContent = "▶ Play";
    playBtn.classList.remove("btn-danger");
    playBtn.classList.add("btn-play");
  } else {
    playBtn.textContent = "⏸ Pause";
    playBtn.classList.remove("btn-play");
    playBtn.classList.add("btn-danger");
    autoPlayInterval = setInterval(() => {
      // Stop auto-play if all processes finished
      if (currentState && currentState.processes && currentState.processes.length) {
        const allDone = currentState.processes.every((p) => p.status === "TERMINATED");
        if (allDone) {
          clearInterval(autoPlayInterval);
          autoPlayInterval = null;
          playBtn.textContent = "▶ Play";
          playBtn.classList.remove("btn-danger");
          playBtn.classList.add("btn-play");
          return;
        }
      }
      api("/api/step", { method: "POST", body: "{}" });
    }, autoPlaySpeed);
  }
});

// Speed Slider
const speedSlider = document.getElementById("speed-slider");
speedSlider.addEventListener("input", (e) => {
  autoPlaySpeed = 1600 - Number(e.target.value);
  const factor = (600 / autoPlaySpeed).toFixed(1);
  document.getElementById("speed-label").textContent = `${factor}x`;
  if (autoPlayInterval) {
    clearInterval(autoPlayInterval);
    autoPlayInterval = setInterval(() => {
      api("/api/step", { method: "POST", body: "{}" });
    }, autoPlaySpeed);
  }
});

// Scenarios & Random Workload (Image 2, #8)
document.getElementById("btn-load-scenario").addEventListener("click", () => {
  const scenario = document.getElementById("scenario-select").value;
  api("/api/scenario", {
    method: "POST",
    body: JSON.stringify({ scenario }),
  });
});

document.getElementById("btn-random-workload").addEventListener("click", () => {
  api("/api/random_workload", {
    method: "POST",
    body: JSON.stringify({ count: 4 }),
  });
});

// Banker's Avoidance Toggle (Image 1, #4)
document.getElementById("btn-toggle-avoidance").addEventListener("click", () => {
  const nextVal = !currentState.deadlock_avoidance;
  api("/api/banker/toggle_avoidance", {
    method: "POST",
    body: JSON.stringify({ enabled: nextVal }),
  });
});

document.getElementById("btn-fix-deadlock").addEventListener("click", () => {
  api("/api/banker/toggle_avoidance", {
    method: "POST",
    body: JSON.stringify({ enabled: true }),
  }).then(() => {
    api("/api/demo", { method: "POST", body: "{}" });
  });
});

// Step-by-Step Resource Request (Image 1, #3)
document.getElementById("resource-request-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const pid = Number(document.getElementById("req-pid-select").value);
  const cpu = Number(document.getElementById("req-cpu").value || 0);
  const ram = Number(document.getElementById("req-ram").value || 0);
  const gpu = Number(document.getElementById("req-gpu").value || 0);
  const storage = Number(document.getElementById("req-storage").value || 0);

  if (!pid) return;

  api("/api/banker/request", {
    method: "POST",
    body: JSON.stringify({ pid, cpu, ram_gb: ram, gpu, storage_gb: storage }),
  }).then((data) => {
    if (data && !data.error) {
      showFeedback(`Allocated +[${cpu} CPU, ${ram}GB RAM, ${gpu} GPU] to P${pid} (Banker's safe!)`, false);
    }
  });
});

document.getElementById("btn-release-res").addEventListener("click", () => {
  const pid = Number(document.getElementById("req-pid-select").value);
  const cpu = Number(document.getElementById("req-cpu").value || 0);
  const ram = Number(document.getElementById("req-ram").value || 0);
  const gpu = Number(document.getElementById("req-gpu").value || 0);
  const storage = Number(document.getElementById("req-storage").value || 0);

  if (!pid) return;

  api("/api/banker/release", {
    method: "POST",
    body: JSON.stringify({ pid, cpu, ram_gb: ram, gpu, storage_gb: storage }),
  }).then((data) => {
    if (data && !data.error) {
      showFeedback(`Released resources from P${pid}`, false);
    }
  });
});

// Memory Policy Selector (Image 3, #11)
document.getElementById("paging-policy-select").addEventListener("change", (e) => {
  api("/api/memory/policy", {
    method: "POST",
    body: JSON.stringify({ policy: e.target.value }),
  });
});

// Scheduler & Multi-Core & Aging Config (Image 2, #5, #6, #7)
document.getElementById("btn-apply-engine-scheduler").addEventListener("click", () => {
  const algorithm = document.getElementById("engine-scheduler-select").value;
  const quantum = Number(document.getElementById("engine-quantum-val").value || 2);
  api("/api/scheduler", {
    method: "POST",
    body: JSON.stringify({ algorithm, quantum }),
  });
});

document.getElementById("engine-scheduler-select").addEventListener("change", (e) => {
  const qField = document.getElementById("quantum-field-group");
  if (qField) {
    if (e.target.value === "Round Robin") {
      qField.style.opacity = "1";
      qField.style.pointerEvents = "auto";
    } else {
      qField.style.opacity = "0.45";
    }
  }
});


document.getElementById("btn-apply-cores").addEventListener("click", () => {
  const cores = Number(document.getElementById("active-cores-select").value);
  api("/api/settings/multicore", {
    method: "POST",
    body: JSON.stringify({ cores }),
  });
});

document.getElementById("btn-apply-aging").addEventListener("click", () => {
  const enabled = document.getElementById("aging-toggle-cb").checked;
  const interval = Number(document.getElementById("aging-interval-val").value || 5);
  api("/api/settings/aging", {
    method: "POST",
    body: JSON.stringify({ enabled, interval }),
  });
});

document.getElementById("aging-toggle-cb").addEventListener("change", (e) => {
  const interval = Number(document.getElementById("aging-interval-val").value || 5);
  api("/api/settings/aging", {
    method: "POST",
    body: JSON.stringify({ enabled: e.target.checked, interval }),
  });
});

// Add Process Form
document.getElementById("add-process-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const form = e.target;
  const payload = {
    name: form.name.value,
    cpu: Number(form.cpu.value),
    ram_gb: Number(form.ram_gb.value),
    gpu: Number(form.gpu.value),
    storage_gb: Number(form.storage_gb.value),
    burst_time: Number(form.burst_time.value),
    priority: Number(form.priority.value),
  };

  const errEl = document.getElementById("add-process-error");
  errEl.classList.add("hidden");

  api("/api/process", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((data) => {
    if (data && data.error) {
      errEl.textContent = data.error;
      errEl.classList.remove("hidden");
    } else {
      form.name.value = "App " + (Math.floor(Math.random() * 90) + 10);
    }
  });
});

document.getElementById("btn-clear-log").addEventListener("click", () => {
  document.getElementById("event-log").textContent = "(log cleared)";
});

// Export Dropdown
const exportBtn = document.getElementById("btn-export-dropdown");
const exportMenu = document.getElementById("export-menu");
exportBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  exportMenu.classList.toggle("show");
});
window.addEventListener("click", () => exportMenu.classList.remove("show"));

// MODAL 1: Scheduler Comparison Studio (Image 3, #10)
const modalCompare = document.getElementById("modal-compare");
document.getElementById("btn-open-compare").addEventListener("click", openCompareModal);
document.getElementById("btn-re-run-compare").addEventListener("click", openCompareModal);
document.getElementById("btn-close-compare").addEventListener("click", () => modalCompare.classList.add("hidden"));
document.getElementById("btn-close-compare-footer").addEventListener("click", () => modalCompare.classList.add("hidden"));

async function openCompareModal() {
  modalCompare.classList.remove("hidden");
  const tableBody = document.getElementById("compare-table-body");
  const chartBars = document.getElementById("compare-chart-bars");
  tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:1.5rem">Running multi-scheduler benchmark simulations...</td></tr>`;

  try {
    const res = await fetch("/api/compare_schedulers", { method: "POST" });
    const data = await res.json();
    if (!data.ok) {
      tableBody.innerHTML = `<tr><td colspan="7" style="color:var(--accent-rose); text-align:center">${data.error}</td></tr>`;
      return;
    }

    document.getElementById("winner-title").textContent = `Best Performing: ${data.winner}`;
    document.getElementById("winner-desc").textContent = data.winner_reason;

    const results = data.comparison || [];
    tableBody.innerHTML = results.map((r) => {
      const isWinner = r.label === data.winner;
      return `
        <tr style="${isWinner ? 'background:rgba(16,185,129,0.08); font-weight:600' : ''}">
          <td>${isWinner ? '🏆 ' : ''}<strong>${escapeHtml(r.label)}</strong></td>
          <td class="mono">${r.total_ticks}t</td>
          <td class="mono">${r.avg_turnaround_time}t</td>
          <td class="mono">${r.avg_waiting_time}t</td>
          <td class="mono">${r.avg_response_time}t</td>
          <td class="mono">${r.cpu_utilization}%</td>
          <td class="mono">${r.throughput}</td>
        </tr>`;
    }).join("");

    // Visual Turnaround Time Bar Chart
    const maxTurnaround = Math.max(...results.map((r) => r.avg_turnaround_time || 1), 1);
    chartBars.innerHTML = results.map((r) => {
      const pct = Math.min(100, Math.round((r.avg_turnaround_time / maxTurnaround) * 100));
      const isWinner = r.label === data.winner;
      return `
        <div class="compare-bar-row">
          <span style="font-weight:${isWinner ? 700 : 500}; color:${isWinner ? 'var(--accent-emerald)' : 'var(--text-main)'}">
            ${escapeHtml(r.label)}
          </span>
          <div class="c-bar-track">
            <div class="c-bar-fill ${isWinner ? 'c-bar-winner' : ''}" style="width: ${pct}%"></div>
          </div>
          <span class="mono" style="text-align:right">${r.avg_turnaround_time}t</span>
        </div>`;
    }).join("");

  } catch (err) {
    tableBody.innerHTML = `<tr><td colspan="7" style="color:var(--accent-rose)">Failed to run benchmark: ${err.message}</td></tr>`;
  }
}

// MODAL 2: Banker's Safe Sequence Audit Proof (Image 1, #3)
const modalProof = document.getElementById("modal-safe-proof");
document.getElementById("btn-show-safe-seq").addEventListener("click", openProofModal);
document.getElementById("btn-modal-proof").addEventListener("click", openProofModal);
document.getElementById("btn-close-proof").addEventListener("click", () => modalProof.classList.add("hidden"));
document.getElementById("btn-close-proof-footer").addEventListener("click", () => modalProof.classList.add("hidden"));

async function openProofModal() {
  modalProof.classList.remove("hidden");
  const stepsBody = document.getElementById("proof-steps-body");
  const availVector = document.getElementById("proof-avail-vector");
  stepsBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:1.5rem">Calculating Banker's matrix deduction...</td></tr>`;

  try {
    const res = await fetch("/api/banker/explain");
    const data = await res.json();

    const heading = document.getElementById("proof-status-heading");
    const reason = document.getElementById("proof-reason-text");
    if (data.is_safe) {
      heading.textContent = "✓ Safe State Verified";
      heading.style.color = "var(--accent-emerald)";
      reason.textContent = data.reason;
    } else {
      heading.textContent = "✗ Unsafe State Detected";
      heading.style.color = "var(--accent-rose)";
      reason.textContent = data.reason;
    }

    const av = data.initial_available || [0, 0, 0, 0];
    availVector.innerHTML = `
      <div class="vec-item">CPU: <strong>${av[0]}</strong></div>
      <div class="vec-item">RAM: <strong>${av[1]} GB</strong></div>
      <div class="vec-item">GPU: <strong>${av[2]}</strong></div>
      <div class="vec-item">Storage: <strong>${av[3]} GB</strong></div>
    `;

    const steps = data.steps || [];
    if (!steps.length) {
      stepsBody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--text-dim); padding:1rem">No steps computed (either no active workloads or deadlock deadlock reached immediately)</td></tr>`;
      return;
    }

    stepsBody.innerHTML = steps.map((s) => `
      <tr>
        <td class="mono">Step ${s.step}</td>
        <td><strong>P${s.pid}: ${escapeHtml(s.name)}</strong></td>
        <td class="mono">[${s.work_before.join(", ")}]</td>
        <td class="mono">[${s.need.join(", ")}]</td>
        <td><span class="badge-safe">✓ True</span></td>
        <td class="mono">+[${s.allocated.join(", ")}]</td>
        <td class="mono"><strong>[${s.work_after.join(", ")}]</strong></td>
      </tr>
    `).join("");

  } catch (err) {
    stepsBody.innerHTML = `<tr><td colspan="7" style="color:var(--accent-rose)">Failed to fetch proof: ${err.message}</td></tr>`;
  }
}

// MODAL 3: System Node Capacity & Resource Editor
const modalSettings = document.getElementById("modal-settings");
const openSettingsBtns = [document.getElementById("btn-open-settings"), document.getElementById("btn-edit-capacity-shortcut")];

function populateSettingsForm() {
  if (!currentState) return;
  const cap = currentState.capacity || {};
  document.getElementById("cfg-cpu").value = cap.cpu || 16;
  document.getElementById("cfg-ram").value = cap.ram_gb || 32;
  document.getElementById("cfg-gpu").value = cap.gpu || 2;
  document.getElementById("cfg-storage").value = cap.storage_gb || 1000;

  const mem = currentState.config?.memory || {};
  document.getElementById("cfg-high-thresh").value = mem.high_threshold ?? 0.75;
  document.getElementById("cfg-crit-thresh").value = mem.critical_threshold ?? 0.9;

  const sched = currentState.config?.scheduler || {};
  document.getElementById("cfg-default-alg").value = sched.default_algorithm || "Round Robin";
  document.getElementById("cfg-quantum").value = currentState.quantum ?? sched.round_robin_quantum ?? 2;
}

openSettingsBtns.forEach((btn) => {
  if (btn) {
    btn.addEventListener("click", () => {
      populateSettingsForm();
      modalSettings.classList.remove("hidden");
    });
  }
});

document.getElementById("btn-close-settings").addEventListener("click", () => modalSettings.classList.add("hidden"));
document.getElementById("btn-close-settings-footer").addEventListener("click", () => modalSettings.classList.add("hidden"));

// Live capacity update without resetting processes
document.getElementById("btn-apply-live-capacity").addEventListener("click", async () => {
  const feedback = document.getElementById("capacity-feedback");
  feedback.classList.add("hidden");
  const payload = {
    cpu: Number(document.getElementById("cfg-cpu").value),
    ram_gb: Number(document.getElementById("cfg-ram").value),
    gpu: Number(document.getElementById("cfg-gpu").value),
    storage_gb: Number(document.getElementById("cfg-storage").value),
    high_threshold: Number(document.getElementById("cfg-high-thresh").value),
    critical_threshold: Number(document.getElementById("cfg-crit-thresh").value),
    save_config: false,
  };
  const data = await api("/api/capacity", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (data && !data.error) {
    feedback.textContent = "✓ Live node capacity updated successfully! Processes retained.";
    feedback.className = "feedback-msg feedback-ok";
    feedback.classList.remove("hidden");
  } else if (data && data.error) {
    feedback.textContent = data.error;
    feedback.className = "feedback-msg feedback-err";
    feedback.classList.remove("hidden");
  }
});

// Save to config.json & Reset
document.getElementById("capacity-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const feedback = document.getElementById("capacity-feedback");
  feedback.classList.add("hidden");
  const cpu = Number(document.getElementById("cfg-cpu").value);
  const ram_gb = Number(document.getElementById("cfg-ram").value);
  const gpu = Number(document.getElementById("cfg-gpu").value);
  const storage_gb = Number(document.getElementById("cfg-storage").value);
  const high_threshold = Number(document.getElementById("cfg-high-thresh").value);
  const critical_threshold = Number(document.getElementById("cfg-crit-thresh").value);
  const default_algorithm = document.getElementById("cfg-default-alg").value;
  const round_robin_quantum = Number(document.getElementById("cfg-quantum").value);

  const payload = {
    capacity: { cpu, ram_gb, gpu, storage_gb },
    memory: { high_threshold, critical_threshold },
    scheduler: { default_algorithm, round_robin_quantum },
    _apply: true,
    _reload_demo: true,
  };

  try {
    const res = await fetch("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      feedback.textContent = "✓ Settings saved to config.json and simulation reset!";
      feedback.className = "feedback-msg feedback-ok";
      feedback.classList.remove("hidden");
      applyState(data);
      setTimeout(() => modalSettings.classList.add("hidden"), 1200);
    } else {
      feedback.textContent = data.error || "Failed to save config";
      feedback.className = "feedback-msg feedback-err";
      feedback.classList.remove("hidden");
    }
  } catch (err) {
    feedback.textContent = `Error: ${err.message}`;
    feedback.className = "feedback-msg feedback-err";
    feedback.classList.remove("hidden");
  }
});

// Close modals on Escape key or backdrop click
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    modalCompare.classList.add("hidden");
    modalProof.classList.add("hidden");
    modalSettings.classList.add("hidden");
  }
});

[modalCompare, modalProof, modalSettings].forEach((modal) => {
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.classList.add("hidden");
    });
  }
});

// Initial State Fetch
fetch("/api/state")
  .then((r) => r.json())
  .then(applyState)
  .catch((err) => console.error("Initial state load failed:", err));

