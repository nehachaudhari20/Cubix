/* Overview / Command Center — live KPIs, battle graph, stream, proof, and ops strip. */

(function (PDT) {
  const SVG_NS = "http://www.w3.org/2000/svg";

  const NODES = [
    { id: "knowledge", title: "Knowledge", kind: "TAXONOMY", x: 40, y: 55 },
    { id: "hunter", title: "Threat Hunter", kind: "RED", x: 250, y: 55 },
    { id: "planner", title: "Planner", kind: "PLAN", x: 460, y: 55 },
    { id: "generator", title: "Generator", kind: "ATTACK", x: 670, y: 55 },
    { id: "state", title: "State Store", kind: "MEMORY", x: 40, y: 250 },
    { id: "sandbox", title: "Sandbox", kind: "SIM", x: 250, y: 250 },
    { id: "blue", title: "FraudShield", kind: "BLUE", x: 460, y: 250 },
    { id: "buffer", title: "Hardening", kind: "LOOP", x: 670, y: 250 },
  ];
  const NODE_W = 170;
  const NODE_H = 62;

  let cursor = 0;
  let timer = null;
  let poll = null;
  let paused = false;
  let ctx = {
    metrics: {},
    ticker: [],
    status: {},
    coverage: {},
    comparison: {},
    gaps: {},
    payments: [],
    runs: [],
  };
  let seenPaymentIds = new Set();

  function el(tag, attrs, parent) {
    const node = document.createElementNS(SVG_NS, tag);
    Object.entries(attrs || {}).forEach(([key, value]) => node.setAttribute(key, value));
    if (parent) parent.appendChild(node);
    return node;
  }

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  }

  function setTile(id, main, line1, line2) {
    const tile = document.querySelector(`[data-kpi="${id}"]`);
    const mainEl = document.getElementById(`kpi-${id}-main`);
    const line1El = document.getElementById(`kpi-${id}-line1`);
    const line2El = document.getElementById(`kpi-${id}-line2`);

    const changed =
      (mainEl && mainEl.textContent !== main) ||
      (line1El && line1El.textContent !== line1) ||
      (line2El && line2El.textContent !== line2);

    if (mainEl) mainEl.textContent = main;
    if (line1El) line1El.textContent = line1;
    if (line2El) line2El.textContent = line2;
    if (changed && tile) {
      tile.classList.remove("flash");
      void tile.offsetWidth;
      tile.classList.add("flash");
    }
  }

  function edgePath(a, b) {
    const ax = a.x + NODE_W / 2;
    const ay = a.y + NODE_H / 2;
    const bx = b.x + NODE_W / 2;
    const by = b.y + NODE_H / 2;

    if (a.y === b.y) {
      const dir = bx > ax ? 1 : -1;
      const from = ax + dir * (NODE_W / 2 + 6);
      const to = bx - dir * (NODE_W / 2 + 6);
      return `M ${from} ${ay} L ${to} ${by}`;
    }
    const from = ay + (by > ay ? NODE_H / 2 + 6 : -(NODE_H / 2 + 6));
    const to = by + (by > ay ? -(NODE_H / 2 + 6) : NODE_H / 2 + 6);
    return `M ${ax} ${from} L ${bx} ${to}`;
  }

  function buildLoop() {
    const svg = document.getElementById("loop-svg");
    if (!svg || svg.dataset.built) return;
    svg.innerHTML = "";

    const defs = el("defs", {}, svg);
    const marker = el("marker", {
      id: "arrow",
      viewBox: "0 0 10 10",
      refX: "9",
      refY: "5",
      markerWidth: "6",
      markerHeight: "6",
      orient: "auto-start-reverse",
    }, defs);
    el("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#c2c8d0" }, marker);

    const edges = el("g", { class: "edges" }, svg);
    for (let index = 0; index < NODES.length; index += 1) {
      const current = NODES[index];
      const next = NODES[(index + 1) % NODES.length];
      el("path", {
        d: edgePath(current, next),
        class: "loop-edge",
        "marker-end": "url(#arrow)",
      }, edges);
    }

    NODES.forEach((node) => {
      const group = el("g", { class: "loop-node-box", "data-node": node.id }, svg);
      el("rect", {
        x: node.x,
        y: node.y,
        width: NODE_W,
        height: NODE_H,
        rx: 11,
        class: "loop-node-rect",
      }, group);
      const kind = el("text", { x: node.x + 14, y: node.y + 22, class: "loop-node-kind" }, group);
      kind.textContent = node.kind;
      const title = el("text", { x: node.x + 14, y: node.y + 43, class: "loop-node-title" }, group);
      title.textContent = node.title;
    });

    svg.dataset.built = "1";
  }

  function latestObservation() {
    return ctx.payments[0] || ctx.ticker[0] || null;
  }

  function latestActiveRun() {
    return (ctx.status && ctx.status.latest_run) || null;
  }

  function describe(nodeId) {
    const latest = latestObservation();
    const metrics = ctx.metrics || {};
    const kb = (ctx.status && ctx.status.kb) || {};
    const buffer = (ctx.status && ctx.status.buffer) || {};
    const run = latestActiveRun();

    switch (nodeId) {
      case "knowledge":
        return `Knowledge: ${kb.total_families ?? "—"} families · ${kb.total_signals ?? "—"} signals · ${kb.total_controls ?? "—"} controls`;
      case "hunter":
        return latest
          ? `Threat Hunter: ${latest.family_id || "campaign"} · ${latest.family_name || PDT.titleize(latest.action_type)}`
          : "Threat Hunter: awaiting a new campaign.";
      case "planner":
        return run
          ? `Planner: ${run.families_count} families in loop ${String(run.id || "").slice(0, 8)}`
          : "Planner: no loop run recorded yet.";
      case "generator":
        return latest
          ? `Generator: step ${latest.step ?? "—"} · ${PDT.titleize(latest.action_type || "pending")}`
          : "Generator: no live actions yet.";
      case "state":
        return `State Store: ${buffer.total ?? 0} evidence rows · ${buffer.families ? buffer.families.length : 0} attack families`;
      case "sandbox":
        return latest
          ? `Sandbox: ${latest.decision} · ${PDT.money(latest.amount)} · ${latest.payment_rail || "synthetic rail"}`
          : "Sandbox: waiting for payment actions.";
      case "blue":
        return `FraudShield ${metrics.model_version || "—"} · recall ${PDT.pct(metrics.recall)} · threshold ${PDT.num(metrics.threshold, 3)}`;
      case "buffer":
        return run
          ? `Hardening: lift ${signed(run.score_lift, 3)} · verify ${run.verify_decision || "pending"}`
          : "Hardening: no training proof yet.";
      default:
        return "";
    }
  }

  function highlight(index) {
    const svg = document.getElementById("loop-svg");
    if (!svg) return;
    const node = NODES[index];

    svg.querySelectorAll(".loop-node-box").forEach((group, groupIndex) => {
      group.classList.toggle("active", groupIndex === index);
      group.classList.toggle("done", groupIndex < index);
    });
    svg.querySelectorAll(".loop-edge").forEach((edge, edgeIndex) => {
      edge.classList.toggle("hot", edgeIndex === index);
    });

    svg.querySelectorAll(".pulse-ring").forEach((ring) => ring.remove());
    const group = svg.querySelector(`[data-node="${node.id}"]`);
    if (group) {
      const ring = document.createElementNS(SVG_NS, "circle");
      ring.setAttribute("cx", node.x + NODE_W - 16);
      ring.setAttribute("cy", node.y + 16);
      ring.setAttribute("class", "pulse-ring");
      group.appendChild(ring);
    }

    setText("readout-node", node.title);
    setText("readout-detail", describe(node.id));
  }

  function animate() {
    if (timer) clearInterval(timer);
    timer = setInterval(() => {
      if (paused) return;
      cursor = (cursor + 1) % NODES.length;
      highlight(cursor);
    }, 1500);
  }

  function signed(value, digits) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    const number = Number(value);
    return `${number > 0 ? "+" : ""}${number.toFixed(digits)}`;
  }

  function percentDelta(before, after, invert = false) {
    if (before === null || before === undefined || after === null || after === undefined) {
      return { text: "—", cls: "flat" };
    }
    const change = Number(after) - Number(before);
    const positive = invert ? change < 0 : change > 0;
    return {
      text: `${positive ? "▲" : change < 0 ? "▼" : "•"} ${signed(change * 100, 1)}%`,
      cls: positive ? "up" : change < 0 ? "down" : "flat",
    };
  }

  function metricByModel(name) {
    const results = (((ctx.status || {}).model || {}).metrics || {}).results || [];
    return results.find((entry) => entry.model === name) || null;
  }

  function previousAndCurrentMetrics() {
    const results = (((ctx.status || {}).model || {}).metrics || {}).results || [];
    const usable = results.filter((entry) => entry.model !== "majority_class");
    if (usable.length < 2) return { previous: usable[0] || null, current: usable[0] || null };

    const currentModelType = (((ctx.status || {}).model || {}).model_type) || "";
    const current = usable.find((entry) => entry.model === currentModelType) || usable[usable.length - 1];
    const currentIndex = usable.findIndex((entry) => entry.model === current.model);
    const previous = usable[Math.max(0, currentIndex - 1)] || usable[0];
    return { previous, current };
  }

  function falsePositiveRate(entry) {
    if (!entry) return null;
    const fp = Number(entry.fp || 0);
    const tn = Number(entry.tn || 0);
    const denom = fp + tn;
    return denom ? fp / denom : null;
  }

  function renderKpis() {
    const metrics = ctx.metrics || {};
    const status = ctx.status || {};
    const kb = status.kb || {};
    const scheduler = status.scheduler || {};
    const run = status.latest_run || {};
    const tested = ctx.coverage || {};
    const rounds = (ctx.runs || []).length;

    setTile(
      "identify",
      `${kb.total_families ?? tested.total_families ?? 0} Families`,
      `${tested.tested_families ?? 0} tested · ${kb.simulatable_families ?? tested.simulatable_families ?? 0} simulatable`,
      `${kb.total_signals ?? 0} signals · ${kb.total_controls ?? 0} controls`
    );

    setTile(
      "generate",
      `${metrics.attacks_executed ?? 0} Payments`,
      `${metrics.campaigns_total ?? 0} campaigns total`,
      `${metrics.campaigns_today ?? 0} campaigns in last 24h`
    );

    const fpr = falsePositiveRate(metricByModel((((status.model || {}).model_type) || "")));
    setTile(
      "defend",
      PDT.pct(metrics.recall),
      `${PDT.pct(metrics.precision)} precision · thr ${PDT.num(metrics.threshold, 3)}`,
      `FPR ${PDT.pct(fpr, 2)} · ${metrics.model_version || "no model"}`
    );

    setTile(
      "loop",
      `${rounds} Rounds`,
      `${run && run.id ? String(run.id).slice(0, 8) : "No"} latest round`,
      `${scheduler.enabled ? "Scheduler on" : "Scheduler off"} · ${status.running_loop ? "running" : "idle"}`
    );
  }

  function truthLabel(payment) {
    if (!payment) return "—";
    if (payment.decision === "ALLOW") return "FN";
    return "TP";
  }

  function renderBattleFacts() {
    const latest = latestObservation();
    const status = ctx.status || {};
    const run = status.latest_run || null;
    const controls = latest && Array.isArray(latest.control_triggers) ? latest.control_triggers.length : 0;
    const learns = run && run.buffer_payments ? "YES" : status.running_loop ? "LEARNING" : "WARM";

    setText(
      "active-campaign",
      latest
        ? `${latest.campaign_id ? String(latest.campaign_id).slice(0, 8) : "campaign"} · ${latest.family_id || "synthetic"} · ${latest.decision || "pending"}`
        : "No active campaign"
    );
    setText("active-risk", latest && latest.risk_score != null ? PDT.num(latest.risk_score, 3) : PDT.num((ctx.metrics || {}).attack_success_rate, 3));
    setText("active-controls", String(controls));
    setText("active-learns", learns);
  }

  function renderPaymentStream() {
    const body = document.getElementById("payment-stream-body");
    const summary = document.getElementById("payment-stream-summary");
    const count = document.getElementById("ticker-count");
    if (!body) return;

    const payments = (ctx.payments || []).slice(0, 12);
    if (!payments.length) {
      body.innerHTML = `
        <tr class="empty-row">
          <td colspan="6">No observations yet — run a campaign.</td>
        </tr>
      `;
      if (summary) summary.textContent = "Since you started: no scored payments yet.";
      if (count) count.textContent = "Latest sandbox payments and decisions.";
      return;
    }

    body.innerHTML = payments.map((payment) => {
      const isFresh = seenPaymentIds.size && !seenPaymentIds.has(payment.id) ? " fresh" : "";
      return `
        <tr class="${isFresh.trim()}">
          <td class="stream-time">${PDT.time(payment.created_at)}</td>
          <td class="stream-amount">${PDT.money(payment.amount)}</td>
          <td class="stream-rail">${PDT.esc(payment.payment_rail || "Synthetic")}</td>
          <td class="stream-score">${payment.ml_score != null ? PDT.num(payment.ml_score, 3) : "—"}</td>
          <td>${PDT.decisionChip(payment.decision || "—")}</td>
          <td>${truthLabel(payment)}</td>
        </tr>
      `;
    }).join("");

    seenPaymentIds = new Set(payments.map((payment) => payment.id));

    const alerts = payments.filter((payment) => payment.decision !== "ALLOW");
    const stoppedAmount = alerts.reduce((sum, payment) => sum + Number(payment.amount || 0), 0);
    if (summary) {
      summary.textContent =
        `Since you started: ${payments.length} scored · ${alerts.length} alerts · ${PDT.money(stoppedAmount)} stopped`;
    }
    if (count) count.textContent = `Latest ${payments.length} payment actions`;
  }

  function renderProof() {
    const comparison = ctx.comparison || {};
    const report = comparison.hardening_report || {};
    const { previous, current } = previousAndCurrentMetrics();
    const currentAsr = (ctx.metrics || {}).attack_success_rate;
    const beforeAsr =
      report.buffer_records && report.bypassed_attacks !== undefined
        ? Number(report.bypassed_attacks || 0) / Number(report.buffer_records || 1)
        : null;

    const recallBefore = previous ? previous.recall_at_1pct_fpr : report.v1_baseline_fraud_recall;
    const recallAfter = current ? current.recall_at_1pct_fpr : report.v2_baseline_fraud_recall;
    const fprBefore = falsePositiveRate(previous);
    const fprAfter = falsePositiveRate(current);
    const asrBefore = beforeAsr;
    const asrAfter = currentAsr;

    const recallDelta = percentDelta(recallBefore, recallAfter);
    const fprDelta = percentDelta(fprBefore, fprAfter, true);
    const asrDelta = percentDelta(asrBefore, asrAfter, true);

    setText("proof-recall-value", `${PDT.pct(recallBefore)} → ${PDT.pct(recallAfter)}`);
    setText("proof-fpr-value", `${PDT.pct(fprBefore, 2)} → ${PDT.pct(fprAfter, 2)}`);
    setText("proof-asr-value", `${PDT.pct(asrBefore)} → ${PDT.pct(asrAfter)}`);

    const recallNode = document.getElementById("proof-recall-delta");
    const fprNode = document.getElementById("proof-fpr-delta");
    const asrNode = document.getElementById("proof-asr-delta");
    if (recallNode) {
      recallNode.textContent = recallDelta.text;
      recallNode.className = `proof-delta ${recallDelta.cls}`;
    }
    if (fprNode) {
      fprNode.textContent = fprDelta.text;
      fprNode.className = `proof-delta ${fprDelta.cls}`;
    }
    if (asrNode) {
      asrNode.textContent = asrDelta.text;
      asrNode.className = `proof-delta ${asrDelta.cls}`;
    }

    const status = ctx.status || {};
    const run = status.latest_run || {};
    const summary = [
      `Hardening cycles: ${(ctx.runs || []).length}`,
      `Score lift: ${signed(run.score_lift, 3)}`,
      `Integrity: ${(((status.model || {}).metrics || {}).leakage_audit_passed) ? "pass" : "pending"}`,
    ];
    setText("proof-summary", summary.join(" · "));
  }

  function topControls(findings) {
    const counts = {};
    findings.forEach((finding) => {
      (finding.evidence || []).forEach((item) => {
        (item.control_triggers || []).forEach((control) => {
          counts[control] = (counts[control] || 0) + 1;
        });
      });
    });
    return Object.entries(counts)
      .sort((left, right) => right[1] - left[1])
      .slice(0, 3)
      .map(([control, count]) => `${control} (${count})`);
  }

  function renderGaps() {
    const list = document.getElementById("gap-list");
    const footer = document.getElementById("gap-top-ctls");
    if (!list) return;

    const findings = ((ctx.gaps || {}).findings || []).slice(0, 3);
    if (!findings.length) {
      list.innerHTML = '<div class="gap-empty">No control gaps recorded yet.</div>';
      if (footer) footer.textContent = "Top control gaps will appear here once bypassed journeys exist.";
      return;
    }

    list.innerHTML = findings.map((finding) => {
      const intervention = (finding.interventions || [])[0];
      const prevention = intervention ? `→ ${PDT.titleize(intervention.name)} (${intervention.friction} friction)` : "→ no intervention recorded yet";
      return `
        <article class="gap-item ${PDT.esc(finding.severity || "low")}">
          <div class="gap-item-head">
            <strong>${PDT.esc(String(finding.severity || "low").toUpperCase())}: ${PDT.esc(finding.title || "Control gap")}</strong>
            <span>${finding.occurrences || 0} hits</span>
          </div>
          <p>${PDT.esc(finding.description || "")}</p>
          <div class="gap-meta">${PDT.esc(prevention)}</div>
        </article>
      `;
    }).join("");

    const controls = topControls(findings);
    if (footer) {
      footer.textContent = controls.length
        ? `Top CTL gaps: ${controls.join(" · ")}`
        : "No recurrent control trigger names found in current gap evidence.";
    }
  }

  function renderOps() {
    const status = ctx.status || {};
    const scheduler = status.scheduler || {};
    const model = status.model || {};
    const run = status.latest_run || {};
    const buffer = status.buffer || {};
    const kb = status.kb || {};

    const next = scheduler.next_run_at ? PDT.date(scheduler.next_run_at) : "not scheduled";
    setText("ops-scheduler", `Scheduler: ${scheduler.enabled ? "ON" : "OFF"} · next: ${next}`);
    setText(
      "ops-latest",
      `Latest: ${model.version || "no model"} trained on ${run.buffer_payments ?? buffer.payment_records ?? 0} adv. payments · Lift: ${signed(run.score_lift, 3)}`
    );
    setText(
      "ops-buffer",
      `Buffer: ${buffer.blocked ?? 0} blocked · ${buffer.total ?? 0} total evidence · ${buffer.bypassed ?? 0} bypassed`
    );
    setText(
      "ops-kb",
      `KB: ${kb.total_families ?? 0} fam · ${kb.total_signals ?? 0} sig · ${kb.total_controls ?? 0} ctl · ${kb.total_stages ?? 0} stages`
    );
    setText(
      "overview-footer-state",
      status.running_loop
        ? `Loop A (Red learning) + Loop B (Blue hardening) running · active run ${String(status.running_loop).slice(0, 8)}`
        : "Loop A (Red learning) + Loop B (Blue hardening) ready"
    );

    const badge = document.getElementById("running-badge");
    if (badge) badge.classList.toggle("hidden", !status.running_loop);

    ["run-loop-btn", "run-loop-btn-inline"].forEach((id) => {
      const button = document.getElementById(id);
      if (button) button.disabled = !!status.running_loop;
    });
  }

  function renderAll() {
    renderKpis();
    renderBattleFacts();
    renderPaymentStream();
    renderProof();
    renderGaps();
    renderOps();
    highlight(cursor);
  }

  async function load() {
    try {
      const [metrics, ticker, status, coverage, comparison, gaps, payments, runs] = await Promise.all([
        PDT.get("/api/platform/metrics"),
        PDT.get("/api/platform/ticker?limit=20"),
        PDT.get("/api/platform/status"),
        PDT.get("/api/red/coverage").catch(() => ({})),
        PDT.get("/api/blue/comparison").catch(() => ({})),
        PDT.get("/api/labs/gaps").catch(() => ({})),
        PDT.get("/api/sandbox/observations?limit=25&action_type=initiate_payment").catch(() => ([])),
        PDT.get("/api/platform/runs?limit=20").catch(() => ([])),
      ]);

      ctx = { metrics, ticker, status, coverage, comparison, gaps, payments, runs };
      renderAll();
    } catch (error) {
      console.error("overview load failed", error);
    }
  }

  async function triggerRun(sourceButton) {
    const message = document.getElementById("loop-message");
    if (sourceButton) sourceButton.disabled = true;
    try {
      const result = await PDT.post("/api/platform/loop/run", {
        families: 5,
        skip_train_v1: true,
        swap_model: true,
        fresh_buffer: true,
      });
      if (message) {
        message.className = "message ok";
        message.textContent = `Campaign loop started — run ${String(result.run_id || "").slice(0, 8)}…`;
      }
      await load();
    } catch (error) {
      if (message) {
        message.className = "message err";
        message.textContent = error.message;
      }
      if (sourceButton) sourceButton.disabled = false;
    }
  }

  function enter() {
    buildLoop();
    load();
    animate();
    if (poll) clearInterval(poll);
    poll = setInterval(load, 4000);
  }

  function leave() {
    if (poll) clearInterval(poll);
    if (timer) clearInterval(timer);
    poll = null;
    timer = null;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const pauseButton = document.getElementById("loop-pause");
    if (pauseButton) {
      pauseButton.addEventListener("click", () => {
        paused = !paused;
        pauseButton.textContent = paused ? "Resume" : "Pause";
      });
    }

    ["run-loop-btn", "run-loop-btn-inline"].forEach((id) => {
      const button = document.getElementById(id);
      if (button) {
        button.addEventListener("click", () => triggerRun(button));
      }
    });

    const refreshButton = document.getElementById("refresh-overview-btn");
    if (refreshButton) refreshButton.addEventListener("click", load);
  });

  PDT.register("overview", { enter, leave });
})(window.PDT);
