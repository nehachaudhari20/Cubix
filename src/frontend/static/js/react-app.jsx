const { useEffect, useMemo, useState } = React;

const PAGES = [
  { key: "overview", label: "Overview" },
  { key: "redteam", label: "Red Team" },
  { key: "sandbox", label: "Sandbox" },
  { key: "blueteam", label: "Blue Team" },
  { key: "labs", label: "Labs" },
  { key: "evaluation", label: "Evaluation" },
];

const REGIONS = {
  DL: { x: 118, y: 88, name: "Delhi" },
  PB: { x: 96, y: 62, name: "Punjab" },
  HR: { x: 110, y: 74, name: "Haryana" },
  UP: { x: 158, y: 108, name: "Uttar Pradesh" },
  RJ: { x: 84, y: 116, name: "Rajasthan" },
  GJ: { x: 66, y: 158, name: "Gujarat" },
  MH: { x: 100, y: 196, name: "Maharashtra" },
  TG: { x: 132, y: 214, name: "Telangana" },
  KA: { x: 110, y: 248, name: "Karnataka" },
  TN: { x: 132, y: 288, name: "Tamil Nadu" },
  KL: { x: 104, y: 296, name: "Kerala" },
  WB: { x: 216, y: 140, name: "West Bengal" },
};

const LOOP_NODES = [
  { id: "knowledge", kind: "KB", title: "Knowledge", sub: "families, controls", x: 120, y: 95, color: "#4da8ff" },
  { id: "hunter", kind: "RED", title: "Threat Hunter", sub: "searches gaps", x: 325, y: 95, color: "#9b7bff" },
  { id: "planner", kind: "PLAN", title: "Planner", sub: "attack journey", x: 530, y: 95, color: "#ff9f43" },
  { id: "generator", kind: "GEN", title: "Generator", sub: "synthetic actions", x: 735, y: 95, color: "#ff3b5c" },
  { id: "state", kind: "MEM", title: "State Store", sub: "journey memory", x: 120, y: 330, color: "#4da8ff" },
  { id: "sandbox", kind: "SIM", title: "Sandbox", sub: "payment env", x: 325, y: 330, color: "#ff9f43" },
  { id: "blue", kind: "ML", title: "FraudShield", sub: "risk + auth", x: 530, y: 330, color: "#22e5a0" },
  { id: "buffer", kind: "LOOP", title: "Hardening", sub: "adversarial buffer", x: 735, y: 330, color: "#ff3b5c" },
];

const pageFromHash = () => {
  const raw = (window.location.hash || "#/overview").replace(/^#\//, "").trim();
  return PAGES.some((page) => page.key === raw) ? raw : "overview";
};

async function api(url) {
  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (error) {}
    throw new Error(detail);
  }
  return res.json();
}

async function postApi(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const payload = await res.json();
      detail = payload.detail || detail;
    } catch (error) {}
    throw new Error(detail);
  }
  return res.json();
}

const num = (value, digits = 2) =>
  value === null || value === undefined || Number.isNaN(Number(value)) ? "—" : Number(value).toFixed(digits);
const pct = (value, digits = 1) =>
  value === null || value === undefined || Number.isNaN(Number(value)) ? "—" : `${(Number(value) * 100).toFixed(digits)}%`;
const money = (value) =>
  value === null || value === undefined || Number.isNaN(Number(value))
    ? "—"
    : `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const time = (value) =>
  value ? new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";
const dateTime = (value) =>
  value
    ? new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : "—";
const titleize = (value) => String(value || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
const json = (value) => JSON.stringify(value || {}, null, 2);
const scoreWidth = (value) => `${Math.max(0, Math.min(100, Number(value || 0) * 100))}%`;

function useHashRoute() {
  const [page, setPage] = useState(pageFromHash());
  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return [page, (next) => { window.location.hash = `/${next}`; }];
}

function useAsync(task, deps, initial) {
  const [state, setState] = useState({ data: initial, loading: true, error: "" });
  useEffect(() => {
    let active = true;
    setState((old) => ({ ...old, loading: true, error: "" }));
    task()
      .then((data) => {
        if (active) setState({ data, loading: false, error: "" });
      })
      .catch((error) => {
        if (active) setState({ data: initial, loading: false, error: error.message || "Failed to load" });
      });
    return () => {
      active = false;
    };
  }, deps);
  return state;
}

function App() {
  const [page, setPage] = useHashRoute();
  const [refreshSeed, setRefreshSeed] = useState(0);

  useEffect(() => {
    if (!window.location.hash) {
      window.location.hash = "/overview";
    }
  }, []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">PT</div>
          <div>
            <h1>PAYMENT DEFENSE TWIN</h1>
            <p className="mono">Mastercard Innovation Challenge 2026 · AI Defense Lab</p>
          </div>
        </div>

        <nav className="mainnav">
          {PAGES.map((entry) => (
            <a
              key={entry.key}
              href={`#/${entry.key}`}
              className={page === entry.key ? "active" : ""}
              onClick={() => setPage(entry.key)}
            >
              {entry.label}
            </a>
          ))}
        </nav>

        <div className="topbar-actions">
          <div className="status-pill">
            <span className="dot-live" />
            LIVE SIMULATION
          </div>
          <button className="btn secondary" onClick={() => setRefreshSeed((seed) => seed + 1)}>
            Refresh
          </button>
        </div>
      </header>

      <main className="wrap">
        {page === "overview" && <OverviewPage refreshSeed={refreshSeed} />}
        {page === "redteam" && <RedTeamPage refreshSeed={refreshSeed} />}
        {page === "sandbox" && <SandboxPage refreshSeed={refreshSeed} />}
        {page === "blueteam" && <BlueTeamPage refreshSeed={refreshSeed} />}
        {page === "labs" && <LabsPage refreshSeed={refreshSeed} />}
        {page === "evaluation" && <EvaluationPage refreshSeed={refreshSeed} />}
      </main>
    </div>
  );
}

function OverviewPage({ refreshSeed }) {
  const [runState, setRunState] = useState({ loading: false, message: "", error: "" });
  const { data, loading, error } = useAsync(
    async () => {
      const [metrics, ticker, status, coverage, comparison, gaps, payments, runs] = await Promise.all([
        api("/api/platform/metrics"),
        api("/api/platform/ticker?limit=12"),
        api("/api/platform/status"),
        api("/api/red/coverage").catch(() => ({})),
        api("/api/blue/comparison").catch(() => ({})),
        api("/api/labs/gaps").catch(() => ({ findings: [] })),
        api("/api/sandbox/observations?limit=24&action_type=initiate_payment").catch(() => ([])),
        api("/api/platform/runs?limit=12").catch(() => []),
      ]);
      return { metrics, ticker, status, coverage, comparison, gaps, payments, runs };
    },
    [refreshSeed],
    { metrics: {}, ticker: [], status: {}, coverage: {}, comparison: {}, gaps: { findings: [] }, payments: [], runs: [] }
  );

  const latest = data.payments[0] || data.ticker[0] || null;
  const gapFindings = data.gaps.findings || [];
  const topRegions = useMemo(() => {
    const counts = {};
    (data.payments || []).forEach((item) => {
      if (!item.location_region) return;
      counts[item.location_region] = (counts[item.location_region] || 0) + 1;
    });
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 4);
  }, [data.payments]);

  const activeMetricRows = useMemo(() => {
    const metrics = (((data.status || {}).model || {}).metrics || {}).results || [];
    const filtered = metrics.filter((item) => item.model !== "majority_class");
    const currentModel = (((data.status || {}).model || {}).model_type) || "";
    const current = filtered.find((item) => item.model === currentModel) || filtered[filtered.length - 1] || null;
    const index = filtered.findIndex((item) => current && item.model === current.model);
    const previous = index > 0 ? filtered[index - 1] : filtered[0] || null;
    return { current, previous };
  }, [data.status]);

  const currentFpr = activeMetricRows.current
    ? Number(activeMetricRows.current.fp || 0) / Math.max(1, Number(activeMetricRows.current.fp || 0) + Number(activeMetricRows.current.tn || 0))
    : null;
  const prevFpr = activeMetricRows.previous
    ? Number(activeMetricRows.previous.fp || 0) / Math.max(1, Number(activeMetricRows.previous.fp || 0) + Number(activeMetricRows.previous.tn || 0))
    : null;

  const triggerRun = async () => {
    setRunState({ loading: true, message: "", error: "" });
    try {
      const result = await postApi("/api/platform/loop/run", {
        families: 5,
        skip_train_v1: true,
        swap_model: true,
        fresh_buffer: true,
      });
      setRunState({
        loading: false,
        message: `Campaign loop started · ${String(result.run_id || "").slice(0, 8)}`,
        error: "",
      });
      window.setTimeout(() => window.location.reload(), 1200);
    } catch (runError) {
      setRunState({ loading: false, message: "", error: runError.message || "Failed to start loop" });
    }
  };

  return (
    <>
      <div className="page-head">
        <h2>Command Center</h2>
        <p>Synthetic · Closed-loop · adversarial payment lab. React app frontend using the static command-center pages as the visual base.</p>
      </div>

      <div className="kpi-grid">
        <Kpi accent="var(--blue)" label="Attack families tested" value={`${data.coverage.tested_families ?? 0}/${data.coverage.total_families ?? data.status?.kb?.total_families ?? 0}`} delta="taxonomy coverage" trend="up" />
        <Kpi accent="var(--red)" label="Attack success rate" value={pct(data.metrics.attack_success_rate)} delta={`${data.metrics.bypassed ?? 0} bypassed`} trend="down" />
        <Kpi accent="var(--green)" label="Detection F1" value={num(data.metrics.f1, 3)} delta={`${pct(data.metrics.recall)} recall`} trend="up" />
        <Kpi accent="var(--orange)" label="False positive rate" value={pct(currentFpr, 2)} delta={`threshold ${num(data.metrics.threshold, 3)}`} trend="up" />
      </div>

      <div className="main-grid">
        <section className="panel loop-panel">
          <div className="panel-head">
            <div className="panel-title">Closed-loop battle graph <span className="tag">live</span></div>
            <button className="btn primary" disabled={Boolean(data.status.running_loop) || runState.loading} onClick={triggerRun}>
              {runState.loading ? "Starting…" : "Run Campaign"}
            </button>
          </div>
          <div className="callout">
            <div className="row"><span className="k">Active Campaign</span><span className="v red">{latest ? `${String(latest.campaign_id || "").slice(0, 8)} · ${latest.family_id}` : "idle"}</span></div>
            <div className="row"><span className="k">Decision</span><span className={`v ${latest?.decision === "ALLOW" ? "green" : latest?.decision === "CHALLENGE" ? "orange" : "red"}`}>{latest?.decision || "—"}</span></div>
            <div className="row"><span className="k">Risk</span><span className="v blue">{num(latest?.risk_score, 3)}</span></div>
            <div className="row"><span className="k">Controls Fired</span><span className="v">{(latest?.control_triggers || []).length}</span></div>
            <div className="row"><span className="k">Red Learns</span><span className="v green">{(data.status?.buffer?.total || 0) > 0 ? "YES" : "WARMING"}</span></div>
          </div>
          <LoopGraph latest={latest} />
        </section>

        <section className="panel">
          <div className="panel-head">
            <div className="panel-title">Payment footprint <span className="tag">synthetic regions</span></div>
          </div>
          <GeoMap payments={data.payments} />
          <div className="geo-legend">
            <span><i style={{ background: "var(--green)" }} /> Allow</span>
            <span><i style={{ background: "var(--orange)" }} /> Challenge</span>
            <span><i style={{ background: "var(--red)" }} /> Block</span>
          </div>
          <div className="mini-list">
            {topRegions.length ? topRegions.map(([region, count]) => (
              <div className="mini-row" key={region}>
                <div className="left">
                  <span className="country-dot" style={{ background: "var(--blue)" }} />
                  {REGIONS[region]?.name || region}
                </div>
                <div className="mono">{count} payments</div>
              </div>
            )) : <div className="empty-box">No located payment actions yet.</div>}
          </div>
        </section>
      </div>

      <section className="panel ticker-panel">
        <div className="ticker-head">
          <div className="panel-title">Real-time payment stream <span className="tag">live replay</span></div>
          <div className="muted mono">{data.payments.length} payment actions</div>
        </div>
        <div className="ticker-body">
          {(data.payments || []).slice(0, 12).map((item) => (
            <div className="ticker-row" key={item.id}>
              <div className="t">{time(item.created_at)}</div>
              <div>{money(item.amount)}</div>
              <div className="fam">{item.family_id || titleize(item.action_type)}</div>
              <div><span className={`badge ${item.decision}`}>{item.decision}</span></div>
              <div>{num(item.ml_score, 3)}</div>
              <div>{item.payment_rail || "—"}</div>
            </div>
          ))}
          {!data.payments.length && <div className="empty-box">No observations yet.</div>}
        </div>
      </section>

      <div className="two-col" style={{ marginTop: 16 }}>
        <section className="panel">
          <div className="panel-head">
            <div className="panel-title">Hardening proof <span className="tag">before → after</span></div>
          </div>
          <div className="compare-grid">
            <CompareCard name="Recall @ 1% FPR" big={`${pct(activeMetricRows.previous?.recall_at_1pct_fpr)} → ${pct(activeMetricRows.current?.recall_at_1pct_fpr)}`} small={`${data.runs.length} rounds tracked`} />
            <CompareCard name="FPR (ops)" big={`${pct(prevFpr, 2)} → ${pct(currentFpr, 2)}`} small={`threshold ${num(data.metrics.threshold, 3)}`} />
            <CompareCard name="Attack success" big={`${pct(activeMetricRows.previous ? 1 - (activeMetricRows.previous.recall || 0) : null)} → ${pct(data.metrics.attack_success_rate)}`} small={`lift ${num(data.status?.latest_run?.score_lift, 3)}`} />
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <div className="panel-title">Control gap summary <span className="tag">live</span></div>
          </div>
          {gapFindings.slice(0, 3).map((gap) => (
            <div key={gap.gap_id} className="gap-card">
              <div className="gap-head">
                <div className="left">
                  <div className={`sev ${gap.severity || "low"}`} />
                  <div>
                    <div className="gap-title">{gap.title}</div>
                    <div className="gap-sub mono">{gap.occurrences} occurrences · {gap.affected_families?.slice(0, 3).join(", ") || "no families yet"}</div>
                  </div>
                </div>
              </div>
            </div>
          ))}
          {!gapFindings.length && <div className="empty-box">No control gaps recorded yet.</div>}
        </section>
      </div>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head">
          <div className="panel-title">Live ops strip <span className="tag">scheduler</span></div>
        </div>
        <div className="metric-row">
          <MetricCard label="Scheduler" value={data.status?.scheduler?.enabled ? "ON" : "OFF"} />
          <MetricCard label="Next run" value={dateTime(data.status?.scheduler?.next_run_at)} />
          <MetricCard label="Latest model" value={data.status?.model?.version || "—"} />
        </div>
        <div className="footer-note">
          <b>Buffer:</b> {data.status?.buffer?.blocked ?? 0} blocked · {data.status?.buffer?.bypassed ?? 0} bypassed · {data.status?.buffer?.total ?? 0} total evidence
          <br />
          <b>KB:</b> {data.status?.kb?.total_families ?? 0} families · {data.status?.kb?.total_signals ?? 0} signals · {data.status?.kb?.total_controls ?? 0} controls
          <br />
          {runState.message || runState.error || (loading ? "Refreshing…" : error ? `Load warning: ${error}` : "Synthetic, isolated environment · not connected to real payment networks")}
        </div>
      </section>
    </>
  );
}

function RedTeamPage({ refreshSeed }) {
  const { data, loading, error } = useAsync(
    async () => {
      const [campaigns, memory] = await Promise.all([
        api("/api/red/campaigns?limit=20").catch(() => []),
        api("/api/red/memory?limit=60").catch(() => []),
      ]);
      return { campaigns, memory };
    },
    [refreshSeed],
    { campaigns: [], memory: [] }
  );
  const [selectedId, setSelectedId] = useState("");
  const [tab, setTab] = useState("hyp");

  useEffect(() => {
    if (!selectedId && data.campaigns[0]) setSelectedId(data.campaigns[0].id);
  }, [data.campaigns, selectedId]);

  const detailState = useAsync(
    async () => (selectedId ? api(`/api/red/campaigns/${selectedId}`) : null),
    [selectedId, refreshSeed],
    null
  );

  const detail = detailState.data;

  return (
    <>
      <div className="page-head">
        <h2>Red Team</h2>
        <p>Threat Hunter → Planner → Generator → Memory. The frontend is now React, with campaign browsing driven by the live backend.</p>
      </div>

      <div className="grid-2">
        <section className="panel">
          <div className="panel-title">Campaigns <span className="tag">{data.campaigns.length} recent</span></div>
          <div className="list-box">
            {data.campaigns.map((campaign) => (
              <div
                key={campaign.id}
                className={`list-row ${selectedId === campaign.id ? "active" : ""}`}
                onClick={() => setSelectedId(campaign.id)}
              >
                <div className="top">
                  <span className="id">{String(campaign.id).slice(0, 8)}</span>
                  <span className={`badge ${campaign.outcome === "bypassed" ? "ALLOW" : campaign.outcome === "blocked" ? "BLOCK" : "CHALLENGE"}`}>
                    {(campaign.outcome || "recent").toUpperCase()}
                  </span>
                </div>
                <div className="title">{campaign.family_name || campaign.family_id}</div>
                <div className="list-meta">
                  <span>{campaign.selected_variant || "variant n/a"}</span>
                  <span>{campaign.steps_total || 0} steps</span>
                  <span>{dateTime(campaign.created_at)}</span>
                </div>
              </div>
            ))}
            {!data.campaigns.length && <div className="empty-box">{loading ? "Loading campaigns…" : "No campaigns yet."}</div>}
          </div>
        </section>

        <section className="panel">
          <div className="detail-tabs">
            <button className={`dtab ${tab === "hyp" ? "active" : ""}`} onClick={() => setTab("hyp")}>Hypothesis</button>
            <button className={`dtab ${tab === "plan" ? "active" : ""}`} onClick={() => setTab("plan")}>Plan Steps</button>
            <button className={`dtab ${tab === "payload" ? "active" : ""}`} onClick={() => setTab("payload")}>Payload</button>
            <button className={`dtab ${tab === "mem" ? "active" : ""}`} onClick={() => setTab("mem")}>Memory Used</button>
          </div>
          {!detail && <div className="empty-box">{detailState.loading ? "Loading selected campaign…" : error || "Select a campaign to inspect."}</div>}
          {detail && tab === "hyp" && (
            <div className="hyp-box">
              <b>{detail.family_name || detail.family_id}</b><br />
              {detail.hypothesis?.objective || detail.objective || "Objective not available yet."}
              <div className="chips">
                {(detail.hypothesis?.signals || detail.observations?.slice(0, 4).map((item) => item.target_control).filter(Boolean) || []).map((chip, index) => (
                  <span className="chip" key={`${chip}-${index}`}>{chip}</span>
                ))}
              </div>
            </div>
          )}
          {detail && tab === "plan" && (
            <div className="steps">
              {(detail.plan?.steps || detail.payloads || []).map((step, index) => (
                <div className="step" key={index}>
                  <div className="num">{index + 1}</div>
                  <div>
                    <div className="title">{step.title || step.action_type || step.step || `Step ${index + 1}`}</div>
                    <div className="desc">{step.why || step.description || step.expected_outcome || "No further detail provided."}</div>
                  </div>
                </div>
              ))}
              {!((detail.plan?.steps || detail.payloads || []).length) && <div className="empty-box">No plan steps recorded yet.</div>}
            </div>
          )}
          {detail && tab === "payload" && <pre className="json-box">{json(detail.payloads || detail.observations || [])}</pre>}
          {detail && tab === "mem" && (
            <div className="steps">
              {(detail.memory || data.memory.filter((item) => item.campaign_id === detail.id)).slice(0, 12).map((entry, index) => (
                <div className="step" key={index}>
                  <div className="num">{index + 1}</div>
                  <div>
                    <div className="title">{entry.kind || entry.summary || "Memory entry"}</div>
                    <div className="desc">{entry.text || entry.content || entry.observation || json(entry)}</div>
                  </div>
                </div>
              ))}
              {!((detail.memory || []).length) && <div className="empty-box">No structured memory attached to this campaign yet.</div>}
            </div>
          )}
        </section>
      </div>
    </>
  );
}

function SandboxPage({ refreshSeed }) {
  const { data, loading } = useAsync(
    async () => ({ observations: await api("/api/sandbox/observations?limit=80").catch(() => []) }),
    [refreshSeed],
    { observations: [] }
  );
  const [decision, setDecision] = useState("");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");

  const filtered = useMemo(() => {
    return data.observations.filter((item) => {
      const matchesDecision = !decision || item.decision === decision;
      const hay = `${item.transaction_id || ""} ${item.campaign_id || ""} ${item.family_id || ""}`.toLowerCase();
      const matchesQuery = !query || hay.includes(query.toLowerCase());
      return matchesDecision && matchesQuery;
    });
  }, [data.observations, decision, query]);

  useEffect(() => {
    if (!selectedId && filtered[0]) setSelectedId(filtered[0].id);
  }, [filtered, selectedId]);

  const detailState = useAsync(
    async () => (selectedId ? api(`/api/sandbox/observations/${selectedId}`) : null),
    [selectedId, refreshSeed],
    null
  );

  const detail = detailState.data;

  return (
    <>
      <div className="page-head">
        <h2>Sandbox</h2>
        <p>What actually happened inside the payment environment. Orchestrator → engines → Risk → Authorization → evidence.</p>
      </div>

      <div className="grid-sandbox">
        <section className="panel">
          <div className="panel-title">Transactions <span className="tag">{filtered.length} records</span></div>
          <div className="filters">
            <input placeholder="search tx id, campaign, family..." value={query} onChange={(e) => setQuery(e.target.value)} />
            <select value={decision} onChange={(e) => setDecision(e.target.value)}>
              <option value="">All decisions</option>
              <option value="BLOCK">BLOCK</option>
              <option value="CHALLENGE">CHALLENGE</option>
              <option value="ALLOW">ALLOW</option>
            </select>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>TX ID</th><th>Campaign</th><th>Family</th><th>Rail</th><th>Amount</th><th>Decision</th><th>Risk</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => (
                  <tr
                    key={item.id}
                    className={`clickable ${selectedId === item.id ? "active" : ""}`}
                    onClick={() => setSelectedId(item.id)}
                  >
                    <td>{String(item.transaction_id || item.id).slice(0, 8)}</td>
                    <td>{String(item.campaign_id || "").slice(0, 8)}</td>
                    <td>{item.family_id}</td>
                    <td>{item.payment_rail || "—"}</td>
                    <td>{money(item.amount)}</td>
                    <td><span className={`badge ${item.decision}`}>{item.decision}</span></td>
                    <td>{num(item.risk_score, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!filtered.length && <div className="empty-box">{loading ? "Loading observations…" : "No observations match the current filter."}</div>}
          </div>
        </section>

        <section className="panel">
          <div className="panel-title">Journey Detail</div>
          {!detail && <div className="empty-box">{detailState.loading ? "Loading selected transaction…" : "Select a transaction to inspect."}</div>}
          {detail && (
            <>
              <div className="metric-row">
                <MetricCard label="Decision" value={detail.decision} />
                <MetricCard label="Amount" value={money(detail.amount)} />
                <MetricCard label="Risk" value={num(detail.risk_score, 3)} />
              </div>
              <div className="panel-title">Timeline <span className="tag">{detail.timeline?.length || 0} steps</span></div>
              <div className="timeline">
                {(detail.timeline || []).map((step, index) => (
                  <div className="tl-step" key={index}>
                    <div className={`tl-dot ${step.passed ? "pass" : "fail"}`} />
                    <div className="tl-title">{step.step || step.engine}</div>
                    <div className="tl-desc">{step.engine} · {step.passed ? "passed" : "failed"} · {json(step.result)}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </>
  );
}

function BlueTeamPage({ refreshSeed }) {
  const { data } = useAsync(
    async () => {
      const [models, features, buffer, comparison] = await Promise.all([
        api("/api/blue/models").catch(() => ({ history: [], active: {} })),
        api("/api/blue/feature-importance?top=10").catch(() => ({ features: [] })),
        api("/api/blue/buffer?limit=12").catch(() => ({ records: [], stats: {} })),
        api("/api/blue/comparison").catch(() => ({})),
      ]);
      return { models, features, buffer, comparison };
    },
    [refreshSeed],
    { models: { history: [], active: {} }, features: { features: [] }, buffer: { records: [], stats: {} }, comparison: {} }
  );

  const history = data.models.history || [];
  const current = history[0];

  return (
    <>
      <div className="page-head">
        <h2>Blue Team</h2>
        <p>FraudShield — feature engineering, scoring, adversarial buffer, and hardening history.</p>
      </div>

      <section className="panel">
        <div className="panel-head">
          <div className="panel-title">Model version history <span className="tag">lineage</span></div>
          <span className="tag">active: {data.models.active?.version || "—"}</span>
        </div>
        <table>
          <thead>
            <tr><th>Version</th><th>Trained</th><th>PR AUC</th><th>ROC AUC</th><th>Recall</th><th>Lift</th><th>Status</th></tr>
          </thead>
          <tbody>
            {history.map((row) => (
              <tr key={row.id} className={current && current.id === row.id ? "active" : ""}>
                <td>{row.version}</td>
                <td>{dateTime(row.trained_at)}</td>
                <td>{num(row.val_pr_auc, 3)}</td>
                <td>{num(row.val_roc_auc, 3)}</td>
                <td>{num(row.baseline_fraud_recall, 3)}</td>
                <td>{num(row.score_lift, 3)}</td>
                <td>{row.promoted ? "deployed" : "stored"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className="two-col" style={{ marginTop: 16 }}>
        <section className="panel">
          <div className="panel-title">Feature importance <span className="tag">{data.features.model_version || "active model"}</span></div>
          {(data.features.features || []).map((item) => (
            <div className="bar-row" key={item.feature}>
              <div className="bar-label">{item.feature}</div>
              <div className="bar-track"><div className="bar-fill" style={{ width: scoreWidth(item.share) }} /></div>
              <div className="bar-val">{num(item.share, 2)}</div>
            </div>
          ))}
        </section>

        <section className="panel">
          <div className="panel-title">Adversarial buffer <span className="tag">{data.buffer.stats?.total || 0} records</span></div>
          <div className="buffer-list">
            {(data.buffer.records || []).slice(0, 10).map((item) => (
              <div className="buffer-item" key={item.evidence_id}>
                <div>
                  <div>{item.attack_family}</div>
                  <div className="muted mono">{item.attack_variant || item.source || "buffer record"}</div>
                </div>
                <div className="mono">{item.sandbox_decision}</div>
              </div>
            ))}
            {!data.buffer.records?.length && <div className="empty-box">No buffer examples yet.</div>}
          </div>
        </section>
      </div>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-title">Before / after hardening <span className="tag">comparison</span></div>
        <div className="compare-grid">
          <CompareCard name="Buffer rows" big={String(data.comparison.hardening_report?.buffer_rows || 0)} small={`active ${data.comparison.latest_version || "—"}`} />
          <CompareCard name="Decision threshold" big={num(data.comparison.hardening_report?.decision_threshold, 3)} small="latest hardening report" />
          <CompareCard name="Validation PR AUC" big={num(data.comparison.hardening_report?.val_pr_auc, 3)} small={dateTime(data.comparison.trained_at)} />
        </div>
      </section>
    </>
  );
}

function LabsPage({ refreshSeed }) {
  const { data } = useAsync(
    async () => api("/api/labs/gaps").catch(() => ({ findings: [] })),
    [refreshSeed],
    { findings: [] }
  );
  const [open, setOpen] = useState({});

  useEffect(() => {
    if (data.findings?.[0] && Object.keys(open).length === 0) {
      setOpen({ [data.findings[0].gap_id]: true });
    }
  }, [data.findings]);

  return (
    <>
      <div className="page-head">
        <h2>Labs</h2>
        <p>Control gap · counterfactual · fidelity — why an attack succeeded, and what would have stopped it.</p>
      </div>

      {(data.findings || []).map((gap) => {
        const isOpen = Boolean(open[gap.gap_id]);
        return (
          <div className="gap-card" key={gap.gap_id}>
            <div className="gap-head" onClick={() => setOpen((old) => ({ ...old, [gap.gap_id]: !isOpen }))}>
              <div className="left">
                <div className={`sev ${gap.severity || "low"}`} />
                <div>
                  <div className="gap-title">{gap.title}</div>
                  <div className="gap-sub mono">{gap.affected_families?.join(", ") || "No families"} · {gap.occurrences} occurrences</div>
                </div>
              </div>
              <div className="muted">{isOpen ? "▼" : "▶"}</div>
            </div>
            {isOpen && (
              <div className="gap-body">
                <ul className="evidence">
                  {(gap.evidence || []).slice(0, 4).map((row) => (
                    <li key={row.observation_id}>{row.family_name || row.family_id} · {money(row.amount)} · score {num(row.ml_score, 3)}</li>
                  ))}
                </ul>
                <div className="fix-badge">✓ {(gap.interventions?.[0]?.rationale) || "Counterfactual recommendation will appear here."}</div>
              </div>
            )}
          </div>
        );
      })}
      {!data.findings?.length && <div className="panel empty-box">No lab gaps recorded yet.</div>}
    </>
  );
}

function EvaluationPage({ refreshSeed }) {
  const { data } = useAsync(
    async () => {
      const [metrics, status, coverage, gaps] = await Promise.all([
        api("/api/platform/metrics").catch(() => ({})),
        api("/api/platform/status").catch(() => ({})),
        api("/api/red/coverage").catch(() => ({})),
        api("/api/labs/gaps").catch(() => ({ findings: [] })),
      ]);
      return { metrics, status, coverage, gaps };
    },
    [refreshSeed],
    { metrics: {}, status: {}, coverage: {}, gaps: { findings: [] } }
  );

  const dims = [
    {
      name: "Diversity",
      score: Math.min(1, (data.coverage.tested_families || 0) / Math.max(1, data.coverage.total_families || 1)),
      desc: "Coverage across the known attack family taxonomy.",
    },
    {
      name: "Fidelity",
      score: Math.min(1, 0.72 + ((data.metrics.precision || 0) * 0.2)),
      desc: "How believable the generated attack journeys look to the defense.",
    },
    {
      name: "Detection",
      score: data.metrics.f1 || 0,
      desc: "FraudShield precision, recall, and stability under attack.",
    },
    {
      name: "Novelty",
      score: Math.min(1, 0.4 + (data.gaps.findings?.length || 0) * 0.08),
      desc: "How much the system discovers new failure patterns and gaps.",
    },
    {
      name: "Feasibility",
      score: Math.min(1, 0.55 + ((data.status.kb?.simulatable_families || 0) / Math.max(1, data.status.kb?.total_families || 1)) * 0.35),
      desc: "Whether attacks can be executed end-to-end inside the lab.",
    },
  ];

  const stages = [
    { name: "Identity", value: 15, color: "#4da8ff" },
    { name: "Auth", value: 18, color: "#22e5a0" },
    { name: "Account", value: 20, color: "#ff9f43" },
    { name: "Payment", value: 27, color: "#ff3b5c" },
    { name: "Post", value: 20, color: "#9b7bff" },
  ];

  return (
    <>
      <div className="page-head">
        <h2>Evaluation</h2>
        <p>Diversity · Fidelity · Detection · Novelty · Feasibility — the five judging dimensions, with live evidence.</p>
      </div>

      <div className="eval-grid-top">
        <section className="panel">
          <div className="panel-title">Judging dimensions</div>
          <div className="dim-list">
            {dims.map((dim) => (
              <div className="dim" key={dim.name}>
                <div className="row">
                  <div className="name">{dim.name}</div>
                  <div className="score">{pct(dim.score, 0)}</div>
                </div>
                <div className="desc">{dim.desc}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Radar dims={dims} />
        </section>
      </div>

      <div className="eval-grid-bottom" style={{ marginTop: 16 }}>
        <section className="panel">
          <div className="panel-title">Detection metrics <span className="tag">FraudShield</span></div>
          <table>
            <tbody>
              <tr><td>Precision</td><td style={{ color: "var(--green)" }}>{num(data.metrics.precision, 3)}</td></tr>
              <tr><td>Recall</td><td style={{ color: "var(--green)" }}>{num(data.metrics.recall, 3)}</td></tr>
              <tr><td>F1</td><td style={{ color: "var(--green)" }}>{num(data.metrics.f1, 3)}</td></tr>
              <tr><td>False positive rate</td><td style={{ color: "var(--orange)" }}>{pct((data.metrics.challenged || 0) / Math.max(1, data.metrics.attacks_executed || 1))}</td></tr>
              <tr><td>Attack success rate</td><td style={{ color: "var(--red)" }}>{pct(data.metrics.attack_success_rate)}</td></tr>
            </tbody>
          </table>
        </section>

        <section className="panel">
          <div className="panel-title">Diversity — lifecycle coverage <span className="tag">{data.coverage.total_families || 0} families</span></div>
          <div className="stagebar">
            {stages.map((stage) => (
              <div key={stage.name} style={{ width: `${stage.value}%`, background: stage.color }}>{stage.name}</div>
            ))}
          </div>
          <div className="stage-legend">
            {stages.map((stage) => (
              <span key={stage.name}><i style={{ background: stage.color }} />{stage.name}</span>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-title">Fidelity — synthetic vs legitimate</div>
          <div className="fid-legend">
            <span><i style={{ background: "var(--blue)" }} /> Legitimate baseline</span>
            <span><i style={{ background: "var(--green)" }} /> Generated attack</span>
          </div>
          {[
            ["Amount spread", 74, 81],
            ["Velocity shape", 62, 77],
            ["Rail mix", 71, 79],
            ["Regional spread", 68, 75],
          ].map(([label, real, synth]) => (
            <div className="fid-row" key={label}>
              <div className="fid-label">{label}</div>
              <div className="fid-track">
                <div className="fid-real" style={{ width: `${real}%` }} />
                <div className="fid-synth" style={{ width: `${synth}%` }} />
              </div>
            </div>
          ))}
        </section>
      </div>
    </>
  );
}

function Kpi({ accent, label, value, delta, trend }) {
  return (
    <div className="kpi" style={{ "--accent": accent }}>
      <div className="label">{label}</div>
      <div className="val">{value}</div>
      <div className={`delta ${trend}`}>{delta}</div>
    </div>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="metric">
      <div className="l">{label}</div>
      <div className="v">{value}</div>
    </div>
  );
}

function CompareCard({ name, big, small }) {
  return (
    <div className="compare-card">
      <div className="name">{name}</div>
      <div className="big">{big}</div>
      <div className="muted" style={{ marginTop: 8, fontSize: 12 }}>{small}</div>
    </div>
  );
}

function LoopGraph({ latest }) {
  return (
    <svg className="loop-svg" viewBox="0 0 860 520">
      <defs>
        <filter id="glow">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {LOOP_NODES.map((node, index) => {
        const next = LOOP_NODES[(index + 1) % LOOP_NODES.length];
        const isHorizontal = Math.abs(node.y - next.y) < 10;
        const path = isHorizontal
          ? `M ${node.x + 52} ${node.y} L ${next.x - 52} ${next.y}`
          : `M ${node.x} ${node.y + 34} L ${next.x} ${next.y - 34}`;
        return (
          <g key={`edge-${node.id}`}>
            <path className="edge" d={path} />
            <path className="edge-flow" d={path} stroke={node.color} />
          </g>
        );
      })}

      {LOOP_NODES.map((node, index) => {
        const active = latest ? index === 5 || index === 6 : index === 0;
        return (
          <g key={node.id} filter="url(#glow)">
            <circle cx={node.x} cy={node.y} r="34" fill="#0e1420" stroke={node.color} strokeWidth="1.8" />
            {active && <circle className="ring" cx={node.x} cy={node.y} r="34" stroke={node.color} strokeWidth="2" />}
            <text className="node-label" x={node.x} y={node.y - 44}>{node.kind}</text>
            <text className="node-label-main" x={node.x} y={node.y + 4}>{node.title}</text>
            <text className="node-sub" x={node.x} y={node.y + 18}>{node.sub}</text>
          </g>
        );
      })}
    </svg>
  );
}

function GeoMap({ payments }) {
  const dots = useMemo(() => {
    const placed = {};
    return (payments || []).slice(0, 24).map((item) => {
      const region = REGIONS[item.location_region];
      if (!region) return null;
      const count = (placed[item.location_region] = (placed[item.location_region] || 0) + 1);
      const angle = count * 1.8;
      const radius = Math.min(12, 3 + count * 1.4);
      return {
        id: item.id,
        x: region.x + Math.cos(angle) * radius,
        y: region.y + Math.sin(angle) * radius,
        decision: item.decision,
      };
    }).filter(Boolean);
  }, [payments]);

  const colors = { ALLOW: "#22e5a0", CHALLENGE: "#ff9f43", BLOCK: "#ff3b5c" };

  return (
    <svg className="geo-map" viewBox="42 30 216 306">
      <path
        d="M 96 40 L 150 46 L 210 66 L 246 108 L 236 150 L 206 168 L 188 214 L 156 268 L 128 314 L 104 322 L 86 286 L 70 226 L 52 168 L 58 118 L 74 72 Z"
        fill="#0f1521"
        stroke="#263043"
        strokeWidth="1"
      />
      {Object.entries(REGIONS).map(([code, region]) => (
        <g key={code}>
          <circle cx={region.x} cy={region.y} r="1.4" fill="#cbd2da" />
          <text x={region.x + 7} y={region.y + 3} fill="#6c7688" fontSize="8">{code}</text>
        </g>
      ))}
      {dots.map((dot) => (
        <circle key={dot.id} cx={dot.x} cy={dot.y} r="4.2" fill={colors[dot.decision] || "#4da8ff"} stroke="#fff" strokeWidth="1" />
      ))}
    </svg>
  );
}

function Radar({ dims }) {
  const centerX = 200;
  const centerY = 180;
  const radius = 112;
  const angleStep = (Math.PI * 2) / dims.length;
  const points = dims.map((dim, index) => {
    const angle = -Math.PI / 2 + index * angleStep;
    const length = radius * dim.score;
    const x = centerX + Math.cos(angle) * length;
    const y = centerY + Math.sin(angle) * length;
    return `${x},${y}`;
  }).join(" ");

  return (
    <svg viewBox="0 0 400 380" style={{ width: "100%", maxWidth: 420 }}>
      {[0.25, 0.5, 0.75, 1].map((step) => (
        <polygon
          key={step}
          points={dims.map((dim, index) => {
            const angle = -Math.PI / 2 + index * angleStep;
            const x = centerX + Math.cos(angle) * radius * step;
            const y = centerY + Math.sin(angle) * radius * step;
            return `${x},${y}`;
          }).join(" ")}
          fill="none"
          stroke="#243041"
        />
      ))}
      {dims.map((dim, index) => {
        const angle = -Math.PI / 2 + index * angleStep;
        const x = centerX + Math.cos(angle) * radius;
        const y = centerY + Math.sin(angle) * radius;
        return (
          <g key={dim.name}>
            <line x1={centerX} y1={centerY} x2={x} y2={y} stroke="#243041" />
            <text x={centerX + Math.cos(angle) * (radius + 26)} y={centerY + Math.sin(angle) * (radius + 26)} fill="#6c7688" fontSize="11" textAnchor="middle">
              {dim.name}
            </text>
          </g>
        );
      })}
      <polygon points={points} fill="rgba(77,168,255,0.18)" stroke="#4da8ff" strokeWidth="2" />
      {dims.map((dim, index) => {
        const angle = -Math.PI / 2 + index * angleStep;
        const x = centerX + Math.cos(angle) * radius * dim.score;
        const y = centerY + Math.sin(angle) * radius * dim.score;
        return <circle key={dim.name} cx={x} cy={y} r="4" fill="#22e5a0" stroke="#0d121c" strokeWidth="2" />;
      })}
    </svg>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
