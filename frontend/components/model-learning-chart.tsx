"use client";

/**
 * Hardcoded model learning line chart showing:
 * - Model version progression over time
 * - Attacks blocked going up and down
 */

const S = {
  panel: "#ffffff",
  border: "#e5e7eb",
  red: "#dc2626",
  green: "#16a34a",
  blue: "#2563eb",
  violet: "#7c3aed",
  orange: "#ea580c",
  muted: "#6b7280",
  mutedBg: "#f3f4f6",
};

// Hardcoded data: 4-day model learning snapshot (demo)
const months = ["Day 1", "Day 2", "Day 3", "Day 4"];
const blockedAttacks = [112, 178, 245, 334];
const fraudDetected = [95, 156, 218, 298];
const modelAccuracy = [0.85, 0.91, 0.94, 0.97];
const attackRuns = [350, 480, 580, 710];

const W = 600;
const H = 220;
const PAD = { top: 20, right: 20, bottom: 30, left: 40 };

function scaleX(i: number) {
  return PAD.left + (i / (months.length - 1)) * (W - PAD.left - PAD.right);
}

function scaleY(val: number, max: number) {
  return PAD.top + (1 - val / max) * (H - PAD.top - PAD.bottom);
}

function pathD(data: number[], max: number) {
  return data.map((v, i) => `${i === 0 ? "M" : "L"}${scaleX(i).toFixed(1)},${scaleY(v, max).toFixed(1)}`).join(" ");
}

export default function ModelLearningChart() {
  const maxVal = Math.max(...blockedAttacks, ...attackRuns) * 1.1;

  return (
    <div style={{ background: S.panel, border: `1px solid ${S.border}`, borderRadius: 12, padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Model Learning Progress</div>
          <div style={{ fontSize: 12, color: S.muted }}>FraudShield v1 → v3 improvement over recent days</div>
        </div>
        <div style={{ display: "flex", gap: 12, fontSize: 11 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 12, height: 3, background: S.green, borderRadius: 2, display: "inline-block" }} />
            Attacks Blocked
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 12, height: 3, background: S.blue, borderRadius: 2, display: "inline-block" }} />
            Fraud Detected
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 12, height: 3, background: S.orange, borderRadius: 2, display: "inline-block", borderStyle: "dashed" }} />
            Attack Runs
          </span>
        </div>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto" }}>
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <line
            key={f}
            x1={PAD.left}
            y1={scaleY(maxVal * f, maxVal)}
            x2={W - PAD.right}
            y2={scaleY(maxVal * f, maxVal)}
            stroke={S.border}
            strokeWidth={0.5}
          />
        ))}

        {/* Y-axis labels */}
        {[0, 100, 200, 300, 400].map((v) => (
          <text
            key={v}
            x={PAD.left - 8}
            y={scaleY(v, maxVal) + 3}
            textAnchor="end"
            fontSize={9}
            fill={S.muted}
            fontFamily="'JetBrains Mono', monospace"
          >
            {v}
          </text>
        ))}

        {/* X-axis labels */}
        {months.map((m, i) => (
          <text
            key={m}
            x={scaleX(i)}
            y={H - 8}
            textAnchor="middle"
            fontSize={9}
            fill={S.muted}
            fontFamily="'JetBrains Mono', monospace"
          >
            {m}
          </text>
        ))}

        {/* Attack Runs line (dashed) */}
        <path
          d={pathD(attackRuns, maxVal)}
          fill="none"
          stroke={S.orange}
          strokeWidth={1.5}
          strokeDasharray="4,3"
          opacity={0.6}
        />

        {/* Fraud Detected line */}
        <path
          d={pathD(fraudDetected, maxVal)}
          fill="none"
          stroke={S.blue}
          strokeWidth={2}
          opacity={0.8}
        />

        {/* Attacks Blocked line */}
        <path
          d={pathD(blockedAttacks, maxVal)}
          fill="none"
          stroke={S.green}
          strokeWidth={2.5}
        />

        {/* Dots on blocked line */}
        {blockedAttacks.map((v, i) => (
          <circle
            key={i}
            cx={scaleX(i)}
            cy={scaleY(v, maxVal)}
            r={3}
            fill={S.green}
            stroke="#fff"
            strokeWidth={1.5}
          />
        ))}

        {/* Model version annotations */}
        <text x={scaleX(0)} y={scaleY(blockedAttacks[0], maxVal) - 10} fontSize={9} fill={S.muted} fontFamily="'JetBrains Mono', monospace" textAnchor="middle">v1</text>
        <text x={scaleX(5)} y={scaleY(blockedAttacks[5], maxVal) - 10} fontSize={9} fill={S.muted} fontFamily="'JetBrains Mono', monospace" textAnchor="middle">v2</text>
        <text x={scaleX(9)} y={scaleY(blockedAttacks[9], maxVal) - 10} fontSize={9} fill={S.muted} fontFamily="'JetBrains Mono', monospace" textAnchor="middle">v3</text>

        {/* Version upgrade markers */}
        <line x1={scaleX(5)} y1={PAD.top} x2={scaleX(5)} y2={H - PAD.bottom} stroke={S.violet} strokeWidth={0.8} strokeDasharray="3,3" opacity={0.5} />
        <line x1={scaleX(9)} y1={PAD.top} x2={scaleX(9)} y2={H - PAD.bottom} stroke={S.violet} strokeWidth={0.8} strokeDasharray="3,3" opacity={0.5} />
      </svg>

      {/* Summary row */}
      <div style={{ display: "flex", gap: 16, marginTop: 12, paddingTop: 12, borderTop: `1px solid ${S.border}` }}>
        {[
          { label: "Model Accuracy", value: "97%", change: "+25% since v1", color: S.green },
          { label: "Attacks Blocked", value: "388", change: "+824% YoY", color: S.blue },
          { label: "Avg Detection Latency", value: "84ms", change: "-12ms from v2", color: S.orange },
          { label: "False Positive Rate", value: "1.2%", change: "-2.2% from v1", color: S.violet },
        ].map((stat) => (
          <div key={stat.label} style={{ flex: 1 }}>
            <div style={{ fontSize: 10, color: S.muted, textTransform: "uppercase", letterSpacing: 0.3 }}>{stat.label}</div>
            <div style={{ fontSize: 16, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace", color: stat.color }}>{stat.value}</div>
            <div style={{ fontSize: 10, color: S.green }}>{stat.change}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
