"use client"
import { useState } from "react"
import CampaignLab from "../campaign-lab/page"
import { RedTeamView } from "@/components/redteam-view"

type Tab = "campaigns" | "launch"

export default function RedTeamHub() {
  const [tab, setTab] = useState<Tab>("campaigns")

  return (
    <div style={{ minHeight: "100vh" }}>
      {/* Header + Tab bar */}
      <div
        style={{
          padding: "18px 28px 0",
          background: "#fff",
          borderBottom: "none",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div
              style={{
                fontSize: 11,
                textTransform: "uppercase",
                letterSpacing: ".6px",
                color: "#6b7280",
                fontWeight: 500,
              }}
            >
              Red Team
            </div>
            <h1 style={{ margin: "4px 0 4px", fontSize: 22, fontWeight: 700 }}>
              Attacks & Campaigns
            </h1>
            <p style={{ margin: "0 0 12px", color: "#6b7280", fontSize: 13, maxWidth: 720 }}>
              Launch a campaign, then deep-dive loop executions — Threat Intelligence, Planner,
              Payloads, and Memory. Control gaps and closed-loop learnings →{" "}
              <a href="/labs" style={{ color: "#2563eb", fontWeight: 600, textDecoration: "none" }}>
                Labs
              </a>
              .
            </p>
          </div>
        </div>

        {/* Tab strip */}
        <div style={{ display: "flex", gap: 4, paddingTop: 2 }}>
          {([
            ["campaigns", "🎯", "Campaigns", "Loop executions · Threat Intel · Planner · Payloads"],
            ["launch", "🚀", "Launch", "Threat Hunter · Hypotheses · Attack families"],
          ] as const).map(([id, icon, label, sub]) => {
            const active = tab === id
            return (
              <button
                key={id}
                onClick={() => setTab(id as Tab)}
                style={{
                  flex: 1,
                  padding: "10px 16px 8px",
                  borderRadius: "8px 8px 0 0",
                  border: "1px solid #e5e7eb",
                  borderBottom: active ? "2px solid #fff" : "2px solid #e5e7eb",
                  background: active ? "#fff" : "#f9fafb",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                  textAlign: "left" as const,
                  position: "relative" as const,
                  zIndex: active ? 1 : 0,
                  marginBottom: active ? -1 : 0,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 15 }}>{icon}</span>
                  <span style={{ fontWeight: active ? 700 : 500, fontSize: 13.5, color: active ? "#111827" : "#9ca3af" }}>{label}</span>
                  <span
                    style={{
                      marginLeft: "auto",
                      fontSize: 9,
                      padding: "2px 7px",
                      borderRadius: 5,
                      background: active ? "#fef2f2" : "#f3f4f6",
                      color: active ? "#dc2626" : "#9ca3af",
                      fontWeight: 600,
                      letterSpacing: ".3px",
                      textTransform: "uppercase" as const,
                    }}
                  >
                    {id === "campaigns" ? "20 camps" : "12 hypo"}
                  </span>
                </div>
                <div style={{ fontSize: 10.5, color: "#9ca3af", marginTop: 3, lineHeight: 1.3 }}>
                  {sub}
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Tab content */}
      {tab === "campaigns" && <RedTeamView embedded />}
      {tab === "launch" && <CampaignLab embedded />}
    </div>
  )
}
