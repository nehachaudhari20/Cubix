"use client"
import { RedTeamView } from "@/components/redteam-view"

export default function RedTeamHub() {
  return (
    <div style={{ minHeight: "100vh" }}>
      <div style={{ padding: "18px 28px 0", background: "#fff" }}>
        <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".6px", color: "#6b7280", fontWeight: 500 }}>
          Red Team
        </div>
        <h1 style={{ margin: "4px 0 4px", fontSize: 22, fontWeight: 700 }}>Attacks & Campaigns</h1>
        <p style={{ margin: "0 0 16px", color: "#6b7280", fontSize: 13, maxWidth: 760 }}>
          Pick a completed loop run and an attack family to inspect Threat Intelligence, Planner,
          Payloads, and Memory. Control gaps →{" "}
          <a href="/labs" style={{ color: "#2563eb", fontWeight: 600, textDecoration: "none" }}>
            Labs
          </a>
          .
        </p>
      </div>
      <RedTeamView embedded />
    </div>
  )
}
