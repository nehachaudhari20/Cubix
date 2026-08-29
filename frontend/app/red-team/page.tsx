"use client"
import { RedTeamView } from "@/components/redteam-view"
import CampaignLab from "../campaign-lab/page"

export default function RedTeamHub() {
  return (
    <div>
      <div style={{ padding: "18px 28px 8px", background: "#fff", borderBottom: "1px solid #e5e7eb" }}>
        <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".6px", color: "#6b7280", fontWeight: 500 }}>
          Red Team
        </div>
        <h1 style={{ margin: "4px 0 4px", fontSize: 22, fontWeight: 700 }}>Attacks & Campaigns</h1>
        <p style={{ margin: "0 0 12px", color: "#6b7280", fontSize: 13 }}>
          Launch a campaign, then deep-dive loop executions — Threat Intelligence, Planner, Payloads, and Memory.
        </p>
      </div>

      <CampaignLab embedded />
      <div style={{ height: 1, background: "#e5e7eb", margin: "0 28px" }} />
      <RedTeamView embedded />
    </div>
  )
}
