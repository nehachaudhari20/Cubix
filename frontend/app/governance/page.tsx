"use client"
import { useEffect, useState } from "react"
import { governance } from "@/lib/api-v1"



export default function GovernancePage() {
  const [safety, setSafety] = useState<any>(null)
  const [registry, setRegistry] = useState<any>(null)
  const [metadata, setMetadata] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      governance.safety().catch(() => null),
      governance.modelRegistry().catch(() => null),
      governance.dataMetadata().catch(() => null),
    ]).then(([s, r, m]) => {
      setSafety(s); setRegistry(r); setMetadata(m); setLoading(false)
    })
  }, [])

  if (loading) return <div style={{ color: "#6b7280", padding: 40, background: "#f8f9fa", minHeight: "100vh" }}>Loading…</div>

  return (
    <div style={{ background: "#f8f9fa", color: "#111827", minHeight: "100vh", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "22px 28px 60px" }}>
        <h2 style={{ margin: "0 0 4px", fontSize: 20 }}>Evidence, Safety & Governance</h2>
        <p style={{ margin: "0 0 20px", color: "#6b7280", fontSize: 13 }}>Safety policy, model registry, experiment reproducibility, and data metadata.</p>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
          {/* Safety Policy */}
          <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Simulation Safety Policy</div>
            {safety?.policy && Object.entries(safety.policy).filter(([k]) => !["prohibited_actions", "gate_checks"].includes(k)).map(([key, val]: [string, any]) => (
              <div key={key} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: `1px solid ${"#e5e7eb"}`, fontSize: 12 }}>
                <span style={{ color: "#6b7280", textTransform: "capitalize" }}>{key.replace("_", " ")}</span>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", color: typeof val === "boolean" ? (val ? "#16a34a" : "#dc2626") : "#111827" }}>{String(val)}</span>
              </div>
            ))}
            {safety?.policy?.prohibited_actions && (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 6 }}>Prohibited Actions</div>
                {safety.policy.prohibited_actions.map((a: string, i: number) => (
                  <div key={i} style={{ fontSize: 11, color: "#dc2626", padding: "3px 0" }}>✗ {a}</div>
                ))}
              </div>
            )}
          </div>

          {/* Data Metadata */}
          <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Data Metadata</div>
            <div style={{ fontSize: 12, color: "#16a34a", marginBottom: 12, fontWeight: 600 }}>Scope: {metadata?.data_scope || "SYNTHETIC_ONLY"}</div>
            {metadata?.non_real_data?.map((item: string, i: number) => (
              <div key={i} style={{ fontSize: 11, color: "#16a34a", padding: "3px 0" }}>✓ {item}</div>
            ))}
            {metadata?.limitations?.map((item: string, i: number) => (
              <div key={i} style={{ fontSize: 11, color: "#ea580c", padding: "3px 0", marginTop: 4 }}>⚠ {item}</div>
            ))}
          </div>
        </div>

        {/* Model Registry */}
        <div style={{ background: "#ffffff", border: `1px solid ${"#e5e7eb"}`, borderRadius: 14, padding: 18, marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Model Registry</div>
          {registry?.registry?.map((model: any, i: number) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "10px 0", borderBottom: `1px solid ${"#e5e7eb"}`, fontSize: 12 }}>
              <div>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, marginRight: 12 }}>FraudShield {model.version}</span>
                <span style={{ color: "#6b7280" }}>{model.model_type}</span>
              </div>
              <div>
                <span style={{ padding: "2px 8px", borderRadius: 100, background: model.status === "deployed" ? "rgba(34,229,160,.16)" : "#f9fafb", color: model.status === "deployed" ? "#16a34a" : "#6b7280", fontSize: 10 }}>{model.status}</span>
                <span style={{ marginLeft: 8, color: "#6b7280" }}>{model.feature_count} features</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
