import { formatRelative } from '../time'

const ROLE_ICONS = {
  support_agent: '🎧',
  email_reviewer: '📬',
  personal_assistant: '💬',
  market_watcher: '📈',
}

export default function RoleCard({ role, onOpen }) {
  const isRunning = role.status === 'running'
  return (
    <button className="role-card" onClick={() => onOpen(role.role)}>
      <div className="role-card-top">
        <span className="role-icon" aria-hidden="true">{ROLE_ICONS[role.role] || '⚡'}</span>
        <span className="role-name">{role.label}</span>
        <span className={`status-pill ${isRunning ? 'status-running' : 'status-idle'}`}>
          <span className="status-dot" />
          {isRunning ? 'Running' : 'Idle'}
        </span>
      </div>

      <p className="role-summary">{role.summary}</p>

      <div className="role-card-footer">
        <span>Last run: {formatRelative(role.last_run)}</span>
        <span>{role.next_run ? `Next: ${formatRelative(role.next_run)}` : 'Event-driven'}</span>
      </div>
    </button>
  )
}
