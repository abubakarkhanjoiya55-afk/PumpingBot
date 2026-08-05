import React, { useEffect, useState, useCallback } from 'react'
import { api } from '../lib/api'
import { useToast } from '../context/AppContext'

function LogVideoModal({ channels, onClose, onSave }) {
  const [form, setForm] = useState({
    channel_id: '', video_title: '', video_url: '',
    duration_minutes: '', notes: '', watched_at: '',
  })

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.channel_id || !form.video_title || !form.duration_minutes) return
    await onSave({
      ...form,
      channel_id: parseInt(form.channel_id),
      duration_minutes: parseFloat(form.duration_minutes),
      watched_at: form.watched_at || undefined,
    })
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-title">
          <span>▶️</span> Log a Video
        </div>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Channel *</label>
            <select className="form-select" required value={form.channel_id}
              onChange={e => setForm(p => ({ ...p, channel_id: e.target.value }))}>
              <option value="">Select a channel...</option>
              {channels.map(ch => (
                <option key={ch.id} value={ch.id}>{ch.name}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Video Title *</label>
            <input className="form-input" required value={form.video_title}
              onChange={e => setForm(p => ({ ...p, video_title: e.target.value }))}
              placeholder="Enter video title..." />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Duration (minutes) *</label>
              <input className="form-input" type="number" required min="0.5" step="0.5"
                value={form.duration_minutes}
                onChange={e => setForm(p => ({ ...p, duration_minutes: e.target.value }))}
                placeholder="e.g. 15.5" />
            </div>
            <div className="form-group">
              <label className="form-label">Watched At</label>
              <input className="form-input" type="datetime-local" value={form.watched_at}
                onChange={e => setForm(p => ({ ...p, watched_at: e.target.value }))} />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Video URL</label>
            <input className="form-input" value={form.video_url}
              onChange={e => setForm(p => ({ ...p, video_url: e.target.value }))}
              placeholder="https://youtube.com/watch?v=..." />
          </div>

          <div className="form-group">
            <label className="form-label">Notes</label>
            <textarea className="form-textarea" value={form.notes}
              onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
              placeholder="Any notes about this video..." />
          </div>

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary">Log Video</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function DurationBadge({ minutes }) {
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  const text = h > 0 ? (m > 0 ? `${h}h ${m}m` : `${h}h`) : `${Math.round(minutes)}m`
  return (
    <span className="badge badge-cyan">{text}</span>
  )
}

export default function WatchHistory() {
  const [logs, setLogs] = useState([])
  const [channels, setChannels] = useState([])
  const [loading, setLoading] = useState(true)
  const [showLog, setShowLog] = useState(false)
  const [search, setSearch] = useState('')
  const [filterChannel, setFilterChannel] = useState('')
  const [page, setPage] = useState(0)
  const toast = useToast()
  const PAGE_SIZE = 20

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const [logsData, chData] = await Promise.all([
        api.getWatchLogs({ limit: 200 }),
        api.getChannels(),
      ])
      setLogs(logsData)
      setChannels(chData)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const handleLog = async (form) => {
    try {
      await api.createWatchLog(form)
      toast('Video logged!', 'success')
      setShowLog(false)
      fetchData()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const handleDelete = async (log) => {
    if (!confirm(`Remove "${log.video_title}" from watch history?`)) return
    try {
      await api.deleteWatchLog(log.id)
      toast('Watch log removed', 'success')
      fetchData()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const filtered = logs.filter(log => {
    const matchSearch = !search ||
      log.video_title.toLowerCase().includes(search.toLowerCase()) ||
      log.channel_name?.toLowerCase().includes(search.toLowerCase())
    const matchCh = !filterChannel || log.channel_id === parseInt(filterChannel)
    return matchSearch && matchCh
  })

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  const totalMinutes = filtered.reduce((a, l) => a + l.duration_minutes, 0)

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">▶️ Watch History</div>
          <div className="page-subtitle">
            {filtered.length} videos · {Math.round(totalMinutes / 60 * 10) / 10}h total
          </div>
        </div>
        <button className="btn btn-primary" onClick={() => setShowLog(true)}>
          + Log Video
        </button>
      </div>

      <div className="page-body">
        <div className="toolbar" style={{ marginBottom: '20px' }}>
          <div className="search-wrapper">
            <span className="search-icon">🔍</span>
            <input className="search-input" placeholder="Search videos or channels..."
              value={search} onChange={e => { setSearch(e.target.value); setPage(0) }} />
          </div>
          <select className="form-select" style={{ width: 'auto', minWidth: '160px' }}
            value={filterChannel} onChange={e => { setFilterChannel(e.target.value); setPage(0) }}>
            <option value="">All Channels</option>
            {channels.map(ch => <option key={ch.id} value={ch.id}>{ch.name}</option>)}
          </select>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginLeft: 'auto' }}>
            {filtered.length} videos
          </div>
        </div>

        {loading ? (
          <div className="loading-spinner"><div className="spinner"></div><span>Loading...</span></div>
        ) : filtered.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">▶️</div>
            <h3>{logs.length === 0 ? 'No videos logged yet' : 'No results'}</h3>
            <p>{logs.length === 0 ? 'Start logging videos you watch!' : 'Try different filters.'}</p>
            {logs.length === 0 && (
              <button className="btn btn-primary" onClick={() => setShowLog(true)}>+ Log First Video</button>
            )}
          </div>
        ) : (
          <>
            <div className="card" style={{ padding: 0 }}>
              <div className="table-wrapper">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Video</th>
                      <th>Channel</th>
                      <th>Duration</th>
                      <th>Watched</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginated.map(log => (
                      <tr key={log.id}>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <div style={{ width: '32px', height: '32px', background: 'rgba(255,0,0,0.1)', borderRadius: '6px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '14px', flexShrink: 0 }}>▶</div>
                            <div>
                              <div style={{ fontWeight: 500, fontSize: '13px' }}>
                                {log.video_url ? (
                                  <a href={log.video_url} target="_blank" rel="noopener noreferrer"
                                    style={{ color: 'var(--text-primary)', textDecoration: 'none' }}
                                    onMouseEnter={e => e.target.style.color = 'var(--accent-red)'}
                                    onMouseLeave={e => e.target.style.color = 'var(--text-primary)'}>
                                    {log.video_title}
                                  </a>
                                ) : log.video_title}
                              </div>
                              {log.notes && <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>{log.notes}</div>}
                            </div>
                          </div>
                        </td>
                        <td>
                          <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{log.channel_name}</span>
                        </td>
                        <td><DurationBadge minutes={log.duration_minutes} /></td>
                        <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                          {new Date(log.watched_at).toLocaleString()}
                        </td>
                        <td>
                          <button className="btn-icon" style={{ borderColor: '#ff444433' }}
                            onClick={() => handleDelete(log)} title="Delete">🗑️</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {totalPages > 1 && (
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center', justifyContent: 'center', marginTop: '16px' }}>
                <button className="btn btn-secondary btn-sm" disabled={page === 0}
                  onClick={() => setPage(p => p - 1)}>← Prev</button>
                <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                  Page {page + 1} of {totalPages}
                </span>
                <button className="btn btn-secondary btn-sm" disabled={page >= totalPages - 1}
                  onClick={() => setPage(p => p + 1)}>Next →</button>
              </div>
            )}
          </>
        )}
      </div>

      {showLog && channels.length > 0 && (
        <LogVideoModal channels={channels} onClose={() => setShowLog(false)} onSave={handleLog} />
      )}
      {showLog && channels.length === 0 && (
        <div className="modal-overlay" onClick={() => setShowLog(false)}>
          <div className="modal">
            <div className="modal-title">⚠️ No Channels Found</div>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '16px' }}>
              Please add at least one channel subscription before logging videos.
            </p>
            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setShowLog(false)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
