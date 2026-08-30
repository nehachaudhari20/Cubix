"use client"

/**
 * RedBlue closed-loop architecture — highlights Red Team, Sandbox, Blue Team
 * and the two learning loops (A: Red learns, B: Blue hardens).
 */
export default function ArchitectureLoop({
  activePillar,
}: {
  activePillar?: "red" | "sandbox" | "blue" | null
  callout?: {
    family?: string
    outcome?: string
    risk?: string
    step?: string
  }
}) {
  const dim = (pillar: string) =>
    activePillar && activePillar !== pillar ? 0.35 : 1

  return (
    <div style={{ position: "relative", width: "100%" }}>
      <svg viewBox="0 0 900 520" style={{ width: "100%", height: "auto", display: "block" }}>
        <defs>
          <marker id="arr" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#9ca3af" />
          </marker>
          <style>{`
            @keyframes flowDash { to { stroke-dashoffset: -100; } }
            .flow { stroke-dasharray: 6 8; animation: flowDash 2.2s linear infinite; fill: none; stroke-width: 2; }
            @keyframes pulseRing {
              0% { r: 42; opacity: .45; }
              100% { r: 70; opacity: 0; }
            }
            .pring { animation: pulseRing 2.4s ease-out infinite; fill: none; }
          `}</style>
        </defs>

        {/* Zone backgrounds */}
        <rect x="24" y="70" width="250" height="380" rx="16" fill="#fef2f2" stroke="#fecaca" strokeWidth="1.5" opacity={dim("red")} />
        <rect x="310" y="70" width="280" height="380" rx="16" fill="#eff6ff" stroke="#bfdbfe" strokeWidth="1.5" opacity={dim("sandbox")} />
        <rect x="626" y="70" width="250" height="380" rx="16" fill="#f0fdf4" stroke="#bbf7d0" strokeWidth="1.5" opacity={dim("blue")} />

        <text x="149" y="98" textAnchor="middle" fontSize="13" fontWeight="700" fill="#dc2626" opacity={dim("red")}>RED TEAM</text>
        <text x="450" y="98" textAnchor="middle" fontSize="13" fontWeight="700" fill="#2563eb" opacity={dim("sandbox")}>SANDBOX</text>
        <text x="751" y="98" textAnchor="middle" fontSize="13" fontWeight="700" fill="#16a34a" opacity={dim("blue")}>BLUE TEAM</text>

        {/* KB top */}
        <rect x="330" y="16" width="240" height="40" rx="10" fill="#fff" stroke="#e5e7eb" strokeWidth="1.5" />
        <text x="450" y="34" textAnchor="middle" fontSize="11" fontWeight="600" fill="#111827">Knowledge Base</text>
        <text x="450" y="48" textAnchor="middle" fontSize="9" fill="#6b7280" fontFamily="'JetBrains Mono', monospace">families · variants · relations</text>

        {/* Red nodes */}
        <g opacity={dim("red")}>
          <Node cx={149} cy={160} r={28} color="#7c3aed" label="Threat Hunter" sub="hypotheses" />
          <Node cx={90} cy={280} r={24} color="#7c3aed" label="Planner" sub="campaign" />
          <Node cx={210} cy={280} r={24} color="#7c3aed" label="Generator" sub="payloads" />
          <Node cx={90} cy={400} r={22} color="#a78bfa" label="Memory" sub="lessons" />
          <Node cx={210} cy={400} r={22} color="#a78bfa" label="Strategy" sub="next move" />
        </g>

        {/* Sandbox nodes */}
        <g opacity={dim("sandbox")}>
          <circle className="pring" cx={450} cy={260} stroke="#2563eb" strokeWidth="1.5" style={{ animationDelay: "0s" } as any} />
          <circle className="pring" cx={450} cy={260} stroke="#2563eb" strokeWidth="1.5" style={{ animationDelay: "0.8s" } as any} />
          <Node cx={450} cy={260} r={42} color="#2563eb" label="Payment Sandbox" sub="engines · risk · auth" big />
          <Node cx={380} cy={400} r={22} color="#3b82f6" label="Risk Engine" sub="unified risk" />
          <Node cx={520} cy={400} r={22} color="#3b82f6" label="Authorization" sub="ALLOW/BLOCK" />
        </g>

        {/* Blue nodes */}
        <g opacity={dim("blue")}>
          <Node cx={751} cy={170} r={28} color="#16a34a" label="RedBlue Model" sub="ensemble v3" />
          <Node cx={700} cy={300} r={24} color="#22c55e" label="Adv. Buffer" sub="evidence" />
          <Node cx={800} cy={300} r={24} color="#22c55e" label="Retrain" sub="harden" />
          <Node cx={751} cy={410} r={22} color="#86efac" label="Failure Anal." sub="gaps → Blue" />
        </g>

        {/* Edges — static */}
        <path d="M450 56 L450 100" stroke="#d1d5db" strokeWidth="1.5" markerEnd="url(#arr)" fill="none" />
        <path d="M370 56 Q 200 80 149 132" stroke="#d1d5db" strokeWidth="1.5" fill="none" markerEnd="url(#arr)" />

        {/* Animated flow: Red → Sandbox → Blue → loops */}
        <path className="flow" d="M238 280 Q 320 260 408 260" stroke="rgba(220,38,38,.75)" markerEnd="url(#arr)" />
        <path className="flow" d="M450 302 L450 360" stroke="rgba(37,99,235,.75)" style={{ animationDelay: ".3s" } as any} />
        <path className="flow" d="M408 400 Q 500 400 530 400" stroke="rgba(37,99,235,.6)" style={{ animationDelay: ".5s" } as any} />
        <path className="flow" d="M542 390 Q 640 340 700 310" stroke="rgba(22,163,74,.75)" style={{ animationDelay: ".7s" } as any} />
        <path className="flow" d="M724 170 Q 620 180 492 230" stroke="rgba(22,163,74,.55)" style={{ animationDelay: "1s" } as any} />

        {/* Loop A label */}
        <path d="M110 422 Q 60 340 125 188" fill="none" stroke="#fca5a5" strokeWidth="1.5" strokeDasharray="4 4" markerEnd="url(#arr)" />
        <text x="48" y="310" fontSize="9" fill="#dc2626" fontWeight="600" transform="rotate(-70 48 310)">Loop A · Red learns</text>

        {/* Loop B label */}
        <path d="M800 324 Q 860 260 779 198" fill="none" stroke="#86efac" strokeWidth="1.5" strokeDasharray="4 4" markerEnd="url(#arr)" />
        <text x="868" y="270" fontSize="9" fill="#16a34a" fontWeight="600" transform="rotate(70 868 270)">Loop B · Blue hardens</text>

        {/* Failure analyzer feed from sandbox */}
        <path className="flow" d="M520 422 Q 620 450 751 432" stroke="rgba(124,58,237,.55)" style={{ animationDelay: "1.2s" } as any} />
        <path d="M729 410 Q 400 470 210 422" fill="none" stroke="#c4b5fd" strokeWidth="1.2" strokeDasharray="3 5" markerEnd="url(#arr)" />
      </svg>

      <div style={{ display: "flex", gap: 16, justifyContent: "center", fontSize: 11, color: "#6b7280", marginTop: 4 }}>
        <span><span style={{ color: "#dc2626", fontWeight: 600 }}>●</span> Loop A — sandbox outcomes → Memory/Strategy → next Red campaign</span>
        <span><span style={{ color: "#16a34a", fontWeight: 600 }}>●</span> Loop B — Adv. Buffer → Retrain → RedBlue scores feed Sandbox</span>
      </div>
    </div>
  )
}

function Node({
  cx,
  cy,
  r,
  color,
  label,
  sub,
  big,
}: {
  cx: number
  cy: number
  r: number
  color: string
  label: string
  sub: string
  big?: boolean
}) {
  return (
    <g>
      <circle cx={cx} cy={cy} r={r + 5} fill={color} opacity={0.12} />
      <circle cx={cx} cy={cy} r={r} fill="#fff" stroke={color} strokeWidth={big ? 2.5 : 1.6} />
      {big ? (
        <>
          <text x={cx} y={cy - 4} textAnchor="middle" fontSize="11" fontWeight="700" fill="#111827">Sandbox</text>
          <text x={cx} y={cy + 10} textAnchor="middle" fontSize="8" fill="#6b7280">{sub}</text>
        </>
      ) : (
        <text x={cx} y={cy + 3} textAnchor="middle" fontSize="8.5" fontWeight="600" fill="#111827">
          {label.length > 12 ? label.split(" ")[0] : label}
        </text>
      )}
      <text x={cx} y={cy + r + 14} textAnchor="middle" fontSize="9.5" fontWeight="600" fill="#374151">
        {label}
      </text>
      <text x={cx} y={cy + r + 26} textAnchor="middle" fontSize="8" fill="#9ca3af" fontFamily="'JetBrains Mono', monospace">
        {sub}
      </text>
    </g>
  )
}
