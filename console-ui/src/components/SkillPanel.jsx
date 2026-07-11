import { useState } from 'react'
import API from '../api'

const SKILL_UI = {
  email_reviewer: {
    title: 'Email review behaviour',
    placeholder: "e.g. Don't flag Chamath newsletters as junk — I want to keep those",
  },
  market_watcher: {
    title: 'Market watcher behaviour',
    placeholder: 'e.g. Also flag ex-dividend dates, not just earnings',
  },
}

function SkillCard({ role, config }) {
  const [feedback, setFeedback] = useState('')
  const [status, setStatus] = useState(null) // null | 'saving' | 'ok' | 'error'

  async function submit() {
    if (!feedback.trim()) return
    setStatus('saving')
    try {
      const res = await API.updateSkill(role, feedback.trim())
      if (res.status === 'ok') {
        setStatus('ok')
        setFeedback('')
      } else {
        setStatus('error')
      }
    } catch {
      setStatus('error')
    }
  }

  return (
    <div className="card skill-card">
      <h3>{config.title}</h3>
      <p className="skill-hint">
        Describe what you want the agent to do differently, in plain English.
        The skill file updates automatically.
      </p>
      <textarea
        rows={3}
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        placeholder={config.placeholder}
      />
      <div className="skill-actions">
        <button className="btn btn-primary" onClick={submit} disabled={status === 'saving'}>
          {status === 'saving' ? 'Updating…' : 'Update skill'}
        </button>
        {status === 'ok' && <span className="skill-status skill-status-ok">Updated</span>}
        {status === 'error' && <span className="skill-status skill-status-error">Something went wrong</span>}
      </div>
    </div>
  )
}

export default function SkillPanel() {
  return (
    <div className="skill-panel">
      {Object.entries(SKILL_UI).map(([role, config]) => (
        <SkillCard key={role} role={role} config={config} />
      ))}
    </div>
  )
}
