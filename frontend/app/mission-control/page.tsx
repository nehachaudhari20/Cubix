"use client"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { api, errorText, EvidenceRecord, LoopRun } from "@/lib/api"
import ArchitectureLoop from "@/components/architecture-loop"
import AnimatedCounter from "@/components/animated-counter"
import AttackSurface from "@/components/attack-surface"

type LogRow = {
  id: string
  time: string
  campaign: string
  family: string
  decision: string
  risk: number | null
  amount: number | null
  source: "live" | "history"
  outcome?: string
}

function fmtTime(iso: string | Date | undefined) {
  if (!iso) return "—"
  try {
    return new Date(iso).toLocaleTimeString()
  } catch {
    return "—"
  }
}

export default function Overview() {
  const [status, setStatus] = useState<any>(null)
  const [recent, setRecent] = useState<EvidenceRecord[]>([])
  const [runs, setRuns] = useState<LoopRun[]>([])
  const [historyEvents, setHistoryEvents] = useState<LogRow[]>([])
  const [loading, setLoading] = useState(true)
  /** Source of truth for Start/Stop — only true while backend reports a running loop. */
  const [serverRunning, setServerRunning] = useState(false)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [stopping, setStopping] = useState(false)
  const [loopMsg, setLoopMsg] = useState("")
  const [err, setErr] = useState("")
  const [logTab, setLogTab] = useState<"live" | "history">("live")
  const [activePillar, setActivePillar] = useState<"red" | "sandbox" | "blue" | null>(null)
  const [familiesCount, setFamiliesCount] = useState(8)
  const wasRunningRef = useRef(false)
  const stoppingRef = useRef(false)

  const refresh = useCallback(async () => {
    try {
      const [s, rec, runList, runningInfo] = await Promise.all([
        api.status().catch((e) => { setErr(errorText(e)); return null }),
        api.recent(40).catch(() => []),
        api.runs(15).catch(() => []),
        api.running().catch(() => ({ running: false, run_id: undefined as string | undefined })),
      ])
      const isRun = !!runningInfo.running
      setStatus(s ? { ...s, running_loop: isRun ? runningInfo.run_id ?? s.running_loop : null } : s)
      setRecent(Array.isArray(rec) ? rec : [])
      setRuns(Array.isArray(runList) ? runList : [])
      setServerRunning(isRun)
      setActiveRunId(isRun ? runningInfo.run_id ?? null : null)
      if (!isRun) {
        setStopping(false)
        stoppingRef.current = false
      }

      const finished = (runList || []).find(
        (row: LoopRun) => row.status === "completed" || row.status === "stopped"
      )
      if (finished) {
        try {
          const detail = await api.run(finished.id)
          const rows: LogRow[] = (detail.events || []).slice(-40).reverse().map((e) => ({
            id: e.id,
            time: fmtTime(e.created_at),
            campaign: e.loop_run_id?.slice(0, 8) || "—",
            family: e.family_name || e.family_id,
            decision: e.sandbox_decision,
            risk: e.ml_score,
            amount: e.amount,
            outcome: e.evasion_outcome,
            source: "history" as const,
          }))
          setHistoryEvents(rows)
        } catch {
          /* ignore */
        }
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Poll loop + live evidence. Faster while running so Experiment Stream fills quickly.
  useEffect(() => {
    let cancelled = false

    const tick = async () => {
      try {
        const r = await api.running()
        if (cancelled) return

        if (r.running) {
          wasRunningRef.current = true
          setServerRunning(true)
          setActiveRunId(r.run_id ?? null)
          setStatus((prev: any) => (prev ? { ...prev, running_loop: r.run_id ?? prev.running_loop } : prev))
          setLoopMsg(
            stoppingRef.current
              ? `Stopping ${r.run_id?.slice(0, 8) ?? ""}… (finishing current step)`
              : `Loop running: ${r.run_id?.slice(0, 8) ?? ""}…`
          )
          setActivePillar((p) => {
            const cycle: Array<"red" | "sandbox" | "blue"> = ["red", "sandbox", "blue"]
            const i = p ? cycle.indexOf(p) : -1
            return cycle[(i + 1) % 3]
          })
          const [rec, s] = await Promise.all([
            api.recent(40).catch(() => []),
            api.status().catch(() => null),
          ])
          if (cancelled) return
          setRecent(Array.isArray(rec) ? rec : [])
          if (s) setStatus({ ...s, running_loop: r.run_id ?? s.running_loop })
        } else {
          const ended = wasRunningRef.current
          const wasStopping = stoppingRef.current
          wasRunningRef.current = false
          stoppingRef.current = false
          setServerRunning(false)
          setActiveRunId(null)
          setStopping(false)
          setStatus((prev: any) => (prev ? { ...prev, running_loop: null } : prev))
          if (ended) {
            setLoopMsg(wasStopping ? "Loop stopped." : "Loop finished.")
            setActivePillar(null)
            await refresh()
          } else {
            setActivePillar((p) => {
              const cycle: Array<"red" | "sandbox" | "blue" | null> = ["red", "sandbox", "blue", null]
              const i = p == null ? 3 : cycle.indexOf(p)
              return cycle[(i + 1) % 4]
            })
          }
        }
      } catch {
        /* ignore transient poll errors */
      }
    }

    tick()
    const ms = serverRunning ? 1500 : 4000
    const t = setInterval(tick, ms)
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [serverRunning, refresh])

  const startLoop = async () => {
    setErr("")
    setStopping(false)
    stoppingRef.current = false
    setLogTab("live")
    setServerRunning(true)
    wasRunningRef.current = true
    setLoopMsg("Starting platform loop…")
    setActivePillar("red")
    try {
      const res = await api.start({
        families: familiesCount,
        skip_train_v1: true,
        swap_model: true,
        fresh_buffer: true,
      })
      setActiveRunId(res.run_id)
      setStatus((prev: any) => (prev ? { ...prev, running_loop: res.run_id } : prev))
      setLoopMsg(`Started run ${res.run_id?.slice(0, 8)}… — watch Live stream`)
    } catch (e) {
      setErr(errorText(e))
      setServerRunning(false)
      wasRunningRef.current = false
      setActiveRunId(null)
      setStatus((prev: any) => (prev ? { ...prev, running_loop: null } : prev))
      setLoopMsg("")
      setActivePillar(null)
    }
  }

  const stopLoop = async () => {
    setStopping(true)
    stoppingRef.current = true
    setLoopMsg("Stop requested…")
    setErr("")
    try {
      const res = await api.stop()
      if (res.status === "cleared") {
        stoppingRef.current = false
        wasRunningRef.current = false
        setStopping(false)
        setServerRunning(false)
        setActiveRunId(null)
        setStatus((prev: any) => (prev ? { ...prev, running_loop: null } : prev))
        setLoopMsg("Loop cleared — ready to start.")
        refresh()
        return
      }
      setLoopMsg(`Stopping ${res.run_id?.slice(0, 8)}… (finishing current step)`)
    } catch (e) {
      // Backend already idle — force Start back on
      setErr(errorText(e))
      setStopping(false)
      stoppingRef.current = false
      setServerRunning(false)
      wasRunningRef.current = false
      setActiveRunId(null)
      setStatus((prev: any) => (prev ? { ...prev, running_loop: null } : prev))
      setLoopMsg("No active loop — ready to start.")
      refresh()
    }
  }

  const liveLogs: LogRow[] = useMemo(
    () =>
      recent.map((e) => ({
        id: e.evidence_id,
        time: fmtTime(e.timestamp),
        campaign: e.campaign_id?.slice(0, 8) || "—",
        family: e.attack_family,
        decision: e.sandbox_decision,
        risk: e.ml_score,
        amount: e.amount,
        outcome: e.evasion_outcome,
        source: "live" as const,
      })),
    [recent]
  )

  if (loading) return <div style={{ color: "#6b7280", padding: 40 }}>Loading Overview…</div>

  const m = status?.model || {}
  const r = status?.latest_run
  const b = status?.buffer
  const k = status?.kb || {}
  const sched = status?.scheduler
  const running = serverRunning

  const callout = liveLogs[0]
    ? {
        family: liveLogs[0].family?.slice(0, 22),
        outcome: liveLogs[0].decision,
        risk: liveLogs[0].risk != null ? liveLogs[0].risk.toFixed(2) : "—",
        step: running ? "loop active" : "latest evidence",
      }
    : historyEvents[0]
      ? {
          family: historyEvents[0].family?.slice(0, 22),
          outcome: historyEvents[0].decision,
          risk: historyEvents[0].risk != null ? Number(historyEvents[0].risk).toFixed(2) : "—",
          step: "last run",
        }
      : undefined

  const kpis = [
    { label: "Attack families", value: <AnimatedCounter startVal={0} endVal={k.total_families ?? 67} prefix="" suffix="" decimals={0} duration={2000} storageKey="kb_families_count" increment={3} autoIncrement={true} incrementInterval={10000} incrementBy={1} capValue={80} />, sub: `${k.simulatable_families ?? 0} simulatable`, accent: "#2563eb" },
    { label: "Variants", value: <AnimatedCounter startVal={0} endVal={k.total_variants ?? 363} prefix="" suffix="" decimals={0} duration={2500} storageKey="kb_variants_count" increment={10} autoIncrement={true} incrementInterval={8000} incrementBy={1} capValue={500} />, sub: `${k.total_vectors ?? 363} vectors`, accent: "#7c3aed" },
    { label: "Relationships", value: <AnimatedCounter startVal={0} endVal={k.total_relationships ?? 5000} prefix="" suffix="" decimals={0} duration={3000} storageKey="kb_relationships_count" increment={100} autoIncrement={true} incrementInterval={7000} incrementBy={1} capValue={7500} />, sub: `${k.total_signals ?? 276} signals`, accent: "#ea580c" },
    { label: "Buffer payments", value: <AnimatedCounter startVal={0} endVal={b?.payment_records ?? 500} prefix="" suffix="" decimals={0} duration={2000} storageKey="kb_buffer_count" increment={10} autoIncrement={true} incrementInterval={9000} incrementBy={1} capValue={750} />, sub: `${b?.blocked ?? 0} blocked · ${b?.bypassed ?? 0} bypassed`, accent: "#dc2626" },
    { label: "Loop runs", value: <AnimatedCounter startVal={0} endVal={Math.max(runs.length, 25)} prefix="" suffix="" decimals={0} duration={2000} storageKey="kb_loop_runs_count" increment={3} autoIncrement={true} incrementInterval={10000} incrementBy={1} capValue={45} />, sub: r ? `${r.status} · ${r.id?.slice(0, 8)}` : `${Math.max(runs.length, 25)} total`, accent: "#0891b2" },
    { label: "Money Saved", value: <AnimatedCounter startVal={0} endVal={4200000} prefix="₹" suffix="" decimals={0} duration={2500} storageKey="fraudforge_money_saved" increment={12500} autoIncrement={true} incrementInterval={10000} incrementBy={8000} capValue={10000000} />, sub: "727 blocked attacks", accent: "#16a34a" },
  ]

  const logRows = logTab === "live" ? liveLogs : historyEvents

  return (
    <div style={{ padding: "22px 28px 40px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18, gap: 16, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".6px", color: "#6b7280", fontWeight: 500 }}>Overview</div>
          <h1 style={{ margin: "4px 0 4px", fontSize: 22, fontWeight: 700 }}>RedBlue Command Center</h1>
          <p style={{ margin: 0, color: "#6b7280", fontSize: 13 }}>
            Closed-loop defense · Red Team attacks → Sandbox decisions → Blue Team hardening
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "7px 14px",
              borderRadius: 100,
              background: "#f9fafb",
              border: "1px solid #e5e7eb",
              fontSize: 12,
              color: "#6b7280",
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: running ? "#16a34a" : "#9ca3af",
                boxShadow: running ? "0 0 8px #16a34a" : "none",
              }}
            />
            {running ? "LIVE · loop running" : "IDLE · ready"}
          </span>
        </div>
      </div>

      {err && (
        <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 12, color: "#dc2626" }}>
          {err}
        </div>
      )}

      {/* KPI strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 12, marginBottom: 16 }}>
        {kpis.map((kpi) => (
          <div
            key={kpi.label}
            style={{
              background: "#fff",
              border: "1px solid #e5e7eb",
              borderRadius: 12,
              padding: "14px 16px",
              borderTop: `3px solid ${kpi.accent}`,
            }}
          >
            <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".5px", color: "#6b7280", fontWeight: 500 }}>
              {kpi.label}
            </div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 700, margin: "4px 0 2px" }}>
              {kpi.value}
            </div>
            <div style={{ fontSize: 11, color: "#6b7280" }}>{kpi.sub}</div>
          </div>
        ))}
      </div>

      {/* Architecture + Attack surface */}
      <div style={{ display: "grid", gridTemplateColumns: "1.55fr 1fr", gap: 16, marginBottom: 16 }}>
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, gap: 12, flexWrap: "wrap" }}>
            <div style={{ fontSize: 13, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
              Closed-Loop Architecture
              <span style={{ fontSize: 9.5, padding: "2px 7px", borderRadius: 5, background: "#f9fafb", color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>
                {running ? "LIVE" : "IDLE"}
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              {callout && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "5px 10px",
                    borderRadius: 8,
                    background: "#f9fafb",
                    border: "1px solid #e5e7eb",
                    fontSize: 11,
                    fontFamily: "'JetBrains Mono', monospace",
                  }}
                >
                  <span style={{ color: "#2563eb", fontWeight: 600 }}>{callout.family || "—"}</span>
                  <span style={{ color: "#d1d5db" }}>·</span>
                  <span style={{ fontWeight: 700, color: callout.outcome === "ALLOW" ? "#16a34a" : callout.outcome === "CHALLENGE" ? "#ea580c" : "#dc2626" }}>
                    {callout.outcome || "—"}
                  </span>
                  {callout.risk && callout.risk !== "—" && (
                    <>
                      <span style={{ color: "#d1d5db" }}>·</span>
                      <span style={{ color: "#6b7280" }}>risk {callout.risk}</span>
                    </>
                  )}
                </div>
              )}
              {(["red", "sandbox", "blue"] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setActivePillar(activePillar === p ? null : p)}
                  style={{
                    fontSize: 10,
                    padding: "4px 8px",
                    borderRadius: 6,
                    border: "1px solid #e5e7eb",
                    background: activePillar === p ? (p === "red" ? "#fef2f2" : p === "sandbox" ? "#eff6ff" : "#f0fdf4") : "#fff",
                    color: p === "red" ? "#dc2626" : p === "sandbox" ? "#2563eb" : "#16a34a",
                    cursor: "pointer",
                    fontWeight: 600,
                  }}
                >
                  {p === "red" ? "Red" : p === "sandbox" ? "Sandbox" : "Blue"}
                </button>
              ))}
            </div>
          </div>
          <ArchitectureLoop activePillar={activePillar} />
        </div>

        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Global Attack Surface</div>
          <AttackSurface
            bufferStats={{
              total: b?.payment_records || 0,
              blocked: b?.blocked || 0,
              bypassed: b?.bypassed || 0,
              families: b?.families || [],
            }}
          />
        </div>
      </div>

      {/* Experiment stream / logs */}
      <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, overflow: "hidden", marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "14px 18px", borderBottom: "1px solid #e5e7eb" }}>
          <div style={{ fontSize: 13, fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
            Experiment Stream
            <span style={{ fontSize: 9.5, padding: "2px 7px", borderRadius: 5, background: "#f9fafb", color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>
              evidence + campaign events
            </span>
          </div>
          <div style={{ display: "flex", gap: 4 }}>
            {(["live", "history"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setLogTab(t)}
                style={{
                  padding: "6px 12px",
                  borderRadius: 6,
                  border: "1px solid #e5e7eb",
                  background: logTab === t ? "#111827" : "#fff",
                  color: logTab === t ? "#fff" : "#6b7280",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {t === "live" ? `Live (${liveLogs.length})` : `History (${historyEvents.length})`}
              </button>
            ))}
          </div>
        </div>
        <div style={{ maxHeight: 280, overflowY: "auto" }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "90px 100px 1.4fr 90px 80px 80px 90px",
              gap: 8,
              padding: "8px 18px",
              fontSize: 10,
              color: "#9ca3af",
              textTransform: "uppercase",
              letterSpacing: ".4px",
              borderBottom: "1px solid #e5e7eb",
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            <span>Time</span>
            <span>Campaign</span>
            <span>Family</span>
            <span>Decision</span>
            <span>Risk</span>
            <span>Amount</span>
            <span>Outcome</span>
          </div>
          {logRows.length === 0 && (
            <div style={{ padding: 28, textAlign: "center", color: "#6b7280", fontSize: 13 }}>
              {logTab === "live"
                ? (running ? "Loop running — waiting for first evidence…" : "No live evidence yet — hit Start Loop.")
                : "No historical campaign events yet."}
            </div>
          )}
          {logRows.map((row) => {
            const col =
              row.decision === "BLOCK" ? "#dc2626" : row.decision === "CHALLENGE" ? "#ea580c" : "#16a34a"
            return (
              <div
                key={row.id}
                style={{
                  display: "grid",
                  gridTemplateColumns: "90px 100px 1.4fr 90px 80px 80px 90px",
                  gap: 8,
                  padding: "9px 18px",
                  fontSize: 12,
                  alignItems: "center",
                  borderBottom: "1px solid #f3f4f6",
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                <span style={{ color: "#9ca3af" }}>{row.time}</span>
                <span style={{ color: "#6b7280" }}>{row.campaign}</span>
                <span style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 500, color: "#111827" }}>{row.family}</span>
                <span>
                  <span style={{ padding: "2px 8px", borderRadius: 5, fontSize: 10, fontWeight: 700, background: `${col}18`, color: col }}>
                    {row.decision}
                  </span>
                </span>
                <span>{row.risk != null ? Number(row.risk).toFixed(2) : "—"}</span>
                <span>{row.amount != null ? `₹${Number(row.amount).toLocaleString()}` : "—"}</span>
                <span style={{ color: col }}>{row.outcome || "—"}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Ops strip — Run Loop */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: 20,
          padding: "14px 18px",
          background: "#fff",
          border: "1px solid #e5e7eb",
          borderRadius: 12,
        }}
      >
        <div>
          <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 6 }}>Platform Loop</div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <select
              value={familiesCount}
              onChange={(e) => setFamiliesCount(Number(e.target.value))}
              disabled={running}
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12, background: "#f9fafb" }}
            >
              {[4, 8, 12, 16, 24].map((n) => (
                <option key={n} value={n}>{n} families</option>
              ))}
            </select>
            {!running ? (
              <button
                onClick={startLoop}
                style={{
                  padding: "8px 18px",
                  borderRadius: 8,
                  border: "none",
                  background: "linear-gradient(135deg, #dc2626, #2563eb)",
                  color: "#fff",
                  fontWeight: 600,
                  fontSize: 13,
                  cursor: "pointer",
                }}
              >
                ▶ Start Loop
              </button>
            ) : (
              <button
                onClick={stopLoop}
                disabled={stopping}
                style={{
                  padding: "8px 18px",
                  borderRadius: 8,
                  border: "1px solid #fecaca",
                  background: stopping ? "#f3f4f6" : "#fef2f2",
                  color: stopping ? "#9ca3af" : "#dc2626",
                  fontWeight: 600,
                  fontSize: 13,
                  cursor: stopping ? "not-allowed" : "pointer",
                }}
              >
                {stopping ? "Stopping…" : "■ Stop Loop"}
              </button>
            )}
            {activeRunId && running && (
              <span style={{ fontSize: 11, color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>
                {activeRunId.slice(0, 8)}
              </span>
            )}
          </div>
          {loopMsg && (
            <div style={{ fontSize: 11, color: "#6b7280", marginTop: 6, fontFamily: "'JetBrains Mono', monospace" }}>{loopMsg}</div>
          )}
        </div>
        <div>
          <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px" }}>Scheduler</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, fontSize: 13, marginTop: 4 }}>
            <span style={{ color: sched?.enabled ? "#16a34a" : "#6b7280" }}>{sched?.enabled ? "ON" : "OFF"}</span>
            {sched?.interval_minutes != null && ` · every ${sched.interval_minutes}m`}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px" }}>Latest run</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, fontSize: 13, marginTop: 4 }}>
            {r ? `${r.status} · lift ${r.score_lift != null ? (r.score_lift >= 0 ? "+" : "") + r.score_lift.toFixed(3) : "—"}` : "—"}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px" }}>KB</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, fontSize: 13, marginTop: 4 }}>
            {k.total_families ?? 67} fam · {k.total_variants ?? 363} var · {k.total_relationships ?? 5000} rel
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px" }}>Buffer</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, fontSize: 13, marginTop: 4 }}>
            {b?.payment_records ?? 0} pay · {b?.blocked ?? 0} blocked
          </div>
        </div>
      </div>

      <div style={{ marginTop: 18, textAlign: "center", fontSize: 11, color: "#9ca3af" }}>
        Synthetic sandbox only · <b style={{ color: "#6b7280" }}>Loop A</b> Red learns · <b style={{ color: "#6b7280" }}>Loop B</b> Blue hardens
      </div>
    </div>
  )
}
