"use client"
import { useEffect, useState } from "react"
import { Sandbox } from "@/components/data-pages"
import { api } from "@/lib/api"

type Tab = "evidence" | "stages" | "controls"

export default function SandboxPage() {
  const [tab, setTab] = useState<Tab>("evidence")
  const [stages, setStages] = useState<any[]>([])
  const [controls, setControls] = useState<any>(null)
  const [buffer, setBuffer] = useState<any>(null)

  useEffect(() => {
    Promise.all([
      api.stages().catch(() => []),
      api.stageControls().catch(() => null),
      api.buffer().catch(() => null),
    ]).then(([st, ctrls, buf]) => {
      setStages(Array.isArray(st) ? st : [])
      setControls(ctrls)
      setBuffer(buf)
    })
  }, [])

  return (
    <div>
      <div style={{ padding: "18px 28px 0", borderBottom: "1px solid #e5e7eb", background: "#fff" }}>
        <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".6px", color: "#6b7280", fontWeight: 500 }}>
          Sandbox
        </div>
        <h1 style={{ margin: "4px 0 12px", fontSize: 22, fontWeight: 700 }}>Payment Sandbox</h1>
        <div style={{ display: "flex", gap: 4 }}>
          {[
            { id: "evidence" as Tab, label: "Evidence" },
            { id: "stages" as Tab, label: "Lifecycle Stages" },
            { id: "controls" as Tab, label: "Controls" },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                padding: "10px 16px",
                border: "none",
                borderBottom: tab === t.id ? "2px solid #16a34a" : "2px solid transparent",
                background: "transparent",
                color: tab === t.id ? "#16a34a" : "#6b7280",
                fontWeight: tab === t.id ? 600 : 400,
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "evidence" && <Sandbox />}

      {tab === "stages" && (
        <div style={{ padding: "22px 28px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12, marginBottom: 16 }}>
            {[
              { label: "Buffer payments", value: buffer?.payment_records ?? "—" },
              { label: "Blocked", value: buffer?.blocked ?? "—" },
              { label: "Bypassed", value: buffer?.bypassed ?? "—" },
              { label: "Stages", value: stages.length || "—" },
            ].map((k) => (
              <div key={k.label} style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: 16 }}>
                <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase" }}>{k.label}</div>
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 20, fontWeight: 700, marginTop: 4 }}>{k.value}</div>
              </div>
            ))}
          </div>
          <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Lifecycle stages</div>
            {stages.length === 0 && <div style={{ color: "#6b7280", fontSize: 13 }}>No stages loaded from KB.</div>}
            {stages.map((s: any, i: number) => (
              <div key={i} style={{ padding: "12px 0", borderBottom: "1px solid #e5e7eb" }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{s.stage || s.stage_name || s.name || `Stage ${i + 1}`}</div>
                <div style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
                  {(s.controls || []).slice(0, 8).join(" · ") || "No controls listed"}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "controls" && (
        <div style={{ padding: "22px 28px" }}>
          <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Controls by stage</div>
            {!controls && <div style={{ color: "#6b7280", fontSize: 13 }}>Loading controls…</div>}
            {controls &&
              Object.entries(controls).map(([stage, ctrls]: [string, any]) => (
                <div key={stage} style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>{stage}</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {(Array.isArray(ctrls) ? ctrls : []).map((c: string) => (
                      <span
                        key={c}
                        style={{
                          fontSize: 11,
                          padding: "4px 8px",
                          borderRadius: 6,
                          background: "#f9fafb",
                          border: "1px solid #e5e7eb",
                          fontFamily: "'JetBrains Mono', monospace",
                          color: "#374151",
                        }}
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}
