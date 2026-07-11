import { useCallback, useEffect, useState } from 'react'
import API from './api'
import RoleCard from './components/RoleCard'
import SessionFeed from './components/SessionFeed'
import ApprovalsView from './components/ApprovalsView'
import SkillPanel from './components/SkillPanel'
import './App.css'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'approvals', label: 'Approvals' },
  { id: 'skills', label: 'Skills' },
]

export default function App() {
  const [tab, setTab] = useState('overview')
  const [roles, setRoles] = useState([])
  const [pending, setPending] = useState([])
  const [openRole, setOpenRole] = useState(null)
  const [roleSessions, setRoleSessions] = useState(null)
  const [loaded, setLoaded] = useState(false)

  const refresh = useCallback(async () => {
    const [rolesRes, pendingRes] = await Promise.all([API.roles(), API.pending()])
    setRoles(rolesRes.roles)
    setPending(pendingRes.pending)
    setLoaded(true)
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 30000)
    return () => clearInterval(interval)
  }, [refresh])

  useEffect(() => {
    if (!openRole) {
      setRoleSessions(null)
      return
    }
    API.roleSessions(openRole).then((res) => setRoleSessions(res.sessions))
  }, [openRole])

  const pendingCount = pending.length

  return (
    <div className="app">
      <header className="header">
        <div className="header-brand">
          <svg viewBox="0 0 50 30" width="26" height="18" aria-hidden="true">
            <polyline points="2,15 10,15 14,4 18,26 22,8 26,15 38,15 48,15"
              fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>Flinch</span>
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`tab ${tab === t.id ? 'tab-active' : ''}`}
              onClick={() => { setTab(t.id); setOpenRole(null) }}
            >
              {t.label}
              {t.id === 'approvals' && pendingCount > 0 && (
                <span className="badge">{pendingCount}</span>
              )}
            </button>
          ))}
        </nav>
      </header>

      <main className="main">
        {!loaded && <div className="empty-state">Loading…</div>}

        {loaded && tab === 'overview' && !openRole && (
          <div className="role-grid">
            {roles.map((r) => (
              <RoleCard key={r.role} role={r} onOpen={setOpenRole} />
            ))}
          </div>
        )}

        {loaded && tab === 'overview' && openRole && (
          <div>
            <button className="link-button back-button" onClick={() => setOpenRole(null)}>
              ← Back to overview
            </button>
            <h2 className="section-title">
              {roles.find((r) => r.role === openRole)?.label} — run history
            </h2>
            {roleSessions === null
              ? <div className="empty-state">Loading…</div>
              : <SessionFeed sessions={roleSessions} />}
          </div>
        )}

        {loaded && tab === 'approvals' && (
          <ApprovalsView pending={pending} onRefresh={refresh} />
        )}

        {loaded && tab === 'skills' && <SkillPanel />}
      </main>
    </div>
  )
}
