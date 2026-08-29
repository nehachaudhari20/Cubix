"use client"
import { useEffect, useMemo, useState } from "react"
import { api } from "@/lib/api"

function fmtPct(v: number | null | undefined, digits = 1) {
  if (v == null || !Number.isFinite(Number(v))) return "—"
  return `${(Number(v) * 100).toFixed(digits)}%`
}

function fmt(v: number | null | undefined, digits = 3) {
  if (v == null || !Number.isFinite(Number(v))) return "—"
  return Number(v).toFixed(digits)
}

type CtrlMeta = { control_id: string; name: string; lifecycle_stage_ids?: string[] }

function controlLabel(id: string, catalog: Record<string, CtrlMeta>) {
  const clean = String(id || "").replace(/^gap_/, "")
  const meta = catalog[clean]
  if (meta?.name) return { id: clean, name: meta.name }
  return { id: clean, name: clean }
}

function familyKeys(data: any): string[] {
  const triggered = Object.keys(data?.families_triggered || {})
  const missed = Object.keys(data?.families_missed || {})
  const gapped = Object.keys(data?.families_gapped || {}).filter((k) => k !== "expected" && !/^\d+$/.test(k))
  return Array.from(new Set([...triggered, ...missed, ...gapped]))
}

export default function LabsPage() {
  const [runs, setRuns] = useState<any[]>([])
  const [selectedRun, setSelectedRun] = useState("")
  const [failureData, setFailureData] = useState<any>(null)
  const [evalData, setEvalData] = useState<any>(null)
  const [catalog, setCatalog] = useState<Record<string, CtrlMeta>>({})
  const [bypassEvidence, setBypassEvidence] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState("")
  const [expandedGap, setExpandedGap] = useState<number | null>(0)

  useEffect(() => {
    Promise.all([
      api.runs(30).catch(() => []),
      api.controlsCatalog().catch(() => ({ controls: {} })),
    ]).then(([r, cat]) => {
      const completed = (r || []).filter((run: any) => run.status === "completed")
      setRuns(completed)
      if (completed.length) setSelectedRun(completed[0].id)
      setCatalog(cat?.controls || {})
      setLoading(false)
    })
  }, [])

  useEffect(() => {
    if (!selectedRun) return
    setLoadErr("")
    Promise.all([
      api.failure(selectedRun).catch((e) => {
        setLoadErr(e.message || "Failure analysis unavailable")
        return null
      }),
      api.evaluation(selectedRun).catch(() => null),
      api.recent(120).catch(() => []),
    ]).then(([fail, ev, recent]) => {
      setFailureData(fail)
      setEvalData(ev)
      const rows = Array.isArray(recent) ? recent : []
      // Prefer bypasses; if none, show high-signal blocked rows so the panel isn't empty
      const bypass = rows.filter(
        (e: any) =>
          e.sandbox_decision === "ALLOW" ||
          e.evasion_outcome === "bypassed" ||
          e.is_hard_negative
      )
      setBypassEvidence((bypass.length ? bypass : rows.filter((e: any) => e.sandbox_decision === "CHALLENGE")).slice(0, 14))
    })
  }, [selectedRun])

  const gapSummary = failureData?.gap_summary || {}
  const redEval = failureData?.red_eval || {}
  const perFamily = failureData?.per_family_asr || []
  const topGapsRaw = failureData?.top_ctl_gaps || []
  const heatmap = failureData?.ctl_heatmap || {}
  const summary = evalData?.summary || {}
  const asr = evalData?.asr || failureData?.asr_overall || {}

  const gapCards = useMemo(() => {
    const fromTop = (topGapsRaw as any[])
      .filter((g) => (g.gap_count || 0) > 0 || (g.miss_count || 0) > 0)
      .map((g) => {
        const label = controlLabel(g.control_id, catalog)
        const fams = familyKeys(g)
        return {
          id: label.id,
          name: label.name,
          gapCount: g.gap_count || 0,
          missed: g.miss_count || 0,
          triggered: g.triggered_count || 0,
          bypassWithTrigger: g.bypass_with_trigger || 0,
          families: fams,
          sev: (g.gap_count || 0) > 5 ? "high" : "med",
        }
      })

    if (fromTop.length) return fromTop.slice(0, 12)

    // Fallback: build from heatmap
    return Object.entries(heatmap)
      .filter(([, d]: any) => (d.gap_count || 0) > 0 || (d.miss_count || 0) > 0)
      .sort((a: any, b: any) => (b[1].gap_count || 0) - (a[1].gap_count || 0))
      .slice(0, 12)
      .map(([ctl, data]: any) => {
        const label = controlLabel(ctl, catalog)
        return {
          id: label.id,
          name: label.name,
          gapCount: data.gap_count || 0,
          missed: data.miss_count || 0,
          triggered: data.triggered_count || 0,
          bypassWithTrigger: data.bypass_with_trigger || 0,
          families: familyKeys(data),
          sev: (data.gap_count || 0) > 5 ? "high" : "med",
        }
      })
  }, [topGapsRaw, heatmap, catalog])

  const uniqueMissing: string[] =
    gapSummary.unique_missing_controls ||
    gapSummary.controls_with_gaps ||
    redEval.unique_missing_controls ||
    []

  const gapControlCount =
    (Array.isArray(gapSummary.controls_with_gaps) && gapSummary.controls_with_gaps.length) ||
    uniqueMissing.length ||
    gapCards.length ||
    Number(gapSummary.control_gaps) ||
    0

  const totalGapEvents =
    gapCards.reduce((s, g) => s + (g.gapCount || 0), 0) ||
    Number(gapSummary.total_findings) ||
    0

  const blockingBreakdown = redEval.blocking_control_breakdown || {}

  const redLearnings = useMemo(() => {
    const items: { title: string; detail: string }[] = []
    const families = redEval.families_tested || []
    items.push({
      title: "Campaign coverage",
      detail: `${redEval.campaign_count ?? "—"} campaigns across ${Array.isArray(families) ? families.length : families} families (${Array.isArray(families) ? families.slice(0, 8).join(", ") : families}${Array.isArray(families) && families.length > 8 ? "…" : ""}). Bypass rate ${fmtPct(redEval.sandbox_bypass_rate)}.`,
    })

    if (gapCards.length) {
      const top = gapCards.slice(0, 4)
      items.push({
        title: "Where Red should probe next",
        detail: `Controls that were expected but did not hold: ${top
          .map((g) => `${g.name} (${g.gapCount} gap events)`)
          .join("; ")}. Re-attack families that rely on these defenses to raise ASR.`,
      })
    } else if (uniqueMissing.length) {
      items.push({
        title: "Missing control coverage",
        detail: `KB expected controls never observed: ${uniqueMissing
          .slice(0, 6)
          .map((id) => controlLabel(id, catalog).name)
          .join(", ")}.`,
      })
    }

    // Families with weakest after-ML recall / highest ASR
    if (perFamily.length) {
      const weak = [...perFamily]
        .sort((a: any, b: any) => (b.after_ml_asr ?? 0) - (a.after_ml_asr ?? 0))
        .slice(0, 3)
      items.push({
        title: "Highest remaining attack success",
        detail: weak
          .map(
            (f: any) =>
              `${f.family}: ASR ${fmtPct(f.after_ml_asr)} (recall ${fmtPct(f.after_ml_recall)}, ${f.attacks} attacks)`
          )
          .join(" · "),
      })
    }

    if (Object.keys(blockingBreakdown).length) {
      const top = Object.entries(blockingBreakdown)
        .sort((a: any, b: any) => Number(b[1]) - Number(a[1]))
        .slice(0, 5)
      items.push({
        title: "What blocked Red this loop",
        detail: top
          .map(([c, n]) => `${controlLabel(String(c), catalog).name} ×${n}`)
          .join(" · "),
      })
    }

    return items
  }, [redEval, gapCards, uniqueMissing, catalog, perFamily, blockingBreakdown])

  const blueLearnings = useMemo(() => {
    const items: { title: string; detail: string }[] = []

    if (summary.buffer_score_lift != null || summary.asr_reduction_matched != null) {
      items.push({
        title: "Hardening impact",
        detail: `Buffer score lift ${fmt(summary.buffer_score_lift, 4)} · matched ASR ${fmtPct(asr.before_ml_asr_matched ?? summary.before_ml_asr_matched)} → ${fmtPct(asr.after_ml_asr_matched ?? summary.after_ml_asr_matched)} (Δ ${fmt(summary.asr_reduction_matched ?? asr.asr_reduction_matched, 4)}). ${summary.recommend_hardening ? "Gate recommends model swap." : "Hardening gate not met yet."}`,
      })
    }

    if (gapCards.length) {
      items.push({
        title: "Controls Blue must strengthen",
        detail: gapCards
          .slice(0, 5)
          .map((g) => `${g.name} — never fired when expected (${g.gapCount} gaps)${g.triggered ? `, triggered ${g.triggered} elsewhere` : ""}`)
          .join("; ") + ". Add rules / features / training rows that cover these failure modes.",
      })
    }

    if (perFamily.length) {
      const improved = [...perFamily]
        .filter((f: any) => (f.asr_reduction || 0) > 0)
        .sort((a: any, b: any) => (b.asr_reduction || 0) - (a.asr_reduction || 0))
        .slice(0, 3)
      const worsened = [...perFamily]
        .filter((f: any) => (f.asr_reduction || 0) < 0)
        .sort((a: any, b: any) => (a.asr_reduction || 0) - (b.asr_reduction || 0))
        .slice(0, 2)
      if (improved.length) {
        items.push({
          title: "Families where Blue improved",
          detail: improved
            .map((f: any) => `${f.family}: ASR down ${fmtPct(f.asr_reduction)}`)
            .join(" · "),
        })
      }
      if (worsened.length) {
        items.push({
          title: "Families needing more Blue work",
          detail: worsened
            .map((f: any) => `${f.family}: ASR up ${fmtPct(Math.abs(f.asr_reduction))} after harden`)
            .join(" · "),
        })
      }
    }

    if (bypassEvidence.length) {
      items.push({
        title: "Buffer fuel for Loop B",
        detail: `${bypassEvidence.length} recent bypass / challenge / hard-negative rows feeding adversarial training (see table below).`,
      })
    }

    if (!items.length) {
      items.push({
        title: "Waiting on loop evaluation",
        detail: "Run a full platform loop so Labs can show buffer lift, ASR before→after, and control-gap priorities.",
      })
    }

    return items
  }, [summary, asr, gapCards, perFamily, bypassEvidence.length])

  if (loading) {
    return <div style={{ color: "#6b7280", padding: 40, background: "#f8f9fa", minHeight: "100vh" }}>Loading Labs…</div>
  }

  return (
    <div style={{ background: "#f8f9fa", color: "#111827", minHeight: "100vh", fontFamily: "'Space Grotesk', sans-serif" }}>
      <div style={{ maxWidth: 1400, margin: "0 auto", padding: "22px 28px 60px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap", marginBottom: 20 }}>
          <div>
            <h2 style={{ margin: "0 0 4px", fontSize: 20 }}>Labs</h2>
            <p style={{ margin: 0, color: "#6b7280", fontSize: 13, maxWidth: 780 }}>
              Closed-loop learnings for judges — which defenses failed (with names, not only IDs), what Red should attack next, and what Blue should harden.
              Scorecard →{" "}
              <a href="/evaluation" style={{ color: "#2563eb", fontWeight: 600, textDecoration: "none" }}>
                Evaluation
              </a>
              .
            </p>
          </div>
          <select
            value={selectedRun}
            onChange={(e) => setSelectedRun(e.target.value)}
            style={{ padding: "10px 14px", borderRadius: 8, border: "1px solid #e5e7eb", background: "#f9fafb", color: "#111827", fontSize: 13, minWidth: 260 }}
          >
            {runs.length === 0 && <option value="">No completed runs</option>}
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.id.slice(0, 8)} · {r.families_count} families · {r.buffer_payments} payments · lift{" "}
                {r.score_lift != null ? r.score_lift.toFixed(3) : "—"}
              </option>
            ))}
          </select>
        </div>

        {loadErr && (
          <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: 12, marginBottom: 16, fontSize: 12, color: "#dc2626" }}>
            {loadErr}
          </div>
        )}

        {/* KPIs */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 20 }}>
          {[
            { label: "FINDINGS", value: gapSummary.total_findings ?? totalGapEvents, color: "#dc2626" },
            { label: "CONTROLS WITH GAPS", value: gapControlCount, color: "#ea580c" },
            { label: "GAP EVENTS", value: totalGapEvents, color: "#7c3aed" },
            {
              label: "BYPASS RATE",
              value: redEval.sandbox_bypass_rate != null ? fmtPct(redEval.sandbox_bypass_rate) : "—",
              color: "#dc2626",
            },
            {
              label: "BUFFER LIFT",
              value: summary.buffer_score_lift != null ? fmt(summary.buffer_score_lift, 3) : "—",
              color: "#16a34a",
            },
          ].map((kpi) => (
            <div
              key={kpi.label}
              style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: "16px 18px", borderTop: `3px solid ${kpi.color}` }}
            >
              <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: ".5px", marginBottom: 8 }}>{kpi.label}</div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 18, fontWeight: 600, color: kpi.color }}>{kpi.value}</div>
            </div>
          ))}
        </div>

        {/* How Red / Blue get better */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }}>
          <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, borderTop: "3px solid #dc2626" }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>How Red Team gets better</div>
            <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 14 }}>Use gaps & weak families to plan the next attack wave</div>
            {redLearnings.map((item, i) => (
              <div key={i} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: i < redLearnings.length - 1 ? "1px solid #f3f4f6" : "none" }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 4 }}>{item.title}</div>
                <div style={{ fontSize: 12, color: "#4b5563", lineHeight: 1.55 }}>{item.detail}</div>
              </div>
            ))}
          </div>
          <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, borderTop: "3px solid #2563eb" }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>How Blue Team gets better</div>
            <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 14 }}>Use the same evidence to harden rules, features, and FraudShield</div>
            {blueLearnings.map((item, i) => (
              <div key={i} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: i < blueLearnings.length - 1 ? "1px solid #f3f4f6" : "none" }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#111827", marginBottom: 4 }}>{item.title}</div>
                <div style={{ fontSize: 12, color: "#4b5563", lineHeight: 1.55 }}>{item.detail}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Control gaps — human readable */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, display: "flex", alignItems: "center", gap: 8 }}>
            Control gaps{" "}
            <span style={{ fontSize: 9.5, padding: "2px 7px", borderRadius: 5, background: "#f9fafb", color: "#6b7280", fontFamily: "'JetBrains Mono', monospace" }}>
              {gapCards.length} defenses
            </span>
          </div>
          <p style={{ margin: "0 0 14px", fontSize: 12, color: "#6b7280", maxWidth: 820 }}>
            A <strong>control gap</strong> means the knowledge base said this defense should fire for the attack, but the sandbox never applied it (or it failed). IDs like CTL-0016 map to real control names below.
          </p>

          {gapCards.length === 0 ? (
            <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 28, color: "#6b7280", fontSize: 13 }}>
              {failureData
                ? "No control-gap rows in this failure report (heatmap gap_count = 0). Check Evaluation for ASR / detection lift."
                : "No failure analysis loaded for this run."}
            </div>
          ) : (
            gapCards.map((gap, i) => (
              <div key={gap.id} style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, marginBottom: 12, overflow: "hidden" }}>
                <div
                  onClick={() => setExpandedGap(expandedGap === i ? null : i)}
                  style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "16px 18px", cursor: "pointer" }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ width: 8, height: 40, borderRadius: 4, background: gap.sev === "high" ? "#dc2626" : "#ea580c" }} />
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 600 }}>{gap.name}</div>
                      <div style={{ fontSize: 11, color: "#6b7280", marginTop: 3, fontFamily: "'JetBrains Mono', monospace" }}>
                        {gap.id} · {gap.gapCount} gaps · {gap.triggered} triggered · {gap.families.length} families linked
                      </div>
                    </div>
                  </div>
                  <div style={{ fontSize: 12, color: "#6b7280", transform: expandedGap === i ? "rotate(90deg)" : "none" }}>▶</div>
                </div>
                {expandedGap === i && (
                  <div style={{ padding: "14px 18px", borderTop: "1px solid #e5e7eb", background: "#fafafa" }}>
                    <div style={{ fontSize: 12, color: "#374151", lineHeight: 1.6, marginBottom: 12 }}>
                      <strong>For Red:</strong> Prefer attack paths that depend on <em>{gap.name}</em> — it failed to hold {gap.gapCount} time(s).
                      <br />
                      <strong>For Blue:</strong> Add coverage (rules, features, or buffer examples) so <em>{gap.name}</em> fires when the KB expects it.
                    </div>
                    {gap.families.length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {gap.families.map((f) => (
                          <span
                            key={f}
                            style={{
                              fontSize: 11,
                              padding: "4px 8px",
                              borderRadius: 6,
                              background: "#eff6ff",
                              color: "#2563eb",
                              fontFamily: "'JetBrains Mono', monospace",
                            }}
                          >
                            {f}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Missing controls chip list */}
        {uniqueMissing.length > 0 && (
          <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Expected controls that never showed up</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {uniqueMissing.map((id: string) => {
                const { name, id: cid } = controlLabel(id, catalog)
                return (
                  <span
                    key={cid}
                    title={cid}
                    style={{
                      fontSize: 12,
                      padding: "6px 10px",
                      borderRadius: 8,
                      background: "#fff7ed",
                      border: "1px solid #fed7aa",
                      color: "#c2410c",
                    }}
                  >
                    {name}
                    <span style={{ marginLeft: 6, fontSize: 10, color: "#9a3412", fontFamily: "'JetBrains Mono', monospace" }}>{cid}</span>
                  </span>
                )
              })}
            </div>
          </div>
        )}

        {/* Per-family */}
        {perFamily.length > 0 && (
          <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Per-family before → after (Blue hardening)</div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr>
                  {["Family", "Attacks", "Before ASR", "After ASR", "ASR Δ", "After recall", "Top triggers"].map((h) => (
                    <th
                      key={h}
                      style={{
                        textAlign: h === "Family" || h === "Top triggers" ? "left" : "right",
                        color: "#6b7280",
                        fontSize: 10.5,
                        textTransform: "uppercase",
                        padding: "8px 9px",
                        borderBottom: "1px solid #e5e7eb",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...perFamily]
                  .sort((a: any, b: any) => (b.attacks || 0) - (a.attacks || 0))
                  .map((r: any, i: number) => {
                    const triggers = (r.top_ctl_triggers || [])
                      .slice(0, 3)
                      .map((t: any) => {
                        const id = Array.isArray(t) ? t[0] : t
                        return controlLabel(String(id), catalog).name
                      })
                      .join(", ")
                    return (
                      <tr key={i}>
                        <td style={{ padding: "9px", borderBottom: "1px solid #e5e7eb", fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>{r.family}</td>
                        <td style={{ padding: "9px", borderBottom: "1px solid #e5e7eb", textAlign: "right", fontFamily: "'JetBrains Mono', monospace" }}>{r.attacks}</td>
                        <td style={{ padding: "9px", borderBottom: "1px solid #e5e7eb", textAlign: "right", fontFamily: "'JetBrains Mono', monospace", color: "#dc2626" }}>
                          {fmtPct(r.before_ml_asr)}
                        </td>
                        <td style={{ padding: "9px", borderBottom: "1px solid #e5e7eb", textAlign: "right", fontFamily: "'JetBrains Mono', monospace" }}>
                          {fmtPct(r.after_ml_asr)}
                        </td>
                        <td style={{ padding: "9px", borderBottom: "1px solid #e5e7eb", textAlign: "right" }}>
                          <span
                            style={{
                              padding: "2px 8px",
                              borderRadius: 100,
                              background: r.asr_reduction > 0 ? "rgba(22,163,74,.12)" : r.asr_reduction < 0 ? "rgba(220,38,38,.08)" : "#f9fafb",
                              color: r.asr_reduction > 0 ? "#16a34a" : r.asr_reduction < 0 ? "#dc2626" : "#6b7280",
                              fontSize: 11,
                              fontFamily: "'JetBrains Mono', monospace",
                            }}
                          >
                            {r.asr_reduction > 0 ? "↓" : r.asr_reduction < 0 ? "↑" : ""}
                            {fmtPct(Math.abs(r.asr_reduction || 0))}
                          </span>
                        </td>
                        <td style={{ padding: "9px", borderBottom: "1px solid #e5e7eb", textAlign: "right", fontFamily: "'JetBrains Mono', monospace" }}>
                          {fmtPct(r.after_ml_recall)}
                        </td>
                        <td style={{ padding: "9px", borderBottom: "1px solid #e5e7eb", fontSize: 11, color: "#4b5563" }}>{triggers || "—"}</td>
                      </tr>
                    )
                  })}
              </tbody>
            </table>
          </div>
        )}

        {/* Evidence */}
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 14, padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Evidence feeding the closed loop</div>
          <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 12 }}>
            Rows Red produced that Blue trains on (bypass / challenge / hard-negative preferred).
          </div>
          {bypassEvidence.length ? (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr>
                  {["Family", "Surface", "Decision", "Outcome", "ML", "Risk"].map((h) => (
                    <th key={h} style={{ textAlign: "left", color: "#6b7280", fontSize: 10, textTransform: "uppercase", padding: "8px", borderBottom: "1px solid #e5e7eb" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bypassEvidence.map((e: any) => (
                  <tr key={e.evidence_id}>
                    <td style={{ padding: "8px", borderBottom: "1px solid #f3f4f6", fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>{e.attack_family}</td>
                    <td style={{ padding: "8px", borderBottom: "1px solid #f3f4f6" }}>{e.surface || "—"}</td>
                    <td style={{ padding: "8px", borderBottom: "1px solid #f3f4f6", fontWeight: 600 }}>{e.sandbox_decision}</td>
                    <td style={{ padding: "8px", borderBottom: "1px solid #f3f4f6" }}>{e.evasion_outcome || "—"}</td>
                    <td style={{ padding: "8px", borderBottom: "1px solid #f3f4f6", fontFamily: "'JetBrains Mono', monospace" }}>
                      {e.ml_score != null ? Number(e.ml_score).toFixed(3) : "—"}
                    </td>
                    <td style={{ padding: "8px", borderBottom: "1px solid #f3f4f6", fontFamily: "'JetBrains Mono', monospace" }}>
                      {e.risk_score != null ? Number(e.risk_score).toFixed(3) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{ fontSize: 12, color: "#6b7280" }}>No recent buffer rows loaded.</div>
          )}
        </div>
      </div>
    </div>
  )
}
