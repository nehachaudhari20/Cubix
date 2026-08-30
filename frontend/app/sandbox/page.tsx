"use client"
import { useCallback, useEffect, useMemo, useState } from "react"
import { api, EvidenceRecord, LoopRun, errorText } from "@/lib/api"

const SURFACE_META: Record<string, { label: string; blurb: string }> = {
  payment: { label: "Payment", blurb: "Payment rail — engines → rules+ML → authz" },
  agent: { label: "AI-Agent", blurb: "GenAI → agent engine → rules → risk blend" },
  auth_se: { label: "Social Eng.", blurb: "Voice-phish / SE surface (not payment cycle)" },
  kyc: { label: "KYC", blurb: "Identity / deepfake evidence surface" },
  open_banking: { label: "Open Banking", blurb: "Consent / third-party surface" },
  device: { label: "Device", blurb: "Session integrity surface" },
  network: { label: "Network", blurb: "Cross-stage network surface" },
}

const NON_PAYMENT = new Set(["agent", "auth_se", "kyc", "open_banking", "device", "network"])

function num(v: unknown): number | null {
  if (v == null || v === "") return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function resolveSurface(r: EvidenceRecord | null): string {
  if (!r) return "payment"
  const s = (r.surface || "").toLowerCase()
  if (s && SURFACE_META[s]) return s
  const action = (r.action_type || "").toLowerCase()
  if (action.includes("genai") || action.includes("agent")) return "agent"
  if (action.includes("social")) return "auth_se"
  if (action.includes("kyc")) return "kyc"
  if (action.includes("consent")) return "open_banking"
  if (action.includes("session")) return "device"
  if (action.includes("orchestrate") || action.includes("network")) return "network"
  return "payment"
}

/** Never collapse ML into combined — that made scores look identical. */
function scores(r: EvidenceRecord | null) {
  if (!r) return { combined: null as number | null, rule: null as number | null, ml: null as number | null }
  const f = (r.features || {}) as Record<string, unknown>
  return {
    combined: num(r.risk_score) ?? num(f.risk_score),
    rule: num(r.rule_risk) ?? num(f.rule_risk),
    ml: num(r.ml_score) ?? num(f.ml_score),
  }
}

function amountOf(r: EvidenceRecord | null): number | null {
  if (!r) return null
  // Prefer top-level amount; only fall back to features for payment rows
  // (control-surface features carry a synthetic training default amount).
  const top = num(r.amount)
  if (top != null) return top
  if (resolveSurface(r) === "payment") {
    return num((r.features as any)?.amount)
  }
  return null
}

function hasGenai(r: EvidenceRecord): boolean {
  const f = r.features || {}
  if (f.genai_features || f.genai_context) return true
  if (f.prompt_injection_risk != null || f.agent_goal_anomaly != null) return true
  const surf = resolveSurface(r)
  return surf === "agent" || (r.attack_family || "").toLowerCase().includes("genai")
}

function fmtMoney(n: number | null | undefined) {
  if (n == null) return "—"
  return `₹${Number(n).toLocaleString("en-IN")}`
}

function fmtScore(n: number | null | undefined) {
  if (n == null) return "—"
  return Number(n).toFixed(3)
}

function fmtTime(iso: string | undefined) {
  if (!iso) return "—"
  try {
    return new Date(iso).toLocaleTimeString()
  } catch {
    return "—"
  }
}

function decisionColor(d: string) {
  const u = (d || "").toUpperCase()
  if (u === "BLOCK") return "#dc2626"
  if (u === "CHALLENGE") return "#ea580c"
  if (u === "ALLOW") return "#16a34a"
  return "#6b7280"
}

function pickBestLoop(loops: LoopRun[]): string {
  const usable = loops.filter((r) => r.status === "completed" || r.status === "stopped")
  if (!usable.length) return loops[0]?.id || ""
  const scored = [...usable].sort((a, b) => {
    const liftA = a.score_lift ?? -999
    const liftB = b.score_lift ?? -999
    if (liftB !== liftA) return liftB - liftA
    const prA = a.val_pr_auc ?? -999
    const prB = b.val_pr_auc ?? -999
    if (prB !== prA) return prB - prA
    return String(b.started_at || "").localeCompare(String(a.started_at || ""))
  })
  return scored[0].id
}

function eventsToEvidence(events: any[], loopId: string): EvidenceRecord[] {
  return (events || []).map((e) => ({
    evidence_id: e.id,
    campaign_id: e.loop_run_id || loopId,
    attack_family: e.family_name || e.family_id || "—",
    action_type: e.family_id || "",
    surface: "payment",
    sandbox_decision: e.sandbox_decision || "—",
    evasion_outcome: e.evasion_outcome || "",
    ml_score: e.ml_score ?? null,
    rule_risk: null,
    risk_score: e.ml_score ?? null,
    amount: e.amount ?? null,
    step: e.step ?? null,
    timestamp: e.created_at || "",
    label: null,
    features: {},
    control_triggers: [],
    blocking_control: null,
    is_hard_negative: false,
  }))
}

export default function SandboxPage() {
  const [records, setRecords] = useState<EvidenceRecord[]>([])
  const [allRecords, setAllRecords] = useState<EvidenceRecord[]>([])
  const [buffer, setBuffer] = useState<any>(null)
  const [stages, setStages] = useState<any[]>([])
  const [controls, setControls] = useState<Record<string, string[]> | null>(null)
  const [loops, setLoops] = useState<LoopRun[]>([])
  const [selectedLoop, setSelectedLoop] = useState("")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [filterDecision, setFilterDecision] = useState("")
  const [filterSurface, setFilterSurface] = useState("")
  const [live, setLive] = useState(false)
  const [err, setErr] = useState("")
  const [stageFocus, setStageFocus] = useState("")

  const refresh = useCallback(async () => {
    try {
      const [rec, buf, st, ctrls, running, runList] = await Promise.all([
        api.recent(500).catch(() => []),
        api.buffer().catch(() => null),
        api.stages().catch(() => []),
        api.stageControls().catch(() => null),
        api.running().catch(() => ({ running: false })),
        api.runs(30).catch(() => []),
      ])
      const list = Array.isArray(runList) ? runList : []
      setLoops(list)
      setAllRecords(Array.isArray(rec) ? rec : [])
      setBuffer(buf)
      setStages(Array.isArray(st) ? st : [])
      setControls(ctrls && typeof ctrls === "object" ? ctrls : null)
      setLive(!!running.running)
      setErr("")
      setSelectedLoop((prev) => prev || pickBestLoop(list))
    } catch (e) {
      setErr(errorText(e))
    }
  }, [])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, live ? 1500 : 5000)
    return () => clearInterval(t)
  }, [refresh, live])

  // When a loop is selected (and not live), prefer that loop's campaign events;
  // fall back to buffer rows whose campaign_id matches the loop id.
  useEffect(() => {
    let cancelled = false
    const apply = async () => {
      if (live || !selectedLoop) {
        setRecords(allRecords)
        return
      }
      const matched = allRecords.filter(
        (r) =>
          r.campaign_id === selectedLoop ||
          (r.campaign_id || "").startsWith(selectedLoop.slice(0, 8))
      )
      if (matched.length >= 8) {
        if (!cancelled) setRecords(matched)
        return
      }
      try {
        const detail = await api.run(selectedLoop)
        const fromEvents = eventsToEvidence(detail.events || [], selectedLoop)
        if (!cancelled) setRecords(fromEvents.length ? fromEvents : matched.length ? matched : allRecords)
      } catch {
        if (!cancelled) setRecords(matched.length ? matched : allRecords)
      }
    }
    apply()
    return () => {
      cancelled = true
    }
  }, [selectedLoop, allRecords, live])

  useEffect(() => {
    if (!selectedId && records[0]) setSelectedId(records[0].evidence_id)
    if (selectedId && records.length && !records.find((r) => r.evidence_id === selectedId)) {
      setSelectedId(records[0]?.evidence_id ?? null)
    }
  }, [records, selectedId])

  const selected = records.find((r) => r.evidence_id === selectedId) || records[0] || null
  const sc = scores(selected)
  const surface = resolveSurface(selected)
  const surfMeta = SURFACE_META[surface] || SURFACE_META.payment
  const isSurface = NON_PAYMENT.has(surface)
  const decision = (selected?.sandbox_decision || "").toUpperCase()
  const isBypass = decision === "ALLOW"
  const isChallenge = decision === "CHALLENGE"
  const earlyExit =
    !!(selected?.features as any)?.early_exit ||
    (!!selected &&
      resolveSurface(selected) === "payment" &&
      sc.ml == null &&
      (sc.combined != null || decision === "BLOCK"))
  const genaiOn = selected ? hasGenai(selected) : false

  // Prefer full-buffer surface counts (not just recent window)
  const surfaceCounts = useMemo(() => {
    const fromBuf = buffer?.surfaces && typeof buffer.surfaces === "object" ? buffer.surfaces : null
    if (fromBuf && Object.keys(fromBuf).length) {
      const m: Record<string, number> = {}
      for (const [k, v] of Object.entries(fromBuf)) m[k || "payment"] = Number(v) || 0
      return m
    }
    const m: Record<string, number> = {}
    for (const r of records) {
      const s = resolveSurface(r)
      m[s] = (m[s] || 0) + 1
    }
    return m
  }, [buffer, records])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return records.filter((r) => {
      const surf = resolveSurface(r)
      if (filterDecision && r.sandbox_decision !== filterDecision) return false
      if (filterSurface && surf !== filterSurface) return false
      if (!q) return true
      return `${r.evidence_id} ${r.campaign_id} ${r.attack_family} ${r.action_type} ${surf}`.toLowerCase().includes(q)
    })
  }, [records, search, filterDecision, filterSurface])

  const stageNames = stages.map((s) => s.stage || s.stage_name || s.name).filter(Boolean)
  const controlEntries = useMemo(() => (controls ? Object.entries(controls) : []), [controls])
  const activeStage = stageFocus || stageNames[0] || controlEntries[0]?.[0] || ""
  const focusedControls = useMemo(() => {
    if (!controls) return [] as string[]
    if (activeStage && controls[activeStage]) return controls[activeStage]
    const hit = controlEntries.find(([k]) => k.toLowerCase() === activeStage.toLowerCase())
    return hit ? hit[1] : []
  }, [controls, activeStage, controlEntries])

  const kpis = [
    { label: "Evidence", value: records.length, sub: selectedLoop ? `loop ${selectedLoop.slice(0, 8)}` : `${allRecords.length} buffer` },
    { label: "Blocked", value: records.filter((r) => r.sandbox_decision === "BLOCK").length, sub: "in view" },
    { label: "Bypassed", value: records.filter((r) => r.sandbox_decision === "ALLOW" || r.evasion_outcome === "bypassed").length, sub: "in view" },
    {
      label: "Surfaces w/ data",
      value: Object.values(surfaceCounts).filter((n) => n > 0).length,
      sub: `${Object.keys(SURFACE_META).length} catalogued`,
    },
  ]

  const loopOptions = useMemo(
    () => loops.filter((r) => r.status === "completed" || r.status === "stopped" || r.status === "failed"),
    [loops]
  )

  return (
    <div style={{ padding: "22px 28px 48px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap", marginBottom: 18 }}>
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".6px", color: "#6b7280", fontWeight: 500 }}>Sandbox</div>
          <h1 style={{ margin: "4px 0 4px", fontSize: 22, fontWeight: 700 }}>Payment Defense Twin</h1>
          <p style={{ margin: 0, color: "#6b7280", fontSize: 13, maxWidth: 720 }}>
            Evidence from every surface — payment, agent, social engineering, KYC, consent, device, network.
            Click a row to load its scores. Combined risk ≠ ML; both run on every surface when FraudShield is loaded.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <select
            value={selectedLoop}
            onChange={(e) => setSelectedLoop(e.target.value)}
            disabled={live}
            style={{
              padding: "8px 12px",
              borderRadius: 8,
              border: "1px solid #e5e7eb",
              background: live ? "#f3f4f6" : "#f9fafb",
              fontSize: 12,
              minWidth: 260,
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            {loopOptions.length === 0 && <option value="">No loop runs yet</option>}
            {loopOptions.map((r) => (
              <option key={r.id} value={r.id}>
                {r.id.slice(0, 8)} · {r.status} · lift {r.score_lift != null ? r.score_lift.toFixed(3) : "—"}
                {r.val_pr_auc != null ? ` · PR ${r.val_pr_auc.toFixed(3)}` : ""}
              </option>
            ))}
          </select>
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
                background: live ? "#16a34a" : "#9ca3af",
                boxShadow: live ? "0 0 8px #16a34a" : "none",
              }}
            />
            {live ? "LIVE · loop feeding evidence" : "IDLE · selected loop"}
          </span>
        </div>
      </div>

      {err && (
        <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 12, color: "#dc2626" }}>
          {err}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
        {kpis.map((k) => (
          <div key={k.label} style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: "14px 16px", borderTop: "3px solid #2563eb" }}>
            <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".5px", color: "#6b7280" }}>{k.label}</div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 700, margin: "4px 0 2px" }}>{k.value}</div>
            <div style={{ fontSize: 11, color: "#6b7280" }}>{k.sub}</div>
          </div>
        ))}
      </div>

      {/* Surface chips — counts from full buffer */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
        {Object.entries(SURFACE_META).map(([id, meta]) => {
          const count = surfaceCounts[id] || 0
          const active = filterSurface === id
          return (
            <button
              key={id}
              onClick={() => setFilterSurface(active ? "" : id)}
              title={meta.blurb}
              style={{
                padding: "6px 10px",
                borderRadius: 8,
                border: active ? "1px solid #2563eb" : "1px solid #e5e7eb",
                background: active ? "#eff6ff" : count ? "#fff" : "#f9fafb",
                cursor: "pointer",
                fontSize: 11,
                opacity: count ? 1 : 0.65,
              }}
            >
              <span style={{ fontWeight: 600, color: active ? "#2563eb" : "#111827" }}>{meta.label}</span>
              <span style={{ color: "#6b7280", marginLeft: 6, fontFamily: "'JetBrains Mono', monospace" }}>{count}</span>
            </button>
          )
        })}
      </div>

      {/* Selected evidence detail — bound to selectedId; cards update on row click */}
      <div
        key={selected?.evidence_id || "empty"}
        style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginBottom: 16 }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 11, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px" }}>Selected evidence</div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 14, fontWeight: 600, marginTop: 4 }}>
              {selected ? selected.evidence_id : "—"}
              {selected && (
                <span style={{ fontWeight: 400, color: "#6b7280" }}>
                  {" "}
                  · {selected.campaign_id || "—"} · {selected.attack_family || "—"}
                </span>
              )}
            </div>
            {selected && (
              <div style={{ marginTop: 4, fontSize: 12, color: "#4b5563" }}>
                {selected.action_type || "—"} · step {selected.step ?? "—"} · {fmtTime(selected.timestamp)}
              </div>
            )}
            <div style={{ marginTop: 6, display: "flex", gap: 6, flexWrap: "wrap" }}>
              <span
                style={{
                  padding: "2px 8px",
                  borderRadius: 5,
                  background: isSurface ? "#f5f3ff" : "#eff6ff",
                  color: isSurface ? "#7c3aed" : "#2563eb",
                  fontWeight: 600,
                  fontSize: 11,
                }}
              >
                {surfMeta.label}
              </span>
              {genaiOn && (
                <span style={{ padding: "2px 8px", borderRadius: 5, background: "#f5f3ff", color: "#7c3aed", fontWeight: 600, fontSize: 11 }}>
                  GenAI context
                </span>
              )}
              {earlyExit && (
                <span style={{ padding: "2px 8px", borderRadius: 5, background: "#fef2f2", color: "#dc2626", fontWeight: 600, fontSize: 11 }}>
                  Early exit (pre-ML)
                </span>
              )}
            </div>
          </div>
          {selected && (
            <span
              style={{
                padding: "6px 14px",
                borderRadius: 8,
                fontWeight: 700,
                fontSize: 13,
                background: `${decisionColor(decision)}18`,
                color: decisionColor(decision),
                border: `1px solid ${decisionColor(decision)}44`,
              }}
            >
              {decision || "—"}
            </span>
          )}
        </div>

        {!selected ? (
          <div style={{ color: "#6b7280", fontSize: 13 }}>No evidence — run a loop or campaign.</div>
        ) : (
          <>
            {(isBypass || isChallenge) && (
              <div
                style={{
                  marginBottom: 14,
                  padding: "12px 14px",
                  borderRadius: 10,
                  background: isBypass ? "#fef2f2" : "#fff7ed",
                  border: `1px solid ${isBypass ? "#fecaca" : "#fed7aa"}`,
                }}
              >
                <div style={{ fontSize: 12, fontWeight: 700, color: isBypass ? "#dc2626" : "#ea580c", marginBottom: 4 }}>
                  {isBypass ? "Bypass — feeds Blue Team buffer" : "Challenge — step-up signal"}
                </div>
                <div style={{ fontSize: 12, color: "#4b5563", lineHeight: 1.5 }}>
                  {surfMeta.blurb}. Outcome={selected.evasion_outcome || "—"}.
                  {selected.blocking_control ? ` Blocking control: ${selected.blocking_control}.` : ""}
                </div>
              </div>
            )}

            {/* Distinct score cards — values from the selected row */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                gap: 8,
                marginBottom: 14,
              }}
            >
              {[
                {
                  l: "Combined risk",
                  v: fmtScore(sc.combined),
                  hint: sc.combined == null ? "Missing on this buffer row" : "risk_score used for decision",
                  c: sc.combined == null ? "#9ca3af" : decisionColor(decision),
                },
                {
                  l: "Rule risk",
                  v: fmtScore(sc.rule),
                  hint: sc.rule == null ? "No rule contribution stored" : "KB rules / early-exit",
                  c: "#111827",
                },
                {
                  l: "ML score",
                  v: fmtScore(sc.ml),
                  hint:
                    sc.ml == null
                      ? earlyExit
                        ? "Blocked before RiskEngine/ML"
                        : "No ML on this record (re-run after surface ML wiring)"
                      : isSurface
                        ? "FraudShield (control-surface features)"
                        : "FraudShield probability",
                  c: sc.ml == null ? "#9ca3af" : "#111827",
                },
                isSurface
                  ? {
                      l: "Surface risk",
                      v: fmtScore(
                        num((selected.features as any)?.surface_risk) ??
                          num((selected.features as any)?.agent_risk) ??
                          num((selected.features as any)?.auth_se_risk) ??
                          num((selected.features as any)?.kyc_risk) ??
                          num((selected.features as any)?.consent_risk) ??
                          num((selected.features as any)?.session_risk) ??
                          num((selected.features as any)?.network_risk)
                      ),
                      hint: selected.action_type || "non-payment",
                      c: "#111827",
                    }
                  : {
                      l: "Amount",
                      v: fmtMoney(amountOf(selected)),
                      hint: selected.action_type || "payment",
                      c: "#111827",
                    },
              ].map((m) => (
                <div key={m.l} style={{ padding: 10, background: "#f9fafb", borderRadius: 8, border: "1px solid #e5e7eb" }}>
                  <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase" }}>{m.l}</div>
                  <div style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, fontSize: 15, color: m.c }}>{m.v}</div>
                  <div style={{ fontSize: 10, color: "#9ca3af", marginTop: 2, lineHeight: 1.35 }}>{m.hint}</div>
                </div>
              ))}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div>
                <div style={{ fontSize: 11, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 8 }}>
                  What happened
                </div>
                <div style={{ fontSize: 12, color: "#374151", lineHeight: 1.55 }}>
                  {isSurface ? (
                    <>
                      Non-payment surface <strong>{surfMeta.label}</strong>: GenAI → surface engine → KB rules → FraudShield ML →
                      blended <code>risk_score</code>.
                    </>
                  ) : (
                    <>
                      Payment adjudication for <strong>{selected.action_type}</strong>
                      {genaiOn ? " with GenAI features folded into risk" : ""}.
                      {earlyExit
                        ? " Engine failed early — ML never ran, so ML stays empty."
                        : " Full path ran RiskEngine (rules + ML) then Authorization."}
                    </>
                  )}
                </div>
                <div style={{ marginTop: 10, fontSize: 11, color: "#6b7280" }}>
                  Evasion {selected.evasion_outcome || "—"} · label {selected.label ?? "—"}
                  {!isSurface && amountOf(selected) != null ? ` · ${fmtMoney(amountOf(selected))}` : ""}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 11, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 6 }}>
                  Controls triggered
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, minHeight: 28 }}>
                  {(selected.control_triggers || []).length ? (
                    selected.control_triggers.map((c, i) => (
                      <span
                        key={`${c}-${i}`}
                        style={{
                          fontSize: 11,
                          padding: "4px 8px",
                          borderRadius: 6,
                          background: "#fff7ed",
                          border: "1px solid #fed7aa",
                          color: "#c2410c",
                          fontFamily: "'JetBrains Mono', monospace",
                        }}
                      >
                        {c}
                      </span>
                    ))
                  ) : (
                    <span style={{ fontSize: 12, color: "#9ca3af" }}>{isBypass ? "None — gap" : "None listed"}</span>
                  )}
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.65fr 1fr", gap: 16 }}>
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, overflow: "hidden" }}>
          <div style={{ padding: "14px 16px", borderBottom: "1px solid #e5e7eb", display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>
              Evidence <span style={{ fontWeight: 400, color: "#6b7280", fontSize: 11 }}>{filtered.length}</span>
            </div>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search…"
              style={{ flex: 1, minWidth: 140, padding: "7px 10px", borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12 }}
            />
            <select
              value={filterDecision}
              onChange={(e) => setFilterDecision(e.target.value)}
              style={{ padding: "7px 10px", borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12, background: "#f9fafb" }}
            >
              <option value="">All decisions</option>
              <option value="BLOCK">BLOCK</option>
              <option value="CHALLENGE">CHALLENGE</option>
              <option value="ALLOW">ALLOW</option>
            </select>
            <select
              value={filterSurface}
              onChange={(e) => setFilterSurface(e.target.value)}
              style={{ padding: "7px 10px", borderRadius: 8, border: "1px solid #e5e7eb", fontSize: 12, background: "#f9fafb" }}
            >
              <option value="">All surfaces</option>
              {Object.entries(SURFACE_META).map(([id, meta]) => (
                <option key={id} value={id}>
                  {meta.label} ({surfaceCounts[id] || 0})
                </option>
              ))}
            </select>
          </div>
          <div style={{ maxHeight: 440, overflow: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, tableLayout: "fixed" }}>
              <thead>
                <tr style={{ background: "#f9fafb", textAlign: "left" }}>
                  {(
                    [
                      ["Time", "12%"],
                      ["Family", "22%"],
                      ["Surface", "14%"],
                      ["Decision", "14%"],
                      ["Risk", "12%"],
                      ["ML", "12%"],
                      ["Amt", "14%"],
                    ] as const
                  ).map(([h, w]) => (
                    <th
                      key={h}
                      style={{
                        width: w,
                        padding: "8px 8px",
                        fontSize: 10,
                        color: "#6b7280",
                        fontWeight: 600,
                        textTransform: "uppercase",
                        borderBottom: "1px solid #e5e7eb",
                        position: "sticky",
                        top: 0,
                        background: "#f9fafb",
                        zIndex: 1,
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => {
                  const active = r.evidence_id === selected?.evidence_id
                  const surf = resolveSurface(r)
                  const s = scores(r)
                  const amt = amountOf(r)
                  return (
                    <tr
                      key={r.evidence_id}
                      onClick={() => setSelectedId(r.evidence_id)}
                      style={{ cursor: "pointer", background: active ? "#eff6ff" : "#fff", borderBottom: "1px solid #f3f4f6" }}
                    >
                      <td style={{ padding: "9px 8px", fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: "#6b7280" }}>
                        {fmtTime(r.timestamp)}
                      </td>
                      <td style={{ padding: "9px 8px", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {r.attack_family}
                      </td>
                      <td style={{ padding: "9px 8px" }}>
                        <span
                          style={{
                            fontSize: 10,
                            padding: "2px 6px",
                            borderRadius: 4,
                            background: NON_PAYMENT.has(surf) ? "#f5f3ff" : "#eff6ff",
                            color: NON_PAYMENT.has(surf) ? "#7c3aed" : "#2563eb",
                            fontFamily: "'JetBrains Mono', monospace",
                          }}
                        >
                          {surf}
                        </span>
                      </td>
                      <td style={{ padding: "9px 8px" }}>
                        <span
                          style={{
                            padding: "2px 8px",
                            borderRadius: 5,
                            fontSize: 10,
                            fontWeight: 700,
                            background: `${decisionColor(r.sandbox_decision)}18`,
                            color: decisionColor(r.sandbox_decision),
                          }}
                        >
                          {r.sandbox_decision}
                        </span>
                      </td>
                      <td style={{ padding: "9px 8px", fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: s.combined == null ? "#9ca3af" : "#111827" }}>
                        {fmtScore(s.combined)}
                      </td>
                      <td style={{ padding: "9px 8px", fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: s.ml == null ? "#9ca3af" : "#111827" }}>
                        {fmtScore(s.ml)}
                      </td>
                      <td style={{ padding: "9px 8px", fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: amt == null ? "#9ca3af" : "#111827" }}>
                        {amt == null ? "—" : fmtMoney(amt)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {!filtered.length && (
              <div style={{ padding: 28, textAlign: "center", color: "#6b7280", fontSize: 13 }}>
                No rows for this filter. Try another surface — counts above use the full buffer.
              </div>
            )}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Why scores differ</div>
            <div style={{ fontSize: 11, color: "#4b5563", lineHeight: 1.55 }}>
              <strong>Combined risk</strong> = <code>risk_score</code> (decision input).
              <br />
              <strong>Rule risk</strong> = KB / engine rules.
              <br />
              <strong>ML</strong> = FraudShield. Surfaces use control-surface features; payments use RiskEngine. Early payment BLOCKs and older buffer rows may show —.
              <br />
              <strong>Amount</strong> is payment-only (many campaigns reuse ₹45,000). Surfaces show surface risk in the detail card instead.
            </div>
          </div>

          <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>KB stages</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, maxHeight: 110, overflow: "auto" }}>
              {(stageNames.length ? stageNames : controlEntries.map(([k]) => k)).map((name) => (
                <button
                  key={name}
                  onClick={() => setStageFocus(name)}
                  style={{
                    fontSize: 11,
                    padding: "5px 9px",
                    borderRadius: 6,
                    border: activeStage === name ? "1px solid #2563eb" : "1px solid #e5e7eb",
                    background: activeStage === name ? "#eff6ff" : "#f9fafb",
                    color: activeStage === name ? "#2563eb" : "#374151",
                    cursor: "pointer",
                    fontWeight: activeStage === name ? 600 : 400,
                  }}
                >
                  {name}
                </button>
              ))}
            </div>
          </div>

          <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 16, flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Controls · {activeStage || "—"}</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, maxHeight: 200, overflow: "auto" }}>
              {focusedControls.slice(0, 40).map((c) => (
                <span
                  key={c}
                  style={{
                    fontSize: 10,
                    padding: "4px 7px",
                    borderRadius: 5,
                    fontFamily: "'JetBrains Mono', monospace",
                    background: "#f9fafb",
                    border: "1px solid #e5e7eb",
                    color: "#4b5563",
                  }}
                >
                  {c}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
