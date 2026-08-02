import React, { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Link } from 'react-router-dom'

function StatCard({ icon, label, value, color, sub }) {
  return (
    <div className="stat-card">
      <div className="stat-icon" style={{ background: color + '22' }}>
        <span style={{ fontSize: '20px' }}>{icon}</span>
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{sub}</div>}
    </div>
  )
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [channels, setChannels] = useState([])
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      api.getAnalytics(30),
      api.getChannels({ active_only: true }),
      api.getWatchLogs({ limit: 5 }),
    ]).then(([analytics, chs, wlogs]) => {
      setData(analytics)
      setChannels(chs.slice(0, 5))
      setLogs(wlogs)
    }).finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div>
        <div className="page-header">
          <div><div className="page-title">Dashboard</div><div className="page-subtitle">Your YouTube activity overview</div></div>
        </div>
        <div className="loading-spinner"><div className="spinner"></div><span>Loading...</span></div>
      </div>
    )
  }

  const fmtTime = (mins) => {
    if (mins < 60) return `${Math.round(mins)}m`
    const h = Math.floor(mins / 60)
    const m = Math.round(mins % 60)
    return m > 0 ? `${h}h ${m}m` : `${h}h`
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Dashboard</div>
          <div className="page-subtitle">Your YouTube activity overview</div>
        </div>
        <Link to="/subscriptions" className="btn btn-primary">
          <span>+</span> Add Channel
        </Link>
      </div>

      <div className="page-body">
        {/* Stats Grid */}
        <div className="stats-grid">
          <StatCard
            icon="📺"
            label="Total Watch Time"
            value={fmtTime(data?.total_watchtime_minutes || 0)}
            color="#ff0000"
            sub={`${(data?.total_watchtime_hours || 0).toFixed(1)} hours total`}
          />
          <StatCard
            icon="▶️"
            label="Videos Watched"
            value={data?.total_videos_watched || 0}
            color="#7c4dff"
            sub="All time"
          />
          <StatCard
            icon="🔔"
            label="Subscriptions"
            value={data?.active_subscriptions || 0}
            color="#00bcd4"
            sub={`${data?.total_subscriptions || 0} total`}
          />
          <StatCard
            icon="📅"
            label="This Week"
            value={fmtTime(data?.this_week_minutes || 0)}
            color="#4caf50"
            sub="Last 7 days"
          />
          <StatCard
            icon="📆"
            label="This Month"
            value={fmtTime(data?.this_month_minutes || 0)}
            color="#ff9800"
            sub="Last 30 days"
          />
          <StatCard
            icon="⏱️"
            label="Avg Daily"
            value={fmtTime(data?.avg_daily_minutes || 0)}
            color="#e91e63"
            sub="Per active day"
          />
        </div>

        <div className="grid-2" style={{ marginBottom: '24px' }}>
          {/* Top Channels */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">🏆 Top Channels by Watch Time</div>
              <Link to="/subscriptions" style={{ fontSize: '12px', color: 'var(--accent-red)', textDecoration: 'none' }}>View all</Link>
            </div>
            {data?.channel_stats?.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {data.channel_stats.slice(0, 5).map((ch, i) => (
                  <div key={ch.channel_id}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '12px', color: 'var(--text-muted)', width: '16px' }}>#{i + 1}</span>
                        <div className="channel-avatar" style={{ width: '28px', height: '28px', fontSize: '12px' }}>
                          {ch.channel_name[0]?.toUpperCase()}
                        </div>
                        <span style={{ fontSize: '13px', fontWeight: 500 }}>{ch.channel_name}</span>
                      </div>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {fmtTime(ch.total_minutes)}
                      </span>
                    </div>
                    <div className="progress-bar">
                      <div className="progress-fill" style={{ width: `${ch.percentage}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state" style={{ padding: '30px' }}>
                <p>No watch history yet.<br />Add channels and log some videos!</p>
              </div>
            )}
          </div>

          {/* Recent Watch History */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">🕐 Recent Activity</div>
              <Link to="/watch-history" style={{ fontSize: '12px', color: 'var(--accent-red)', textDecoration: 'none' }}>View all</Link>
            </div>
            {logs.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {logs.map(log => (
                  <div key={log.id} style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', padding: '10px', background: 'var(--bg-secondary)', borderRadius: '8px' }}>
                    <div style={{ width: '36px', height: '36px', background: 'rgba(255,0,0,0.15)', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '16px', flexShrink: 0 }}>▶</div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: '13px', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{log.video_title}</div>
                      <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                        {log.channel_name} · {fmtTime(log.duration_minutes)}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '1px' }}>
                        {new Date(log.watched_at).toLocaleDateString()}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state" style={{ padding: '30px' }}>
                <p>No videos logged yet.</p>
              </div>
            )}
          </div>
        </div>

        {/* Quick Actions */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: '16px' }}>⚡ Quick Actions</div>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <Link to="/subscriptions" className="btn btn-primary">🔔 Manage Subscriptions</Link>
            <Link to="/watch-history" className="btn btn-secondary">▶️ Log a Video</Link>
            <Link to="/goals" className="btn btn-secondary">🎯 Set a Goal</Link>
            <Link to="/analytics" className="btn btn-secondary">📈 View Analytics</Link>
          </div>
        </div>
      </div>
    </div>
  )
}
