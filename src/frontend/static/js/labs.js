/* Labs page — control gap findings, evidence, counterfactual replay, recommended fix. */

(function (PDT) {
  function evidenceTable(evidence) {
    if (!evidence.length) return '<div class="empty">No evidence rows.</div>';
    return `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Family</th><th>Step</th><th>Amount</th>
            <th>ML</th><th>Rule</th><th>Unified</th><th>Controls that fired</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${evidence
            .map(
              (e) => `
            <tr>
              <td class="mono">${PDT.esc(e.family_id)}</td>
              <td>${e.step ?? "—"}</td>
              <td>${PDT.money(e.amount)}</td>
              <td>${PDT.num(e.ml_score, 3)}</td>
              <td>${PDT.num(e.rule_risk, 3)}</td>
              <td>${PDT.num(e.risk_score, 3)}</td>
              <td>${
                e.control_triggers.length
                  ? PDT.chips(e.control_triggers, "amber")
                  : '<span class="chip green">none fired</span>'
              }</td>
              <td><a href="#/sandbox" class="hint">inspect</a></td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
  }

  function interventionCard(gapId, iv, index, sampleObsId) {
    const overrides = Object.entries(iv.overrides)
      .map(([k, v]) => `${k} → ${v}`)
      .join(", ");

    return `
    <div class="intervention" data-gap="${PDT.esc(gapId)}" data-index="${index}">
      <div class="intervention-head">
        <div>
          <h5>${PDT.esc(iv.name)}</h5>
          <p>${PDT.esc(iv.rationale)}</p>
          <div class="chiplist" style="margin-top:0.5rem">
            <span class="chip blue">${PDT.esc(overrides)}</span>
            <span class="chip ${
              iv.friction === "high" ? "red" : iv.friction === "medium" ? "amber" : "green"
            }">friction: ${PDT.esc(iv.friction)}</span>
          </div>
        </div>
        <button class="btn secondary tiny replay-btn"
                data-obs="${PDT.esc(sampleObsId || "")}"
                data-overrides='${PDT.esc(JSON.stringify(iv.overrides))}'
                ${sampleObsId ? "" : "disabled"}>
          Replay journey
        </button>
      </div>
      <div class="replay-slot"></div>
    </div>`;
  }

  function renderReplay(slot, r) {
    const prevented = r.outcome.attacks_prevented;
    const cls = prevented > 0 ? "win" : "neutral";

    slot.innerHTML = `
      <div class="replay-result ${cls}">
        <b>${PDT.esc(r.outcome.verdict)}</b> — replayed campaign
        <span class="mono">${PDT.esc(r.campaign_id)}</span> against the live sandbox.
        <div class="kv" style="margin-top:0.7rem">
          <div><dt>Baseline allowed</dt><dd>${r.baseline.allowed} / ${r.baseline.payments}</dd></div>
          <div><dt>With intervention</dt><dd>${r.counterfactual.allowed} / ${r.counterfactual.payments}</dd></div>
          <div><dt>Prevention rate</dt><dd>${PDT.pct(r.outcome.prevention_rate)}</dd></div>
          <div><dt>Added friction</dt><dd>${PDT.pct(r.outcome.added_friction_rate)}</dd></div>
        </div>
        <p class="footnote">${PDT.esc(r.note)}</p>
      </div>`;
  }

  function gapCard(g) {
    const sample = g.evidence[0];
    return `
    <details class="gap-card">
      <summary>
        <div class="gap-sev ${PDT.esc(g.severity)}"></div>
        <div>
          <div class="gap-title">${PDT.esc(g.title)}</div>
          <div class="gap-sub">${PDT.esc(g.affected_families.join(", ") || "no families")}</div>
        </div>
        <div class="gap-count">
          ${g.occurrences} occurrence${g.occurrences === 1 ? "" : "s"}<br>
          <span class="hint">avg ml ${PDT.num(g.avg_ml_score, 3)}</span>
        </div>
      </summary>

      <div class="gap-body">
        <div class="gap-section">
          <h4>Finding</h4>
          <div class="reason-block red">${PDT.esc(g.description)}</div>
        </div>

        <div class="gap-section">
          <h4>Evidence</h4>
          ${evidenceTable(g.evidence)}
        </div>

        <div class="gap-section">
          <h4>Counterfactual replay — candidate interventions</h4>
          ${
            g.interventions.length
              ? g.interventions
                  .map((iv, i) => interventionCard(g.gap_id, iv, i, sample && sample.observation_id))
                  .join("")
              : '<div class="empty">No candidate interventions defined for this gap.</div>'
          }
        </div>
      </div>
    </details>`;
  }

  async function load() {
    const box = document.getElementById("gap-cards");
    if (!box) return;
    box.innerHTML = '<div class="panel placeholder">Loading control gap findings…</div>';

    try {
      const data = await PDT.get("/api/labs/gaps");

      if (!data.findings.length) {
        box.innerHTML = `
          <div class="panel placeholder">
            No control gaps found yet. Gaps appear once an adversarial payment is allowed
            through — run a campaign from the Overview.
          </div>`;
        return;
      }

      box.innerHTML =
        `<div class="cards">
          <div class="card">
            <h3>Bypassed payments</h3>
            <div class="metric">${data.total_bypassed}</div>
            <div class="sub">adversarial journeys allowed</div>
          </div>
          <div class="card">
            <h3>Distinct gaps</h3>
            <div class="metric">${data.findings.length}</div>
            <div class="sub">systemic findings</div>
          </div>
        </div>` + data.findings.map(gapCard).join("");

      box.querySelectorAll(".replay-btn").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const slot = btn.closest(".intervention").querySelector(".replay-slot");
          btn.disabled = true;
          btn.textContent = "Replaying…";
          slot.innerHTML = '<div class="replay-result neutral">Re-executing the campaign against the sandbox…</div>';
          try {
            const r = await PDT.post("/api/labs/counterfactual", {
              observation_id: btn.dataset.obs,
              overrides: JSON.parse(btn.dataset.overrides),
            });
            renderReplay(slot, r);
          } catch (err) {
            slot.innerHTML = `<div class="replay-result neutral">Replay failed: ${PDT.esc(err.message)}</div>`;
          } finally {
            btn.disabled = false;
            btn.textContent = "Replay journey";
          }
        });
      });
    } catch (err) {
      box.innerHTML = `<div class="panel placeholder">Could not load findings: ${PDT.esc(err.message)}</div>`;
    }
  }

  PDT.register("labs", { enter: load });
})(window.PDT);
