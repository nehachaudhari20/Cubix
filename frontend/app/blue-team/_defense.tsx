"use client"
import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { blueTeamV1 } from "@/lib/api-v1"

export default function BlueDefense() {
  const [status, setStatus] = useState<any>(null)
  const [models, setModels] = useState<any>(null)
  const [recent, setRecent] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState("")

  useEffect(() => {
    Promise.all([
      api.status().catch((e) => { setErr(e.message); return null }),
      blueTeamV1.models().catch(() => null),
      api.recent(12).catch(() => []),
    ]).then(([s, m, rec]) => {
      setStatus(s)
      setModels(m)
      setRecent(Array.isArray(rec) ? rec : [])
      setLoading(false)
    })
  }, [])

  if (loading) return <div style={{ color: "#6b7280", padding: 40 }}>Loading...</div>

  const m = status?.model || {}
  const r = status?.latest_run
  const b = status?.buffer
  const hr = m?.hardening_report || {}
  const det = hr.detection || m?.metrics || {}
  const tm = hr.training_manifest || null

  const fi = det?.feature_importance || {}
  const features = Object.keys(fi).length > 0
    ? Object.entries(fi).sort((a: any, b: any) => b[1] - a[1]).slice(0, 10)
    : []

  const bufferList = recent.slice(0, 8).map((e: any) => ({
    fam: e.attack_family || "unknown",
    why: e.evasion_outcome || e.action_type || "analysis pending",
    reason: e.sandbox_decision === "ALLOW" ? "novel failure" : e.sandbox_decision === "CHALLENGE" ? "high-information" : "baseline",
  }))

  const modelRows = models?.models || []
  const v1Metrics = det?.v1_metrics || {}
  const v3Metrics = det?.v3_metrics || det || {}
  const compare = [
    { l: "Precision", old: v1Metrics.precision?.toFixed(3) || "--", new: v3Metrics.precision?.toFixed(3) || "--" },
    { l: "Recall", old: v1Metrics.recall?.toFixed(3) || "--", new: v3Metrics.recall?.toFixed(3) || "--" },
    { l: "F1", old: v1Metrics.f1?.toFixed(3) || "--", new: v3Metrics.f1?.toFixed(3) || "--" },
    { l: "AUC", old: v1Metrics.roc_auc?.toFixed(3) || "--", new: v3Metrics.roc_auc?.toFixed(3) || "--" },
    { l: "FPR", old: v1Metrics.fpr != null ? (v1Metrics.fpr * 100).toFixed(1) + "%" : "--", new: v3Metrics.fpr != null ? (v3Metrics.fpr * 100).toFixed(1) + "%" : "--" },
  ]

  return (
    <div style={{ padding: "22px 28px 0" }}>
      {err && <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 12, color: "#dc2626" }}>{err}</div>}

      <p style={{ margin: "0 0 18px", color: "#6b7280", fontSize: 13 }}>
        RedBlue model hardening — feature engineering, scoring, adversarial buffer, and the closed-loop pipeline.
      </p>

      <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>Model version history</div>
          <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 100, background: "rgba(22,163,74,.12)", color: "#16a34a", fontFamily: "'JetBrains Mono', monospace" }}>
            active: {m?.version || "v3"}
          </span>
        </div>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr>
              {["Version", "Trained on", "Precision", "Recall", "F1", "AUC", "FPR", "Status"].map((h) => (
                <th key={h} style={{ textAlign: "left", color: "#6b7280", fontWeight: 500, fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".5px", padding: "9px 10px", borderBottom: "1px solid #e5e7eb" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb" }}><span style={{ padding: "2px 9px", borderRadius: 5, fontSize: 10.5, fontWeight: 700, background: "#f3f4f6" }}>v1</span></td>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb" }}>baseline + known fraud</td>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb", fontFamily: "'JetBrains Mono', monospace" }}>{v1Metrics.precision?.toFixed(3) || "--"}</td>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb", fontFamily: "'JetBrains Mono', monospace" }}>{v1Metrics.recall?.toFixed(3) || "--"}</td>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb", fontFamily: "'JetBrains Mono', monospace" }}>{v1Metrics.f1?.toFixed(3) || "--"}</td>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb", fontFamily: "'JetBrains Mono', monospace" }}>{v1Metrics.roc_auc?.toFixed(3) || "--"}</td>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb", fontFamily: "'JetBrains Mono', monospace" }}>{v1Metrics.fpr != null ? (v1Metrics.fpr * 100).toFixed(1) + "%" : "--"}</td>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb", color: "#6b7280" }}>archived</td>
            </tr>
            <tr style={{ background: "rgba(22,163,74,0.03)" }}>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb" }}><span style={{ padding: "2px 9px", borderRadius: 5, fontSize: 10.5, fontWeight: 700, background: "rgba(22,163,74,.12)", color: "#16a34a" }}>{m?.version || "v3"}</span></td>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb" }}>hardened + adversarial buffer</td>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb", fontFamily: "'JetBrains Mono', monospace" }}>{v3Metrics.precision?.toFixed(3) || "--"}</td>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb", fontFamily: "'JetBrains Mono', monospace" }}>{v3Metrics.recall?.toFixed(3) || "--"}</td>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb", fontFamily: "'JetBrains Mono', monospace" }}>{v3Metrics.f1?.toFixed(3) || "--"}</td>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb", fontFamily: "'JetBrains Mono', monospace" }}>{v3Metrics.roc_auc?.toFixed(3) || "--"}</td>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb", fontFamily: "'JetBrains Mono', monospace" }}>{v3Metrics.fpr != null ? (v3Metrics.fpr * 100).toFixed(1) + "%" : "--"}</td>
              <td style={{ padding: "11px 10px", borderBottom: "1px solid #e5e7eb", color: "#16a34a", fontWeight: 600 }}>deployed</td>
            </tr>
          </tbody>
        </table>
        {modelRows.length > 0 && (
          <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
            {modelRows.map((row: any) => (
              <span key={row.version} style={{ fontSize: 10, padding: "3px 8px", borderRadius: 6, background: "#f9fafb", border: "1px solid #e5e7eb", color: "#374151", fontFamily: "'JetBrains Mono', monospace" }}>
                {row.version}: {row.type || row.status}
              </span>
            ))}
          </div>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>
            Feature importance <span style={{ fontSize: 9.5, padding: "2px 7px", borderRadius: 5, background: "#f9fafb", color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>RedBlue {m?.version || "v3"}</span>
          </div>
          {features.length > 0 ? features.map(([name, value]) => (
            <div key={String(name)} style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 11 }}>
              <div style={{ width: 150, fontSize: 11.5, color: "#6b7280", flexShrink: 0, fontFamily: "'JetBrains Mono', monospace" }}>{String(name)}</div>
              <div style={{ flex: 1, height: 9, background: "#f3f4f6", borderRadius: 5, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${Math.min(100, (value as number) * 100)}%`, background: "linear-gradient(90deg, #2563eb, #7c3aed)", borderRadius: 5 }} />
              </div>
              <div style={{ width: 42, textAlign: "right", fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: "#6b7280" }}>{(value as number).toFixed(2)}</div>
            </div>
          )) : <div style={{ color: "#6b7280", fontSize: 13 }}>No feature importance data available.</div>}
        </div>

        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>
            Adversarial buffer <span style={{ fontSize: 9.5, padding: "2px 7px", borderRadius: 5, background: "#f9fafb", color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>{b?.payment_records || 0} examples</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 340, overflowY: "auto" }}>
            {bufferList.length > 0 ? bufferList.map((buf: any, i: number) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 9, padding: "10px 12px", fontSize: 12 }}>
                <div>
                  <div style={{ fontWeight: 500 }}>{buf.fam}</div>
                  <div style={{ color: "#6b7280", fontSize: 10.5, marginTop: 2 }}>{buf.why}</div>
                </div>
                <span style={{ fontSize: 9.5, padding: "2px 8px", borderRadius: 100, background: "rgba(124,58,237,0.08)", color: "#7c3aed", fontFamily: "'JetBrains Mono', monospace" }}>{buf.reason}</span>
              </div>
            )) : <div style={{ color: "#6b7280", fontSize: 13 }}>No buffer data available.</div>}
          </div>
        </div>
      </div>

      <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginBottom: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Before / after hardening</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
          {compare.map((c) => (
            <div key={c.l} style={{ background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 10, padding: 12, textAlign: "center" }}>
              <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".4px", marginBottom: 8 }}>{c.l}</div>
              <div style={{ fontSize: 12, color: "#9ca3af", textDecoration: "line-through" }}>{c.old}</div>
              <div style={{ fontSize: 17, fontWeight: 600, fontFamily: "'JetBrains Mono', monospace", marginTop: 2, color: "#16a34a" }}>{c.new}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Latest Completed Run</div>
          {r && r.status === "completed" ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10 }}>
              {[
                ["Buffer Payments", r.buffer_payments],
                ["Bypassed", r.buffer_bypassed],
                ["Score Lift", r.score_lift != null ? `${r.score_lift >= 0 ? "+" : ""}${r.score_lift.toFixed(4)}` : "--"],
                ["PR-AUC", r.val_pr_auc?.toFixed(4) || "--"],
                ["Verify", r.verify_decision || "--"],
                ["ML Score", r.verify_ml_score?.toFixed(4) || "--"],
              ].map(([k, v]) => (
                <div key={String(k)} style={{ padding: "10px 12px", background: "#f9fafb", borderRadius: 8 }}>
                  <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".4px", marginBottom: 4 }}>{String(k)}</div>
                  <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 14, fontWeight: 600 }}>{v}</div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: "#6b7280", fontSize: 13 }}>No completed run found.</div>
          )}
        </div>

        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Evidence Buffer</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10, marginBottom: 14 }}>
            {[
              ["Payments", b?.payment_records],
              ["Blocked", b?.blocked],
              ["Bypassed", b?.bypassed],
              ["Fraud Labeled", b?.fraud_labeled],
            ].map(([k, v]) => (
              <div key={String(k)} style={{ padding: "10px 12px", background: "#f9fafb", borderRadius: 8 }}>
                <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".4px", marginBottom: 4 }}>{String(k)}</div>
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 14, fontWeight: 600 }}>{v ?? "--"}</div>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {(b?.families || []).slice(0, 12).map((f: string) => (
              <span key={f} style={{ fontSize: 10, padding: "2px 7px", borderRadius: 5, background: "#f3f4f6", color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>{f}</span>
            ))}
          </div>
        </div>
      </div>

      {tm && (
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginTop: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Training Manifest</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
            {[
              ["Baseline Rows", tm.baseline_rows],
              ["Buffer Rows", tm.buffer_selected_rows],
              ["Total Rows", tm.total_rows],
              ["Fraud Rows", tm.fraud_rows],
              ["Legit Rows", tm.legit_rows],
              ["Train Fraud Rate", tm.train_fraud_rate?.toFixed?.(3)],
              ["Val Fraud Rate", tm.val_fraud_rate?.toFixed?.(3)],
              ["Campaigns", tm.adv_campaigns_total],
            ].map(([k, v]) => (
              <div key={String(k)} style={{ padding: "10px 12px", background: "#f9fafb", borderRadius: 8 }}>
                <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".4px", marginBottom: 4 }}>{String(k)}</div>
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 14, fontWeight: 600 }}>{v ?? "--"}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
