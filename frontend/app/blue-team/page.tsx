"use client"
import { useState } from "react"
import BlueDefense from "./_defense"
import ModelEvolution from "../model-evolution/page"

type Tab = "defense" | "models"

const TABS: { id: Tab; label: string }[] = [
  { id: "defense", label: "Defense" },
  { id: "models", label: "Models" },
]

export default function BlueTeamHub() {
  const [tab, setTab] = useState<Tab>("defense")

  return (
    <div>
      <div style={{ padding: "18px 28px 0", borderBottom: "1px solid #e5e7eb", background: "#fff" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".6px", color: "#6b7280", fontWeight: 500 }}>
              Blue Team
            </div>
            <h1 style={{ margin: "4px 0 4px", fontSize: 22, fontWeight: 700 }}>RedBlue Defense</h1>
            <p style={{ margin: "0 0 12px", color: "#6b7280", fontSize: 13, maxWidth: 640 }}>
              Model ops and hardening. Control gaps, failure analysis, and closed-loop learnings live in{" "}
              <a href="/labs" style={{ color: "#2563eb", fontWeight: 600, textDecoration: "none" }}>
                Labs
              </a>
              ; loop scorecards in{" "}
              <a href="/evaluation" style={{ color: "#2563eb", fontWeight: 600, textDecoration: "none" }}>
                Evaluation
              </a>
              .
            </p>
          </div>
        </div>
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
      {tab === "models" && <ModelEvolution />}
    </div>
  )
}
