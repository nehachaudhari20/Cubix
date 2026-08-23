/* Blue Team page — model lineage, feature importance, buffer, hardening deltas. */

(function (PDT) {
  function renderCards(models, buffer) {
    const box = document.getElementById("blue-cards");
    if (!box) return;

    const active = models.active || {};
    const metrics = (active.metrics || {}).results || [];
    const best = metrics.length ? metrics[metrics.length - 1] : {};
    const stats = buffer.stats || {};

    box.innerHTML = `
      <div class="card">
        <h3>Active model</h3>
        <div class="metric">${PDT.esc(active.version || "none")}</div>
        <div class="sub">${PDT.esc(active.model_type || "not loaded")}</div>
      </div>
      <div class="card">
        <h3>Decision threshold</h3>
        <div class="metric">${PDT.num(active.threshold, 3)}</div>
        <div class="sub">tuned on validation split</div>
      </div>
      <div class="card">
        <h3>Holdout PR-AUC</h3>
        <div class="metric">${PDT.num(best.pr_auc, 3)}</div>
        <div class="sub">ROC-AUC ${PDT.num(best.roc_auc, 3)}</div>
      </div>
      <div class="card">
        <h3>Adversarial buffer</h3>
        <div class="metric">${stats.payment_records ?? 0}</div>
        <div class="sub">${stats.bypassed ?? 0} bypassed · ${stats.blocked ?? 0} contained</div>
      </div>
      <div class="card">
        <h3>Training rounds</h3>
        <div class="metric">${(models.history || []).length}</div>
        <div class="sub">${(stats.families || []).length} families in buffer</div>
      </div>`;
  }

  function renderHistory(models) {
    const body = document.getElementById("model-history-body");
    if (!body) return;

    const history = models.history || [];
    if (!history.length) {
      body.innerHTML =
        '<tr><td colspan="8" class="empty">No training rounds recorded yet — run a loop with hardening enabled.</td></tr>';
      return;
    }

    body.innerHTML = history
      .map(
        (m) => `
      <tr>
        <td><b>${PDT.esc(m.version)}</b><br><span class="hint">${PDT.esc(m.model_type)}</span></td>
        <td class="mono">${PDT.date(m.trained_at)}</td>
        <td class="mono">${m.baseline_rows} baseline<br><span class="hint">${m.buffer_rows} adversarial</span></td>
        <td>${PDT.num(m.val_pr_auc, 4)}<br>${PDT.delta(m.delta_pr_auc)}</td>
        <td>${PDT.num(m.val_roc_auc, 4)}<br>${PDT.delta(m.delta_roc_auc)}</td>
        <td>${PDT.delta(m.score_lift)}</td>
        <td class="mono">${PDT.num(m.decision_threshold, 3)}</td>
        <td>${m.promoted ? '<span class="chip green">promoted</span>' : '<span class="chip">held</span>'}</td>
      </tr>`
      )
      .join("");
  }

  function renderImportance(data) {
    const box = document.getElementById("feature-importance");
    if (!box) return;

    if (!data.available || !data.features.length) {
      box.innerHTML = `<div class="empty">${PDT.esc(data.reason || "No importance available")}</div>`;
      return;
    }

    const max = data.features[0].gain || 1;
    box.innerHTML =
      `<p class="hint" style="margin-bottom:0.7rem">${PDT.esc(data.model_version)} · ${PDT.esc(
        data.model_type
      )} · gain</p>` +
      data.features
        .map(
          (f) => `
      <div class="bar-row">
        <span class="bar-name" title="${PDT.esc(f.feature)}">${PDT.esc(f.feature)}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${(f.gain / max) * 100}%"></div></div>
        <span class="bar-val">${PDT.pct(f.share, 1)}</span>
      </div>`
        )
        .join("");
  }

  function renderComparison(data) {
    const box = document.getElementById("hardening-compare");
    if (!box) return;

    const c = data.comparison || {};
    if (!Object.keys(c).length) {
      box.innerHTML = '<div class="empty">No hardening comparison recorded yet.</div>';
      return;
    }

    const rows = [
      {
        label: "Mean score on adversarial buffer",
        v1: c.v1_buffer_mean_score,
        v2: c.v2_buffer_mean_score,
        better: "up",
      },
      {
        label: "Baseline fraud recall",
        v1: c.v1_baseline_fraud_recall,
        v2: c.v2_baseline_fraud_recall,
        better: "up",
      },
    ];

    const bars = rows
      .map((r) => {
        const d = r.v1 != null && r.v2 != null ? r.v2 - r.v1 : null;
        return `
        <div class="compare-row">
          <span>${PDT.esc(r.label)}</span>
          <b>${PDT.num(r.v1, 4)}</b>
          <b>${PDT.num(r.v2, 4)}</b>
          ${PDT.delta(d)}
        </div>`;
      })
      .join("");

    box.innerHTML = `
      <div class="compare-row header">
        <span>Metric</span><span>v1</span><span>v2</span><span>Δ</span>
      </div>
      ${bars}
      <div class="kv" style="margin-top:1rem">
        <div><dt>Buffer records</dt><dd>${c.buffer_records ?? 0}</dd></div>
        <div><dt>Attacks that bypassed</dt><dd>${c.bypassed_attacks ?? 0}</dd></div>
        <div><dt>Recommendation</dt><dd style="font-size:0.85rem">${
          c.recommend_swap ? '<span class="chip green">promote v2</span>' : '<span class="chip amber">hold v1</span>'
        }</dd></div>
      </div>`;
  }

  function renderBuffer(data) {
    const body = document.getElementById("buffer-body");
    if (!body) return;

    const records = data.records || [];
    if (!records.length) {
      body.innerHTML = '<tr><td colspan="8" class="empty">Buffer is empty.</td></tr>';
      return;
    }

    body.innerHTML = records
      .map(
        (r) => `
      <tr>
        <td class="mono">${PDT.esc(r.evidence_id)}</td>
        <td class="mono">${PDT.esc(r.attack_family)}</td>
        <td>${r.step ?? "—"}</td>
        <td class="d-${PDT.esc(r.sandbox_decision)}">${PDT.esc(r.sandbox_decision)}</td>
        <td>${PDT.esc(r.evasion_outcome)}</td>
        <td>${PDT.num(r.ml_score, 3)}</td>
        <td>${PDT.num(r.rule_risk, 3)}</td>
        <td>${r.amount != null ? PDT.money(r.amount) : "—"}</td>
      </tr>`
      )
      .join("");
  }

  async function load() {
    const filter = document.getElementById("buffer-filter");
    const outcome = filter ? filter.value : "";

    try {
      const [models, importance, comparison, buffer] = await Promise.all([
        PDT.get("/api/blue/models"),
        PDT.get("/api/blue/feature-importance?top=18"),
        PDT.get("/api/blue/comparison"),
        PDT.get(`/api/blue/buffer?limit=60${outcome ? `&outcome=${outcome}` : ""}`),
      ]);

      renderCards(models, buffer);
      renderHistory(models);
      renderImportance(importance);
      renderComparison(comparison);
      renderBuffer(buffer);
    } catch (err) {
      console.error("blue team load failed", err);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const filter = document.getElementById("buffer-filter");
    if (filter) filter.addEventListener("change", load);
  });

  PDT.register("blue", { enter: load });
})(window.PDT);
