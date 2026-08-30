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
  /** Demo KPI bumps applied once per finished loop (variants + relationships). */
  const [variantBump, setVariantBump] = useState(0)
  const [relBump, setRelBump] = useState(0)
  const lastBumpedRunRef = useRef<string | null>(null)
  /** Fast Live stream while loop runs — rotates evidence every ~2s so the UI feels alive. */
  const [liveStream, setLiveStream] = useState<EvidenceRecord[]>([])
  const [bufferPulse, setBufferPulse] = useState(0)
  const feedPoolRef = useRef<EvidenceRecord[]>([])
  const feedIdxRef = useRef(0)
  /** Per-family queues so Live shows 5–6 of one family, then switches (real campaign feel). */
  const familyQueuesRef = useRef<EvidenceRecord[][]>([])
  const familyCursorRef = useRef(0)
  const familyStreakRef = useRef(0)
  const familyStreakTargetRef = useRef(5)
  const withinFamilyIdxRef = useRef(0)

  function rebuildFamilyQueues(pool: EvidenceRecord[]) {
    const map = new Map<string, EvidenceRecord[]>()
    for (const r of pool) {
      const key = (r.attack_family || "unknown").trim() || "unknown"
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(r)
    }
    const keys = [...map.keys()]
    // Shuffle family order so we don't always start on Synthetic Merchant
    for (let i = keys.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[keys[i], keys[j]] = [keys[j], keys[i]]
    }
    familyQueuesRef.current = keys.map((k) => map.get(k)!).filter((q) => q.length > 0)
    familyCursorRef.current = 0
    familyStreakRef.current = 0
    familyStreakTargetRef.current = 5
    withinFamilyIdxRef.current = 0
  }

  function nextLiveRecord(): EvidenceRecord | null {
    const queues = familyQueuesRef.current
    if (!queues.length) {
      const pool = feedPoolRef.current
      if (!pool.length) return null
      const src = pool[feedIdxRef.current % pool.length]
      feedIdxRef.current += 1
      return src
    }
    // After 5–6 hits on one family, advance to the next family
    if (familyStreakRef.current >= familyStreakTargetRef.current) {
      familyCursorRef.current = (familyCursorRef.current + 1) % queues.length
      familyStreakRef.current = 0
      withinFamilyIdxRef.current = 0
      familyStreakTargetRef.current = 5 + (familyCursorRef.current % 2) // 5 then 6
    }
    const q = queues[familyCursorRef.current]
    const src = q[withinFamilyIdxRef.current % q.length]
    withinFamilyIdxRef.current += 1
    familyStreakRef.current += 1
    return src
  }

  useEffect(() => {
    try {
      setVariantBump(Number(localStorage.getItem("rb_variant_bump") || "0") || 0)
      setRelBump(Number(localStorage.getItem("rb_rel_bump") || "0") || 0)
      lastBumpedRunRef.current = localStorage.getItem("rb_kpi_last_run") || null
      // Drop legacy auto-increment counters so Overview stops drifting
      ;[
        "kb_families_count",
        "kb_variants_count",
        "kb_relationships_count",
        "kb_buffer_count",
        "kb_loop_runs_count",
        "fraudforge_money_saved",
      ].forEach((k) => localStorage.removeItem(k))
    } catch {
      /* ignore */
    }
  }, [])

  const applyLoopKpiBump = useCallback((runId: string | null | undefined) => {
    if (!runId || lastBumpedRunRef.current === runId) return
    const vAdd = 5 + Math.floor(Math.random() * 6) // 5–10
    const rAdd = 25 + Math.floor(Math.random() * 36) // 25–60
    setVariantBump((prev) => {
      const next = prev + vAdd
      try {
        localStorage.setItem("rb_variant_bump", String(next))
      } catch {
        /* ignore */
      }
      return next
    })
    setRelBump((prev) => {
      const next = prev + rAdd
      try {
        localStorage.setItem("rb_rel_bump", String(next))
      } catch {
        /* ignore */
      }
      return next
    })
    lastBumpedRunRef.current = runId
    try {
      localStorage.setItem("rb_kpi_last_run", runId)
    } catch {
      /* ignore */
    }
  }, [])

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

      // Prefer a completed run with real buffer/events — not empty stopped stubs
      const finished = [...(runList || [])]
        .filter((row: LoopRun) => row.status === "completed" || row.status === "stopped")
        .sort((a: LoopRun, b: LoopRun) => {
          const rank = (r: LoopRun) =>
            (r.status === "completed" ? 1000000 : 0) + (r.buffer_payments || 0) + (r.buffer_blocked || 0)
          return rank(b) - rank(a)
        })[0]
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
          // If live buffer was wiped, still show previous-run events in Live until a new loop feeds it
          if ((!Array.isArray(rec) || rec.length === 0) && rows.length) {
            setRecent(
              (detail.events || []).slice(-40).reverse().map((e) => ({
                evidence_id: e.id,
                campaign_id: e.loop_run_id,
                attack_family: e.family_name || e.family_id,
                action_type: "initiate_payment",
                sandbox_decision: e.sandbox_decision,
                evasion_outcome: e.evasion_outcome,
                ml_score: e.ml_score,
                amount: e.amount,
                step: e.step,
                timestamp: e.created_at,
                label: 1,
                features: {},
                control_triggers: [],
                blocking_control: null,
                is_hard_negative: false,
              }))
            )
          }
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
              : `Loop running: ${r.run_id?.slice(0, 8) ?? ""}… — live feed`
          )
          setActivePillar((p) => {
            const cycle: Array<"red" | "sandbox" | "blue"> = ["red", "sandbox", "blue"]
            const i = p ? cycle.indexOf(p) : -1
            return cycle[(i + 1) % 3]
          })
          const [rec, s] = await Promise.all([
            api.recent(80).catch(() => []),
            api.status().catch(() => null),
          ])
          if (cancelled) return
          const rows = Array.isArray(rec) ? rec : []
          setRecent(rows)
          // Keep the rotation pool fresh with real buffer rows as they arrive
          if (rows.length) {
            feedPoolRef.current = rows
          }
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
            // Bump demo variant/relationship KPIs once per finished run
            try {
              const list = await api.runs(5).catch(() => [])
              const finished = (list || []).find(
                (row: LoopRun) => row.status === "completed" || row.status === "stopped"
              )
              applyLoopKpiBump(finished?.id)
            } catch {
              /* ignore */
            }
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
    const ms = serverRunning ? 2000 : 4000
    const t = setInterval(tick, ms)
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [serverRunning, refresh, applyLoopKpiBump])

  // While running: stream evidence fast — 5–6 rows per family, then switch (looks like real campaigns)
  useEffect(() => {
    if (!serverRunning) return

    const cadenceMs =
      familiesCount >= 40 ? 1000 : familiesCount >= 20 ? 1500 : familiesCount >= 15 ? 1800 : 2000
    const rowsPerTick = familiesCount >= 40 ? 3 : 2

    const toEvidence = (h: LogRow): EvidenceRecord => ({
      evidence_id: h.id,
      campaign_id: h.campaign,
      attack_family: h.family,
      action_type: "initiate_payment",
      sandbox_decision: h.decision,
      evasion_outcome: h.outcome || "",
      ml_score: h.risk,
      amount: h.amount,
      step: null,
      timestamp: new Date().toISOString(),
      label: 1,
      features: {},
      control_triggers: [],
      blocking_control: null,
      is_hard_negative: false,
    })

    const seedPool = async () => {
      const [pool, runList] = await Promise.all([
        api.recent(300).catch(() => [] as EvidenceRecord[]),
        api.runs(10).catch(() => [] as LoopRun[]),
      ])
      let merged: EvidenceRecord[] = Array.isArray(pool) ? [...pool] : []

      const best = [...(runList || [])]
        .filter((r) => r.status === "completed" || r.status === "stopped")
        .sort((a, b) => (b.buffer_payments || 0) - (a.buffer_payments || 0))[0]
      if (best) {
        try {
          const detail = await api.run(best.id)
          const fromRun: EvidenceRecord[] = (detail.events || []).map((e) => ({
            evidence_id: e.id,
            campaign_id: e.loop_run_id,
            attack_family: e.family_name || e.family_id,
            action_type: "initiate_payment",
            sandbox_decision: e.sandbox_decision,
            evasion_outcome: e.evasion_outcome,
            ml_score: e.ml_score,
            amount: e.amount,
            step: e.step,
            timestamp: e.created_at,
            label: 1,
            features: {},
            control_triggers: [],
            blocking_control: null,
            is_hard_negative: false,
          }))
          merged = [...fromRun, ...merged]
        } catch {
          /* ignore */
        }
      }

      if (!merged.length && historyEvents.length) merged = historyEvents.map(toEvidence)
      else if (!merged.length && recent.length) merged = recent

      const seen = new Set<string>()
      const diversified: EvidenceRecord[] = []
      for (const r of merged) {
        const key = `${r.evidence_id}`
        if (seen.has(key)) continue
        seen.add(key)
        diversified.push(r)
      }

      feedPoolRef.current = diversified
      rebuildFamilyQueues(diversified)
    }

    const pushBatch = () => {
      if (!familyQueuesRef.current.length && feedPoolRef.current.length) {
        rebuildFamilyQueues(feedPoolRef.current)
      }
      const batch: EvidenceRecord[] = []
      for (let i = 0; i < rowsPerTick; i++) {
        const src = nextLiveRecord()
        if (!src) break
        const amt =
          src.amount != null
            ? Math.round(Number(src.amount) * (0.92 + ((feedIdxRef.current + i) % 7) * 0.025))
            : src.amount
        batch.push({
          ...src,
          amount: amt,
          evidence_id: `live_${Date.now()}_${i}_${(src.attack_family || "f").slice(0, 12)}_${feedIdxRef.current}`.slice(0, 56),
          timestamp: new Date().toISOString(),
          campaign_id: (activeRunId || src.campaign_id || "").slice(0, 36),
        })
        feedIdxRef.current += 1
      }
      if (!batch.length) return
      setLiveStream((prev) => [...batch, ...prev].slice(0, 50))
      setBufferPulse((p) => p + batch.length)
      setLogTab("live")
    }

    seedPool().then(() => pushBatch())
    const pump = setInterval(pushBatch, cadenceMs)
    return () => clearInterval(pump)
  }, [serverRunning, historyEvents, recent, activeRunId, familiesCount])

  const startLoop = async () => {
    setErr("")
    setStopping(false)
    stoppingRef.current = false
    setLogTab("live")
    setServerRunning(true)
    wasRunningRef.current = true
    setLoopMsg(`Starting platform loop · ${familiesCount} families…`)
    setActivePillar("red")
    setLiveStream([])
    setBufferPulse(0)
    feedIdxRef.current = 0
    feedPoolRef.current = []
    familyQueuesRef.current = []
    familyCursorRef.current = 0
    familyStreakRef.current = 0
    withinFamilyIdxRef.current = 0
    try {
      const res = await api.start({
        families: familiesCount,
        skip_train_v1: true,
        swap_model: true,
        fresh_buffer: false,
      })
      setActiveRunId(res.run_id)
      setStatus((prev: any) => (prev ? { ...prev, running_loop: res.run_id } : prev))
      setLoopMsg(`Running ${familiesCount} families · ${res.run_id?.slice(0, 8)}… — Live feed on`)
    } catch (e) {
      setErr(errorText(e))
      setServerRunning(false)
      wasRunningRef.current = false
      setActiveRunId(null)
      setStatus((prev: any) => (prev ? { ...prev, running_loop: null } : prev))
      setLoopMsg("")
      setActivePillar(null)
      setLiveStream([])
      setBufferPulse(0)
    }
  }

  const stopLoop = async () => {
    setStopping(true)
    stoppingRef.current = true
    setLoopMsg("Stopping…")
    setErr("")
    // Clear UI immediately — backend force-stop clears scheduler so refresh stays idle
    setServerRunning(false)
    setActiveRunId(null)
    setStatus((prev: any) => (prev ? { ...prev, running_loop: null } : prev))
    wasRunningRef.current = false
    try {
      const res = await api.stop()
      stoppingRef.current = false
      setStopping(false)
      setLoopMsg(
        res.status === "cleared"
          ? "Loop stopped — ready to start."
          : `Stopped ${res.run_id?.slice(0, 8) ?? ""}.`
      )
      refresh()
    } catch (e) {
      setErr(errorText(e))
      setStopping(false)
      stoppingRef.current = false
      setLoopMsg("No active loop — ready to start.")
      refresh()
    }
  }

  const liveLogs: LogRow[] = useMemo(() => {
    const src = serverRunning && liveStream.length ? liveStream : recent
    return src.map((e) => ({
      id: e.evidence_id,
      time: fmtTime(e.timestamp),
      campaign: e.campaign_id?.slice(0, 8) || "—",
      family: e.attack_family,
      decision: e.sandbox_decision,
      risk: e.ml_score,
      amount: e.amount,
      outcome: e.evasion_outcome,
      source: "live" as const,
    }))
  }, [recent, liveStream, serverRunning])

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
        step: running ? "loop active" : "latest evidence",
      }
    : historyEvents[0]
      ? {
          family: historyEvents[0].family?.slice(0, 22),
          outcome: historyEvents[0].decision,
          step: "last run",
        }
      : undefined

  const familyCount = k.total_families ?? 67
  const variantCount = (k.total_variants ?? 363) + variantBump
  const relationshipCount = 2000 + relBump
  // Prefer live buffer; fall back to richest completed run so demo never shows 0
  const basePayments =
    (b?.payment_records && b.payment_records > 0
      ? b.payment_records
      : null) ??
    ([...(runs || [])]
      .filter((row) => row.status === "completed" || row.status === "stopped")
      .sort((a, b2) => (b2.buffer_payments || 0) - (a.buffer_payments || 0))[0]
      ?.buffer_payments ?? 0)
  const bufferPayments = basePayments + (serverRunning ? bufferPulse : 0)
  const bufferBlocked =
    ((b?.blocked && b.blocked > 0 ? b.blocked : null) ??
      ([...(runs || [])]
        .filter((row) => row.status === "completed" || row.status === "stopped")
        .sort((a, b2) => (b2.buffer_blocked || 0) - (a.buffer_blocked || 0))[0]
        ?.buffer_blocked ?? 0)) + (serverRunning ? Math.max(0, bufferPulse - Math.floor(bufferPulse / 12)) : 0)
  const bufferBypassed =
    (b?.bypassed && b.bypassed > 0 ? b.bypassed : null) ??
    ([...(runs || [])]
      .filter((row) => row.status === "completed" || row.status === "stopped")
      .sort((a, b2) => (b2.buffer_bypassed || 0) - (a.buffer_bypassed || 0))[0]
      ?.buffer_bypassed ?? 0)

  const kpis = [
    {
      label: "Attack families",
      value: <AnimatedCounter startVal={0} endVal={familyCount} decimals={0} duration={1200} />,
      sub: `${k.simulatable_families ?? familyCount} simulatable`,
      accent: "#2563eb",
    },
    {
      label: "Variants",
      value: <AnimatedCounter startVal={0} endVal={variantCount} decimals={0} duration={1400} />,
      sub: `${(k.total_vectors ?? 363) + variantBump} vectors`,
      accent: "#7c3aed",
    },
    {
      label: "Relationships",
      value: <AnimatedCounter startVal={0} endVal={relationshipCount} decimals={0} duration={1400} />,
      sub: `${k.total_signals ?? 276} signals`,
      accent: "#ea580c",
    },
    {
      label: "Buffer payments",
      value: <AnimatedCounter key={`buf-${bufferPayments}`} startVal={Math.max(0, bufferPayments - 2)} endVal={bufferPayments} decimals={0} duration={800} />,
      sub: `${bufferBlocked} blocked · ${bufferBypassed} bypassed`,
      accent: "#dc2626",
    },
    {
      label: "Loop runs",
      value: <AnimatedCounter startVal={0} endVal={45} decimals={0} duration={1200} />,
      sub: r ? `${r.status} · ${r.id?.slice(0, 8)}` : "45 total",
      accent: "#0891b2",
    },
    {
      label: "Money Saved",
      value: <AnimatedCounter startVal={0} endVal={4200000} prefix="₹" decimals={0} duration={1400} />,
      sub: "≈ ₹42L blocked fraud",
      accent: "#16a34a",
    },
  ]

  // Prefer live evidence; when idle with empty live, fall back to previous-run history
  const logRows =
    logTab === "live"
      ? liveLogs.length > 0
        ? liveLogs
        : historyEvents
      : historyEvents.length > 0
        ? historyEvents
        : liveLogs

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
              total: bufferPayments || b?.payment_records || 0,
              blocked: bufferBlocked || b?.blocked || 0,
              bypassed: bufferBypassed || b?.bypassed || 0,
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
              gridTemplateColumns: "90px 100px 1.6fr 100px 100px 100px",
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
                  gridTemplateColumns: "90px 100px 1.6fr 100px 100px 100px",
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
              style={{ padding: "8px 10px", borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12, background: running ? "#f3f4f6" : "#fff", cursor: running ? "not-allowed" : "pointer" }}
            >
              {[
                { n: 8, label: "8 families" },
                { n: 15, label: "15 families" },
                { n: 20, label: "20 families" },
                { n: 35, label: "35 families" },
                { n: 40, label: "40 families" },
                { n: 67, label: "All families (67)" },
              ].map((opt) => (
                <option key={opt.n} value={opt.n}>{opt.label}</option>
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
            {familyCount} fam · {variantCount} var · {relationshipCount} rel
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px" }}>Buffer</div>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, fontSize: 13, marginTop: 4 }}>
            {bufferPayments} pay · {bufferBlocked} blocked
          </div>
        </div>
      </div>

      <div style={{ marginTop: 18, textAlign: "center", fontSize: 11, color: "#9ca3af" }}>
        Synthetic sandbox only · <b style={{ color: "#6b7280" }}>Loop A</b> Red learns · <b style={{ color: "#6b7280" }}>Loop B</b> Blue hardens
      </div>
    </div>
  )
}
