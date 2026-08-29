"use client"
import { useEffect, useRef, useState } from "react"
import { errorText } from "@/lib/api"
import { redTeamCampaignV1 } from "@/lib/api-v1"

export default function CampaignLab() {
  const [families, setFamilies] = useState<any[]>([])
  const [hypotheses, setHypotheses] = useState<any[]>([])
  const [campaign, setCampaign] = useState<any>(null)
  const [selectedFamily, setSelectedFamily] = useState("")
  const [strategy, setStrategy] = useState("sequential")
  const [loading, setLoading] = useState(true)
  const [launching, setLaunching] = useState(false)
  const [err, setErr] = useState("")
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    Promise.all([
      redTeamCampaignV1.families().catch(() => ({ families: [] })),
      redTeamCampaignV1.hypotheses({ max_hypotheses: 5, prefer_composites: true }).catch(() => null),
    ]).then(([fam, hyp]) => {
      setFamilies(fam.families || [])
      if (hyp?.hypotheses) setHypotheses(hyp.hypotheses)
      setLoading(false)
    })
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

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
        /* ignore transient */
      }
    }, 2000)
  }

  const createCampaign = async () => {
    if (!selectedFamily) return
    setLaunching(true)
    setErr("")
    try {
      const c = await redTeamCampaignV1.createCampaign({
        attack_family: selectedFamily,
        strategy,
        campaign_size: 12,
        execute: true,
      })
      setCampaign(c)
      pollCampaign(c.campaign_id)
    } catch (e) {
      setErr(errorText(e))
      setLaunching(false)
    }
  }

  const useHypothesis = (h: any) => {
    setSelectedFamily(h.primary_family)
    if (h.jailbreak_strategy) setStrategy(h.jailbreak_strategy)
  }

  const agents = campaign?.timeline || []

  if (loading) return <div style={{ color: "#6b7280", padding: 40 }}>Loading Campaign Lab…</div>

  return (
    <div style={{ background: "#f8f9fa", color: "#111827", minHeight: "100vh", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "22px 28px 60px" }}>
        <h2 style={{ margin: "0 0 4px", fontSize: 20 }}>Red Team Campaign Lab</h2>
        <p style={{ margin: "0 0 20px", color: "#6b7280", fontSize: 13 }}>
          Controlled adversarial validation — Threat Hunter → Planner → Generator → Sandbox.
        </p>

        {err && (
          <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 12, color: "#dc2626" }}>
            {err}
          </div>
        )}

        {/* Hypotheses from Threat Hunter */}
        {hypotheses.length > 0 && (
          <div style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Threat Hunter hypotheses</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 10 }}>
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
                  <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 6 }}>novelty {(h.novelty_score ?? 0).toFixed(2)}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Setup */}
        <div style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Campaign Setup</div>
          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <select
              value={selectedFamily}
              onChange={(e) => setSelectedFamily(e.target.value)}
              style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid #e5e7eb", background: "#f9fafb", fontSize: 13, minWidth: 300 }}
            >
              <option value="">Select attack family…</option>
              {families.map((f) => (
                <option key={f.attack_id} value={f.attack_id}>
                  {f.attack_id} — {f.name}
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
            <button
              onClick={createCampaign}
              disabled={!selectedFamily || launching}
              style={{
                padding: "10px 24px",
                borderRadius: 8,
                background: "linear-gradient(135deg, #dc2626, #ea580c)",
                color: "#fff",
                fontWeight: 600,
                fontSize: 13,
                border: "none",
                cursor: !selectedFamily || launching ? "not-allowed" : "pointer",
                opacity: !selectedFamily || launching ? 0.6 : 1,
              }}
            >
              {launching ? "Running…" : "Launch Campaign"}
            </button>
            {campaign?.status && (
              <span style={{ fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: "#6b7280" }}>
                {campaign.campaign_id} · {campaign.status}
              </span>
            )}
          </div>
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

        {campaign && (
          <div style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Campaign Output</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
              {[
                { label: "Generated", value: campaign.events_generated || 0 },
                { label: "Blocked", value: campaign.events_blocked || 0 },
                { label: "Allowed", value: campaign.events_allowed || 0 },
                { label: "Memory Entries", value: campaign.memory_entries || 0 },
              ].map((k, i) => (
                <div key={i} style={{ textAlign: "center", padding: 12, background: "#f9fafb", borderRadius: 8 }}>
                  <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", marginBottom: 4 }}>{k.label}</div>
                  <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 18, fontWeight: 600 }}>{k.value}</div>
                </div>
              ))}
            </div>
            {campaign.hypothesis && (
              <div style={{ marginTop: 14, fontSize: 12, color: "#6b7280", lineHeight: 1.5 }}>
                <strong style={{ color: "#111827" }}>Hypothesis:</strong> {campaign.hypothesis.reasoning || campaign.hypothesis.name}
              </div>
            )}
            {campaign.summary?.final_decision && (
              <div style={{ marginTop: 8, fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}>
                final_decision={campaign.summary.final_decision} · gaps={campaign.summary.control_gaps ?? 0}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
