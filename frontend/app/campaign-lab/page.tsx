"use client"
import { useEffect, useMemo, useRef, useState } from "react"
import { errorText } from "@/lib/api"
import { redTeamCampaignV1 } from "@/lib/api-v1"

export default function CampaignLab({ embedded = false }: { embedded?: boolean }) {
  const [families, setFamilies] = useState<any[]>([])
  const [hypotheses, setHypotheses] = useState<any[]>([])
  const [campaign, setCampaign] = useState<any>(null)
  const [selectedFamily, setSelectedFamily] = useState("")
  const [familyFilter, setFamilyFilter] = useState("")
  const [strategy, setStrategy] = useState("sequential")
  const [campaignSize, setCampaignSize] = useState(20)
  const [loading, setLoading] = useState(true)
  const [launching, setLaunching] = useState(false)
  const [err, setErr] = useState("")
  const [detailTab, setDetailTab] = useState<"intel" | "plan" | "out" | "mem">("intel")
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    Promise.all([
      redTeamCampaignV1.families().catch(() => ({ families: [] })),
      redTeamCampaignV1.hypotheses({ max_hypotheses: 12, prefer_composites: true }).catch(() => null),
    ]).then(([fam, hyp]) => {
      setFamilies(fam.families || [])
      if (hyp?.hypotheses) setHypotheses(hyp.hypotheses)
      setLoading(false)
    })
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const filteredFamilies = useMemo(() => {
    const q = familyFilter.trim().toLowerCase()
    if (!q) return families
    return families.filter((f) =>
      `${f.attack_id} ${f.name} ${f.lifecycle_stage} ${f.surface}`.toLowerCase().includes(q)
    )
  }, [families, familyFilter])

  const selectedMeta = families.find((f) => f.attack_id === selectedFamily)
  const selectedHyp =
    hypotheses.find((h) => h.primary_family === selectedFamily) || campaign?.hypothesis

  const pollCampaign = (id: string) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const c = await redTeamCampaignV1.campaign(id)
        setCampaign(c)
        if (["completed", "failed", "stopped"].includes(c.status)) {
          if (pollRef.current) clearInterval(pollRef.current)
          setLaunching(false)
        }
      } catch {
        /* ignore */
      }
    }, 1500)
  }

  const createCampaign = async () => {
    if (!selectedFamily) return
    setLaunching(true)
    setErr("")
    setDetailTab("out")
    try {
      const c = await redTeamCampaignV1.createCampaign({
        attack_family: selectedFamily,
        strategy,
        campaign_size: campaignSize,
        execute: true,
      })
      setCampaign(c)
      pollCampaign(c.campaign_id)
    } catch (e) {
      setErr(errorText(e))
      setLaunching(false)
    }
  }

  const stopCampaign = async () => {
    if (!campaign?.campaign_id) return
    try {
      await redTeamCampaignV1.stopCampaign(campaign.campaign_id)
      const c = await redTeamCampaignV1.campaign(campaign.campaign_id)
      setCampaign(c)
      setLaunching(false)
    } catch (e) {
      setErr(errorText(e))
    }
  }

  const useHypothesis = (h: any) => {
    setSelectedFamily(h.primary_family)
    if (h.jailbreak_strategy) setStrategy(h.jailbreak_strategy)
    setDetailTab("intel")
  }

  const agents = campaign?.timeline || []
  const summary = campaign?.summary || {}
  const hyp = campaign?.hypothesis || selectedHyp

  if (loading) return <div style={{ color: "#6b7280", padding: embedded ? "22px 28px" : 40 }}>Loading Campaign Lab…</div>

  return (
    <div style={{ background: embedded ? "transparent" : "#f8f9fa", color: "#111827", minHeight: embedded ? undefined : "100vh", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div style={{ maxWidth: embedded ? undefined : 1400, margin: embedded ? undefined : "0 auto", padding: embedded ? "18px 28px 8px" : "22px 28px 60px" }}>
        {!embedded && (
          <>
            <h2 style={{ margin: "0 0 4px", fontSize: 20 }}>Launch Campaign</h2>
            <p style={{ margin: "0 0 20px", color: "#6b7280", fontSize: 13 }}>
              Controlled adversarial validation — Threat Hunter → Planner → Generator → Sandbox. Uses full KB families.
            </p>
          </>
        )}
        {embedded && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".5px", color: "#6b7280", fontWeight: 500 }}>Launch</div>
            <h2 style={{ margin: "4px 0 0", fontSize: 16, fontWeight: 700 }}>Run a campaign</h2>
          </div>
        )}

        {err && (
          <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 12, color: "#dc2626" }}>
            {err}
          </div>
        )}

        {hypotheses.length > 0 && (
          <div style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Threat Hunter — live hypotheses</div>
            <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 14 }}>{hypotheses.length} ranked composites / families from KB</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
              {hypotheses.map((h, i) => (
                <button
                  key={i}
                  onClick={() => useHypothesis(h)}
                  style={{
                    textAlign: "left",
                    padding: 12,
                    borderRadius: 10,
                    border: selectedFamily === h.primary_family ? "1px solid #dc2626" : "1px solid #e5e7eb",
                    background: selectedFamily === h.primary_family ? "#fef2f2" : "#f9fafb",
                    cursor: "pointer",
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>{h.name}</div>
                  <div style={{ fontSize: 11, color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>
                    {h.primary_family}
                    {h.composite_families?.length ? ` + ${h.composite_families.join(", ")}` : ""}
                  </div>
                  <div style={{ fontSize: 11, color: "#4b5563", marginTop: 8, lineHeight: 1.45 }}>
                    {(h.reasoning || h.attack_flow_summary || "").slice(0, 160)}
                    {(h.reasoning || h.attack_flow_summary || "").length > 160 ? "…" : ""}
                  </div>
                  <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 8, display: "flex", gap: 10 }}>
                    <span>novelty {(h.novelty_score ?? 0).toFixed(2)}</span>
                    <span>p(success) {(h.success_probability ?? 0).toFixed(2)}</span>
                    {h.jailbreak_strategy && <span>{h.jailbreak_strategy}</span>}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        <div style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>
            Campaign Setup <span style={{ fontWeight: 400, color: "#6b7280" }}>({families.length} KB families)</span>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 12 }}>
            <input
              value={familyFilter}
              onChange={(e) => setFamilyFilter(e.target.value)}
              placeholder="Filter families…"
              style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid #e5e7eb", background: "#fff", fontSize: 13, minWidth: 200 }}
            />
            <select
              value={selectedFamily}
              onChange={(e) => setSelectedFamily(e.target.value)}
              style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid #e5e7eb", background: "#f9fafb", fontSize: 13, minWidth: 320, flex: 1 }}
            >
              <option value="">Select attack family…</option>
              {filteredFamilies.map((f) => (
                <option key={f.attack_id} value={f.attack_id}>
                  {f.attack_id} — {f.name}
                  {f.lifecycle_stage ? ` · ${f.lifecycle_stage}` : ""}
                  {Array.isArray(f.variants) ? ` · ${f.variants.length} var` : ""}
                </option>
              ))}
            </select>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid #e5e7eb", background: "#f9fafb", fontSize: 13 }}
            >
              <option value="sequential">Sequential</option>
              <option value="tree">Tree</option>
              <option value="crescendo">Crescendo</option>
              <option value="kb">KB Direct</option>
            </select>
            <select
              value={campaignSize}
              onChange={(e) => setCampaignSize(Number(e.target.value))}
              style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid #e5e7eb", background: "#f9fafb", fontSize: 13 }}
            >
              {[8, 12, 16, 20, 24].map((n) => (
                <option key={n} value={n}>{n} steps</option>
              ))}
            </select>
            {!launching ? (
              <button
                onClick={createCampaign}
                disabled={!selectedFamily}
                style={{
                  padding: "10px 24px",
                  borderRadius: 8,
                  background: "linear-gradient(135deg, #dc2626, #ea580c)",
                  color: "#fff",
                  fontWeight: 600,
                  fontSize: 13,
                  border: "none",
                  cursor: !selectedFamily ? "not-allowed" : "pointer",
                  opacity: !selectedFamily ? 0.6 : 1,
                }}
              >
                ▶ Launch Campaign
              </button>
            ) : (
              <button
                onClick={stopCampaign}
                style={{
                  padding: "10px 24px",
                  borderRadius: 8,
                  background: "#fef2f2",
                  color: "#dc2626",
                  fontWeight: 600,
                  fontSize: 13,
                  border: "1px solid #fecaca",
                  cursor: "pointer",
                }}
              >
                ■ Stop
              </button>
            )}
            {campaign?.status && (
              <span style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: "#6b7280" }}>
                {campaign.campaign_id} · {campaign.status}
              </span>
            )}
          </div>

          {selectedMeta && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10, padding: 12, background: "#f9fafb", borderRadius: 8, border: "1px solid #e5e7eb" }}>
              <div><div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase" }}>Stage</div><div style={{ fontSize: 12, fontWeight: 600 }}>{selectedMeta.lifecycle_stage || "—"}</div></div>
              <div><div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase" }}>Surface</div><div style={{ fontSize: 12, fontWeight: 600 }}>{selectedMeta.surface || "—"}</div></div>
              <div><div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase" }}>Variants</div><div style={{ fontSize: 12, fontWeight: 600 }}>{selectedMeta.variants?.length || 0}</div></div>
              <div><div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase" }}>Controls</div><div style={{ fontSize: 12, fontWeight: 600 }}>{selectedMeta.controls_targeted?.length || 0}</div></div>
              <div><div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase" }}>GenAI</div><div style={{ fontSize: 12, fontWeight: 600 }}>{selectedMeta.is_genai ? "yes" : "no"}</div></div>
            </div>
          )}
        </div>

        {campaign?.safety_gate && (
          <div style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14, display: "flex", alignItems: "center", gap: 8 }}>
              Safety Gate <span style={{ color: "#16a34a", fontSize: 12 }}>✓ PASSED</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
              {campaign.safety_gate.map((check: any, i: number) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#16a34a" }}>
                  <span>✓</span> {check.check}
                </div>
              ))}
            </div>
          </div>
        )}

        {agents.length > 0 && (
          <div style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Campaign Timeline</div>
            <div style={{ position: "relative", paddingLeft: 22 }}>
              <div style={{ position: "absolute", left: 6, top: 4, bottom: 4, width: 1.5, background: "#e5e7eb" }} />
              {agents.map((a: any, i: number) => (
                <div key={i} style={{ position: "relative", paddingBottom: 16 }}>
                  <div
                    style={{
                      position: "absolute",
                      left: -22,
                      top: 2,
                      width: 12,
                      height: 12,
                      borderRadius: "50%",
                      border: `2px solid ${a.status === "completed" ? "#16a34a" : a.status === "running" ? "#ea580c" : a.status === "failed" ? "#dc2626" : "#6b7280"}`,
                      background: "#ffffff",
                    }}
                  />
                  <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 2 }}>
                    {i + 1}. {a.agent}
                  </div>
                  <div style={{ fontSize: 11, color: "#6b7280" }}>
                    {a.status === "completed"
                      ? `✓ Completed${a.detail ? ` — ${a.detail}` : ""}`
                      : a.status === "running"
                        ? "● Running…"
                        : a.status === "failed"
                          ? `✗ Failed${a.detail ? ` — ${a.detail}` : ""}`
                          : "○ Waiting"}
                  </div>
                </div>
              ))}
            </div>
            {campaign?.error && (
              <div style={{ marginTop: 8, fontSize: 12, color: "#dc2626" }}>{campaign.error}</div>
            )}
          </div>
        )}

        {(hyp || campaign) && (
          <div style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
            <div style={{ display: "flex", gap: 4, marginBottom: 16, borderBottom: "1px solid #e5e7eb" }}>
              {([
                ["intel", "Threat Intelligence"],
                ["plan", "Planner / Flow"],
                ["out", "Outcomes"],
                ["mem", "Memory / Strategy"],
              ] as const).map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => setDetailTab(id)}
                  style={{
                    padding: "8px 14px",
                    border: "none",
                    borderBottom: detailTab === id ? "2px solid #dc2626" : "2px solid transparent",
                    background: "transparent",
                    color: detailTab === id ? "#dc2626" : "#6b7280",
                    fontWeight: detailTab === id ? 600 : 400,
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  {label}
                </button>
              ))}
            </div>

            {detailTab === "intel" && hyp && (
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>{hyp.name}</div>
                <div style={{ fontSize: 12, color: "#4b5563", lineHeight: 1.55, marginBottom: 12 }}>
                  {hyp.reasoning || hyp.attack_flow_summary || "—"}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 12 }}>
                  <div style={{ padding: 10, background: "#f9fafb", borderRadius: 8 }}>
                    <div style={{ fontSize: 10, color: "#6b7280" }}>PRIMARY</div>
                    <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>{hyp.primary_family}</div>
                  </div>
                  <div style={{ padding: 10, background: "#f9fafb", borderRadius: 8 }}>
                    <div style={{ fontSize: 10, color: "#6b7280" }}>NOVELTY</div>
                    <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>{(hyp.novelty_score ?? 0).toFixed(2)}</div>
                  </div>
                  <div style={{ padding: 10, background: "#f9fafb", borderRadius: 8 }}>
                    <div style={{ fontSize: 10, color: "#6b7280" }}>STRATEGY</div>
                    <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>{hyp.jailbreak_strategy || strategy}</div>
                  </div>
                  <div style={{ padding: 10, background: "#f9fafb", borderRadius: 8 }}>
                    <div style={{ fontSize: 10, color: "#6b7280" }}>VARIANT</div>
                    <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>{hyp.suggested_variant || "—"}</div>
                  </div>
                </div>
                {hyp.composite_families?.length > 0 && (
                  <div style={{ fontSize: 12, marginBottom: 8 }}>
                    <strong>Composites:</strong> {hyp.composite_families.join(", ")}
                  </div>
                )}
                {hyp.prerequisites?.length > 0 && (
                  <div style={{ fontSize: 12 }}>
                    <strong>Prerequisites:</strong>
                    <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                      {hyp.prerequisites.map((p: string, i: number) => (
                        <li key={i}>{p}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {hyp.attack_flow_summary && (
                  <div style={{ marginTop: 12, fontSize: 12, padding: 12, background: "#f9fafb", borderRadius: 8, lineHeight: 1.5 }}>
                    <strong>Flow:</strong> {hyp.attack_flow_summary}
                  </div>
                )}
              </div>
            )}

            {detailTab === "plan" && (
              <div>
                {hyp?.attack_flow_summary ? (
                  <div style={{ fontSize: 12, lineHeight: 1.55, marginBottom: 12 }}>{hyp.attack_flow_summary}</div>
                ) : (
                  <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 12 }}>
                    Planner output appears after launch (jailbreak strategy: {strategy}).
                  </div>
                )}
                {summary?.action_type_counts && (
                  <pre style={{ background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 8, padding: 12, fontSize: 11, overflow: "auto" }}>
                    {JSON.stringify(
                      {
                        strategy: hyp?.jailbreak_strategy || strategy,
                        steps_executed: summary.steps_executed,
                        payloads_generated: summary.payloads_generated,
                        linear_retries_used: summary.linear_retries_used,
                        action_type_counts: summary.action_type_counts,
                        covered_families: summary.covered_families,
                      },
                      null,
                      2
                    )}
                  </pre>
                )}
                {!summary?.action_type_counts && selectedMeta?.variants && (
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>KB variants for planner</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {selectedMeta.variants.map((v: string) => (
                        <span key={v} style={{ fontSize: 11, padding: "4px 8px", background: "#f3f4f6", borderRadius: 6 }}>{v}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {detailTab === "out" && campaign && (
              <div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 14 }}>
                  {[
                    { label: "Generated", value: campaign.events_generated || 0 },
                    { label: "Blocked", value: campaign.events_blocked || 0 },
                    { label: "Allowed", value: campaign.events_allowed || 0 },
                    { label: "Memory", value: campaign.memory_entries || 0 },
                  ].map((k, i) => (
                    <div key={i} style={{ textAlign: "center", padding: 12, background: "#f9fafb", borderRadius: 8 }}>
                      <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", marginBottom: 4 }}>{k.label}</div>
                      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 18, fontWeight: 600 }}>{k.value}</div>
                    </div>
                  ))}
                </div>
                {summary?.final_decision && (
                  <div style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", marginBottom: 10 }}>
                    final_decision={summary.final_decision} · gaps={summary.control_gaps ?? 0} · variations={summary.variations ?? 0}
                  </div>
                )}
                {summary && Object.keys(summary).length > 0 && (
                  <pre style={{ background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 8, padding: 12, fontSize: 11, overflow: "auto", maxHeight: 360 }}>
                    {JSON.stringify(summary, null, 2)}
                  </pre>
                )}
                {!summary?.final_decision && launching && (
                  <div style={{ fontSize: 12, color: "#6b7280" }}>Campaign running — outcomes will stream here…</div>
                )}
              </div>
            )}

            {detailTab === "mem" && (
              <div>
                {campaign?.strategy_state ? (
                  <pre style={{ background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 8, padding: 12, fontSize: 11, overflow: "auto", marginBottom: 12 }}>
                    {JSON.stringify(campaign.strategy_state, null, 2)}
                  </pre>
                ) : (
                  <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 12 }}>Strategy / memory fills after Memory Agent completes.</div>
                )}
                {campaign?.findings && (
                  <pre style={{ background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 8, padding: 12, fontSize: 11, overflow: "auto" }}>
                    {JSON.stringify(campaign.findings, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
