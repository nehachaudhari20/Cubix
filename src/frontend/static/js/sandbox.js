/* Sandbox page — pick an action, replay its journey through the engines. */

(function (PDT) {
  let observations = [];
  let selected = null;

  function renderList() {
    const box = document.getElementById("observation-list");
    if (!box) return;

    if (!observations.length) {
      box.innerHTML = '<div class="empty">No observations yet — run a campaign.</div>';
      return;
    }

    box.innerHTML = observations
      .map((o) => {
        const cls = { ALLOW: "red", CHALLENGE: "amber", BLOCK: "green" }[o.decision] || "blue";
        return `
        <div class="list-item ${o.id === selected ? "selected" : ""}" data-id="${PDT.esc(o.id)}">
          <div class="li-top">
            <span class="li-id">${PDT.esc(o.transaction_id || o.action_type)}</span>
            <span class="chip ${cls}">${PDT.esc(o.decision)}</span>
          </div>
          <div class="li-name">${PDT.esc(o.family_id)} · ${PDT.esc(o.family_name || "")}</div>
          <div class="li-meta">
            <span>step ${o.step ?? "—"}</span>
            <span>${o.amount != null ? PDT.money(o.amount) : PDT.titleize(o.action_type)}</span>
            <span>${PDT.time(o.created_at)}</span>
          </div>
        </div>`;
      })
      .join("");

    box.querySelectorAll(".list-item").forEach((el) => {
      el.addEventListener("click", () => select(el.dataset.id));
    });
  }

  function headerPanel(o) {
    return `
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>${PDT.esc(o.transaction_id || o.action_type)}</h2>
          <p class="hint">${PDT.esc(o.family_id)} · ${PDT.esc(o.family_name)} · step ${o.step ?? "—"}</p>
        </div>
        ${PDT.decisionChip(o.decision)}
      </div>

      <div class="kv">
        <div><dt>Action</dt><dd style="font-size:0.82rem" class="mono">${PDT.esc(o.action_type)}</dd></div>
        <div><dt>Reason</dt><dd style="font-size:0.82rem">${PDT.esc(PDT.titleize(o.reason))}</dd></div>
        <div><dt>Amount</dt><dd>${o.amount != null ? PDT.money(o.amount) : "—"}</dd></div>
        <div><dt>Rail</dt><dd style="font-size:0.82rem">${PDT.esc(o.payment_rail || "—")}</dd></div>
        <div><dt>Target control</dt><dd style="font-size:0.78rem">${PDT.esc(o.target_control || "—")}</dd></div>
        <div><dt>Expected</dt><dd style="font-size:0.82rem">${PDT.esc(o.expected_outcome || "—")}</dd></div>
      </div>

      <div class="grid-2">
        <div>
          <h4 class="sublabel">Risk composition</h4>
          ${PDT.scoreBar("FraudShield ML score", o.ml_score, "ml")}
          ${PDT.scoreBar("Static rule risk", o.rule_risk, "rule")}
          ${PDT.scoreBar("Unified risk", o.risk_score, "unified")}
        </div>
        <div>
          <h4 class="sublabel">Controls triggered</h4>
          ${PDT.chips(o.control_triggers, "amber")}
          ${
            o.blocking_control
              ? `<p class="hint" style="margin-top:0.6rem">Blocking control: <b class="mono">${PDT.esc(o.blocking_control)}</b></p>`
              : ""
          }
        </div>
      </div>
    </section>`;
  }

  function resultGrid(result) {
    if (!result || typeof result !== "object") return "";
    const entries = Object.entries(result).filter(
      ([, v]) => v !== null && v !== undefined && typeof v !== "object"
    );
    if (!entries.length) return "";
    return `<div class="result-grid">${entries
      .map(
        ([k, v]) =>
          `<div><span>${PDT.esc(PDT.titleize(k))}</span><b>${PDT.esc(
            typeof v === "number" ? PDT.num(v, 3) : String(v)
          )}</b></div>`
      )
      .join("")}</div>`;
  }

  function timelinePanel(o) {
    if (!o.timeline || !o.timeline.length) {
      return `<section class="panel"><div class="empty">No journey trace recorded for this action.</div></section>`;
    }

    const items = o.timeline
      .map((t) => {
        const r = t.result || {};
        const decided = r.decision || r.result;
        const failed = t.passed === false;
        const scoring = /risk|score/i.test(t.step);
        const cls = failed ? "fail" : scoring ? "info" : "pass";
        const controls = r.control_triggers || r.triggers || [];

        return `
        <div class="tl-item ${cls}">
          <div class="tl-head">
            <span class="tl-step">${PDT.esc(PDT.titleize(t.step))}</span>
            <span class="tl-engine">${PDT.esc(t.engine)}</span>
            ${decided ? PDT.decisionChip(decided) : ""}
          </div>
          <div class="tl-detail">
            ${resultGrid(r)}
            ${controls.length ? `<div style="margin-top:0.45rem">${PDT.chips(controls, "amber")}</div>` : ""}
          </div>
        </div>`;
      })
      .join("");

    return `
    <section class="panel">
      <div class="panel-head compact">
        <h2>Journey through the payment environment</h2>
        <span class="hint">only the engines this action invoked</span>
      </div>
      <div class="timeline">${items}</div>
    </section>`;
  }

  function statePanel(o) {
    const changes = Object.entries(o.state_changes || {});
    const rows = changes.length
      ? changes
          .map(
            ([field, d]) => `
        <div class="diff-row">
          <span class="diff-field">${PDT.esc(field)}</span>
          <span class="diff-before">${PDT.esc(JSON.stringify(d.before))}</span>
          <span class="diff-arrow">→</span>
          <span class="diff-after">${PDT.esc(JSON.stringify(d.after))}</span>
        </div>`
          )
          .join("")
      : '<div class="empty">This action did not change tracked state.</div>';

    return `
    <section class="panel">
      <div class="panel-head compact">
        <h2>State transition</h2>
        <span class="hint">what the synthetic world looked like before and after</span>
      </div>
      ${rows}
      <div class="grid-2" style="margin-top:1rem">
        <details class="payload">
          <summary><span>State before</span></summary>
          <div>${PDT.jsonView(o.state_before)}</div>
        </details>
        <details class="payload">
          <summary><span>State after</span></summary>
          <div>${PDT.jsonView(o.state_after)}</div>
        </details>
      </div>
    </section>`;
  }

  function contractPanel(o) {
    return `
    <section class="panel">
      <div class="panel-head compact">
        <h2>Raw contracts</h2>
        <span class="hint">one experiment, one source of truth</span>
      </div>
      <details class="payload">
        <summary><span>Action payload sent to the Orchestrator</span></summary>
        <div>${PDT.jsonView(o.payload)}</div>
      </details>
      <details class="payload">
        <summary><span>Feature vector handed to FraudShield</span></summary>
        <div>${PDT.jsonView(o.features)}</div>
      </details>
      <details class="payload">
        <summary><span>Red Team outcome analysis</span></summary>
        <div>${PDT.jsonView(o.analysis)}</div>
      </details>
    </section>`;
  }

  async function select(id) {
    selected = id;
    renderList();
    const box = document.getElementById("observation-detail");
    box.innerHTML = '<div class="panel placeholder">Loading observation…</div>';

    try {
      const o = await PDT.get(`/api/sandbox/observations/${encodeURIComponent(id)}`);
      box.innerHTML =
        headerPanel(o) + timelinePanel(o) + statePanel(o) + contractPanel(o);
    } catch (err) {
      box.innerHTML = `<div class="panel placeholder">Could not load: ${PDT.esc(err.message)}</div>`;
    }
  }

  async function load() {
    const filter = document.getElementById("sandbox-filter");
    const decision = filter ? filter.value : "";
    const url = `/api/sandbox/observations?limit=150${decision ? `&decision=${decision}` : ""}`;
    try {
      observations = await PDT.get(url);
      renderList();
      if (observations.length && !observations.find((o) => o.id === selected)) {
        select(observations[0].id);
      }
    } catch (err) {
      console.error(err);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const filter = document.getElementById("sandbox-filter");
    if (filter) filter.addEventListener("change", load);
  });

  PDT.register("sandbox", { enter: load });
})(window.PDT);
