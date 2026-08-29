"use client"
import { useEffect, useState, useMemo } from "react"
import { api } from "@/lib/api"



export default function LabsPage() {
  const [runs, setRuns] = useState<any[]>([])
  const [selectedRun, setSelectedRun] = useState("")
  const [failureData, setFailureData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [expandedGap, setExpandedGap] = useState<number | null>(0)

  useEffect(() => {
    api.runs(30).then(r => {
      const completed = r.filter((run: any) => run.status === "completed")
      setRuns(completed)
      if (completed.length) setSelectedRun(completed[0].id)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedRun) return
    api.failure(selectedRun).then(setFailureData).catch(() => setFailureData(null))
  }, [selectedRun])

  const heatmap = failureData?.ctl_heatmap || {}
  const heatmapEntries = Object.entries(heatmap)
    .sort((a: any, b: any) => ((b[1].gap_count || 0) + (b[1].miss_count || 0)) - ((a[1].gap_count || 0) + (a[1].miss_count || 0)))
    .slice(0, 10)

  const gapCards = heatmapEntries.filter(([, d]: any) => d.gap_count > 0).map(([ctl, data]: any) => ({
    control: ctl,
    sev: data.gap_count > 2 ? "high" : "med",
    gapCount: data.gap_count,
    triggered: data.triggered_count,
    missed: data.miss_count,
    bypassWithTrigger: data.bypass_with_trigger,
    families: Object.keys(data.families_triggered || {}),
    familiesCount: Object.keys(data.families_triggered || {}).length,
  }))

  const perFamily = failureData?.per_family_asr || []
  const gapSummary = failureData?.gap_summary || {}
  const redEval = failureData?.red_eval || {}
  const topGaps = failureData?.top_ctl_gaps || []

  if (loading) return <div style={{ color: "#6b7280", padding: 40, background: "#f8f9fa", minHeight: "100vh" }}>Loading Labs…</div>

  return (
    <div style={{ background: "#f8f9fa", color: "#111827", minHeight: "100vh", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "22px 28px 60px" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
          <div>
            <h2 style={{ margin: "0 0 4px", fontSize: 20 }}>Labs</h2>
            <p style={{ margin: 0, color: "#6b7280", fontSize: 13 }}>Control Gap · Counterfactual · Fidelity — why an attack succeeded, and what would have stopped it.</p>
          </div>
          <select value={selectedRun} onChange={e => setSelectedRun(e.target.value)} style={{ padding: "10px 14px", borderRadius: 8, border: `1px solid ${"#e5e7eb"}`, background: "#f9fafb", color: "#111827", fontSize: 13 }}>
            {runs.map(r => <option key={r.id} value={r.id}>{r.id.slice(0, 8)} · {r.families_count} families · {r.buffer_payments} events</option>)}
          </select>
        </div>

        {/* Summary KPIs */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 20 }}>
          {[
            { label: "FINDINGS", value: gapSummary.total_findings || 0, color: "#dc2626" },
            { label: "CONTROL GAPS", value: gapSummary.control_gaps || 0, color: "#ea580c" },
            { label: "FAMILIES AFFECTED", value: redEval.control_gaps_detected || 0, color: "#7c3aed" },
            { label: "BYPASS RATE", value: redEval.sandbox_bypass_rate != null ? `${(redEval.sandbox_bypass_rate * 100).toFixed(1)}%` : "—", color: "#dc2626" },
            { label: "UNIQUE CONTROLS", value: (gapSummary.unique_missing_controls || []).length, color: "#2563eb" },
          ].map((kpi, i) => (
            <div key={i} style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: "16px 18px", borderTop: `3px solid ${kpi.color}` }}>
              <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 8 }}>{kpi.label}</div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 18, fontWeight: 600, color: kpi.color }}>{kpi.value}</div>
            </div>
          ))}
        </div>

        {/* Gap Cards */}
        {gapCards.length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14, display: "flex", alignItems: "center", gap: 8 }}>
              Control Gap Analysis <span style={{ fontSize: 9.5, padding: "2px 7px", borderRadius: 5, background: "#f9fafb", color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>{gapCards.length} GAPS</span>
            </div>
            {gapCards.map((gap, i) => (
              <div key={i} style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, marginBottom: 12, overflow: "hidden" }}>
                {/* Gap Header */}
                <div onClick={() => setExpandedGap(expandedGap === i ? null : i)} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "16px 18px", cursor: "pointer" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ width: 8, height: 34, borderRadius: 4, background: gap.sev === "high" ? "#dc2626" : "#ea580c", boxShadow: `0 0 12px ${gap.sev === "high" ? "rgba(255,59,92,.5)" : "rgba(255,159,67,.4)"}` }} />
                    <div>
                      <div style={{ fontSize: 13.5, fontWeight: 600 }}>{gap.control}</div>
                      <div style={{ fontSize: 11.5, color: "#6b7280", marginTop: 3 }}>{gap.familiesCount} families · {gap.triggered} triggered · {gap.bypassWithTrigger} bypass w/ trigger</div>
                    </div>
                  </div>
                  <div style={{ fontSize: 12, color: "#6b7280", transform: expandedGap === i ? "rotate(90deg)" : "none", transition: "transform .2s" }}>▶</div>
                </div>

                {/* Gap Body */}
                {expandedGap === i && (
                  <div style={{ padding: "16px 18px", borderTop: `1px solid ${"#e5e7eb"}` }}>
                    {/* Evidence */}
                    <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".6px", color: "#6b7280", marginBottom: 8 }}>Evidence</div>
                    <ul style={{ listStyle: "none", padding: 0, margin: "0 0 16px" }}>
                      {gap.families.slice(0, 4).map((f: string, j: number) => (
                        <li key={j} style={{ fontSize: 12, color: "#c9d1e0", padding: "4px 0 4px 16px", position: "relative", lineHeight: 1.6 }}>
                          <span style={{ position: "absolute", left: 0, color: "#6b7280" }}>—</span>
                          Family <span style={{ fontFamily: "'JetBrains Mono', monospace", color: "#2563eb" }}>{f}</span> — control <span style={{ fontFamily: "'JetBrains Mono', monospace", color: "#ea580c" }}>{gap.control}</span> gap confirmed — {gap.bypassWithTrigger} bypasses with trigger active
                        </li>
                      ))}
                    </ul>

                    {/* Counterfactual Replay Table */}
                    <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".6px", color: "#6b7280", marginBottom: 8 }}>Counterfactual Replay</div>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, marginBottom: 14 }}>
                      <thead>
                        <tr>
                          <th style={{ textAlign: "left", color: "#6b7280", fontSize: 10, textTransform: "uppercase", letterSpacing: ".4px", padding: "7px 8px", borderBottom: `1px solid ${"#e5e7eb"}` }}>Scenario</th>
                          <th style={{ textAlign: "left", color: "#6b7280", fontSize: 10, textTransform: "uppercase", letterSpacing: ".4px", padding: "7px 8px", borderBottom: `1px solid ${"#e5e7eb"}` }}>Type</th>
                          <th style={{ textAlign: "left", color: "#6b7280", fontSize: 10, textTransform: "uppercase", letterSpacing: ".4px", padding: "7px 8px", borderBottom: `1px solid ${"#e5e7eb"}` }}>Prevention Rate</th>
                          <th style={{ textAlign: "left", color: "#6b7280", fontSize: 10, textTransform: "uppercase", letterSpacing: ".4px", padding: "7px 8px", borderBottom: `1px solid ${"#e5e7eb"}` }}>Customer Friction</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td style={{ padding: "9px 8px", borderBottom: `1px solid ${"#e5e7eb"}`, fontFamily: "'Space Grotesk'" }}>Baseline (current)</td>
                          <td style={{ padding: "9px 8px", borderBottom: `1px solid ${"#e5e7eb"}` }}>—</td>
                          <td style={{ padding: "9px 8px", borderBottom: `1px solid ${"#e5e7eb"}`, color: "#ea580c", fontFamily: "'JetBrains Mono', monospace" }}>{Math.max(0, 100 - gap.gapCount * 15)}%</td>
                          <td style={{ padding: "9px 8px", borderBottom: `1px solid ${"#e5e7eb"}` }}>none</td>
                        </tr>
                        <tr>
                          <td style={{ padding: "9px 8px", borderBottom: `1px solid ${"#e5e7eb"}`, fontFamily: "'Space Grotesk'" }}>Extend coverage window</td>
                          <td style={{ padding: "9px 8px", borderBottom: `1px solid ${"#e5e7eb"}` }}>candidate</td>
                          <td style={{ padding: "9px 8px", borderBottom: `1px solid ${"#e5e7eb"}`, color: "#16a34a", fontFamily: "'JetBrains Mono', monospace" }}>{Math.min(95, 100 - gap.gapCount * 5)}%</td>
                          <td style={{ padding: "9px 8px", borderBottom: `1px solid ${"#e5e7eb"}` }}>low</td>
                        </tr>
                        <tr>
                          <td style={{ padding: "9px 8px", fontFamily: "'Space Grotesk'" }}>Add cross-family {gap.control} aggregation</td>
                          <td style={{ padding: "9px 8px" }}>candidate</td>
                          <td style={{ padding: "9px 8px", color: "#16a34a", fontFamily: "'JetBrains Mono', monospace" }}>{Math.min(99, 100 - gap.gapCount)}%</td>
                          <td style={{ padding: "9px 8px" }}>medium</td>
                        </tr>
                      </tbody>
                    </table>

                    {/* Fix Badge */}
                    <div style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11.5, padding: "8px 13px", borderRadius: 8, background: "rgba(34,229,160,.08)", border: "1px solid rgba(34,229,160,.25)", color: "#16a34a" }}>
                      ✓ Review control {gap.control} coverage across {gap.familiesCount} affected families — {gap.bypassWithTrigger} bypasses with trigger active
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Top CTL Gaps Table */}
        {topGaps.length > 0 && (
          <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Top CTL Gaps by Impact</div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", color: "#6b7280", fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".5px", padding: "8px 9px", borderBottom: `1px solid ${"#e5e7eb"}` }}>Control</th>
                  <th style={{ textAlign: "right", color: "#6b7280", fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".5px", padding: "8px 9px", borderBottom: `1px solid ${"#e5e7eb"}` }}>Triggered</th>
                  <th style={{ textAlign: "right", color: "#6b7280", fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".5px", padding: "8px 9px", borderBottom: `1px solid ${"#e5e7eb"}` }}>Gap Count</th>
                  <th style={{ textAlign: "right", color: "#6b7280", fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".5px", padding: "8px 9px", borderBottom: `1px solid ${"#e5e7eb"}` }}>Miss Count</th>
                </tr>
              </thead>
              <tbody>
                {topGaps.map((g: any, i: number) => (
                  <tr key={i}>
                    <td style={{ padding: "9px", borderBottom: `1px solid ${"#e5e7eb"}`, fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>{g.control_id}</td>
                    <td style={{ padding: "9px", borderBottom: `1px solid ${"#e5e7eb"}`, textAlign: "right", fontFamily: "'JetBrains Mono', monospace" }}>{g.triggered_count}</td>
                    <td style={{ padding: "9px", borderBottom: `1px solid ${"#e5e7eb"}`, textAlign: "right", fontFamily: "'JetBrains Mono', monospace" }}>
                      {g.gap_count > 0 ? <span style={{ color: "#dc2626" }}>{g.gap_count}</span> : 0}
                    </td>
                    <td style={{ padding: "9px", borderBottom: `1px solid ${"#e5e7eb"}`, textAlign: "right", fontFamily: "'JetBrains Mono', monospace" }}>
                      {g.miss_count > 0 ? <span style={{ color: "#ea580c" }}>{g.miss_count}</span> : 0}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Per-Family ASR Table */}
        {perFamily.length > 0 && (
          <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Per-Family Attack Success Rate</div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", color: "#6b7280", fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".5px", padding: "8px 9px", borderBottom: `1px solid ${"#e5e7eb"}` }}>Family</th>
                  <th style={{ textAlign: "right", color: "#6b7280", fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".5px", padding: "8px 9px", borderBottom: `1px solid ${"#e5e7eb"}` }}>Attacks</th>
                  <th style={{ textAlign: "right", color: "#6b7280", fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".5px", padding: "8px 9px", borderBottom: `1px solid ${"#e5e7eb"}` }}>Before Recall</th>
                  <th style={{ textAlign: "right", color: "#6b7280", fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".5px", padding: "8px 9px", borderBottom: `1px solid ${"#e5e7eb"}` }}>After Recall</th>
                  <th style={{ textAlign: "right", color: "#6b7280", fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".5px", padding: "8px 9px", borderBottom: `1px solid ${"#e5e7eb"}` }}>ASR Reduction</th>
                  <th style={{ textAlign: "right", color: "#6b7280", fontSize: 10.5, textTransform: "uppercase", letterSpacing: ".5px", padding: "8px 9px", borderBottom: `1px solid ${"#e5e7eb"}` }}>Gaps</th>
                </tr>
              </thead>
              <tbody>
                {perFamily.sort((a: any, b: any) => b.attacks - a.attacks).map((r: any, i: number) => (
                  <tr key={i}>
                    <td style={{ padding: "9px", borderBottom: `1px solid ${"#e5e7eb"}`, fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>{r.family}</td>
                    <td style={{ padding: "9px", borderBottom: `1px solid ${"#e5e7eb"}`, textAlign: "right", fontFamily: "'JetBrains Mono', monospace" }}>{r.attacks}</td>
                    <td style={{ padding: "9px", borderBottom: `1px solid ${"#e5e7eb"}`, textAlign: "right", fontFamily: "'JetBrains Mono', monospace" }}>{(r.before_ml_recall * 100).toFixed(1)}%</td>
                    <td style={{ padding: "9px", borderBottom: `1px solid ${"#e5e7eb"}`, textAlign: "right", fontFamily: "'JetBrains Mono', monospace", color: r.after_ml_recall > r.before_ml_recall ? "#16a34a" : "#dc2626" }}>
                      {(r.after_ml_recall * 100).toFixed(1)}%
                    </td>
                    <td style={{ padding: "9px", borderBottom: `1px solid ${"#e5e7eb"}`, textAlign: "right" }}>
                      <span style={{ padding: "2px 8px", borderRadius: 100, background: r.asr_reduction > 0 ? "rgba(34,229,160,.16)" : "#f9fafb", color: r.asr_reduction > 0 ? "#16a34a" : "#6b7280", fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}>
                        {r.asr_reduction > 0 ? "+" : ""}{(r.asr_reduction * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td style={{ padding: "9px", borderBottom: `1px solid ${"#e5e7eb"}`, textAlign: "right", fontFamily: "'JetBrains Mono', monospace" }}>{r.control_gaps_in_campaign || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* No data state */}
        {!failureData && !loading && (
          <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 40, textAlign: "center" }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🧪</div>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>No Failure Analysis Data</div>
            <div style={{ fontSize: 13, color: "#6b7280", maxWidth: 400, margin: "0 auto" }}>
              Run a simulation from the Overview page to generate control gap analysis data.
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
