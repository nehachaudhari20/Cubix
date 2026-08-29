"use client"
import { useEffect, useState } from "react"
import { redTeamCampaignV1 } from "@/lib/api-v1"



export default function CampaignLab() {
  const [families, setFamilies] = useState<any[]>([])
  const [campaign, setCampaign] = useState<any>(null)
  const [selectedFamily, setSelectedFamily] = useState("")
  const [strategy, setStrategy] = useState("sequential")
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    redTeamCampaignV1.families().then(r => { setFamilies(r.families); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  const createCampaign = async () => {
    if (!selectedFamily) return
    try {
      const c = await redTeamCampaignV1.createCampaign({ attack_family: selectedFamily, strategy, campaign_size: 12 })
      setCampaign(c)
    } catch (e) { console.error(e) }
  }

  const agents = campaign?.timeline || []

  return (
    <div style={{ background: "#f8f9fa", color: "#111827", minHeight: "100vh", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "22px 28px 60px" }}>
        <h2 style={{ margin: "0 0 4px", fontSize: 20 }}>Red Team Campaign Lab</h2>
        <p style={{ margin: "0 0 20px", color: "#6b7280", fontSize: 13 }}>Controlled adversarial validation — sandbox only. 6 agents working through a campaign.</p>

        {/* Setup */}
        <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18, marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Campaign Setup</div>
          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <select value={selectedFamily} onChange={e => setSelectedFamily(e.target.value)} style={{ padding: "10px 14px", borderRadius: 8, border: `1px solid ${"#e5e7eb"}`, background: "#f9fafb", color: "#111827", fontSize: 13, minWidth: 300 }}>
              <option value="">Select attack family…</option>
              {families.map(f => <option key={f.attack_id} value={f.attack_id}>{f.attack_id} — {f.name}</option>)}
            </select>
            <select value={strategy} onChange={e => setStrategy(e.target.value)} style={{ padding: "10px 14px", borderRadius: 8, border: `1px solid ${"#e5e7eb"}`, background: "#f9fafb", color: "#111827", fontSize: 13 }}>
              <option value="sequential">Sequential</option>
              <option value="tree">Tree</option>
              <option value="crescendo">Crescendo</option>
              <option value="kb">KB Direct</option>
            </select>
            <button onClick={createCampaign} style={{ padding: "10px 24px", borderRadius: 8, background: `linear-gradient(135deg, ${"#dc2626"}, ${"#ea580c"})`, color: "#fff", fontWeight: 600, fontSize: 13, border: "none", cursor: "pointer" }}>Launch Campaign</button>
          </div>
        </div>

        {/* Safety Gate */}
        {campaign?.safety_gate && (
          <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18, marginBottom: 16 }}>
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

        {/* Agent Timeline */}
        {agents.length > 0 && (
          <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>LangGraph Campaign Timeline</div>
            <div style={{ position: "relative", paddingLeft: 22 }}>
              <div style={{ position: "absolute", left: 6, top: 4, bottom: 4, width: 1.5, background: "#e5e7eb" }} />
              {agents.map((a: any, i: number) => (
                <div key={i} style={{ position: "relative", paddingBottom: 16 }}>
                  <div style={{ position: "absolute", left: -22, top: 2, width: 12, height: 12, borderRadius: "50%", border: `2px solid ${a.status === "completed" ? "#16a34a" : a.status === "running" ? "#ea580c" : "#6b7280"}`, background: "#ffffff" }} />
                  <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 2 }}>{i + 1}. {a.agent}</div>
                  <div style={{ fontSize: 11, color: "#6b7280" }}>{a.status === "completed" ? "✓ Completed" : a.status === "running" ? "● Running…" : "○ Waiting"}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Campaign output */}
        {campaign && (
          <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18 }}>
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
          </div>
        )}
      </div>
    </div>
  )
}
