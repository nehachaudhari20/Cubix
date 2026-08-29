"use client"
import { useEffect, useState } from "react"
import { closedLoop } from "@/lib/api-v1"



export default function ClosedLoopArena() {
  const [comp, setComp] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const runComparison = async () => {
    setLoading(true)
    try {
      const loop = await closedLoop.run({ families: 8 })
      const c = await closedLoop.comparison(loop.loop_id)
      setComp(c)
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  return (
    <div style={{ background: "#f8f9fa", color: "#111827", minHeight: "100vh", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "22px 28px 60px" }}>
        <h2 style={{ margin: "0 0 4px", fontSize: 20 }}>Closed-Loop Arena</h2>
        <p style={{ margin: "0 0 20px", color: "#6b7280", fontSize: 13 }}>Attack → Detect → Learn → Harden → Re-test — measurable robustness improvement.</p>

        <button onClick={runComparison} disabled={loading} style={{ padding: "12px 24px", borderRadius: 10, background: `linear-gradient(135deg, ${"#dc2626"}, ${"#ea580c"})`, color: "#fff", fontWeight: 600, fontSize: 14, border: "none", cursor: "pointer", marginBottom: 24 }}>
          {loading ? "Running…" : "🔄 Run Comparison"}
        </button>

        {comp && (
          <>
            {/* Flow diagram */}
            <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18, marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Closed-Loop Flow</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                {["Red Team Attack", "FraudShield v1 Scores", "Gaps Found", "Blue Team Retrains", "FraudShield v3 Scores", "ASR Measured"].map((step, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ padding: "8px 12px", background: "#f9fafb", borderRadius: 8, border: `1px solid ${"#e5e7eb"}`, color: "#111827" }}>{step}</div>
                    {i < 5 && <span style={{ color: "#6b7280" }}>→</span>}
                  </div>
                ))}
              </div>
            </div>

            {/* Before/After comparison */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
              {[
                { label: "FraudShield v1", data: comp.before, color: "#6b7280" },
                { label: "FraudShield v3", data: comp.after, color: "#16a34a" },
              ].map((model, i) => (
                <div key={i} style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: model.color }}>{model.label}</div>
                  <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 16 }}>{model.data.type}</div>
                  {[
                    { label: "PR-AUC", value: model.data.pr_auc },
                    { label: "F1", value: model.data.f1 },
                    { label: "Recall", value: model.data.recall },
                    { label: "FPR", value: model.data.fpr },
                    { label: "ASR", value: model.data.asr },
                  ].map((m, j) => (
                    <div key={j} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: `1px solid ${"#e5e7eb"}`, fontSize: 12 }}>
                      <span style={{ color: "#6b7280" }}>{m.label}</span>
                      <span style={{ fontFamily: "'JetBrains Mono', monospace", color: m.label === "ASR" ? (model.data.asr > 0.1 ? "#dc2626" : "#16a34a") : "#111827" }}>{m.value?.toFixed(4) || "—"}</span>
                    </div>
                  ))}
                </div>
              ))}
            </div>

            {/* Deltas */}
            <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Improvement Deltas</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12 }}>
                {Object.entries(comp.deltas || {}).map(([key, val]: [string, any]) => (
                  <div key={key} style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", marginBottom: 4 }}>{key.replace("_", " ")}</div>
                    <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 16, fontWeight: 600, color: val > 0 ? "#16a34a" : "#dc2626" }}>
                      {val > 0 ? "+" : ""}{typeof val === "number" ? val.toFixed(4) : val}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
