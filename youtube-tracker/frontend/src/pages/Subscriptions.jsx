import React, { useEffect, useState, useCallback } from 'react'
import { api } from '../lib/api'
import { useToast } from '../context/AppContext'

const CATEGORIES = ['General', 'Tech', 'Gaming', 'Music', 'Education', 'News', 'Entertainment', 'Sports', 'Science', 'Lifestyle', 'Comedy', 'Other']

const CATEGORY_COLORS = {
  Tech: 'badge-cyan', Gaming: 'badge-purple', Music: 'badge-red',
  Education: 'badge-green', News: 'badge-orange', Entertainment: 'badge-red',
  Sports: 'badge-green', Science: 'badge-cyan', Lifestyle: 'badge-purple',
  Comedy: 'badge-orange', General: 'badge-gray', Other: 'badge-gray',
}

function AddChannelModal({ onClose, onSave }) {
  const [form, setForm] = useState({
    name: '', channel_id: '', description: '', thumbnail_url: '',
    subscriber_count: '', category: 'General', url: '',
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!form.name.trim() || !form.channel_id.trim()) return
    onSave(form)
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-title">
          <span style={{ fontSize: '24px' }}>🔔</span>
          Add New Subscription
        </div>
        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Channel Name *</label>
              <input className="form-input" required value={form.name}
                onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                placeholder="e.g. MrBeast" />
            </div>
            <div className="form-group">
              <label className="form-label">Channel ID / Handle *</label>
              <input className="form-input" required value={form.channel_id}
                onChange={e => setForm(p => ({ ...p, channel_id: e.target.value }))}
                placeholder="e.g. @MrBeast or UCX6OQ3..." />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Category</label>
              <select className="form-select" value={form.category}
                onChange={e => setForm(p => ({ ...p, category: e.target.value }))}>
                {CATEGORIES.map(c => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Subscriber Count</label>
              <input className="form-input" value={form.subscriber_count}
                onChange={e => setForm(p => ({ ...p, subscriber_count: e.target.value }))}
                placeholder="e.g. 200M, 5.2K" />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Channel URL</label>
            <input className="form-input" value={form.url}
              onChange={e => setForm(p => ({ ...p, url: e.target.value }))}
              placeholder="https://youtube.com/@channelname" />
          </div>

          <div className="form-group">
            <label className="form-label">Thumbnail URL</label>
            <input className="form-input" value={form.thumbnail_url}
              onChange={e => setForm(p => ({ ...p, thumbnail_url: e.target.value }))}
              placeholder="https://..." />
          </div>

          <div className="form-group">
            <label className="form-label">Description</label>
            <textarea className="form-textarea" value={form.description}
              onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
              placeholder="Short description of the channel..." />
          </div>

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary">Add Subscription</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function EditChannelModal({ channel, onClose, onSave }) {
  const [form, setForm] = useState({
    name: channel.name, description: channel.description || '',
    thumbnail_url: channel.thumbnail_url || '',
    subscriber_count: channel.subscriber_count || '',
    category: channel.category || 'General',
    url: channel.url || '',
    is_active: channel.is_active,
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave(channel.id, form)
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-title">✏️ Edit Channel</div>
        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Channel Name</label>
              <input className="form-input" value={form.name}
                onChange={e => setForm(p => ({ ...p, name: e.target.value }))} />
            </div>
            <div className="form-group">
              <label className="form-label">Category</label>
              <select className="form-select" value={form.category}
                onChange={e => setForm(p => ({ ...p, category: e.target.value }))}>
                {CATEGORIES.map(c => <option key={c}>{c}</option>)}
              </select>
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Subscriber Count</label>
              <input className="form-input" value={form.subscriber_count}
                onChange={e => setForm(p => ({ ...p, subscriber_count: e.target.value }))} />
            </div>
            <div className="form-group">
              <label className="form-label">Channel URL</label>
              <input className="form-input" value={form.url}
                onChange={e => setForm(p => ({ ...p, url: e.target.value }))} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Thumbnail URL</label>
            <input className="form-input" value={form.thumbnail_url}
              onChange={e => setForm(p => ({ ...p, thumbnail_url: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Description</label>
            <textarea className="form-textarea" value={form.description}
              onChange={e => setForm(p => ({ ...p, description: e.target.value }))} />
          </div>
          <div className="form-group">
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '14px', color: 'var(--text-primary)' }}>
              <input type="checkbox" checked={form.is_active}
                onChange={e => setForm(p => ({ ...p, is_active: e.target.checked }))} />
              Active subscription
            </label>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary">Save Changes</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function Subscriptions() {
  const [channels, setChannels] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const [editChannel, setEditChannel] = useState(null)
  const [search, setSearch] = useState('')
  const [filterCat, setFilterCat] = useState('')
  const toast = useToast()

  const fetchChannels = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getChannels()
      setChannels(data)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchChannels() }, [fetchChannels])

  const handleAdd = async (form) => {
    try {
      await api.createChannel(form)
      toast('Channel added successfully!', 'success')
      setShowAdd(false)
      fetchChannels()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const handleEdit = async (id, form) => {
    try {
      await api.updateChannel(id, form)
      toast('Channel updated!', 'success')
      setEditChannel(null)
      fetchChannels()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const handleDelete = async (ch) => {
    if (!confirm(`Remove "${ch.name}" from subscriptions? All watch history for this channel will also be deleted.`)) return
    try {
      await api.deleteChannel(ch.id)
      toast('Channel removed', 'success')
      fetchChannels()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const fmtTime = (mins) => {
    if (mins < 60) return `${Math.round(mins)}m`
    const h = Math.floor(mins / 60)
    const m = Math.round(mins % 60)
    return m > 0 ? `${h}h ${m}m` : `${h}h`
  }

  const filtered = channels.filter(ch => {
    const matchSearch = !search || ch.name.toLowerCase().includes(search.toLowerCase()) ||
      ch.channel_id.toLowerCase().includes(search.toLowerCase())
    const matchCat = !filterCat || ch.category === filterCat
    return matchSearch && matchCat
  })

  const categories = [...new Set(channels.map(c => c.category).filter(Boolean))]

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">🔔 Subscriptions</div>
          <div className="page-subtitle">{channels.length} channels · {channels.filter(c => c.is_active).length} active</div>
        </div>
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
          + Add Channel
        </button>
      </div>

      <div className="page-body">
        {/* Toolbar */}
        <div className="toolbar" style={{ marginBottom: '20px' }}>
          <div className="search-wrapper">
            <span className="search-icon">🔍</span>
            <input className="search-input" placeholder="Search channels..."
              value={search} onChange={e => setSearch(e.target.value)} />
          </div>
          <select className="form-select" style={{ width: 'auto', minWidth: '140px' }}
            value={filterCat} onChange={e => setFilterCat(e.target.value)}>
            <option value="">All Categories</option>
            {categories.map(c => <option key={c}>{c}</option>)}
          </select>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginLeft: 'auto' }}>
            {filtered.length} result{filtered.length !== 1 ? 's' : ''}
          </div>
        </div>

        {loading ? (
          <div className="loading-spinner"><div className="spinner"></div><span>Loading channels...</span></div>
        ) : filtered.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📺</div>
            <h3>{channels.length === 0 ? 'No subscriptions yet' : 'No results found'}</h3>
            <p>{channels.length === 0 ? 'Add your favorite YouTube channels to start tracking!' : 'Try a different search or filter.'}</p>
            {channels.length === 0 && (
              <button className="btn btn-primary" onClick={() => setShowAdd(true)}>+ Add First Channel</button>
            )}
          </div>
        ) : (
          <div className="channels-grid">
            {filtered.map(ch => (
              <div key={ch.id} className="channel-card" style={{ opacity: ch.is_active ? 1 : 0.6 }}>
                <div className="channel-card-header">
                  <div className="channel-avatar">
                    {ch.thumbnail_url ? (
                      <img src={ch.thumbnail_url} alt={ch.name}
                        onError={e => { e.target.style.display = 'none' }} />
                    ) : null}
                    {!ch.thumbnail_url && ch.name[0]?.toUpperCase()}
                  </div>
                  <div className="channel-info">
                    <div className="channel-name">{ch.name}</div>
                    <div className="channel-meta">
                      {ch.subscriber_count && `${ch.subscriber_count} subscribers · `}
                      {new Date(ch.subscribed_at).toLocaleDateString()}
                    </div>
                  </div>
                  <span className={`badge ${CATEGORY_COLORS[ch.category] || 'badge-gray'}`}>{ch.category}</span>
                </div>

                {ch.description && (
                  <p style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.4', maxHeight: '36px', overflow: 'hidden' }}>
                    {ch.description}
                  </p>
                )}

                <div className="channel-stats-row">
                  <div className="channel-stat-box">
                    <div className="value">{fmtTime(ch.total_watchtime)}</div>
                    <div className="label">Watch Time</div>
                  </div>
                  <div className="channel-stat-box">
                    <div className="value">{ch.video_count}</div>
                    <div className="label">Videos</div>
                  </div>
                </div>

                {!ch.is_active && (
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', textAlign: 'center' }}>
                    Inactive subscription
                  </div>
                )}

                <div className="channel-actions">
                  {ch.url && (
                    <a href={ch.url} target="_blank" rel="noopener noreferrer"
                      className="btn-icon" title="Open on YouTube">🔗</a>
                  )}
                  <button className="btn-icon" title="Edit" onClick={() => setEditChannel(ch)}>✏️</button>
                  <button className="btn-icon" title="Remove" style={{ borderColor: '#ff444433' }}
                    onClick={() => handleDelete(ch)}>🗑️</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showAdd && <AddChannelModal onClose={() => setShowAdd(false)} onSave={handleAdd} />}
      {editChannel && <EditChannelModal channel={editChannel} onClose={() => setEditChannel(null)} onSave={handleEdit} />}
    </div>
  )
}
