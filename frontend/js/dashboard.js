const API = "/api/platform";

let pollTimer = null;

function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function fmtNum(n, digits = 2) {
  if (n === null || n === undefined) return "—";
  return Number(n).toFixed(digits);
}

function showMessage(text, ok = true) {
  const el = document.getElementById("loop-message");
  el.textContent = text;
  el.className = `message ${ok ? "ok" : "err"}`;
  el.classList.remove("hidden");
}

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

function renderStatus(data) {
  const kb = data.kb || {};
  document.getElementById("kb-families").textContent = kb.total_families ?? "—";
  document.getElementById("kb-signals").textContent = kb.total_signals ?? "—";
  document.getElementById("kb-simulatable").textContent = kb.simulatable_families ?? "—";

  const buf = data.buffer || {};
  document.getElementById("buf-payments").textContent = buf.payment_records ?? 0;
  document.getElementById("buf-blocked").textContent = `${buf.blocked ?? 0} blocked`;
  document.getElementById("buf-bypassed").textContent = `${buf.bypassed ?? 0} bypassed`;

  const model = data.model || {};
  document.getElementById("model-version").textContent = model.version || "none";
  document.getElementById("model-type").textContent = model.model_type
    ? `${model.model_type} active`
    : "not loaded";
  document.getElementById("model-threshold").textContent = fmtNum(model.threshold, 3);

  const sched = data.scheduler || {};
  document.getElementById("sched-status").textContent = sched.enabled ? "ON" : "OFF";
  document.getElementById("sched-interval").textContent = sched.enabled
    ? `every ${sched.interval_minutes} min`
    : "disabled";
  document.getElementById("sched-next").textContent = sched.enabled
    ? fmtDate(sched.next_run_at)
    : "—";

  document.getElementById("sched-enabled").checked = !!sched.enabled;
  document.getElementById("sched-minutes").value = sched.interval_minutes ?? 60;
  document.getElementById("sched-families").value = sched.families ?? 5;
  document.getElementById("sched-skip-v1").checked = sched.skip_train_v1 !== false;
  document.getElementById("sched-auto-swap").checked = sched.auto_swap !== false;
  document.getElementById("sched-fresh-buffer").checked = !!sched.fresh_buffer;

  const badge = document.getElementById("running-badge");
  const runBtn = document.getElementById("run-btn");
  if (data.running_loop) {
    badge.classList.remove("hidden");
    runBtn.disabled = true;
    document.getElementById("latest-run-id").textContent = `Running: ${data.running_loop.slice(0, 8)}…`;
  } else {
    badge.classList.add("hidden");
    runBtn.disabled = false;
    if (data.latest_run) {
      document.getElementById("latest-run-id").textContent =
        `Latest: ${data.latest_run.id.slice(0, 8)}… (${data.latest_run.status})`;
    }
  }
}

function renderRuns(runs) {
  const body = document.getElementById("runs-body");
  if (!runs.length) {
    body.innerHTML = '<tr><td colspan="7" class="empty">No loop runs yet — click Run Loop</td></tr>';
    return;
  }
  body.innerHTML = runs.map((r) => `
    <tr>
      <td>${fmtDate(r.started_at)}</td>
      <td class="status-${r.status}">${r.status}</td>
      <td>${r.trigger}</td>
      <td>${r.families_count} <span class="hint">(${r.families_tested || "—"})</span></td>
      <td>${r.buffer_payments} pay / ${r.buffer_bypassed} bypass</td>
      <td>${r.score_lift != null ? (r.score_lift >= 0 ? "+" : "") + fmtNum(r.score_lift, 4) : "—"}</td>
      <td>${r.verify_decision || "—"} ${r.verify_ml_score != null ? fmtNum(r.verify_ml_score, 3) : ""}</td>
    </tr>
  `).join("");
}

function renderEvidence(rows) {
  const body = document.getElementById("evidence-body");
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="7" class="empty">No evidence yet</td></tr>';
    return;
  }
  body.innerHTML = rows.map((r) => `
    <tr>
      <td>${fmtDate(r.timestamp)}</td>
      <td>${r.attack_family}</td>
      <td>${r.step ?? "—"}</td>
      <td class="decision-${r.sandbox_decision}">${r.sandbox_decision}</td>
      <td>${r.evasion_outcome}</td>
      <td>${fmtNum(r.ml_score, 3)}</td>
      <td>${r.amount != null ? "₹" + Number(r.amount).toLocaleString() : "—"}</td>
    </tr>
  `).join("");
}

async function refresh() {
  try {
    const [status, runs, evidence] = await Promise.all([
      fetchJson(`${API}/status`),
      fetchJson(`${API}/runs?limit=15`),
      fetchJson(`${API}/buffer/recent?limit=20`),
    ]);
    renderStatus(status);
    renderRuns(runs);
    renderEvidence(evidence);
  } catch (err) {
    console.error(err);
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    await refresh();
    const running = await fetchJson(`${API}/loop/running`);
    if (!running.running) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }, 4000);
}

document.getElementById("refresh-btn").addEventListener("click", refresh);

document.getElementById("loop-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = document.getElementById("run-btn");
  btn.disabled = true;
  try {
    const payload = {
      families: Number(document.getElementById("families").value),
      skip_train_v1: document.getElementById("skip-train-v1").checked,
      swap_model: document.getElementById("swap-model").checked,
      fresh_buffer: document.getElementById("fresh-buffer").checked,
    };
    const result = await fetchJson(`${API}/loop/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showMessage(`Loop started — run ID ${result.run_id}`, true);
    startPolling();
    await refresh();
  } catch (err) {
    showMessage(err.message, false);
    btn.disabled = false;
  }
});

document.getElementById("scheduler-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const payload = {
      enabled: document.getElementById("sched-enabled").checked,
      interval_minutes: Number(document.getElementById("sched-minutes").value),
      families: Number(document.getElementById("sched-families").value),
      skip_train_v1: document.getElementById("sched-skip-v1").checked,
      auto_swap: document.getElementById("sched-auto-swap").checked,
      fresh_buffer: document.getElementById("sched-fresh-buffer").checked,
    };
    await fetchJson(`${API}/scheduler`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    showMessage("Scheduler settings saved", true);
    await refresh();
  } catch (err) {
    showMessage(err.message, false);
  }
});

refresh();
