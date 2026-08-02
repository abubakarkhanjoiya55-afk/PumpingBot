import React, { useEffect, useState } from 'react'
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'
import { api } from '../lib/api'

const COLORS = ['#ff0000', '#7c4dff', '#00bcd4', '#4caf50', '#ff9800', '#e91e63', '#9c27b0', '#03a9f4', '#8bc34a', '#ffc107']

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload?.length) {
    return (
      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: '8px', padding: '10px 14px', fontSize: '13px' }}>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '4px' }}>{label}</p>
        {payload.map((p, i) => (
          <p key={i} style={{ color: p.color, fontWeight: 600 }}>
            {p.name}: {typeof p.value === 'number' ? (p.name === 'Videos' ? p.value : `${Math.round(p.value)}m`) : p.value}
          </p>
        ))}
      </div>
    )
  }
  return null
}

export default function Analytics() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)

  useEffect(() => {
    setLoading(true)
    api.getAnalytics(days).then(d => {
      setData(d)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [days])

  const fmtTime = (mins) => {
    if (!mins) return '0m'
    if (mins < 60) return `${Math.round(mins)}m`
    const h = Math.floor(mins / 60)
    const m = Math.round(mins % 60)
    return m > 0 ? `${h}h ${m}m` : `${h}h`
  }

  // Prepare chart data - show only every Nth day for readability
  const dailyChartData = data?.daily_stats?.map(d => ({
    date: d.date.slice(5), // MM-DD
    Minutes: Math.round(d.total_minutes),
    Videos: d.video_count,
  })).filter(d => d.Minutes > 0 || d.Videos > 0) || []

  // For the bar chart, use last 14 days
  const recentBarData = data?.daily_stats?.slice(-14).map(d => ({
    date: d.date.slice(5),
    Minutes: Math.round(d.total_minutes),
    Videos: d.video_count,
  })) || []

  const pieData = data?.channel_stats?.slice(0, 8).map((ch, i) => ({
    name: ch.channel_name,
    value: Math.round(ch.total_minutes),
    color: COLORS[i % COLORS.length],
  })) || []

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">📈 Analytics</div>
          <div className="page-subtitle">Detailed watchtime insights</div>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {[7, 30, 90, 365].map(d => (
            <button key={d} className={`btn btn-sm ${days === d ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setDays(d)}>
              {d === 365 ? '1yr' : `${d}d`}
            </button>
          ))}
        </div>
      </div>

      <div className="page-body">
        {loading ? (
          <div className="loading-spinner"><div className="spinner"></div><span>Loading analytics...</span></div>
        ) : !data ? (
          <div className="empty-state">
            <div className="empty-state-icon">📊</div>
            <h3>No data yet</h3>
            <p>Start logging videos to see your analytics here!</p>
          </div>
        ) : (
          <>
            {/* Summary cards */}
            <div className="stats-grid" style={{ marginBottom: '24px' }}>
              {[
                { icon: '⏱️', label: 'Total Watch Time', value: fmtTime(data.total_watchtime_minutes), color: '#ff0000' },
                { icon: '🎞️', label: 'Total Videos', value: data.total_videos_watched, color: '#7c4dff' },
                { icon: '📅', label: 'Avg Per Day', value: fmtTime(data.avg_daily_minutes), color: '#00bcd4' },
                { icon: '📆', label: 'This Week', value: fmtTime(data.this_week_minutes), color: '#4caf50' },
                { icon: '🗓️', label: 'This Month', value: fmtTime(data.this_month_minutes), color: '#ff9800' },
                { icon: '🏆', label: 'Top Channel', value: data.top_channel || '—', color: '#e91e63' },
              ].map(s => (
                <div key={s.label} className="stat-card">
                  <div className="stat-icon" style={{ background: s.color + '22' }}>
                    <span style={{ fontSize: '20px' }}>{s.icon}</span>
                  </div>
                  <div className="stat-value" style={{ fontSize: typeof s.value === 'string' && s.value.length > 6 ? '18px' : '28px' }}>{s.value}</div>
                  <div className="stat-label">{s.label}</div>
                </div>
              ))}
            </div>

            {/* Watchtime over time (line) */}
            <div className="card" style={{ marginBottom: '20px' }}>
              <div className="card-header">
                <div className="card-title">📈 Watchtime Trend ({days}d)</div>
              </div>
              {dailyChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={dailyChartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} />
                    <Tooltip content={<CustomTooltip />} />
                    <Line type="monotone" dataKey="Minutes" stroke="#ff0000" strokeWidth={2} dot={false} name="Minutes" />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>No data in this period</div>
              )}
            </div>

            <div className="grid-2" style={{ marginBottom: '20px' }}>
              {/* Daily bar chart */}
              <div className="card">
                <div className="card-header">
                  <div className="card-title">📊 Daily Activity (Last 14d)</div>
                </div>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={recentBarData} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
                    <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="Minutes" fill="#ff0000" radius={[4, 4, 0, 0]} name="Minutes" />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Pie chart */}
              <div className="card">
                <div className="card-header">
                  <div className="card-title">🥧 By Channel</div>
                </div>
                {pieData.length > 0 ? (
                  <>
                    <ResponsiveContainer width="100%" height={160}>
                      <PieChart>
                        <Pie data={pieData} cx="50%" cy="50%" outerRadius={70} dataKey="value" label={false}>
                          {pieData.map((entry, i) => (
                            <Cell key={i} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v) => [`${v}m`, 'Watchtime']} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '8px' }}>
                      {pieData.map((entry, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
                          <div style={{ width: '10px', height: '10px', borderRadius: '2px', background: entry.color, flexShrink: 0 }} />
                          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>{entry.name}</span>
                          <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{fmtTime(entry.value)}</span>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>No data</div>
                )}
              </div>
            </div>

            {/* Channel breakdown table */}
            {data.channel_stats.length > 0 && (
              <div className="card">
                <div className="card-header">
                  <div className="card-title">📋 Channel Breakdown</div>
                </div>
                <div className="table-wrapper">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Channel</th>
                        <th>Total Watchtime</th>
                        <th>Videos</th>
                        <th>Share</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.channel_stats.map((ch, i) => (
                        <tr key={ch.channel_id}>
                          <td style={{ color: 'var(--text-muted)', fontSize: '13px' }}>#{i + 1}</td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: COLORS[i % COLORS.length] }} />
                              <span style={{ fontWeight: 500 }}>{ch.channel_name}</span>
                            </div>
                          </td>
                          <td><span className="badge badge-cyan">{fmtTime(ch.total_minutes)}</span></td>
                          <td style={{ color: 'var(--text-secondary)' }}>{ch.video_count}</td>
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <div className="progress-bar" style={{ width: '80px' }}>
                                <div className="progress-fill" style={{ width: `${ch.percentage}%` }} />
                              </div>
                              <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{ch.percentage}%</span>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
