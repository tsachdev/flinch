import { useState } from 'react'
import { formatTimestamp } from '../time'

function SessionItem({ session }) {
  const [expanded, setExpanded] = useState(false)
  const hasActions = session.actions && session.actions.length > 0

  return (
    <div className="session-item">
      <div className="session-item-row">
        <span className="session-ts">{formatTimestamp(session.timestamp)}</span>
        <p className="session-preview">{session.preview || 'No summary available.'}</p>
        {hasActions && (
          <button className="link-button" onClick={() => setExpanded(!expanded)}>
            {expanded ? 'Hide detail' : 'Show tool calls'}
          </button>
        )}
      </div>
      {expanded && (
        <ul className="session-actions">
          {session.actions.map((a, i) => <li key={i}>{a}</li>)}
        </ul>
      )}
    </div>
  )
}

export default function SessionFeed({ sessions }) {
  if (!sessions || sessions.length === 0) {
    return <div className="empty-state">No sessions yet.</div>
  }
  return (
    <div className="session-feed">
      {sessions.map((s, i) => <SessionItem key={i} session={s} />)}
    </div>
  )
}
