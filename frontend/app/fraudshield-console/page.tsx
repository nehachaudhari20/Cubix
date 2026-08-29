"use client"
import { useEffect, useState } from "react"
import { blueTeamV1 } from "@/lib/api-v1"



export default function FraudShieldConsole() {
  const [eventId, setEventId] = useState("txn_demo_001")
  const [result, setResult] = useState<any>(null)
  const [explain, setExplain] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const handleScore = async () => {
    setLoading(true)
    try {
      const res = await blueTeamV1.score({ event_id: eventId })
      setResult(res)
      const exp = await blueTeamV1.explain(res.score_id)
      setExplain(exp)
    } catch (e) { console.error(e) }
    setLoading(false)
  }

  return (
    <div style={{ background: "#f8f9fa", color: "#111827", minHeight: "100vh", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "22px 28px 60px" }}>
        <h2 style={{ margin: "0 0 4px", fontSize: 20 }}>Blue Team — FraudShield Console</h2>
        <p style={{ margin: "0 0 20px", color: "#6b7280", fontSize: 13 }}>Score, explain, and audit payment decisions through the full FraudShield v3 ensemble.</p>

        {/* Score input */}
        <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18, marginBottom: 16 }}>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <input value={eventId} onChange={e => setEventId(e.target.value)} placeholder="Event ID" style={{ flex: 1, padding: "10px 14px", borderRadius: 8, border: `1px solid ${"#e5e7eb"}`, background: "#f9fafb", color: "#111827", fontSize: 13, fontFamily: "'JetBrains Mono', monospace" }} />
            <button onClick={handleScore} disabled={loading} style={{ padding: "10px 24px", borderRadius: 8, background: `linear-gradient(135deg, ${"#2563eb"}, ${"#7c3aed"})`, color: "#fff", fontWeight: 600, fontSize: 13, border: "none", cursor: "pointer" }}>
              {loading ? "Scoring…" : "Score with FraudShield"}
            </button>
          </div>
        </div>

        {result && (
          <>
            {/* Decision card */}
            <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 24, marginBottom: 16, textAlign: "center" }}>
              <div style={{ fontSize: 36, fontWeight: 700, color: result.decision.action === "BLOCK" ? "#dc2626" : result.decision.action === "CHALLENGE" ? "#ea580c" : "#16a34a" }}>
                {result.decision.action}
              </div>
              <div style={{ fontSize: 18, fontFamily: "'JetBrains Mono', monospace", marginTop: 4, color: "#6b7280" }}>
                RISK SCORE {result.scores.final_blended_risk}
              </div>
              <div style={{ fontSize: 12, color: "#6b7280", marginTop: 8 }}>
                Model: {result.model.version} · Latency: {result.latency_ms}ms · Policy: {result.decision.threshold}
              </div>
            </div>

            {/* Two columns: Ensemble + Reasons */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              {/* Ensemble breakdown */}
              <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18 }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Ensemble Contributions</div>
                {[
                  { label: "XGBoost", value: result.scores.xgboost_probability, color: "#dc2626" },
                  { label: "LightGBM", value: result.scores.lightgbm_probability, color: "#2563eb" },
                  { label: "Logistic", value: result.scores.logistic_probability, color: "#16a34a" },
                  { label: "Meta Learner", value: result.scores.meta_learner_probability, color: "#7c3aed" },
                  { label: "Isolation Forest", value: result.scores.anomaly_score, color: "#ea580c" },
                  { label: "Rule Risk", value: result.scores.rule_risk, color: "#6b7280" },
                ].map((m, i) => (
                  <div key={i} style={{ marginBottom: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 3 }}>
                      <span style={{ color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>{m.label}</span>
                      <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>{m.value.toFixed(4)}</span>
                    </div>
                    <div style={{ height: 6, background: "#f9fafb", borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${m.value * 100}%`, background: m.color, borderRadius: 3 }} />
                    </div>
                  </div>
                ))}
              </div>

              {/* Reason codes */}
              <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18 }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Why Was It {result.decision.action}?</div>
                {explain?.reason_codes?.map((rc: any, i: number) => (
                  <div key={i} style={{ padding: "10px 12px", background: "#f9fafb", borderRadius: 8, marginBottom: 8, borderLeft: `3px solid ${rc.severity === "CRITICAL" ? "#dc2626" : rc.severity === "HIGH" ? "#ea580c" : "#2563eb"}` }}>
                    <div style={{ fontSize: 11, fontFamily: "'JetBrains Mono', monospace", color: rc.severity === "CRITICAL" ? "#dc2626" : "#ea580c" }}>{rc.code}</div>
                    <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>{rc.label}</div>
                  </div>
                ))}
                {explain?.feature_impact?.map((f: any, i: number) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: `1px solid ${"#e5e7eb"}`, fontSize: 12 }}>
                    <span style={{ fontFamily: "'JetBrains Mono', monospace", color: "#6b7280" }}>{f.feature}</span>
                    <span style={{ color: f.direction === "increases_risk" ? "#dc2626" : "#16a34a" }}>{f.impact > 0 ? "+" : ""}{f.impact.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Blend weights */}
            <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18, marginTop: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Risk Score Breakdown</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
                <div>
                  <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>Rules & Controls</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ flex: 1, height: 10, background: "#f9fafb", borderRadius: 5, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${result.scores.rule_risk * 100}%`, background: "#dc2626", borderRadius: 5 }} />
                    </div>
                    <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, fontWeight: 600 }}>{result.scores.rule_risk.toFixed(2)}</span>
                  </div>
                  <div style={{ fontSize: 10, color: "#6b7280", marginTop: 2 }}>weight {result.blend_weights?.rule_risk || 0.4}</div>
                </div>
                <div>
                  <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>ML Ensemble</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ flex: 1, height: 10, background: "#f9fafb", borderRadius: 5, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${result.scores.meta_learner_probability * 100}%`, background: "#2563eb", borderRadius: 5 }} />
                    </div>
                    <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, fontWeight: 600 }}>{result.scores.meta_learner_probability.toFixed(2)}</span>
                  </div>
                  <div style={{ fontSize: 10, color: "#6b7280", marginTop: 2 }}>weight {result.blend_weights?.ml_score || 0.45}</div>
                </div>
                <div>
                  <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 4 }}>Anomaly</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ flex: 1, height: 10, background: "#f9fafb", borderRadius: 5, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${result.scores.anomaly_score * 100}%`, background: "#7c3aed", borderRadius: 5 }} />
                    </div>
                    <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, fontWeight: 600 }}>{result.scores.anomaly_score.toFixed(2)}</span>
                  </div>
                  <div style={{ fontSize: 10, color: "#6b7280", marginTop: 2 }}>weight {result.blend_weights?.anomaly_score || 0.15}</div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
