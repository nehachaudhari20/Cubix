"use client"
import { useEffect, useMemo, useRef } from "react"
import L from "leaflet"

const BASE_REGIONS = [
  { name: "North America", lat: 40, lng: -100, weight: 0.18 },
  { name: "Europe", lat: 50, lng: 10, weight: 0.16 },
  { name: "South Asia", lat: 20, lng: 78, weight: 0.28 },
  { name: "East Asia", lat: 35, lng: 115, weight: 0.12 },
  { name: "Africa", lat: 0, lng: 25, weight: 0.1 },
  { name: "South America", lat: -15, lng: -60, weight: 0.09 },
  { name: "Oceania", lat: -25, lng: 135, weight: 0.07 },
]

const TRANSFER_ROUTES = [
  { from: [40, -100], to: [50, 10], risk: "high" },
  { from: [50, 10], to: [20, 78], risk: "high" },
  { from: [20, 78], to: [35, 115], risk: "medium" },
  { from: [40, -100], to: [20, 78], risk: "high" },
  { from: [50, 10], to: [0, 25], risk: "medium" },
  { from: [35, 115], to: [-25, 135], risk: "low" },
  { from: [20, 78], to: [-15, -60], risk: "medium" },
  { from: [40, -100], to: [-15, -60], risk: "low" },
]

type BufferStats = {
  total?: number
  blocked?: number
  bypassed?: number
  families?: string[]
}

function distribute(stats?: BufferStats) {
  const total = Math.max(0, stats?.total || 0)
  const blockedTotal = Math.max(0, stats?.blocked || 0)
  const families = stats?.families || []
  const blockRate = total > 0 ? blockedTotal / Math.max(1, total) : 0.82
  const attackBase = total > 0 ? total : 1718

  return BASE_REGIONS.map((r, i) => {
    const attacks = Math.max(8, Math.round(attackBase * r.weight))
    const blocked = Math.min(attacks, Math.round(attacks * blockRate))
    const slice = families.length
      ? families.filter((_, fi) => fi % BASE_REGIONS.length === i).slice(0, 3)
      : ["ATO-001", "SIF-001", "UPI-003"].slice(0, 2)
    return { ...r, attacks, blocked, families: slice }
  })
}

export default function WorldMap({ bufferStats }: { bufferStats?: BufferStats }) {
  const mapRef = useRef<HTMLDivElement>(null)
  const mapInstance = useRef<L.Map | null>(null)
  const regions = useMemo(() => distribute(bufferStats), [bufferStats])
  const totalKey = bufferStats?.total ?? 0

  useEffect(() => {
    if (!mapRef.current) return

    if (mapInstance.current) {
      mapInstance.current.remove()
      mapInstance.current = null
    }

    const map = L.map(mapRef.current, {
      center: [18, 20],
      zoom: 1.6,
      minZoom: 1,
      maxZoom: 6,
      zoomControl: false,
      attributionControl: false,
      dragging: true,
      scrollWheelZoom: false,
      worldCopyJump: true,
    })

    L.control.zoom({ position: "bottomright" }).addTo(map)

    // Free Carto basemap — no API key required
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png", {
      subdomains: "abcd",
      maxZoom: 19,
      crossOrigin: true,
    }).addTo(map)

    // Soft label layer for geography (also free)
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png", {
      subdomains: "abcd",
      maxZoom: 19,
      opacity: 0.55,
      crossOrigin: true,
    }).addTo(map)

    const base = Math.max(70, totalKey || 1718)

    regions.forEach((region) => {
      const radius = Math.max(8, Math.min(24, region.attacks / Math.max(12, base / 25)))
      const blockedRate = region.attacks ? region.blocked / region.attacks : 0
      const color = blockedRate > 0.85 ? "#16a34a" : blockedRate > 0.7 ? "#ea580c" : "#dc2626"

      L.circleMarker([region.lat, region.lng], {
        radius: radius + 8,
        fillColor: color,
        fillOpacity: 0.12,
        stroke: false,
      }).addTo(map)

      const circle = L.circleMarker([region.lat, region.lng], {
        radius,
        fillColor: color,
        fillOpacity: 0.65,
        color,
        weight: 2,
        opacity: 0.9,
      }).addTo(map)

      circle.bindPopup(`
        <div style="font-family: 'Space Grotesk', sans-serif; min-width: 180px;">
          <div style="font-weight: 600; font-size: 13px; margin-bottom: 6px;">${region.name}</div>
          <div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">Attacks: <b style="color: #dc2626">${region.attacks}</b></div>
          <div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">Blocked: <b style="color: #16a34a">${region.blocked}</b> (${(blockedRate * 100).toFixed(0)}%)</div>
          <div style="font-size: 10px; color: #9ca3af; margin-top: 6px;">Families: ${region.families.join(", ") || "—"}</div>
        </div>
      `)
    })

    const routeColors: Record<string, string> = {
      high: "#dc2626",
      medium: "#ea580c",
      low: "#9ca3af",
    }

    TRANSFER_ROUTES.forEach((route) => {
      L.polyline([route.from as L.LatLngExpression, route.to as L.LatLngExpression], {
        color: routeColors[route.risk],
        weight: 1.5,
        opacity: 0.45,
        dashArray: route.risk === "low" ? "4 6" : undefined,
      }).addTo(map)
    })

    mapInstance.current = map

    // Fix grey tiles when container size settles
    const t = window.setTimeout(() => {
      map.invalidateSize()
    }, 120)

    return () => {
      window.clearTimeout(t)
      map.remove()
      mapInstance.current = null
    }
  }, [regions, totalKey])

  return (
    <div style={{ position: "relative" }}>
      <div
        ref={mapRef}
        style={{
          width: "100%",
          height: 260,
          borderRadius: 12,
          background: "#e8eef5",
          overflow: "hidden",
          border: "1px solid #e5e7eb",
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: 10,
          left: 10,
          display: "flex",
          gap: 10,
          fontSize: 10,
          color: "#6b7280",
          background: "rgba(255,255,255,0.92)",
          padding: "4px 8px",
          borderRadius: 6,
          border: "1px solid #e5e7eb",
        }}
      >
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#16a34a" }} />
          High block
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#ea580c" }} />
          Medium
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#dc2626" }} />
          Low block
        </span>
      </div>
    </div>
  )
}
