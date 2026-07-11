const API = {
  roles() {
    return fetchJSON('/api/roles')
  },
  roleSessions(role, limit = 20) {
    return fetchJSON(`/api/roles/${role}/sessions?limit=${limit}`)
  },
  pending() {
    return fetchJSON('/api/pending')
  },
  approve(taskId) {
    return postJSON(`/api/pending/${taskId}/approve`)
  },
  reject(taskId) {
    return postJSON(`/api/pending/${taskId}/reject`)
  },
  bulk(action, ids) {
    return postJSON('/api/pending/bulk', { action, ids })
  },
  updateSkill(role, feedback) {
    return postJSON(`/update-skill/${role}`, { feedback })
  },
  watchlist() {
    return fetchJSON('/api/watchlist')
  },
}

async function fetchJSON(path) {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json()
}

async function postJSON(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  })
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json()
}

export default API
