import React, { useEffect, useRef, useState } from 'react'
import MapView from './Map.jsx'
import Telemetry from './Telemetry.jsx'
import IncidentLog from './IncidentLog.jsx'

const WS_URL = (() => {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  // In dev, vite proxies /ws -> backend. In prod, hit backend directly.
  if (window.location.port === '5173') return `${proto}://${window.location.host}/ws/telemetry`
  return `${proto}://${window.location.hostname}:8000/ws/telemetry`
})()

const API_BASE = (() => {
  if (window.location.port === '5173') return '/api'
  return `http://${window.location.hostname}:8000`
})()

export default function App() {
  const [telemetry, setTelemetry] = useState(null)
  const [missions, setMissions] = useState([])
  const [wsState, setWsState] = useState('connecting')
  const wsRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    let retry = null

    function connect() {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws
      setWsState('connecting')
      ws.onopen = () => setWsState('open')
      ws.onclose = () => {
        setWsState('closed')
        if (!cancelled) retry = setTimeout(connect, 2000)
      }
      ws.onerror = () => setWsState('error')
      ws.onmessage = (ev) => {
        try { setTelemetry(JSON.parse(ev.data)) } catch (e) { /* ignore */ }
      }
    }
    connect()
    return () => { cancelled = true; if (retry) clearTimeout(retry); if (wsRef.current) wsRef.current.close() }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function refresh() {
      try {
        const r = await fetch(`${API_BASE}/missions?limit=50`)
        if (!r.ok) return
        const data = await r.json()
        if (!cancelled) setMissions(data)
      } catch (e) { /* ignore */ }
    }
    refresh()
    const id = setInterval(refresh, 3000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const stateLabel = telemetry?.state ?? 'OFFLINE'
  const pillClass = (() => {
    if (wsState !== 'open') return 'pill err'
    if (['COMPLETED', 'LANDED'].includes(stateLabel)) return 'pill ok'
    if (['ABORTED', 'FAILED'].includes(stateLabel)) return 'pill err'
    if (stateLabel === 'IDLE') return 'pill idle'
    return 'pill warn'
  })()

  async function trigger(lat, lon, priority, incident_type) {
    const r = await fetch(`${API_BASE}/trigger`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat, lon, priority, incident_type })
    })
    return r.json()
  }

  async function addWaypoint(missionId, lat, lon) {
    const r = await fetch(`${API_BASE}/mission/${missionId}/waypoint`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat, lon })
    })
    return r.json()
  }

  return (
    <div className="app">
      <div className="header">
        <h1>DRONE SAFETY VIEWER</h1>
        <span className={pillClass}>{wsState === 'open' ? stateLabel : 'WS ' + wsState.toUpperCase()}</span>
        {telemetry?.mission_id && <span className="pill idle">mission {telemetry.mission_id.slice(0, 8)}</span>}
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: '#8b949e' }}>viewer-only · autonomous flight</span>
      </div>

      <div className="map-wrap">
        <MapView telemetry={telemetry} />
      </div>

      <div className="side">
        <Telemetry telemetry={telemetry} onTrigger={trigger} onAddWaypoint={addWaypoint} />
        <IncidentLog missions={missions} />
      </div>
    </div>
  )
}
