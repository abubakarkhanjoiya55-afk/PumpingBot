const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

export const api = {
  // Channels
  getChannels: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return request(`/channels${q ? '?' + q : ''}`)
  },
  createChannel: (data) => request('/channels', { method: 'POST', body: JSON.stringify(data) }),
  updateChannel: (id, data) => request(`/channels/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteChannel: (id) => request(`/channels/${id}`, { method: 'DELETE' }),
  getChannel: (id) => request(`/channels/${id}`),
  getCategories: () => request('/categories'),

  // Watch Logs
  getWatchLogs: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return request(`/watch-logs${q ? '?' + q : ''}`)
  },
  createWatchLog: (data) => request('/watch-logs', { method: 'POST', body: JSON.stringify(data) }),
  deleteWatchLog: (id) => request(`/watch-logs/${id}`, { method: 'DELETE' }),

  // Goals
  getGoals: () => request('/goals'),
  createGoal: (data) => request('/goals', { method: 'POST', body: JSON.stringify(data) }),
  deleteGoal: (id) => request(`/goals/${id}`, { method: 'DELETE' }),

  // Analytics
  getAnalytics: (days = 30) => request(`/analytics?days=${days}`),
}
