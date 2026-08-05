import React, { useEffect, useState, useCallback } from 'react'
import { api } from '../lib/api'
import { useToast } from '../context/AppContext'

function AddGoalModal({ onClose, onSave }) {
  const [form, setForm] = useState({
    title: '', target_minutes: '', period: 'weekly',
  })

  const PRESETS = [
    { label: '30 min/day', period: 'daily', minutes: 30 },
    { label: '1 hr/day', period: 'daily', minutes: 60 },
    { label: '5 hr/week', period: 'weekly', minutes: 300 },
    { label: '10 hr/week', period: 'weekly', minutes: 600 },
    { label: '20 hr/month', period: 'monthly', minutes: 1200 },
  ]

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-title">🎯 Set New Goal</div>

        <div style={{ marginBottom: '20px' }}>
          <div className="form-label" style={{ marginBottom: '8px' }}>Quick Presets</div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {PRESETS.map(p => (
              <button key={p.label} className="btn btn-secondary btn-sm"
                onClick={() => setForm({ title: `Watch ${p.label}`, target_minutes: p.minutes.toString(), period: p.period })}>
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div className="divider" />

        <form onSubmit={e => { e.preventDefault(); if (form.title && form.target_minutes) onSave(form) }}>
          <div className="form-group">
            <label className="form-label">Goal Title *</label>
            <input className="form-input" required value={form.title}
              onChange={e => setForm(p => ({ ...p, title: e.target.value }))}
              placeholder="e.g. Watch 5 hours this week" />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Target (minutes) *</label>
              <input className="form-input" type="number" required min="1" value={form.target_minutes}
                onChange={e => setForm(p => ({ ...p, target_minutes: e.target.value }))}
                placeholder="e.g. 300" />
            </div>
            <div className="form-group">
              <label className="form-label">Period *</label>
              <select className="form-select" value={form.period}
                onChange={e => setForm(p => ({ ...p, period: e.target.value }))}>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
              </select>
            </div>
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary">Create Goal</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function GoalCard({ goal, onDelete }) {
  const percent = goal.progress_percent
  const isComplete = percent >= 100

  const fmtTime = (mins) => {
    if (mins < 60) return `${Math.round(mins)}m`
    const h = Math.floor(mins / 60)
    const m = Math.round(mins % 60)
    return m > 0 ? `${h}h ${m}m` : `${h}h`
  }

  const PERIOD_LABELS = { daily: '📅 Daily', weekly: '📆 Weekly', monthly: '🗓️ Monthly' }

  return (
    <div className="card" style={{ borderColor: isComplete ? 'rgba(76,175,80,0.4)' : 'var(--border)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
        <div>
          <div style={{ fontSize: '16px', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
            {isComplete ? '✅' : '🎯'} {goal.title}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            <span className="badge badge-purple" style={{ marginRight: '6px' }}>{PERIOD_LABELS[goal.period]}</span>
            Created {new Date(goal.created_at).toLocaleDateString()}
          </div>
        </div>
        <button className="btn-icon" style={{ borderColor: '#ff444433' }}
          onClick={() => onDelete(goal)} title="Remove goal">🗑️</button>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <div style={{ fontSize: '28px', fontWeight: 700, color: isComplete ? 'var(--accent-green)' : 'var(--text-primary)' }}>
          {percent}%
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {fmtTime(goal.progress_minutes)} / {fmtTime(goal.target_minutes)}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            {isComplete ? 'Goal achieved! 🎉' : `${fmtTime(Math.max(0, goal.target_minutes - goal.progress_minutes))} remaining`}
          </div>
        </div>
      </div>

      <div className="progress-bar" style={{ height: '10px' }}>
        <div className={`progress-fill ${isComplete ? 'green' : ''}`}
          style={{ width: `${Math.min(100, percent)}%` }} />
      </div>
    </div>
  )
}

export default function Goals() {
  const [goals, setGoals] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)
  const toast = useToast()

  const fetchGoals = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.getGoals()
      setGoals(data)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchGoals() }, [fetchGoals])

  const handleAdd = async (form) => {
    try {
      await api.createGoal({
        title: form.title,
        target_minutes: parseFloat(form.target_minutes),
        period: form.period,
      })
      toast('Goal created!', 'success')
      setShowAdd(false)
      fetchGoals()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const handleDelete = async (goal) => {
    if (!confirm(`Delete goal "${goal.title}"?`)) return
    try {
      await api.deleteGoal(goal.id)
      toast('Goal removed', 'success')
      fetchGoals()
    } catch (err) {
      toast(err.message, 'error')
    }
  }

  const completed = goals.filter(g => g.progress_percent >= 100).length

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">🎯 Goals</div>
          <div className="page-subtitle">
            {goals.length} active goal{goals.length !== 1 ? 's' : ''} · {completed} completed
          </div>
        </div>
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>+ New Goal</button>
      </div>

      <div className="page-body">
        {loading ? (
          <div className="loading-spinner"><div className="spinner"></div><span>Loading goals...</span></div>
        ) : goals.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">🎯</div>
            <h3>No goals yet</h3>
            <p>Set daily, weekly, or monthly watchtime goals to stay on track!</p>
            <button className="btn btn-primary" onClick={() => setShowAdd(true)}>+ Create First Goal</button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', maxWidth: '700px' }}>
            {/* Stats */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginBottom: '8px' }}>
              {[
                { label: 'Total Goals', value: goals.length, icon: '📋' },
                { label: 'Completed', value: completed, icon: '✅' },
                { label: 'In Progress', value: goals.length - completed, icon: '⏳' },
              ].map(s => (
                <div key={s.label} className="stat-card" style={{ flexDirection: 'row', padding: '14px' }}>
                  <span style={{ fontSize: '22px' }}>{s.icon}</span>
                  <div>
                    <div style={{ fontSize: '22px', fontWeight: 700 }}>{s.value}</div>
                    <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{s.label}</div>
                  </div>
                </div>
              ))}
            </div>

            {goals.map(goal => (
              <GoalCard key={goal.id} goal={goal} onDelete={handleDelete} />
            ))}
          </div>
        )}
      </div>

      {showAdd && <AddGoalModal onClose={() => setShowAdd(false)} onSave={handleAdd} />}
    </div>
  )
}
