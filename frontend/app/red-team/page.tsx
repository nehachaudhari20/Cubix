"use client"
import { useState } from "react"
import { RedTeamView } from "@/components/redteam-view"
import CampaignLab from "../campaign-lab/page"
import NovelAttackPage from "../novel-attack/page"

type Tab = "campaigns" | "launch" | "novel"

const TABS: { id: Tab; label: string }[] = [
  { id: "campaigns", label: "Campaigns" },
  { id: "launch", label: "Launch Campaign" },
  { id: "novel", label: "Novel Attacks" },
]

export default function RedTeamHub() {
  const [tab, setTab] = useState<Tab>("campaigns")

  return (
    <div>
      <div style={{ padding: "18px 28px 0", borderBottom: "1px solid #e5e7eb", background: "#fff" }}>
        <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".6px", color: "#6b7280", fontWeight: 500 }}>
          Red Team
        </div>
        <h1 style={{ margin: "4px 0 12px", fontSize: 22, fontWeight: 700 }}>Attacks & Campaigns</h1>
        <div style={{ display: "flex", gap: 4 }}>
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                padding: "10px 16px",
                border: "none",
                borderBottom: tab === t.id ? "2px solid #dc2626" : "2px solid transparent",
                background: "transparent",
                color: tab === t.id ? "#dc2626" : "#6b7280",
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

      {tab === "campaigns" && <RedTeamView />}
      {tab === "launch" && <CampaignLab />}
      {tab === "novel" && <NovelAttackPage />}
    </div>
  )
}
