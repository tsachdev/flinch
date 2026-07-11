import { useEffect, useState } from 'react'
import API from '../api'
import ApprovalCard from './ApprovalCard'

export default function ApprovalsView({ pending, onRefresh }) {
  const [selected, setSelected] = useState(new Set())

  useEffect(() => {
    setSelected(new Set())
  }, [pending.length])

  function toggle(id) {
    const next = new Set(selected)
    next.has(id) ? next.delete(id) : next.add(id)
    setSelected(next)
  }

  function toggleAll(checked) {
    setSelected(checked ? new Set(pending.map((p) => p.id)) : new Set())
  }

  async function act(id, action) {
    if (action === 'approve') await API.approve(id)
    else if (action === 'reject') await API.reject(id)
    else if (action === 'later') await API.bulk('later', [id])
    onRefresh()
  }

  async function bulkAct(action) {
    if (selected.size === 0) return
    await API.bulk(action, [...selected])
    onRefresh()
  }

  if (pending.length === 0) {
    return <div className="empty-state">No pending approvals — you're all caught up.</div>
  }

  return (
    <div>
      <div className="bulk-bar">
        <label className="bulk-select-all">
          <input
            type="checkbox"
            checked={selected.size === pending.length}
            onChange={(e) => toggleAll(e.target.checked)}
          />
          Select all ({pending.length})
        </label>
        <button className="btn btn-approve" onClick={() => bulkAct('approve')}>Delete selected</button>
        <button className="btn btn-reject" onClick={() => bulkAct('reject')}>Keep selected</button>
        <button className="btn btn-defer" onClick={() => bulkAct('later')}>Later selected</button>
        {selected.size > 0 && <span className="bulk-count">{selected.size} selected</span>}
      </div>

      <div className="approval-list">
        {pending.map((item) => (
          <ApprovalCard
            key={item.id}
            item={item}
            selected={selected.has(item.id)}
            onToggle={toggle}
            onApprove={(id) => act(id, 'approve')}
            onReject={(id) => act(id, 'reject')}
            onDefer={(id) => act(id, 'later')}
          />
        ))}
      </div>
    </div>
  )
}
