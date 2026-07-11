export default function ApprovalCard({ item, selected, onToggle, onApprove, onReject, onDefer }) {
  return (
    <div className={`approval-card ${selected ? 'approval-card-selected' : ''}`}>
      <input
        type="checkbox"
        className="approval-checkbox"
        checked={selected}
        onChange={() => onToggle(item.id)}
      />
      <div className="approval-body">
        <div className="approval-meta">
          <span className="approval-sender">{item.sender || 'Unknown sender'}</span>
          <span className="approval-source">{item.source === 'outlook' ? 'Outlook' : 'Gmail'}</span>
        </div>
        <div className="approval-subject">{item.subject || '(no subject)'}</div>
        <div className="approval-reason">{item.reason}</div>
      </div>
      <div className="approval-actions">
        <button className="btn btn-approve" onClick={() => onApprove(item.id)}>Delete</button>
        <button className="btn btn-reject" onClick={() => onReject(item.id)}>Keep</button>
        <button className="btn btn-defer" onClick={() => onDefer(item.id)}>Later</button>
      </div>
    </div>
  )
}
