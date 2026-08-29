"use client"
import { useState } from "react"
import { novelAttack } from "@/lib/api-v1"
import { errorText } from "@/lib/api"



const MODEL_OPTIONS = [
  { id: "openai/gpt-4o-mini", name: "GPT-4o Mini", speed: "Fast", cost: "$0.15/M", quality: "Good" },
  { id: "openai/gpt-4o", name: "GPT-4o", speed: "Medium", cost: "$2.50/M", quality: "Very Good" },
  { id: "x-ai/grok-4.6", name: "Grok 4.6", speed: "Slow", cost: "$2/M", quality: "Excellent" },
  { id: "deepseek/deepseek-chat", name: "DeepSeek V3", speed: "Medium", cost: "$0.27/M", quality: "Excellent" },
]

const FOCUS_AREAS = [
  "AI-agent payment fraud",
  "Synthetic identity attacks",
  "UPI/QR code fraud",
  "Merchant collusion",
  "Device spoofing",
  "Velocity attacks",
  "Cross-border fraud",
  "GenAI deepfake attacks",
]

export default function NovelAttackPage() {
  const [focusArea, setFocusArea] = useState("AI-agent payment fraud")
  const [model, setModel] = useState("openai/gpt-4o-mini")
  const [numAttacks, setNumAttacks] = useState(3)
  const [result, setResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const generate = async () => {
    setLoading(true)
    setError("")
    setResult(null)
    try {
      const data = await novelAttack.generate({
        focus_area: focusArea,
        model,
        num_attacks: numAttacks,
        include_kb_context: true,
      })
      if (data.error) {
        setError(data.error)
      } else {
        setResult(data)
      }
    } catch (e: any) {
      setError(errorText(e))
    }
    setLoading(false)
  }

  return (
    <div style={{ background: "#f8f9fa", color: "#111827", minHeight: "100vh", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "22px 28px 60px" }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4 }}>
          <div style={{ width: 34, height: 34, borderRadius: 9, background: `linear-gradient(135deg, ${"#dc2626"}, ${"#ea580c"})`, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 14 }}>🧠</div>
          <div>
            <h2 style={{ margin: 0, fontSize: 20 }}>Novel Attack Generator</h2>
            <p style={{ margin: 0, color: "#6b7280", fontSize: 12 }}>LLM-powered discovery of novel attack vectors for defensive hardening</p>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "380px 1fr", gap: 16, marginTop: 20 }}>
          {/* Left: Controls */}
          <div>
            {/* Focus Area */}
            <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18, marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Focus Area</div>
              <select value={focusArea} onChange={e => setFocusArea(e.target.value)} style={{ width: "100%", padding: "10px 14px", borderRadius: 8, border: `1px solid ${"#e5e7eb"}`, background: "#f9fafb", color: "#111827", fontSize: 13 }}>
                {FOCUS_AREAS.map(f => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>

            {/* Model Selection */}
            <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18, marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>LLM Model</div>
              {MODEL_OPTIONS.map(m => (
                <div key={m.id} onClick={() => setModel(m.id)} style={{ padding: "10px 12px", background: model === m.id ? "rgba(77,168,255,.15)" : "#f9fafb", border: `1px solid ${model === m.id ? "#2563eb" : "#e5e7eb"}`, borderRadius: 8, marginBottom: 8, cursor: "pointer", transition: "all .2s" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{m.name}</span>
                    <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: "#ffffff", color: "#6b7280" }}>{m.quality}</span>
                  </div>
                  <div style={{ display: "flex", gap: 12, marginTop: 4, fontSize: 11, color: "#6b7280" }}>
                    <span>⏱ {m.speed}</span>
                    <span>💰 {m.cost}</span>
                  </div>
                </div>
              ))}
            </div>

            {/* Number of attacks */}
            <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18, marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Number of Attacks</div>
              <div style={{ display: "flex", gap: 8 }}>
                {[1, 2, 3, 5].map(n => (
                  <button key={n} onClick={() => setNumAttacks(n)} style={{ flex: 1, padding: "10px", borderRadius: 8, background: numAttacks === n ? "#2563eb" : "#f9fafb", border: `1px solid ${numAttacks === n ? "#2563eb" : "#e5e7eb"}`, color: "#111827", fontWeight: 600, cursor: "pointer" }}>
                    {n}
                  </button>
                ))}
              </div>
            </div>

            {/* Generate Button */}
            <button onClick={generate} disabled={loading} style={{ width: "100%", padding: "14px 24px", borderRadius: 10, background: loading ? "#f9fafb" : `linear-gradient(135deg, ${"#dc2626"}, ${"#ea580c"})`, color: "#fff", fontWeight: 600, fontSize: 15, border: "none", cursor: loading ? "not-allowed" : "pointer" }}>
              {loading ? (
                <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
                  <span style={{ animation: "spin 1s linear infinite", display: "inline-block" }}>⏳</span>
                  Generating…
                </span>
              ) : "🧠 Generate Novel Attacks"}
            </button>
          </div>

          {/* Right: Results */}
          <div>
            {error && (
              <div style={{ background: "rgba(255,59,92,.15)", border: `1px solid ${"#dc2626"}`, borderRadius: 14, padding: 18, marginBottom: 16, color: "#dc2626" }}>
                Error: {error}
              </div>
            )}

            {result && (
              <>
                {/* Summary */}
                <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18, marginBottom: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 600 }}>Generated {result.num_generated} Novel Attacks</div>
                      <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>Model: {result.model} · Time: {result.elapsed_seconds}s</div>
                    </div>
                    <div style={{ padding: "6px 12px", borderRadius: 8, background: "rgba(34,229,160,.15)", color: "#16a34a", fontSize: 12, fontWeight: 600 }}>✓ Complete</div>
                  </div>
                </div>

                {/* Attack Cards */}
                {result.attacks?.map((attack: any, i: number) => (
                  <div key={i} style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 20, marginBottom: 16 }}>
                    {/* Attack Header */}
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                      <div>
                        <div style={{ fontSize: 16, fontWeight: 700, color: "#dc2626" }}>{attack.name || `Attack ${i + 1}`}</div>
                        <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>Family: {attack.primary_family || "Unknown"}</div>
                      </div>
                      <div style={{ display: "flex", gap: 8 }}>
                        {attack.novelty_score && (
                          <div style={{ padding: "4px 10px", borderRadius: 6, background: attack.novelty_score > 0.7 ? "rgba(34,229,160,.15)" : "rgba(255,159,67,.15)", color: attack.novelty_score > 0.7 ? "#16a34a" : "#ea580c", fontSize: 11, fontWeight: 600 }}>
                            Novelty: {(attack.novelty_score * 100).toFixed(0)}%
                          </div>
                        )}
                        {attack.success_probability && (
                          <div style={{ padding: "4px 10px", borderRadius: 6, background: "rgba(155,123,255,.15)", color: "#7c3aed", fontSize: 11, fontWeight: 600 }}>
                            Success: {(attack.success_probability * 100).toFixed(0)}%
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Target Stages */}
                    {attack.target_stages && (
                      <div style={{ marginBottom: 12 }}>
                        <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 6 }}>Target Stages</div>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                          {attack.target_stages.map((stage: string, j: number) => (
                            <span key={j} style={{ padding: "3px 8px", borderRadius: 4, background: "#f9fafb", color: "#2563eb", fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}>{stage}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Attack Flow */}
                    {attack.attack_flow && (
                      <div style={{ marginBottom: 12 }}>
                        <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 6 }}>Attack Flow</div>
                        <div style={{ position: "relative", paddingLeft: 22 }}>
                          <div style={{ position: "absolute", left: 6, top: 4, bottom: 4, width: 1.5, background: "#e5e7eb" }} />
                          {attack.attack_flow.map((step: string, j: number) => (
                            <div key={j} style={{ position: "relative", paddingBottom: 8, fontSize: 12, color: "#111827" }}>
                              <div style={{ position: "absolute", left: -22, top: 2, width: 10, height: 10, borderRadius: "50%", border: `2px solid ${"#ea580c"}`, background: "#ffffff" }} />
                              {step}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Evasion Technique */}
                    {attack.evasion_technique && (
                      <div style={{ padding: "10px 12px", background: "rgba(255,159,67,.1)", border: `1px solid rgba(255,159,67,.3)`, borderRadius: 8, marginBottom: 12 }}>
                        <div style={{ fontSize: 10, color: "#ea580c", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 4 }}>Evasion Technique</div>
                        <div style={{ fontSize: 12, color: "#111827" }}>{attack.evasion_technique}</div>
                      </div>
                    )}

                    {/* Controls Targeted */}
                    {attack.controls_targeted && (
                      <div style={{ marginBottom: 12 }}>
                        <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 6 }}>Controls Targeted</div>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                          {attack.controls_targeted.map((ctrl: string, j: number) => (
                            <span key={j} style={{ padding: "3px 8px", borderRadius: 4, background: "rgba(255,59,92,.15)", color: "#dc2626", fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}>{ctrl}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Blue Team Recommendation */}
                    {attack.blue_team_recommendation && (
                      <div style={{ padding: "10px 12px", background: "rgba(34,229,160,.1)", border: `1px solid rgba(34,229,160,.3)`, borderRadius: 8 }}>
                        <div style={{ fontSize: 10, color: "#16a34a", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 4 }}>Blue Team Recommendation</div>
                        <div style={{ fontSize: 12, color: "#111827" }}>{attack.blue_team_recommendation}</div>
                      </div>
                    )}
                  </div>
                ))}

                {/* Raw Response */}
                {result.raw_response && (
                  <details style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18 }}>
                    <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 600, color: "#6b7280" }}>Raw LLM Response</summary>
                    <pre style={{ marginTop: 12, padding: 12, background: "#f9fafb", borderRadius: 8, fontSize: 11, fontFamily: "'JetBrains Mono', monospace", overflow: "auto", maxHeight: 400, color: "#6b7280" }}>
                      {result.raw_response}
                    </pre>
                  </details>
                )}
              </>
            )}

            {!result && !error && (
              <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 40, textAlign: "center" }}>
                <div style={{ fontSize: 48, marginBottom: 16 }}>🧠</div>
                <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>Ready to Discover Novel Attacks</div>
                <div style={{ fontSize: 13, color: "#6b7280", maxWidth: 400, margin: "0 auto" }}>
                  Select a focus area and model, then click Generate. The LLM will discover novel attack vectors that could bypass current fraud controls.
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
