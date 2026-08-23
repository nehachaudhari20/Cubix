/* Red Team page — campaign list, hypothesis reasoning, plan, payloads, memory. */

(function (PDT) {
  let campaigns = [];
  let selected = null;

  function renderList() {
    const box = document.getElementById("campaign-list");
    if (!box) return;

    if (!campaigns.length) {
      box.innerHTML = '<div class="empty">No campaigns yet — run a loop from the Overview.</div>';
      return;
    }

    box.innerHTML = campaigns
      .map((c) => {
        const bypassed = c.steps_bypassed > 0;
        return `
        <div class="list-item ${c.id === selected ? "selected" : ""}" data-id="${PDT.esc(c.id)}">
          <div class="li-top">
            <span class="li-id">${PDT.esc(c.family_id)}</span>
            <span class="chip ${bypassed ? "red" : "green"}">${bypassed ? "bypassed" : "contained"}</span>
          </div>
          <div class="li-name">${PDT.esc(c.family_name)}</div>
          <div class="li-meta">
            <span>${c.steps_total} steps</span>
            <span>novelty ${PDT.num(c.novelty_score, 2)}</span>
            <span>${PDT.date(c.created_at)}</span>
          </div>
        </div>`;
      })
      .join("");

    box.querySelectorAll(".list-item").forEach((el) => {
      el.addEventListener("click", () => select(el.dataset.id));
    });
  }

  function hypothesisPanel(h, c) {
    return `
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>${PDT.esc(h.name || c.family_name)}</h2>
          <p class="hint">${PDT.esc(c.family_id)} · ${PDT.esc(c.lifecycle_stage || "—")}</p>
        </div>
        <span class="chip ${c.steps_bypassed ? "red" : "green"}">
          ${c.steps_bypassed ? `${c.steps_bypassed} step(s) bypassed` : "contained"}
        </span>
      </div>

      <div class="kv">
        <div><dt>Novelty</dt><dd>${PDT.num(h.novelty_score ?? c.novelty_score, 2)}</dd></div>
        <div><dt>Est. success</dt><dd>${PDT.num(h.success_probability ?? c.success_probability, 2)}</dd></div>
        <div><dt>Variant</dt><dd style="font-size:0.8rem">${PDT.esc(c.selected_variant || "default")}</dd></div>
        <div><dt>Steps</dt><dd>${c.steps_total}</dd></div>
      </div>

      <div class="gap-section">
        <h4>Why the Threat Hunter chose this attack</h4>
        <div class="reason-block red">${PDT.esc(h.reasoning || "No reasoning recorded.")}</div>
      </div>

      <div class="gap-section">
        <h4>Attack flow summary</h4>
        <div class="reason-block">${PDT.esc(h.attack_flow_summary || "—")}</div>
      </div>

      <div class="grid-2">
        <div class="gap-section">
          <h4>Target lifecycle stages</h4>
          ${PDT.chips(h.target_stages, "blue")}
        </div>
        <div class="gap-section">
          <h4>Prerequisites assumed</h4>
          ${PDT.chips(h.prerequisites)}
        </div>
      </div>
      ${
        (h.composite_families || []).length
          ? `<div class="gap-section"><h4>Composite families</h4>${PDT.chips(h.composite_families, "amber")}</div>`
          : ""
      }
    </section>`;
  }

  function planPanel(plan, observations) {
    const byStep = {};
    (observations || []).forEach((o) => { byStep[o.step] = o; });

    const steps = (plan.steps || [])
      .map((s) => {
        const obs = byStep[s.step];
        const outcome = obs
          ? `<span class="chip ${
              obs.decision === "ALLOW" ? "red" : obs.decision === "BLOCK" ? "green" : "amber"
            }">actual: ${PDT.esc(obs.decision)}</span>`
          : "";
        return `
        <div class="plan-step">
          <div class="step-num">${s.step}</div>
          <div class="step-body">
            <h4>${PDT.esc(s.action || s.action_type)}</h4>
            <div class="step-meta">
              <span>action: <b class="mono">${PDT.esc(s.action_type)}</b></span>
              <span>targets: <b class="mono">${PDT.esc(s.target_control)}</b></span>
              <span>expected: ${PDT.esc(s.expected_outcome)}</span>
              ${outcome}
            </div>
            <div class="step-why">${PDT.esc(s.rationale || "")}</div>
          </div>
        </div>`;
      })
      .join("");

    return `
    <section class="panel">
      <div class="panel-head compact">
        <h2>Attack plan</h2>
        <span class="hint">complexity: ${PDT.esc(plan.estimated_complexity || "—")}</span>
      </div>
      <div class="gap-section">
        <h4>Objective</h4>
        <div class="reason-block amber">${PDT.esc(plan.objective || "—")}</div>
      </div>
      ${
        plan.reasoning
          ? `<div class="gap-section"><h4>Planner reasoning</h4><div class="reason-block">${PDT.esc(plan.reasoning)}</div></div>`
          : ""
      }
      <div class="gap-section">
        <h4>Steps</h4>
        ${steps || '<div class="empty">No steps recorded.</div>'}
      </div>
      <div class="gap-section">
        <h4>Success criteria</h4>
        <div class="reason-block">${PDT.esc(plan.success_criteria || "—")}</div>
      </div>
    </section>`;
  }

  function payloadsPanel(payloads) {
    if (!payloads || !payloads.length) {
      return '<section class="panel"><div class="empty">No payloads recorded.</div></section>';
    }
    const items = payloads
      .map(
        (p) => `
      <details class="payload">
        <summary>
          <span>step ${p.step} · <b class="mono">${PDT.esc(p.action_type)}</b></span>
          <span class="hint">${PDT.esc(p.target_control || "")}</span>
        </summary>
        <div>
          ${p.narrative ? `<div class="reason-block" style="margin-bottom:0.6rem">${PDT.esc(p.narrative)}</div>` : ""}
          ${PDT.jsonView(p.action_payload || p)}
        </div>
      </details>`
      )
      .join("");

    return `
    <section class="panel">
      <div class="panel-head compact">
        <h2>Generated payloads</h2>
        <span class="hint">raw action contracts sent to the Orchestrator</span>
      </div>
      ${items}
    </section>`;
  }

  function memoryPanel(memory) {
    if (!memory || !memory.length) {
      return `
      <section class="panel">
        <div class="panel-head compact"><h2>Memory written by this campaign</h2></div>
        <div class="empty">No memory entries recorded.</div>
      </section>`;
    }

    const rows = memory
      .map(
        (m) => `
      <div class="plan-step">
        <div class="step-num">${PDT.esc((m.memory_id || "").slice(-2))}</div>
        <div class="step-body">
          <h4>${PDT.esc(m.attack_attempted || "observation")}</h4>
          <div class="step-meta">
            <span>observed control: <b class="mono">${PDT.esc(m.observed_control)}</b></span>
            <span>response: <b>${PDT.esc(m.response)}</b></span>
            <span>confidence ${PDT.num(m.confidence, 2)}</span>
          </div>
          <div class="step-why">${PDT.esc(m.context || "")}</div>
        </div>
      </div>`
      )
      .join("");

    return `
    <section class="panel">
      <div class="panel-head compact">
        <h2>Memory written by this campaign</h2>
        <span class="hint">what the attacker now knows about this environment</span>
      </div>
      ${rows}
    </section>`;
  }

  async function select(id) {
    selected = id;
    renderList();
    const box = document.getElementById("campaign-detail");
    box.innerHTML = '<div class="panel placeholder">Loading campaign…</div>';

    try {
      const c = await PDT.get(`/api/red/campaigns/${encodeURIComponent(id)}`);
      box.innerHTML =
        hypothesisPanel(c.hypothesis || {}, c) +
        planPanel(c.plan || {}, c.observations) +
        payloadsPanel(c.payloads) +
        memoryPanel(c.memory);
    } catch (err) {
      box.innerHTML = `<div class="panel placeholder">Could not load campaign: ${PDT.esc(err.message)}</div>`;
    }
  }

  async function load() {
    const filter = document.getElementById("red-filter");
    const outcome = filter ? filter.value : "";
    const url = `/api/red/campaigns?limit=100${outcome ? `&outcome=${outcome}` : ""}`;
    try {
      campaigns = await PDT.get(url);
      renderList();
      if (campaigns.length && !campaigns.find((c) => c.id === selected)) {
        select(campaigns[0].id);
      }
    } catch (err) {
      console.error(err);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const filter = document.getElementById("red-filter");
    if (filter) filter.addEventListener("change", load);
  });

  PDT.register("red", { enter: load });
})(window.PDT);
