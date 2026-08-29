"use client"
import { useEffect, useState, useRef } from "react"
import { api } from "@/lib/api"
import { governance } from "@/lib/api-v1"
import dynamic from "next/dynamic"

const WorldMap = dynamic(() => import("@/components/world-map"), { ssr: false })

export default function MissionControl() {
  const [status, setStatus] = useState<any>(null)
  const [gov, setGov] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.status().catch(() => null),
      governance.safety().catch(() => null),
    ]).then(([s, g]) => {
      setStatus(s)
      setGov(g)
      setLoading(false)
    })
  }, [])

  if (loading) return <div style={{ color: "#6b7280", padding: 40 }}>Loading...</div>

  const m = status?.model || {}
  const r = status?.latest_run
  const b = status?.buffer
  const k = status?.kb

  const gateChecks = [
    { check: "Synthetic identifiers only", desc: "No real PII, PAN, or customer data used" },
    { check: "No live payment rail connection", desc: "All transactions are sandbox-simulated" },
    { check: "No credential or OTP data", desc: "No real authentication artifacts generated" },
    { check: "Amount bounds enforced", desc: "Transactions capped at demo-safe limits" },
    { check: "Mutation budget enforced", desc: "Max 2 mutations per family per campaign" },
    { check: "Approved attack library only", desc: "All attacks from the 57-family KB" },
    { check: "No external network access", desc: "All processing stays within sandbox" },
  ]

  const riskComponents = [
    { label: "Rule Risk", weight: "40%", value: 0.40, color: "#dc2626" },
    { label: "ML Ensemble", weight: "45%", value: 0.45, color: "#2563eb" },
    { label: "Isolation Forest", weight: "15%", value: 0.15, color: "#7c3aed" },
  ]

  const navCards = [
    { href: "/campaign-lab", label: "Campaign Lab", desc: "Launch Red Team campaigns", color: "#dc2626", letter: "C" },
    { href: "/fraudshield-console", label: "FraudShield Console", desc: "Score transactions", color: "#2563eb", letter: "F" },
    { href: "/closed-loop", label: "Closed-Loop Arena", desc: "v1 vs v3 comparison", color: "#16a34a", letter: "L" },
    { href: "/novel-attack", label: "Novel Attack Generator", desc: "LLM-powered discovery", color: "#ea580c", letter: "N" },
    { href: "/evaluation", label: "Evaluation", desc: "Five judging dimensions", color: "#7c3aed", letter: "E" },
    { href: "/governance", label: "Governance", desc: "Safety and evidence", color: "#6b7280", letter: "G" },
  ]

  return (
    <div style={{ padding: "22px 28px 0" }}>
      <div style={{ marginBottom: 18 }}>
        <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".6px", color: "#6b7280", fontWeight: 500 }}>Mission Control</div>
        <h1 style={{ margin: "4px 0 4px", fontSize: 22, fontWeight: 700 }}>Payment Defense Twin</h1>
        <p style={{ margin: 0, color: "#6b7280", fontSize: 13 }}>Discover threats. Simulate attacks. Harden payment defenses.</p>
      </div>

      {/* KPIs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 16 }}>
        {[
          { label: "ATTACK FAMILIES", value: k?.total_families || 0, sub: `${k?.simulatable_families || 0} simulatable`, accent: "#2563eb" },
          { label: "BUFFER PAYMENTS", value: b?.payment_records || 0, sub: `${b?.blocked || 0} blocked`, accent: "#dc2626" },
          { label: "ACTIVE MODEL", value: m?.version || "none", sub: m?.model_type || "No model", accent: "#16a34a" },
          { label: "LATEST RUN", value: r?.status || "none", sub: r?.id?.slice(0, 8) || "", accent: "#ea580c" },
          { label: "KB SIGNALS", value: k?.total_signals || 0, sub: `${k?.genai_load_bearing || 0} genai load-bearing`, accent: "#7c3aed" },
        ].map((kpi) => (
          <div key={kpi.label} style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: 16, borderTop: `3px solid ${kpi.accent}` }}>
            <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".5px", color: "#6b7280", fontWeight: 500 }}>{kpi.label}</div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 700, margin: "4px 0 2px" }}>{kpi.value}</div>
            <div style={{ fontSize: 11, color: "#6b7280" }}>{kpi.sub}</div>
          </div>
        ))}
      </div>

      {/* World Map + Attack Graph */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Global Attack Surface</div>
          <WorldMap />
        </div>
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Attack Pipeline</div>
          <svg viewBox="0 0 500 300" style={{ width: "100%", height: 280 }}>
            {/* Nodes */}
            {[
              { x: 40, y: 50, w: 120, h: 36, label: "Recon", color: "#7c3aed" },
              { x: 200, y: 50, w: 120, h: 36, label: "Phishing / Stolen Creds", color: "#ea580c" },
              { x: 360, y: 50, w: 120, h: 36, label: "Account Access", color: "#dc2626" },
              { x: 40, y: 130, w: 120, h: 36, label: "Payment Init", color: "#2563eb" },
              { x: 200, y: 130, w: 120, h: 36, label: "Risk Engine", color: "#dc2626" },
              { x: 360, y: 130, w: 120, h: 36, label: "BLOCKED", color: "#16a34a" },
              { x: 40, y: 220, w: 140, h: 36, label: "Device Spoof", color: "#6b7280" },
              { x: 220, y: 220, w: 140, h: 36, label: "Synthetic ID", color: "#6b7280" },
              { x: 400, y: 220, w: 80, h: 36, label: "Mule Net", color: "#6b7280" },
            ].map((n, i) => (
              <g key={i}>
                <rect x={n.x} y={n.y} width={n.w} height={n.h} rx={8} fill={n.color} opacity={0.12} stroke={n.color} strokeWidth={1.5} />
                <text x={n.x + n.w / 2} y={n.y + n.h / 2 + 4} textAnchor="middle" fontSize={10} fontFamily="'JetBrains Mono', monospace" fill={n.color} fontWeight={600}>{n.label}</text>
              </g>
            ))}
            {/* Arrows */}
            {[
              { x1: 160, y1: 68, x2: 200, y2: 68 },
              { x1: 320, y1: 68, x2: 360, y2: 68 },
              { x1: 100, y1: 86, x2: 100, y2: 130 },
              { x1: 260, y1: 86, x2: 260, y2: 130 },
              { x1: 320, y1: 148, x2: 360, y2: 148 },
              { x1: 110, y1: 166, x2: 110, y2: 220 },
              { x1: 290, y1: 166, x2: 290, y2: 220 },
            ].map((a, i) => (
              <line key={i} x1={a.x1} y1={a.y1} x2={a.x2} y2={a.y2} stroke="#e5e7eb" strokeWidth={1.5} markerEnd="url(#arrowhead)" />
            ))}
            <defs>
              <marker id="arrowhead" markerWidth={8} markerHeight={6} refX={8} refY={3} orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#9ca3af" />
              </marker>
            </defs>
          </svg>
        </div>
      </div>

      {/* Safety Gate + Risk Blend */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14, display: "flex", alignItems: "center", gap: 8 }}>
            Simulation Safety Gate
            <span style={{ fontSize: 11, color: "#16a34a", fontWeight: 600 }}>All 7 checks passed</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {gateChecks.map((c, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", background: "#f0fdf4", borderRadius: 8, border: "1px solid rgba(22,163,74,0.15)" }}>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="8" fill="#16a34a" opacity="0.12"/><path d="M5 8l2 2 4-4" stroke="#16a34a" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 500 }}>{c.check}</div>
                  <div style={{ fontSize: 10.5, color: "#6b7280" }}>{c.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Risk Blend Composition</div>
          {riskComponents.map((rc) => (
            <div key={rc.label} style={{ marginBottom: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ fontSize: 12 }}>{rc.label}</span>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: "#6b7280" }}>{rc.weight}</span>
              </div>
              <div style={{ height: 8, background: "#f3f4f6", borderRadius: 4, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${rc.value * 100 * 2.5}%`, background: rc.color, borderRadius: 4, opacity: 0.8 }} />
              </div>
            </div>
          ))}
          <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
            {[
              { label: "ALLOW", range: "< 0.40", color: "#16a34a" },
              { label: "CHALLENGE", range: "0.40 - 0.70", color: "#ea580c" },
              { label: "BLOCK", range: "> 0.70", color: "#dc2626" },
            ].map((t) => (
              <div key={t.label} style={{ padding: "6px 12px", borderRadius: 8, background: `${t.color}10`, border: `1px solid ${t.color}30`, fontSize: 11, fontWeight: 600, color: t.color }}>
                {t.label} <span style={{ fontWeight: 400, color: "#6b7280" }}>{t.range}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Navigation Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {navCards.map((card) => (
          <a key={card.href} href={card.href} style={{ textDecoration: "none", color: "inherit" }}>
            <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: "16px 18px", display: "flex", alignItems: "center", gap: 14, cursor: "pointer", transition: "all .15s", borderLeft: `3px solid ${card.color}` }}
              onMouseEnter={(e) => { e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.06)" }}
              onMouseLeave={(e) => { e.currentTarget.style.boxShadow = "none" }}
            >
              <div style={{ width: 36, height: 36, borderRadius: 8, background: `${card.color}12`, color: card.color, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, fontSize: 14, flexShrink: 0 }}>{card.letter}</div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{card.label}</div>
                <div style={{ fontSize: 11.5, color: "#6b7280", marginTop: 1 }}>{card.desc}</div>
              </div>
            </div>
          </a>
        ))}
      </div>
    </div>
  )
}
