"use client"
import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { blueTeamV1, governance } from "@/lib/api-v1"

export default function ModelEvolution() {
  const [models, setModels] = useState<any>(null)
  const [registry, setRegistry] = useState<any>(null)
  const [status, setStatus] = useState<any>(null)
  const [details, setDetails] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      blueTeamV1.models().catch(() => null),
      governance.modelRegistry().catch(() => null),
      api.status().catch(() => null),
    ]).then(async ([m, r, s]) => {
      setModels(m)
      setRegistry(r)
      setStatus(s)
      const versions = (m?.models || []).map((x: any) => x.version).filter(Boolean)
      const det: Record<string, any> = {}
      await Promise.all(
        versions.slice(0, 4).map(async (v: string) => {
          try {
            det[v] = await blueTeamV1.modelDetail(v)
          } catch {
            /* ignore */
          }
        })
      )
      setDetails(det)
      setLoading(false)
    })
  }, [])

  if (loading) return <div style={{ color: "#6b7280", padding: 40, background: "#f8f9fa", minHeight: "100vh" }}>Loading…</div>

  const hr = status?.model?.hardening_report || {}
  const tm = hr.training_manifest || {}
  const det = hr.detection || status?.model?.metrics || {}
  const blend = { rule: 0.4, ml: 0.45, anomaly: 0.15 }

  const cards = (models?.models || []).map((m: any) => {
    const d = details[m.version] || {}
    const metrics = d.metrics || {}
    return {
      version: m.version,
      title: m.role?.split("—")[0]?.trim() || m.type,
      type: m.type,
      training: m.training_data || `${d.feature_count || "—"} features`,
      status: m.status,
      color: m.status === "deployed" || m.status === "active" ? "#16a34a" : "#6b7280",
      metrics,
      components: m.components,
    }
  })

  // Ensure at least v1/v3 placeholders from registry if models empty
  const displayCards = cards.length
    ? cards
    : (registry?.registry || []).map((m: any) => ({
        version: m.version,
        title: m.model_type,
        type: m.model_type,
        training: `${m.feature_count} features`,
        status: m.status,
        color: m.status === "deployed" ? "#16a34a" : "#6b7280",
        metrics: {},
        components: null,
      }))

  return (
    <div style={{ background: "#f8f9fa", color: "#111827", minHeight: "100vh", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "22px 28px 60px" }}>
        <h2 style={{ margin: "0 0 4px", fontSize: 20 }}>RedBlue Model Evolution</h2>
        <p style={{ margin: "0 0 20px", color: "#6b7280", fontSize: 13 }}>
          Model versions from registry · active={models?.active_version || status?.model?.version || "—"}
          {tm.buffer_selected_rows != null && ` · buffer rows=${tm.buffer_selected_rows}`}
        </p>

        <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.max(1, Math.min(3, displayCards.length || 1))}, 1fr)`, gap: 16, marginBottom: 24 }}>
          {displayCards.map((m: any, i: number) => (
            <div key={i} style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 20, borderTop: `3px solid ${m.color}`, position: "relative" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: m.color }}>{m.version}</div>
                <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 100, background: m.status === "deployed" || m.status === "active" ? "rgba(34,229,160,.16)" : "#f9fafb", color: m.status === "deployed" || m.status === "active" ? "#16a34a" : "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>{m.status}</span>
              </div>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{m.title}</div>
              <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 8 }}>{m.type}</div>
              <div style={{ fontSize: 11, color: "#6b7280" }}>{m.training}</div>
              {(m.metrics?.pr_auc != null || m.metrics?.f1 != null) && (
                <div style={{ marginTop: 10, display: "flex", gap: 10, fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}>
                  {m.metrics.pr_auc != null && <span>PR-AUC {Number(m.metrics.pr_auc).toFixed(3)}</span>}
                  {m.metrics.f1 != null && <span>F1 {Number(m.metrics.f1).toFixed(3)}</span>}
                </div>
              )}
            </div>
          ))}
        </div>

        {displayCards.map((model: any, i: number) =>
          model.components ? (
            <div key={i} style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginBottom: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <div style={{ fontSize: 14, fontWeight: 600 }}>RedBlue {model.version}</div>
                <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 100, background: "#f9fafb", color: "#6b7280" }}>{model.status}</span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8 }}>
                {Object.entries(model.components).map(([name, desc]: [string, any]) => (
                  <div key={name} style={{ padding: "8px 10px", background: "#f9fafb", borderRadius: 8 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: "#2563eb", fontFamily: "'JetBrains Mono', monospace", marginBottom: 2 }}>{name}</div>
                    <div style={{ fontSize: 10, color: "#6b7280" }}>{desc}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null
        )}

        <div style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>
            Active risk blend — {status?.model?.version || "RedBlue"} ({status?.model?.model_type || "—"})
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 16 }}>
            {[
              { name: "Rule Risk", pct: blend.rule * 100, color: "#dc2626" },
              { name: "ML Ensemble", pct: blend.ml * 100, color: "#2563eb" },
              { name: "Isolation Forest", pct: blend.anomaly * 100, color: "#ea580c" },
            ].map((m, i) => (
              <div key={i} style={{ padding: 12, background: "#f9fafb", borderRadius: 10, borderLeft: `3px solid ${m.color}` }}>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 2 }}>{m.name}</div>
                <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 8 }}>{m.pct.toFixed(0)}%</div>
                <div style={{ height: 6, background: "#e5e7eb", borderRadius: 3, overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${m.pct}%`, background: m.color, borderRadius: 3 }} />
                </div>
              </div>
            ))}
          </div>
          {(det.pr_auc != null || det.f1 != null) && (
            <div style={{ display: "flex", gap: 16, fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: "#374151" }}>
              {det.pr_auc != null && <span>PR-AUC {Number(det.pr_auc).toFixed(3)}</span>}
              {det.f1 != null && <span>F1 {Number(det.f1).toFixed(3)}</span>}
              {det.roc_auc != null && <span>ROC-AUC {Number(det.roc_auc).toFixed(3)}</span>}
              {det.fpr != null && <span>FPR {(Number(det.fpr) * 100).toFixed(1)}%</span>}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
