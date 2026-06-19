import React, { useState } from 'react'

function fmt(v, digits = 2, suffix = '') {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return `${typeof v === 'number' ? v.toFixed(digits) : v}${suffix}`
}

function validCoords(lat, lon) {
  return Number.isFinite(lat) && Number.isFinite(lon) &&
    lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180
}

export default function Telemetry({ telemetry, onTrigger, onAddWaypoint, onCancel }) {
  const t = telemetry || {}
  const [tLat, setTLat] = useState('21.1493')
  const [tLon, setTLon] = useState('79.0884')
  const [prio, setPrio] = useState('normal')
  const [incident, setIncident] = useState('medical')
  const [wLat, setWLat] = useState('')
  const [wLon, setWLon] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const triggerValid = validCoords(parseFloat(tLat), parseFloat(tLon))
  const waypointValid = validCoords(parseFloat(wLat), parseFloat(wLon))
  const missionActive = !!t.mission_id &&
    !['COMPLETED', 'LANDED', 'ABORTED', 'FAILED', 'IDLE'].includes(t.state)

  async function submitTrigger(e) {
    e.preventDefault()
    if (!triggerValid) { setMsg('enter a valid lat/lon'); return }
    setBusy(true); setMsg('')
    try {
      const r = await onTrigger(parseFloat(tLat), parseFloat(tLon), prio, incident)
      if (r.detail) setMsg(`rejected: ${JSON.stringify(r.detail)}`)
      else setMsg(`queued ${r.mission_id} · ETA ~${r.estimated_arrival_s}s`)
    } catch (err) { setMsg(`error: ${err.message}`) }
    finally { setBusy(false) }
  }

  async function submitWaypoint(e) {
    e.preventDefault()
    if (!t.mission_id) { setMsg('no active mission'); return }
    if (!waypointValid) { setMsg('enter a valid lat/lon'); return }
    setBusy(true); setMsg('')
    try {
      const r = await onAddWaypoint(t.mission_id, parseFloat(wLat), parseFloat(wLon))
      if (r.detail) setMsg(`rejected: ${JSON.stringify(r.detail)}`)
      else { setMsg('waypoint queued'); setWLat(''); setWLon('') }
    } catch (err) { setMsg(`error: ${err.message}`) }
    finally { setBusy(false) }
  }

  async function cancelActive() {
    if (!t.mission_id) return
    setBusy(true); setMsg('')
    try {
      const r = await onCancel(t.mission_id)
      setMsg(r.ok ? `cancel: ${r.result} — drone returning home` : `cancel failed: ${JSON.stringify(r.detail)}`)
    } catch (err) { setMsg(`error: ${err.message}`) }
    finally { setBusy(false) }
  }

  return (
    <>
      <div className="section">
        <h2>Telemetry</h2>
        <div className="kv">
          <div className="k">State</div><div className="v">{t.state ?? '—'}</div>
          <div className="k">Mode</div><div className="v">{t.mode ?? '—'}</div>
          <div className="k">Armed</div><div className="v">{t.armed ? 'YES' : 'no'}</div>
          <div className="k">Lat</div><div className="v">{fmt(t.lat, 6)}</div>
          <div className="k">Lon</div><div className="v">{fmt(t.lon, 6)}</div>
          <div className="k">Altitude</div><div className="v">{fmt(t.alt_m, 1, ' m')}</div>
          <div className="k">Ground spd</div><div className="v">{fmt(t.ground_speed_ms, 1, ' m/s')}</div>
          <div className="k">Heading</div><div className="v">{fmt(t.heading_deg, 0, '°')}</div>
          <div className="k">Battery</div><div className="v">{fmt(t.battery_pct, 0, '%')} ({fmt(t.battery_voltage, 1, ' V')})</div>
          <div className="k">GPS</div><div className="v">fix {t.gps_fix ?? '—'} · {t.gps_sats ?? 0} sats</div>
        </div>
      </div>

      <div className="section">
        <h2>Trigger mission</h2>
        <form className="form" onSubmit={submitTrigger}>
          <input type="number" step="0.0001" value={tLat} onChange={(e) => setTLat(e.target.value)} placeholder="lat" />
          <input type="number" step="0.0001" value={tLon} onChange={(e) => setTLon(e.target.value)} placeholder="lon" />
          <select value={prio} onChange={(e) => setPrio(e.target.value)}>
            <option value="low">low</option>
            <option value="normal">normal</option>
            <option value="high">high</option>
            <option value="critical">critical</option>
          </select>
          <input value={incident} onChange={(e) => setIncident(e.target.value)} placeholder="incident type" />
          <button type="submit" disabled={busy || !triggerValid}>Dispatch drone</button>
          <div className="hint">No manual flight — the drone auto-arms, flies, and returns.</div>
          {msg && <div className="hint">{msg}</div>}
        </form>
        {missionActive && (
          <button
            type="button"
            onClick={cancelActive}
            disabled={busy}
            style={{ marginTop: 8, width: '100%', background: '#8b2d2d', color: '#fff', border: 'none', padding: '8px', borderRadius: 4, cursor: 'pointer' }}
          >
            Cancel mission — return home
          </button>
        )}
      </div>

      <div className="section">
        <h2>Add waypoint (optional)</h2>
        <form className="form" onSubmit={submitWaypoint}>
          <input type="number" step="0.0001" value={wLat} onChange={(e) => setWLat(e.target.value)} placeholder="lat" />
          <input type="number" step="0.0001" value={wLon} onChange={(e) => setWLon(e.target.value)} placeholder="lon" />
          <button type="submit" disabled={busy || !t.mission_id || !waypointValid}>Add waypoint</button>
          <div className="hint">Inserted into the active mission only. No manual piloting.</div>
        </form>
      </div>

      <div className="section">
        <h2>Recent log</h2>
        <div className="log">
          {(t.log_tail || []).slice().reverse().map((line, i) => (
            <div className="row" key={i}>{line}</div>
          ))}
          {(!t.log_tail || t.log_tail.length === 0) && <div className="row">no events yet</div>}
        </div>
      </div>
    </>
  )
}
