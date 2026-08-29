"use client"
import { useEffect, useState } from "react"
import { api, errorText } from "@/lib/api"
import { closedLoop } from "@/lib/api-v1"

export default function ClosedLoopArena() {
  const [comp, setComp] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [statusMsg, setStatusMsg] = useState("")
  const [err, setErr] = useState("")
  const [loopId, setLoopId] = useState("")
  const [missed, setMissed] = useState<any>(null)
  const [mode, setMode] = useState<"latest" | "new">("latest")

  // Prefill from latest completed platform run
  useEffect(() => {
    api.runs(10)
      .then(async (runs) => {
        const completed = runs.find((r) => r.status === "completed")
        if (!completed) return
        setLoopId(completed.id)
        try {
          const c = await closedLoop.comparison(completed.id)
          setComp(c)
        } catch {
          /* no eval yet */
        }
      })
      .catch(() => {})
  }, [])

  const pollUntilDone = async (id: string) => {
    for (let i = 0; i < 180; i++) {
      const state = await closedLoop.loop(id)
      setStatusMsg(`Status: ${state.status}${state.running ? " (running)" : ""}`)
      if (state.status === "completed" || state.status === "failed") {
        return state
      }
      await new Promise((r) => setTimeout(r, 3000))
    }
    throw new Error("Timed out waiting for loop")
  }

  const runComparison = async () => {
    setLoading(true)
    setErr("")
    setMissed(null)
    try {
      if (mode === "latest") {
        setStatusMsg("Loading latest completed run…")
        const loop = await closedLoop.run({ families: 8, run_full_loop: false })
        setLoopId(loop.loop_id || loop.run_id)
        const c = loop.comparison || (await closedLoop.comparison(loop.loop_id || loop.run_id))
        setComp(c)
        setStatusMsg(`Loaded ${loop.loop_id || loop.run_id}`)
      } else {
        setStatusMsg("Starting platform loop…")
        const loop = await closedLoop.run({
          families: 8,
          run_full_loop: true,
          skip_train_v1: false,
          swap_model: false,
        })
        const id = loop.loop_id || loop.run_id
        setLoopId(id)
        if (loop.status === "completed" && loop.comparison) {
          setComp(loop.comparison)
        } else {
          await pollUntilDone(id)
          const c = await closedLoop.comparison(id)
          setComp(c)
        }
        setStatusMsg("Loop completed")
      }
      if (loopId || comp) {
        const mid = loopId || comp?.loop_id
        if (mid) {
          closedLoop.missedEvents(mid).then(setMissed).catch(() => {})
        }
      }
    } catch (e) {
      setErr(errorText(e))
    }
    setLoading(false)
  }

  useEffect(() => {
    if (comp?.loop_id) {
      closedLoop.missedEvents(comp.loop_id).then(setMissed).catch(() => {})
    }
  }, [comp?.loop_id])

  const fmt = (v: any) => (typeof v === "number" ? v.toFixed(4) : "—")

  return (
    <div style={{ background: "#f8f9fa", color: "#111827", minHeight: "100vh", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "22px 28px 60px" }}>
        <h2 style={{ margin: "0 0 4px", fontSize: 20 }}>Closed-Loop Arena</h2>
        <p style={{ margin: "0 0 20px", color: "#6b7280", fontSize: 13 }}>
          Attack → Detect → Learn → Harden → Re-test — metrics from real platform loop runs.
        </p>

        <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 16, flexWrap: "wrap" }}>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as "latest" | "new")}
            style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid #e5e7eb", background: "#fff", fontSize: 13 }}
          >
            <option value="latest">Compare latest completed run</option>
            <option value="new">Start new platform loop (slow)</option>
          </select>
          <button
            onClick={runComparison}
            disabled={loading}
            style={{
              padding: "12px 24px",
              borderRadius: 10,
              background: "linear-gradient(135deg, #dc2626, #ea580c)",
              color: "#fff",
              fontWeight: 600,
              fontSize: 14,
              border: "none",
              cursor: loading ? "wait" : "pointer",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? "Running…" : mode === "latest" ? "Load Comparison" : "Run Full Loop"}
          </button>
          {statusMsg && (
            <span style={{ fontSize: 12, color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>{statusMsg}</span>
          )}
        </div>

        {err && (
          <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 12, color: "#dc2626" }}>
            {err}
          </div>
        )}

        {comp && (
          <>
            <div style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Closed-Loop Flow</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, flexWrap: "wrap" }}>
                {["Red Team Attack", "RedBlue v1 Scores", "Gaps Found", "Blue Team Retrains", "RedBlue v3 Scores", "ASR Measured"].map((step, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{ padding: "8px 12px", background: "#f9fafb", borderRadius: 8, border: "1px solid #e5e7eb" }}>{step}</div>
                    {i < 5 && <span style={{ color: "#6b7280" }}>→</span>}
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 10, fontSize: 11, color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>
                source={comp.source || "platform_loop"} · run={comp.loop_id?.slice(0, 8)}
                {comp.run ? ` · payments=${comp.run.buffer_payments} bypassed=${comp.run.buffer_bypassed}` : ""}
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
              {[
                { label: "RedBlue v1", data: comp.before, color: "#6b7280" },
                { label: "RedBlue v3", data: comp.after, color: "#16a34a" },
              ].map((model, i) => (
                <div key={i} style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12, color: model.color }}>{model.label}</div>
                  <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 16 }}>{model.data?.type}</div>
                  {[
                    { label: "PR-AUC", value: model.data?.pr_auc },
                    { label: "F1", value: model.data?.f1 },
                    { label: "Recall", value: model.data?.recall },
                    { label: "FPR", value: model.data?.fpr },
                    { label: "ASR", value: model.data?.asr },
                    { label: "Buffer mean", value: model.data?.buffer_mean_score },
                  ].map((m, j) => (
                    <div key={j} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #e5e7eb", fontSize: 12 }}>
                      <span style={{ color: "#6b7280" }}>{m.label}</span>
                      <span style={{ fontFamily: "'JetBrains Mono', monospace", color: m.label === "ASR" && m.value > 0.1 ? "#dc2626" : "#111827" }}>
                        {fmt(m.value)}
                      </span>
                    </div>
                  ))}
                </div>
              ))}
            </div>

            <div style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginBottom: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Improvement Deltas</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 12 }}>
                {Object.entries(comp.deltas || {}).map(([key, val]: [string, any]) => (
                  <div key={key} style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", marginBottom: 4 }}>{key.replace(/_/g, " ")}</div>
                    <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 16, fontWeight: 600, color: typeof val === "number" && val > 0 ? "#16a34a" : "#dc2626" }}>
                      {typeof val === "number" ? `${val > 0 ? "+" : ""}${val.toFixed(4)}` : "—"}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {missed?.events?.length > 0 && (
              <div style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>
                  Missed / challenged events <span style={{ color: "#6b7280", fontWeight: 400 }}>({missed.total})</span>
                </div>
                <div style={{ maxHeight: 280, overflowY: "auto" }}>
                  {missed.events.slice(0, 20).map((e: any, i: number) => (
                    <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #e5e7eb", fontSize: 12 }}>
                      <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>{e.attack_family}</span>
                      <span style={{ color: e.sandbox_decision === "ALLOW" ? "#dc2626" : "#ea580c" }}>{e.sandbox_decision}</span>
                      <span style={{ color: "#6b7280" }}>{e.ml_score != null ? Number(e.ml_score).toFixed(3) : "—"}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {!comp && !loading && (
          <div style={{ color: "#6b7280", fontSize: 13, padding: 24, background: "#fff", borderRadius: 14, border: "1px solid #e5e7eb" }}>
            No comparison loaded yet. Load the latest completed platform run, or start a new loop.
          </div>
        )}
      </div>
    </div>
  )
}
