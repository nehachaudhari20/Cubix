"use client"
import { useEffect, useState } from "react"
import { blueTeamV1 } from "@/lib/api-v1"



export default function ModelEvolution() {
  const [models, setModels] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    blueTeamV1.models().then(r => { setModels(r); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ color: "#6b7280", padding: 40, background: "#f8f9fa", minHeight: "100vh" }}>Loading…</div>

  return (
    <div style={{ background: "#f8f9fa", color: "#111827", minHeight: "100vh", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "22px 28px 60px" }}>
        <h2 style={{ margin: "0 0 4px", fontSize: 20 }}>FraudShield Model Evolution</h2>
        <p style={{ margin: "0 0 20px", color: "#6b7280", fontSize: 13 }}>Every model version is a response to an observed attack gap.</p>

        {/* Evolution chain */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 24 }}>
          {[
            { version: "v1", title: "Baseline Booster", type: "Single XGBoost/LightGBM", training: "Historical data", color: "#6b7280", status: "archived" },
            { version: "v2", title: "Hardened Booster", type: "Single Booster + adversarial", training: "+ 2,140 Red Team examples", color: "#ea580c", status: "archived" },
            { version: "v3", title: "Stacked Ensemble", type: "XGB + LGB + Logistic → Meta", training: "+ 4,812 Red Team examples", color: "#16a34a", status: "deployed" },
          ].map((m, i) => (
            <div key={i} style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 20, borderTop: `3px solid ${m.color}`, position: "relative" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: m.color }}>{m.version}</div>
                <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 100, background: m.status === "deployed" ? "rgba(34,229,160,.16)" : "#f9fafb", color: m.status === "deployed" ? "#16a34a" : "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>{m.status}</span>
              </div>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{m.title}</div>
              <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 8 }}>{m.type}</div>
              <div style={{ fontSize: 11, color: "#6b7280" }}>{m.training}</div>
              {i < 2 && <div style={{ position: "absolute", right: -20, top: "50%", transform: "translateY(-50%)", fontSize: 18, color: "#6b7280" }}>→</div>}
            </div>
          ))}
        </div>

        {/* Model details */}
        {models?.models?.map((model: any, i: number) => (
          <div key={i} style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18, marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>FraudShield {model.version}</div>
              <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 100, background: model.status === "deployed" ? "rgba(34,229,160,.16)" : "#f9fafb", color: model.status === "deployed" ? "#16a34a" : "#6b7280" }}>{model.status}</span>
            </div>
            <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 8 }}>{model.role}</div>
            {model.components && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8 }}>
                {Object.entries(model.components).map(([name, desc]: [string, any]) => (
                  <div key={name} style={{ padding: "8px 10px", background: "#f9fafb", borderRadius: 8 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: "#2563eb", fontFamily: "'JetBrains Mono', monospace", marginBottom: 2 }}>{name}</div>
                    <div style={{ fontSize: 10, color: "#6b7280" }}>{desc}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

        {/* Ensemble composition */}
        <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Active Model: FraudShield v3 — Stacked Ensemble</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12 }}>
            {[
              { name: "XGBoost", role: "Non-linear patterns", pct: 40, color: "#dc2626" },
              { name: "LightGBM", role: "Gradient-boosted signals", pct: 30, color: "#2563eb" },
              { name: "Logistic", role: "Linear boundary", pct: 20, color: "#16a34a" },
              { name: "Meta Learner", role: "Combines probabilities", pct: 100, color: "#7c3aed" },
              { name: "Isolation Forest", role: "Anomaly detection", pct: 15, color: "#ea580c" },
            ].map((m, i) => (
              <div key={i} style={{ padding: "12px", background: "#f9fafb", borderRadius: 10, borderLeft: `3px solid ${m.color}` }}>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 2 }}>{m.name}</div>
                <div style={{ fontSize: 10, color: "#6b7280", marginBottom: 8 }}>{m.role}</div>
                <div style={{ height: 6, background: "#e5e7eb", borderRadius: 3, overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${m.pct}%`, background: m.color, borderRadius: 3 }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
