/* Overview / Command Center — live KPIs, animated loop, geo map, event ticker. */

(function (PDT) {
  const SVG_NS = "http://www.w3.org/2000/svg";

  // The canonical loop from the spec, laid out as a closed circuit.
  const NODES = [
    { id: "knowledge", title: "Knowledge",      kind: "TAXONOMY",   x: 40,  y: 55 },
    { id: "red",       title: "Red Team",       kind: "ADVERSARY",  x: 250, y: 55 },
    { id: "journey",   title: "Attack Journey", kind: "CAMPAIGN",   x: 460, y: 55 },
    { id: "sandbox",   title: "Sandbox",        kind: "ENGINES",    x: 670, y: 55 },
    { id: "blue",      title: "Blue Score",     kind: "FRAUDSHIELD", x: 670, y: 250 },
    { id: "decision",  title: "Final Decision", kind: "AUTHORIZATION", x: 460, y: 250 },
    { id: "learn",     title: "Red Learns / Blue Buffer", kind: "EVIDENCE", x: 250, y: 250 },
    { id: "reattack",  title: "Re-attack / Harden", kind: "LOOP",   x: 40,  y: 250 },
  ];
  const NW = 170, NH = 62;

  let cursor = 0;
  let timer = null;
  let paused = false;
  let ctx = { metrics: {}, ticker: [], status: {}, coverage: {} };
  let seenIds = new Set();

  /* ─────────── loop diagram ─────────── */
  function el(tag, attrs, parent) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
    if (parent) parent.appendChild(node);
    return node;
  }

  function edgePath(a, b) {
    const ax = a.x + NW / 2, ay = a.y + NH / 2;
    const bx = b.x + NW / 2, by = b.y + NH / 2;

    if (a.y === b.y) {
      const dir = bx > ax ? 1 : -1;
      const from = ax + dir * (NW / 2 + 6);
      const to = bx - dir * (NW / 2 + 6);
      return `M ${from} ${ay} L ${to} ${by}`;
    }
    // vertical hop down the side of the circuit
    const from = ay + (by > ay ? NH / 2 + 6 : -(NH / 2 + 6));
    const to = by + (by > ay ? -(NH / 2 + 6) : NH / 2 + 6);
    return `M ${ax} ${from} L ${bx} ${to}`;
  }

  function buildLoop() {
    const svg = document.getElementById("loop-svg");
    if (!svg || svg.dataset.built) return;
    svg.innerHTML = "";

    const defs = el("defs", {}, svg);
    const marker = el("marker", {
      id: "arrow", viewBox: "0 0 10 10", refX: "9", refY: "5",
      markerWidth: "6", markerHeight: "6", orient: "auto-start-reverse",
    }, defs);
    el("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#2b3b4f" }, marker);

    const edges = el("g", { class: "edges" }, svg);
    for (let i = 0; i < NODES.length; i++) {
      const a = NODES[i];
      const b = NODES[(i + 1) % NODES.length];
      el("path", {
        d: edgePath(a, b),
        class: "loop-edge",
        "marker-end": "url(#arrow)",
        "data-edge": i,
      }, edges);
    }

    NODES.forEach((n) => {
      const g = el("g", { class: "loop-node-box", "data-node": n.id }, svg);
      el("rect", { x: n.x, y: n.y, width: NW, height: NH, rx: 11, class: "loop-node-rect" }, g);
      const kind = el("text", { x: n.x + 14, y: n.y + 22, class: "loop-node-kind" }, g);
      kind.textContent = n.kind;

      const title = el("text", { x: n.x + 14, y: n.y + 43, class: "loop-node-title" }, g);
      // wrap long titles onto the available width
      if (n.title.length > 20) {
        const parts = n.title.split(" / ");
        title.textContent = parts[0] + " /";
        const second = el("text", { x: n.x + 14, y: n.y + 56, class: "loop-node-title" }, g);
        second.textContent = parts[1] || "";
      } else {
        title.textContent = n.title;
      }
      el("circle", { cx: n.x + NW - 16, cy: n.y + 16, r: 0, class: "pulse-holder" }, g);
    });

    svg.dataset.built = "1";
  }

  function describe(nodeId) {
    const m = ctx.metrics || {};
    const kb = (ctx.status && ctx.status.kb) || {};
    const buf = (ctx.status && ctx.status.buffer) || {};
    const latest = ctx.ticker[0];

    switch (nodeId) {
      case "knowledge":
        return `Knowledge Base: ${kb.total_families ?? "—"} attack families, ${kb.total_signals ?? "—"} detection signals, ${kb.simulatable_families ?? "—"} simulatable`;
      case "red":
        return latest
          ? `Red Team: generating ${latest.family_id} — ${latest.family_name || "campaign"}`
          : "Red Team: idle, awaiting hypothesis";
      case "journey":
        return latest
          ? `Attack Journey: step ${latest.step ?? "—"} · action ${latest.action_type || "—"}`
          : "Attack Journey: no active campaign";
      case "sandbox":
        return latest
          ? `Sandbox: ${latest.decision} — ${PDT.titleize(latest.reason || "processed")}`
          : "Sandbox: idle";
      case "blue":
        return latest && latest.ml_score !== null && latest.ml_score !== undefined
          ? `FraudShield ${m.model_version || ""}: ml=${PDT.num(latest.ml_score, 3)} (threshold ${PDT.num(m.threshold, 3)})`
          : `FraudShield ${m.model_version || "—"} active, threshold ${PDT.num(m.threshold, 3)}`;
      case "decision":
        return latest
          ? `Authorization: ${latest.decision} on ${PDT.money(latest.amount)}`
          : "Authorization: no decisions yet";
      case "learn":
        return `Evidence: ${buf.payment_records ?? 0} payments buffered · ${buf.bypassed ?? 0} bypassed · ${buf.blocked ?? 0} contained`;
      case "reattack":
        return `Hardening: ${m.model_version || "v1"} active · attack success rate ${PDT.pct(m.attack_success_rate)}`;
      default:
        return "";
    }
  }

  function highlight(index) {
    const svg = document.getElementById("loop-svg");
    if (!svg) return;
    const node = NODES[index];

    svg.querySelectorAll(".loop-node-box").forEach((g, i) => {
      g.classList.toggle("active", i === index);
      g.classList.toggle("done", i < index);
    });
    svg.querySelectorAll(".loop-edge").forEach((e, i) => {
      e.classList.toggle("hot", i === index);
    });

    // pulse ring on the active node
    svg.querySelectorAll(".pulse-ring").forEach((r) => r.remove());
    const g = svg.querySelector(`[data-node="${node.id}"]`);
    if (g) {
      const ring = document.createElementNS(SVG_NS, "circle");
      ring.setAttribute("cx", node.x + NW - 16);
      ring.setAttribute("cy", node.y + 16);
      ring.setAttribute("class", "pulse-ring");
      g.appendChild(ring);
    }

    const nameEl = document.getElementById("readout-node");
    const detailEl = document.getElementById("readout-detail");
    if (nameEl) nameEl.textContent = node.title;
    if (detailEl) detailEl.textContent = describe(node.id);
  }

  function animate() {
    if (timer) clearInterval(timer);
    timer = setInterval(() => {
      if (paused) return;
      cursor = (cursor + 1) % NODES.length;
      highlight(cursor);
    }, 1500);
  }

  /* ─────────── KPI tiles ─────────── */
  function flash(id) {
    const tile = document.getElementById(id)?.closest(".kpi");
    if (!tile) return;
    tile.classList.remove("flash");
    void tile.offsetWidth;
    tile.classList.add("flash");
  }

  function setKpi(id, value, subId, sub) {
    const el = document.getElementById(id);
    if (el && el.textContent !== value) {
      el.textContent = value;
      flash(id);
    }
    if (subId && sub !== undefined) {
      const s = document.getElementById(subId);
      if (s) s.textContent = sub;
    }
  }

  function renderKpis() {
    const m = ctx.metrics || {};
    const cov = ctx.coverage || {};

    setKpi("kpi-f1", m.f1 != null ? PDT.num(m.f1, 3) : "—", "kpi-f1-sub",
      `P ${PDT.num(m.precision, 3)} · R ${PDT.num(m.recall, 3)}`);

    setKpi("kpi-asr", PDT.pct(m.attack_success_rate), "kpi-asr-sub",
      `${m.bypassed ?? 0} of ${m.attacks_executed ?? 0} payments`);

    setKpi("kpi-model", m.model_version || "—", "kpi-model-sub",
      `${m.model_type || "not loaded"} · thr ${PDT.num(m.threshold, 3)}`);

    setKpi("kpi-campaigns", String(m.campaigns_today ?? 0), "kpi-campaigns-sub",
      `${m.campaigns_total ?? 0} total`);

    setKpi("kpi-gaps", String(m.control_gaps ?? 0));

    setKpi("kpi-coverage",
      cov.tested_families != null ? `${cov.tested_families}` : "—",
      "kpi-coverage-sub",
      `of ${cov.total_families ?? "—"} families`);
  }

  /* ─────────── geo map ─────────── */
  const REGIONS = {
    DL: { x: 118, y: 88,  name: "Delhi" },
    PB: { x: 96,  y: 62,  name: "Punjab" },
    HR: { x: 110, y: 74,  name: "Haryana" },
    UP: { x: 158, y: 108, name: "Uttar Pradesh" },
    RJ: { x: 84,  y: 116, name: "Rajasthan" },
    GJ: { x: 66,  y: 158, name: "Gujarat" },
    MH: { x: 100, y: 196, name: "Maharashtra" },
    TG: { x: 132, y: 214, name: "Telangana" },
    KA: { x: 110, y: 248, name: "Karnataka" },
    TN: { x: 132, y: 288, name: "Tamil Nadu" },
    KL: { x: 104, y: 296, name: "Kerala" },
    WB: { x: 216, y: 140, name: "West Bengal" },
  };

  function renderGeo() {
    const svg = document.getElementById("geo-svg");
    if (!svg) return;
    svg.innerHTML = "";

    // abstract landmass so pins have context without pretending to be a real map
    el("path", {
      d: "M 96 40 L 150 46 L 210 66 L 246 108 L 236 150 L 206 168 L 188 214 L 156 268 " +
         "L 128 314 L 104 322 L 86 286 L 70 226 L 52 168 L 58 118 L 74 72 Z",
      class: "geo-region",
    }, svg);

    const counts = {};
    ctx.ticker.forEach((o) => {
      const r = o.location_region;
      if (r && REGIONS[r]) counts[r] = (counts[r] || 0) + 1;
    });

    Object.entries(REGIONS).forEach(([code, p]) => {
      const label = el("text", { x: p.x + 7, y: p.y + 3, class: "geo-label" }, svg);
      label.textContent = code;
      el("circle", { cx: p.x, cy: p.y, r: 1.6, fill: "#26364a" }, svg);
    });

    const colors = { ALLOW: "#22c55e", CHALLENGE: "#f59e0b", BLOCK: "#eb001b" };
    const placed = {};

    ctx.ticker.slice(0, 40).forEach((o) => {
      const region = REGIONS[o.location_region];
      if (!region) return;
      const n = (placed[o.location_region] = (placed[o.location_region] || 0) + 1);
      // fan out repeated hits so they stay countable
      const angle = n * 1.9;
      const radius = Math.min(11, 2.5 + n * 1.4);
      const cx = region.x + Math.cos(angle) * radius;
      const cy = region.y + Math.sin(angle) * radius;

      const dot = el("circle", {
        cx, cy, r: 3.2,
        fill: colors[o.decision] || "#5d6b7f",
        "fill-opacity": 0.85,
        class: "geo-pin",
      }, svg);
      const t = el("title", {}, dot);
      t.textContent = `${o.family_id} · ${o.decision} · ${region.name}`;
    });

    if (!Object.keys(placed).length) {
      const note = el("text", { x: 160, y: 330, class: "geo-label", "text-anchor": "middle" }, svg);
      note.textContent = "no located transactions yet";
    }
  }

  /* ─────────── ticker ─────────── */
  function renderTicker() {
    const box = document.getElementById("ticker");
    const count = document.getElementById("ticker-count");
    if (!box) return;

    if (!ctx.ticker.length) {
      box.innerHTML = '<div class="empty">No observations yet — run a campaign.</div>';
      if (count) count.textContent = "";
      return;
    }

    if (count) count.textContent = `last ${ctx.ticker.length} actions`;

    box.innerHTML = ctx.ticker
      .map((o) => {
        const fresh = seenIds.size && !seenIds.has(o.id) ? " fresh" : "";
        return `
        <div class="ticker-row${fresh}">
          <span class="t-time">${PDT.time(o.created_at)}</span>
          <span class="t-fam">${PDT.esc(o.family_id)}</span>
          <span class="t-name">${PDT.esc(o.family_name || o.action_type)}</span>
          <span class="d-${PDT.esc(o.decision)}">${PDT.esc(o.decision)}</span>
          <span class="t-score">${o.ml_score != null ? PDT.num(o.ml_score, 3) : "—"}</span>
          <span class="t-amount">${o.amount != null ? PDT.money(o.amount) : "—"}</span>
        </div>`;
      })
      .join("");

    seenIds = new Set(ctx.ticker.map((o) => o.id));
  }

  /* ─────────── data ─────────── */
  async function load() {
    try {
      const [metrics, ticker, status, coverage] = await Promise.all([
        PDT.get("/api/platform/metrics"),
        PDT.get("/api/platform/ticker?limit=20"),
        PDT.get("/api/platform/status"),
        PDT.get("/api/red/coverage").catch(() => ({})),
      ]);
      ctx = { metrics, ticker, status, coverage };

      renderKpis();
      renderTicker();
      renderGeo();
      highlight(cursor);

      const badge = document.getElementById("running-badge");
      const runBtn = document.getElementById("run-loop-btn");
      if (badge) badge.classList.toggle("hidden", !status.running_loop);
      if (runBtn) runBtn.disabled = !!status.running_loop;
    } catch (err) {
      console.error("overview load failed", err);
    }
  }

  let poll = null;

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
    poll = timer = null;
  }

  /* ─────────── controls ─────────── */
  document.addEventListener("DOMContentLoaded", () => {
    const pauseBtn = document.getElementById("loop-pause");
    if (pauseBtn) {
      pauseBtn.addEventListener("click", () => {
        paused = !paused;
        pauseBtn.textContent = paused ? "Resume" : "Pause";
      });
    }

    const runBtn = document.getElementById("run-loop-btn");
    if (runBtn) {
      runBtn.addEventListener("click", async () => {
        const msg = document.getElementById("loop-message");
        runBtn.disabled = true;
        try {
          const r = await PDT.post("/api/platform/loop/run", {
            families: 5, skip_train_v1: true, swap_model: true, fresh_buffer: true,
          });
          if (msg) {
            msg.className = "message ok";
            msg.textContent = `Campaign loop started — run ${r.run_id.slice(0, 8)}…`;
          }
        } catch (err) {
          if (msg) {
            msg.className = "message err";
            msg.textContent = err.message;
          }
          runBtn.disabled = false;
        }
      });
    }
  });

  PDT.register("overview", { enter, leave });
})(window.PDT);
