"use client"
import { useEffect, useRef } from "react"
import L from "leaflet"

const ATTACK_REGIONS = [
  { name: "North America", lat: 40, lng: -100, attacks: 342, blocked: 298, families: ["ATO-001", "UPI-003", "DEV-007"] },
  { name: "Europe", lat: 50, lng: 10, attacks: 287, blocked: 251, families: ["SIF-001", "MUL-002", "MRC-003"] },
  { name: "South Asia", lat: 20, lng: 78, attacks: 512, blocked: 443, families: ["UPI-003", "OTP-004", "QR-005"] },
  { name: "East Asia", lat: 35, lng: 115, attacks: 198, blocked: 176, families: ["DEV-007", "SYN-006", "ATO-001"] },
  { name: "Africa", lat: 0, lng: 25, attacks: 156, blocked: 131, families: ["MUL-002", "BEN-008", "UPI-003"] },
  { name: "South America", lat: -15, lng: -60, attacks: 134, blocked: 118, families: ["MRC-003", "DEV-007", "SYN-006"] },
  { name: "Oceania", lat: -25, lng: 135, attacks: 89, blocked: 82, families: ["ATO-001", "UPI-003", "QR-005"] },
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

export default function WorldMap() {
  const mapRef = useRef<HTMLDivElement>(null)
  const mapInstance = useRef<L.Map | null>(null)

  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return

    const map = L.map(mapRef.current, {
      center: [20, 10],
      zoom: 2,
      minZoom: 2,
      maxZoom: 6,
      zoomControl: false,
      attributionControl: false,
      dragging: true,
      scrollWheelZoom: false,
    })

    L.control.zoom({ position: "bottomright" }).addTo(map)

    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png", {
      subdomains: "abcd",
      maxZoom: 19,
    }).addTo(map)

    // Add attack region markers
    ATTACK_REGIONS.forEach((region) => {
      const radius = Math.max(8, Math.min(20, region.attacks / 30))
      const blockedRate = region.blocked / region.attacks
      const color = blockedRate > 0.85 ? "#16a34a" : blockedRate > 0.7 ? "#ea580c" : "#dc2626"

      const circle = L.circleMarker([region.lat, region.lng], {
        radius,
        fillColor: color,
        fillOpacity: 0.6,
        color: color,
        weight: 2,
        opacity: 0.8,
      }).addTo(map)

      circle.bindPopup(`
        <div style="font-family: 'Space Grotesk', sans-serif; min-width: 180px;">
          <div style="font-weight: 600; font-size: 13px; margin-bottom: 6px;">${region.name}</div>
          <div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">Attacks: <b style="color: #dc2626">${region.attacks}</b></div>
          <div style="font-size: 11px; color: #6b7280; margin-bottom: 4px;">Blocked: <b style="color: #16a34a">${region.blocked}</b> (${(blockedRate * 100).toFixed(0)}%)</div>
          <div style="font-size: 10px; color: #9ca3af; margin-top: 6px;">Families: ${region.families.join(", ")}</div>
        </div>
      `)

      // Pulse animation
      L.circleMarker([region.lat, region.lng], {
        radius: radius + 6,
        fillColor: color,
        fillOpacity: 0.15,
        stroke: false,
      }).addTo(map)
    })

    // Add transfer route lines
    const routeColors: Record<string, string> = {
      high: "#dc2626",
      medium: "#ea580c",
      low: "#9ca3af",
    }

    TRANSFER_ROUTES.forEach((route) => {
      L.polyline([route.from as L.LatLngExpression, route.to as L.LatLngExpression], {
        color: routeColors[route.risk],
        weight: 1.5,
        opacity: 0.5,
        dashArray: route.risk === "low" ? "4 6" : undefined,
      }).addTo(map)
    })

    mapInstance.current = map

    return () => {
      map.remove()
      mapInstance.current = null
    }
  }, [])

  return (
    <div style={{ position: "relative" }}>
      <div ref={mapRef} style={{ width: "100%", height: 280, borderRadius: 12, background: "#f9fafb" }} />
      <div style={{ position: "absolute", bottom: 8, left: 8, display: "flex", gap: 10, fontSize: 10, color: "#6b7280", background: "rgba(255,255,255,0.9)", padding: "4px 8px", borderRadius: 6 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: "50%", background: "#16a34a" }} />High block rate</span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: "50%", background: "#ea580c" }} />Medium</span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, borderRadius: "50%", background: "#dc2626" }} />Low block rate</span>
      </div>
    </div>
  )
}
