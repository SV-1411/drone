import React, { useMemo } from 'react'
import { MapContainer, TileLayer, Marker, Polyline, Popup, CircleMarker, useMap } from 'react-leaflet'
import L from 'leaflet'

// Default Leaflet markers reference local images that Vite can't resolve.
// Bundle them via imports so the dashboard works without internet access
// (field deployments often have no WAN).
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

function droneIcon(headingDeg) {
  const h = Number.isFinite(headingDeg) ? headingDeg : 0
  const html = `
    <div class="drone-marker" style="transform: rotate(${h}deg); width: 28px; height: 28px;">
      <svg viewBox="0 0 24 24" width="28" height="28" xmlns="http://www.w3.org/2000/svg">
        <polygon points="12,2 20,22 12,17 4,22" fill="#58a6ff" stroke="#0d1117" stroke-width="1.2" stroke-linejoin="round"/>
      </svg>
    </div>`
  return L.divIcon({ html, className: '', iconSize: [28, 28], iconAnchor: [14, 14] })
}

function homeIcon() {
  const html = `
    <div style="width: 24px; height: 24px;">
      <svg viewBox="0 0 24 24" width="24" height="24"><circle cx="12" cy="12" r="10" fill="#1f6f3a" stroke="#0d1117" stroke-width="2"/><text x="12" y="16" font-size="12" font-family="Arial" font-weight="bold" fill="#fff" text-anchor="middle">H</text></svg>
    </div>`
  return L.divIcon({ html, className: '', iconSize: [24, 24], iconAnchor: [12, 12] })
}

function targetIcon() {
  const html = `
    <div style="width: 24px; height: 24px;">
      <svg viewBox="0 0 24 24" width="24" height="24"><circle cx="12" cy="12" r="10" fill="#d29922" stroke="#0d1117" stroke-width="2"/><circle cx="12" cy="12" r="4" fill="#0d1117"/></svg>
    </div>`
  return L.divIcon({ html, className: '', iconSize: [24, 24], iconAnchor: [12, 12] })
}

function Recenter({ lat, lon, enabled }) {
  const map = useMap()
  React.useEffect(() => {
    if (enabled && Number.isFinite(lat) && Number.isFinite(lon)) {
      map.panTo([lat, lon], { animate: true, duration: 0.4 })
    }
  }, [lat, lon, map, enabled])
  return null
}

export default function MapView({ telemetry, follow = true }) {
  const home = telemetry ? [telemetry.home_lat, telemetry.home_lon] : [28.6139, 77.2090]
  const drone = telemetry && Number.isFinite(telemetry.lat) ? [telemetry.lat, telemetry.lon] : null
  const target = telemetry && Number.isFinite(telemetry.target_lat) ? [telemetry.target_lat, telemetry.target_lon] : null

  const path = useMemo(() => {
    if (!telemetry?.path) return []
    return telemetry.path.map((p) => [p.lat, p.lon])
  }, [telemetry])

  const center = drone || target || home

  return (
    <MapContainer center={center} zoom={15} style={{ width: '100%', height: '100%' }} scrollWheelZoom>
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
      />

      <Marker position={home} icon={homeIcon()}>
        <Popup>Home base<br/>{home[0].toFixed(5)}, {home[1].toFixed(5)}</Popup>
      </Marker>

      {target && (
        <Marker position={target} icon={targetIcon()}>
          <Popup>Target<br/>{target[0].toFixed(5)}, {target[1].toFixed(5)}</Popup>
        </Marker>
      )}

      {path.length > 1 && (
        <Polyline positions={path} pathOptions={{ color: '#58a6ff', weight: 3, opacity: 0.85 }} />
      )}

      {drone && (
        <>
          <CircleMarker center={drone} radius={18} pathOptions={{ color: '#58a6ff', fillOpacity: 0.05, weight: 1 }} />
          <Marker position={drone} icon={droneIcon(telemetry.heading_deg)}>
            <Popup>
              Drone<br/>
              {drone[0].toFixed(5)}, {drone[1].toFixed(5)}<br/>
              alt {telemetry.alt_m?.toFixed?.(1) ?? '—'} m
            </Popup>
          </Marker>
          <Recenter lat={drone[0]} lon={drone[1]} enabled={follow} />
        </>
      )}
    </MapContainer>
  )
}
