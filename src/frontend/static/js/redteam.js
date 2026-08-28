/* Red Team Lab — generate a threat, finish against the frozen Blue detector. */

(function (PDT) {
  const state = {
    catalog: null,
    mode: "standard",
    source: "known",
    difficulty: "MEDIUM",
    scale: 1000,
    run: null,
    tab: "result",
    busy: false,
    chatBusy: false,
    draft: null,
    chat: [],
    failing: null,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function selectedFamily() {
    const id = $("red-family")?.value;
    return (state.catalog?.families || []).find((f) => f.attack_id === id) || null;
  }

  function fillFamilies() {
    const sel = $("red-family");
    if (!sel || !state.catalog) return;
    const current = sel.value;
    sel.innerHTML = state.catalog.families
      .map((f) => {
        const tag = f.is_novel ? " · novel" : "";
        return `<option value="${PDT.esc(f.attack_id)}">${PDT.esc(f.attack_id)} ${PDT.esc(f.name)}${tag}</option>`;
      })
      .join("");
    const prefer = current || state.catalog.default?.family_id;
    if (prefer && [...sel.options].some((o) => o.value === prefer)) sel.value = prefer;
    fillVariants();
  }

  function fillVariants() {
    const sel = $("red-variant");
    const fam = selectedFamily();
    if (!sel) return;
    const variants = fam?.variants || [{ code: "GEN-N01", name: "default" }];
    sel.innerHTML = variants
      .map((v) => `<option value="${PDT.esc(v.code)}">${PDT.esc(v.code)} ${PDT.esc(v.name)}</option>`)
      .join("");
    if (fam?.visual) $("red-image").checked = true;
  }

  function setSegment(rootId, attr, value) {
    const root = $(rootId);
    if (!root) return;
    root.querySelectorAll(".seg-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset[attr] === String(value));
    });
  }

  function syncSource() {
    $("red-known-fields")?.classList.toggle("hidden", state.source !== "known");
    $("red-novel-fields")?.classList.toggle("hidden", state.source !== "novel");
    $("red-chat-fields")?.classList.toggle("hidden", state.source !== "chat");
    if (state.source === "novel" || state.source === "chat") $("red-image").checked = true;
    if (state.source === "chat") loadFailing();
    updateButton();
  }

  function updateButton() {
    const btn = $("red-generate");
    if (!btn) return;
    if (state.busy) {
      btn.textContent = "Scoring…";
      btn.disabled = true;
      return;
    }
    if (state.chatBusy) {
      btn.disabled = true;
      btn.textContent = state.mode === "network" ? "Generate attack" : "Run attack";
      $("red-replay").disabled = !state.run;
      return;
    }
    btn.disabled = state.source === "chat" && !state.draft;
    btn.textContent = state.mode === "network" ? "Generate attack" : "Run attack";
    $("red-replay").disabled = !state.run;
  }

  function payload() {
    const body = {
      mode: state.mode,
      family_id: $("red-family")?.value || "",
      variant: $("red-variant")?.value || "",
      difficulty: state.difficulty,
      population: $("red-population")?.value || "normal_customers",
      scale: state.scale,
      seed: Number($("red-seed")?.value || 424242),
      generate_image: !!$("red-image")?.checked,
    };
    if (state.source === "novel" || state.source === "chat") {
      const draft = state.draft || {};
      body.novel = {
        name: $("red-novel-name")?.value.trim() || draft.name || "Novel beneficiary anomaly",
        description: $("red-novel-desc")?.value.trim() || draft.description || "",
        lifecycle_stage: draft.lifecycle_stage || "Payment Initiation",
        generate_image: body.generate_image || !!draft.generate_image,
        variants: draft.variants,
        detection_signals: draft.detection_signals,
      };
      body.family_id = "";
      if (draft.mode) body.mode = draft.mode;
      if (draft.difficulty) body.difficulty = draft.difficulty;
    }
    return body;
  }

  async function generate() {
    if (state.busy) return;
    state.busy = true;
    updateButton();
    $("red-setup-hint").textContent = "Scoring every synthetic row on the frozen Blue model…";
    try {
      const run = await PDT.post("/api/red/runs", payload());
      showRun(run);
    } catch (err) {
      $("red-setup-hint").textContent = err.message || "Generate failed";
    } finally {
      state.busy = false;
      updateButton();
    }
  }

  async function replay() {
    if (state.busy || !state.run) return;
    state.busy = true;
    updateButton();
    $("red-setup-hint").textContent = "Replaying this seed on the current Blue model…";
    try {
      const run = await PDT.post(`/api/red/runs/${encodeURIComponent(state.run.id)}/replay`, {});
      showRun(run);
    } catch (err) {
      $("red-setup-hint").textContent = err.message || "Replay failed";
    } finally {
      state.busy = false;
      updateButton();
    }
  }

  function showRun(run) {
    state.run = run;
    state.tab = "result";
    $("red-empty")?.classList.add("hidden");
    $("red-result")?.classList.remove("hidden");
    $("red-replay").disabled = false;
    $("red-setup-hint").textContent = `${run.family_id} · ${run.variant_code} · ${run.difficulty} · ${run.id.slice(0, 8)}`;
    sessionStorage.setItem("pdt.redRun", run.id);
    renderFinish();
  }

  function renderFinish() {
    const run = state.run;
    const box = $("red-result");
    if (!run || !box) return;
    const result = run.result || {};
    box.innerHTML = `
      <div class="kpi-strip lab-kpis">
        <div class="kpi"><div class="kpi-label">Generated</div><div class="kpi-value">${run.generated.toLocaleString("en-IN")}</div></div>
        <div class="kpi"><div class="kpi-label">Detected (Blue)</div><div class="kpi-value">${run.detected.toLocaleString("en-IN")}</div></div>
        <div class="kpi"><div class="kpi-label">Missed / bypassed</div><div class="kpi-value warn">${run.missed.toLocaleString("en-IN")}</div></div>
        <div class="kpi"><div class="kpi-label">Attack success</div><div class="kpi-value ${run.attack_success > 0.1 ? "danger" : "good"}">${PDT.pct(run.attack_success)}</div></div>
      </div>

      <section class="panel">
        <div class="tabs" id="red-tabs">
          ${["result", "missed", "graph", "report", "leaderboard"]
            .map((t) => `<button class="tab ${state.tab === t ? "active" : ""}" data-tab="${t}">${PDT.titleize(t)}</button>`)
            .join("")}
        </div>
        <div id="red-tab-body">${tabBody(run, result)}</div>
      </section>

      <section class="panel">
        <div class="panel-head compact"><h2>Finish actions</h2></div>
        <div class="lab-actions wrap">
          <button class="btn secondary tiny" data-jump="missed">View missed</button>
          <button class="btn secondary tiny" data-jump="graph">View graph</button>
          <button class="btn secondary tiny" data-jump="report">View report</button>
          <a class="btn primary tiny" href="#/blue">Open Blue Team defense</a>
          <button class="btn ghost tiny" id="red-replay-inline">Replay</button>
          <button class="btn secondary tiny" id="red-chat-from-misses">Chat a novel from misses</button>
        </div>
      </section>`;

    box.querySelectorAll("#red-tabs .tab").forEach((el) => {
      el.addEventListener("click", () => {
        state.tab = el.dataset.tab;
        renderFinish();
      });
    });
    box.querySelectorAll("[data-jump]").forEach((el) => {
      el.addEventListener("click", () => {
        state.tab = el.dataset.jump;
        renderFinish();
      });
    });
    box.querySelector("#red-replay-inline")?.addEventListener("click", replay);
    box.querySelector("#red-chat-from-misses")?.addEventListener("click", () => openChatFromMisses());
  }

  function tabBody(run, result) {
    if (state.tab === "missed") return missedTab(result.missed || []);
    if (state.tab === "graph") return graphTab(result.graph || {}, result.image);
    if (state.tab === "report") return reportTab(run, result);
    if (state.tab === "leaderboard") return '<div id="red-board"><div class="placeholder">Loading leaderboard…</div></div>';
    return resultTab(run, result);
  }

  function resultTab(run, result) {
    const fid = result.fidelity || {};
    const fam = result.family || {};
    return `
      <div class="finish-head">
        <div>
          <h2>${PDT.esc(run.family_name)}</h2>
          <p class="hint">${PDT.esc(run.variant_code)} · ${PDT.esc(run.difficulty)} · ${PDT.esc(run.id.slice(0, 8))} · model ${PDT.esc(run.model_version || "—")}</p>
        </div>
        <div class="finish-rate">
          <div class="kpi-label">Detection</div>
          <div class="kpi-value">${PDT.pct(run.detection_rate)}</div>
        </div>
      </div>
      <div class="kv">
        <div><dt>Fidelity on the mix</dt><dd>${PDT.num(fid.precision, 3)} precision</dd></div>
        <div><dt>PR-AUC of this scored set</dt><dd>${PDT.num(fid.pr_auc, 3)}</dd></div>
        <div><dt>Benign scored</dt><dd>${fid.benign_scored ?? "—"}</dd></div>
        <div><dt>Threshold</dt><dd>${PDT.num(run.threshold, 2)}</dd></div>
      </div>
      <p class="hint">${PDT.esc(fid.note || "Not training holdout F1.")}</p>
      <div class="gap-section">
        <h4>Attack behavior</h4>
        <div class="reason-block red">${PDT.esc(result.behavior || "—")}</div>
      </div>
      ${
        fam.is_novel
          ? `<div class="gap-section"><h4>Novel family</h4><div class="reason-block">${PDT.esc(fam.description || fam.name)}</div></div>`
          : ""
      }
      ${result.image ? imageBlock(result.image) : ""}`;
  }

  function missedTab(rows) {
    if (!rows.length) {
      return '<div class="empty">Blue scored every generated row at or above 0.5.</div>';
    }
    const body = rows
      .map(
        (r) => `
      <tr>
        <td class="mono">${PDT.esc(r.row_id)}</td>
        <td class="mono">${PDT.esc(r.customer_id)}</td>
        <td class="mono">${PDT.esc(r.beneficiary_id)}</td>
        <td>${PDT.money(r.amount)}</td>
        <td>${r.is_new_beneficiary ? '<span class="chip amber">new payee</span>' : "—"}</td>
        <td class="mono">${PDT.num(r.score, 3)}</td>
      </tr>`
      )
      .join("");
    return `
      <p class="hint" style="margin-bottom:0.7rem">Rows Blue scored below 0.5. Showing ${rows.length} samples.</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Row</th><th>Customer</th><th>Beneficiary</th><th>Amount</th><th>Signal</th><th>Score</th></tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>`;
  }

  function graphTab(graph, image) {
    const nodes = graph.nodes || [];
    const edges = graph.edges || [];
    if (!nodes.length) return '<div class="empty">No entity links for this run.</div>';
    const w = 720, h = 420;
    const kinds = { customer: 0, device: 1, beneficiary: 2 };
    const placed = nodes.map((n, i) => {
      const col = kinds[n.kind] ?? 1;
      const inCol = nodes.filter((x) => x.kind === n.kind);
      const idx = inCol.indexOf(n);
      return {
        ...n,
        x: 90 + col * 240,
        y: 36 + ((idx + 1) / (inCol.length + 1)) * (h - 72),
      };
    });
    const byId = Object.fromEntries(placed.map((n) => [n.id, n]));
    const lines = edges
      .map((e) => {
        const a = byId[e.source], b = byId[e.target];
        if (!a || !b) return "";
        return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" class="g-edge ${e.missed ? "missed" : ""}"/>`;
      })
      .join("");
    const dots = placed
      .map(
        (n) => `
      <g>
        <circle cx="${n.x}" cy="${n.y}" r="${n.missed ? 7 : 5}" class="g-node ${n.kind} ${n.missed ? "missed" : ""}"/>
        <text x="${n.x}" y="${n.y + 16}" class="g-label">${PDT.esc(n.id)}</text>
      </g>`
      )
      .join("");
    return `
      <p class="hint" style="margin-bottom:0.7rem">${PDT.esc(graph.title || "Entity links")} · ${nodes.length} nodes</p>
      <svg class="lab-graph" viewBox="0 0 ${w} ${h}">${lines}${dots}</svg>
      <div class="geo-legend">
        <span><i class="dot contained"></i>Detected link</span>
        <span><i class="dot bypassed"></i>Missed link</span>
      </div>
      ${image ? imageBlock(image) : ""}`;
  }

  function reportTab(run, result) {
    const r = result.report || {};
    return `
      <div class="gap-section">
        <h4>Finding</h4>
        <div class="reason-block red">${PDT.esc(r.finding || "—")}</div>
      </div>
      <div class="grid-2">
        <div class="gap-section">
          <h4>Detected signals</h4>
          ${PDT.chips(r.detected_signals, "blue")}
        </div>
        <div class="gap-section">
          <h4>Attack behavior</h4>
          <div class="reason-block">${PDT.esc(r.behavior || result.behavior || "—")}</div>
        </div>
      </div>
      <div class="grid-2">
        <div class="gap-section">
          <h4>Red next attack</h4>
          <div class="reason-block amber">${PDT.esc(r.red_next || "—")}</div>
        </div>
        <div class="gap-section">
          <h4>Blue fix</h4>
          <div class="reason-block">${PDT.esc(r.blue_fix || "—")}</div>
        </div>
      </div>
      ${result.image ? imageBlock(result.image) : ""}`;
  }

  function imageBlock(image) {
    return `
      <div class="gap-section">
        <h4>${PDT.esc(image.title || "Generated image")}</h4>
        <div class="lab-image">${image.svg || ""}</div>
        <p class="footnote">${PDT.esc(image.caption || "")}</p>
      </div>`;
  }

  async function loadLeaderboard() {
    const box = $("red-board");
    if (!box) return;
    try {
      const rows = await PDT.get("/api/red/runs?limit=20");
      if (!rows.length) {
        box.innerHTML = '<div class="empty">No lab runs yet.</div>';
        return;
      }
      box.innerHTML = `
        <div class="table-wrap">
          <table>
            <thead><tr><th>Family</th><th>Variant</th><th>Scale</th><th>Detected</th><th>Missed</th><th>Attack success</th></tr></thead>
            <tbody>
              ${rows
                .map(
                  (r) => `
                <tr data-run="${PDT.esc(r.id)}" class="${r.id === state.run?.id ? "selected-row" : ""}">
                  <td><b>${PDT.esc(r.family_id)}</b><br><span class="hint">${PDT.esc(r.family_name)}</span></td>
                  <td class="mono">${PDT.esc(r.variant_code)} · ${PDT.esc(r.difficulty)}</td>
                  <td>${r.scale.toLocaleString("en-IN")}</td>
                  <td>${r.detected.toLocaleString("en-IN")}</td>
                  <td>${r.missed.toLocaleString("en-IN")}</td>
                  <td class="${r.attack_success > 0.1 ? "d-ALLOW" : "d-BLOCK"}">${PDT.pct(r.attack_success)}</td>
                </tr>`
                )
                .join("")}
            </tbody>
          </table>
        </div>`;
      box.querySelectorAll("tr[data-run]").forEach((el) => {
        el.addEventListener("click", async () => {
          const run = await PDT.get(`/api/red/runs/${encodeURIComponent(el.dataset.run)}`);
          showRun(run);
        });
      });
    } catch (err) {
      box.innerHTML = `<div class="empty">${PDT.esc(err.message)}</div>`;
    }
  }

  async function loadFailing() {
    const box = $("red-failing-summary");
    if (!box) return;
    try {
      const runId = state.run?.id || sessionStorage.getItem("pdt.redRun") || "";
      state.failing = await PDT.get(`/api/red/failing${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`);
      box.textContent = state.failing.summary || "No failing attacks yet.";
      if (!state.chat.length) {
        pushChat(
          "assistant",
          state.failing.seed
            ? `${state.failing.summary} Tell me how to mutate it, or use a prompt chip.`
            : state.failing.summary
        );
      }
    } catch (err) {
      box.textContent = err.message || "Could not load failing attacks.";
    }
  }

  function pushChat(role, text) {
    state.chat.push({ role, content: text });
    renderChat();
  }

  function renderChat() {
    const log = $("red-chat-log");
    if (!log) return;
    log.innerHTML = state.chat
      .map((m) => `<div class="chat-msg ${m.role}"><p>${PDT.esc(m.content)}</p></div>`)
      .join("");
    log.scrollTop = log.scrollHeight;
    renderDraft();
  }

  function renderDraft() {
    const box = $("red-chat-draft");
    if (!box) return;
    const d = state.draft;
    if (!d) {
      box.classList.add("hidden");
      box.innerHTML = "";
      return;
    }
    box.classList.remove("hidden");
    box.innerHTML = `
      <h4 class="sublabel">Draft novel family</h4>
      <div class="reason-block red">
        <b>${PDT.esc(d.name)}</b><br />${PDT.esc(d.description)}
      </div>
      <div class="lab-actions wrap" style="margin-top:0.55rem">
        <button class="btn primary tiny" id="red-use-draft" type="button">Use this family</button>
      </div>`;
    $("red-use-draft")?.addEventListener("click", applyDraft);
  }

  function applyDraft() {
    const d = state.draft;
    if (!d) return;
    if (d.mode) {
      state.mode = d.mode;
      setSegment("red-mode", "mode", state.mode);
    }
    if (d.difficulty) {
      state.difficulty = d.difficulty;
      setSegment("red-difficulty", "diff", state.difficulty);
    }
    if (d.generate_image) $("red-image").checked = true;
    $("red-novel-name") && ($("red-novel-name").value = d.name || "");
    $("red-novel-desc") && ($("red-novel-desc").value = d.description || "");
    $("red-setup-hint").textContent = `Draft ready: ${d.name}. Generate to score it.`;
    updateButton();
  }

  async function sendChat(text) {
    const message = (text || $("red-chat-input")?.value || "").trim();
    if (!message || state.busy || state.chatBusy) return;
    if ($("red-chat-input")) $("red-chat-input").value = "";
    pushChat("user", message);
    state.chatBusy = true;
    updateButton();
    const sendBtn = $("red-chat-send");
    if (sendBtn) sendBtn.disabled = true;
    try {
      const res = await PDT.post("/api/red/chat", {
        message,
        run_id: state.run?.id || state.failing?.seed_run_id || null,
        history: state.chat.slice(-8).map((m) => ({ role: m.role, content: m.content })),
      });
      state.draft = res.draft || null;
      pushChat("assistant", res.reply || "Draft ready.");
      applyDraft();
    } catch (err) {
      pushChat("assistant", err.message || "Chat failed.");
    } finally {
      state.chatBusy = false;
      if (sendBtn) sendBtn.disabled = false;
      updateButton();
    }
  }

  function openChatFromMisses() {
    state.source = "chat";
    setSegment("red-source", "source", "chat");
    syncSource();
    sendChat("Create a novel attack from these misses.");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function bind() {
    $("red-mode")?.querySelectorAll(".seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.mode = btn.dataset.mode;
        setSegment("red-mode", "mode", state.mode);
        updateButton();
      });
    });
    $("red-source")?.querySelectorAll(".seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.source = btn.dataset.source;
        setSegment("red-source", "source", state.source);
        syncSource();
      });
    });
    $("red-difficulty")?.querySelectorAll(".seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.difficulty = btn.dataset.diff;
        setSegment("red-difficulty", "diff", state.difficulty);
      });
    });
    $("red-scale")?.querySelectorAll(".seg-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.scale = Number(btn.dataset.scale);
        setSegment("red-scale", "scale", state.scale);
      });
    });
    $("red-family")?.addEventListener("change", fillVariants);
    $("red-generate")?.addEventListener("click", generate);
    $("red-replay")?.addEventListener("click", replay);
    $("red-chat-send")?.addEventListener("click", () => sendChat());
    $("red-chat-input")?.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        sendChat();
      }
    });
    $("red-chat-prompts")?.querySelectorAll("[data-prompt]").forEach((el) => {
      el.addEventListener("click", () => sendChat(el.dataset.prompt));
    });
  }

  async function load() {
    try {
      state.catalog = await PDT.get("/api/red/lab/catalog");
      fillFamilies();
      syncSource();
      updateButton();
      if (state.tab === "leaderboard") loadLeaderboard();
    } catch (err) {
      console.error(err);
    }
  }

  const _renderFinish = renderFinish;
  renderFinish = function () {
    _renderFinish();
    if (state.tab === "leaderboard") loadLeaderboard();
  };

  document.addEventListener("DOMContentLoaded", bind);
  PDT.register("red", { enter: load });
})(window.PDT);
