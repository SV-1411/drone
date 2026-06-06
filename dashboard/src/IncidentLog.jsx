import React from 'react'

function fmtTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString()
}

export default function IncidentLog({ missions }) {
  return (
    <div className="section">
      <h2>Incident log</h2>
      {(!missions || missions.length === 0) && <div style={{ fontSize: 12, color: '#8b949e' }}>no incidents yet</div>}
      {missions && missions.map((m) => (
        <div className="incident" key={m.mission_id}>
          <div className="top">
            <span className="id">{m.mission_id.slice(0, 8)}</span>
            <span className={`badge ${m.priority}`}>{m.priority}</span>
          </div>
          <div style={{ marginTop: 4 }}>
            <strong>{m.incident_type}</strong> · {m.target_lat.toFixed(4)}, {m.target_lon.toFixed(4)}
          </div>
          <div style={{ marginTop: 4, display: 'flex', justifyContent: 'space-between', color: '#8b949e' }}>
            <span>{fmtTime(m.queued_at)}</span>
            <span className={`badge ${m.status}`}>{m.status}{m.final_state ? ` · ${m.final_state}` : ''}</span>
          </div>
        </div>
      ))}
    </div>
  )
}
