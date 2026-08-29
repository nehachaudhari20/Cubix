"use client"
import { useState } from "react"
import BlueDefense from "./_defense"
import ScoreConsole from "../fraudshield-console/page"
import ClosedLoopArena from "../closed-loop/page"
import ModelEvolution from "../model-evolution/page"

type Tab = "defense" | "score" | "loop" | "models"

const TABS: { id: Tab; label: string }[] = [
  { id: "defense", label: "Defense" },
  { id: "score", label: "Score Console" },
  { id: "loop", label: "Closed Loop" },
  { id: "models", label: "Models" },
]

export default function BlueTeamHub() {
  const [tab, setTab] = useState<Tab>("defense")

  return (
    <div>
      <div style={{ padding: "18px 28px 0", borderBottom: "1px solid #e5e7eb", background: "#fff" }}>
        <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".6px", color: "#6b7280", fontWeight: 500 }}>
          Blue Team
        </div>
        <h1 style={{ margin: "4px 0 12px", fontSize: 22, fontWeight: 700 }}>RedBlue Defense</h1>
        <div style={{ display: "flex", gap: 4 }}>
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              style={{
                padding: "10px 16px",
                border: "none",
                borderBottom: tab === t.id ? "2px solid #2563eb" : "2px solid transparent",
                background: "transparent",
                color: tab === t.id ? "#2563eb" : "#6b7280",
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

      {tab === "defense" && <BlueDefense />}
      {tab === "score" && <ScoreConsole />}
      {tab === "loop" && <ClosedLoopArena />}
      {tab === "models" && <ModelEvolution />}
    </div>
  )
}
