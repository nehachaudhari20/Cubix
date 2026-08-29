"use client"
import { usePathname } from "next/navigation"

const navItems = [
  { href: "/mission-control", label: "Overview", icon: "O" },
  { href: "/red-team", label: "Red Team", icon: "R" },
  { href: "/red-team/chat", label: "Attack Designer", icon: "A" },
  { href: "/sandbox", label: "Sandbox", icon: "S" },
  { href: "/blue-team", label: "Blue Team", icon: "B" },
  { href: "/labs", label: "Labs", icon: "L" },
  { href: "/evaluation", label: "Evaluation", icon: "E" },
]

export default function Sidebar() {
  const pathname = usePathname()

  return (
    <aside
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        bottom: 0,
        width: 240,
        background: "#ffffff",
        borderRight: "1px solid #e5e7eb",
        display: "flex",
        flexDirection: "column",
        zIndex: 100,
      }}
    >
      <div style={{ padding: "24px 20px", borderBottom: "1px solid #e5e7eb" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
            <rect width="36" height="36" rx="10" fill="url(#grad)" />
            <path d="M10 18L14 10L22 14L18 22L10 18Z" fill="white" opacity="0.9" />
            <path d="M18 22L26 18L22 10L14 14L18 22Z" fill="white" opacity="0.7" />
            <defs>
              <linearGradient id="grad" x1="0" y1="0" x2="36" y2="36">
                <stop offset="0%" stopColor="#dc2626" />
                <stop offset="100%" stopColor="#2563eb" />
              </linearGradient>
            </defs>
          </svg>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "#111827", letterSpacing: ".5px" }}>REDBLUE</div>
            <div style={{ fontSize: 11, color: "#6b7280", marginTop: 1 }}>Payment Defense Twin</div>
          </div>
        </div>
      </div>

      <nav style={{ flex: 1, padding: "16px 12px", overflowY: "auto" }}>
        {navItems.map((item) => {
          const active =
            item.href === "/red-team"
              ? pathname === "/red-team"
              : pathname === item.href ||
                (item.href !== "/mission-control" && pathname.startsWith(item.href))
          return (
            <a
              key={item.href}
              href={item.href}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "10px 14px",
                borderRadius: 8,
                marginBottom: 2,
                textDecoration: "none",
                fontSize: 13,
                fontWeight: active ? 600 : 400,
                color: active ? "#dc2626" : "#374151",
                background: active ? "#fef2f2" : "transparent",
                transition: "all .15s",
              }}
            >
              <span
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: 6,
                  background: active ? "#dc2626" : "#f3f4f6",
                  color: active ? "#fff" : "#6b7280",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 12,
                  fontWeight: 600,
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                {item.icon}
              </span>
              {item.label}
            </a>
          )
        })}
      </nav>

      <div style={{ padding: "16px 20px", borderTop: "1px solid #e5e7eb" }}>
        <div style={{ fontSize: 11, color: "#6b7280", lineHeight: 1.5 }}>
          <div style={{ fontWeight: 500, color: "#374151" }}>Mastercard Innovation Challenge</div>
          <div>2026 · AI Defense Lab</div>
        </div>
        <div
          style={{
            marginTop: 8,
            padding: "6px 10px",
            background: "#f0fdf4",
            borderRadius: 6,
            fontSize: 10,
            color: "#16a34a",
            fontWeight: 500,
          }}
        >
          SYNTHETIC DATA ONLY
        </div>
      </div>
    </aside>
  )
}
