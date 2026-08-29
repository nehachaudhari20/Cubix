"use client"
/**
 * Global Attack Surface — real Leaflet basemap + buffer-driven markers.
 * Falls back to illustrative volumes when the evidence buffer is empty.
 */
import dynamic from "next/dynamic"

const WorldMap = dynamic(() => import("@/components/world-map"), { ssr: false })

type BufferStats = {
  total?: number
  blocked?: number
  bypassed?: number
  families?: string[]
}

export default function AttackSurface({ bufferStats }: { bufferStats?: BufferStats }) {
  const total = bufferStats?.total || 0
  const blocked = bufferStats?.blocked || 0
  const bypassed = bufferStats?.bypassed || 0
  const live = total > 0

  // Feed WorldMap either live buffer stats or a rich illustrative baseline
  const mapStats: BufferStats = live
    ? bufferStats!
    : {
        total: 1718,
        blocked: 1408,
        bypassed: 186,
        families: ["ATO-001", "SIF-001", "UPI-003", "MUL-002", "DEV-007", "MRC-003", "SYN-006"],
      }

  const corridors = [
    { c: "South Asia · UPI / RTP", v: live ? `${Math.round(blocked * 0.28)} blocked` : "482 blocked", color: "#dc2626" },
    { c: "Europe · Open Banking", v: live ? `${Math.round(Math.max(bypassed, 1) * 0.2)} challenged` : "58 challenged", color: "#ea580c" },
    { c: "N. America · Card CNP", v: live ? `${Math.round(blocked * 0.16)} blocked` : "298 blocked", color: "#dc2626" },
    { c: "Africa · Instant rails", v: live ? `${Math.round(blocked * 0.1)} blocked` : "131 blocked", color: "#dc2626" },
    { c: "E. Asia · Real-time", v: live ? `${Math.round(blocked * 0.12)} blocked` : "176 blocked", color: "#16a34a" },
  ]

  return (
    <div>
      <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 8 }}>
        {live
          ? `Live from evidence buffer · ${total} payments · ${blocked} blocked · ${bypassed} bypassed`
          : "Illustrative volumes (buffer empty — run a loop to go live)"}
      </div>

      <WorldMap bufferStats={mapStats} />

      <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        {corridors.map((c) => (
          <div
            key={c.c}
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 12,
              paddingBottom: 8,
              borderBottom: "1px solid #e5e7eb",
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 8, color: "#6b7280" }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: c.color }} />
              {c.c}
            </span>
            <span style={{ fontFamily: "'JetBrains Mono', monospace", color: c.color, fontWeight: 600 }}>{c.v}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
