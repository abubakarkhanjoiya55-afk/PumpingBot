import React from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { ToastProvider } from './context/AppContext'
import Dashboard from './pages/Dashboard'
import Subscriptions from './pages/Subscriptions'
import WatchHistory from './pages/WatchHistory'
import Goals from './pages/Goals'
import Analytics from './pages/Analytics'

const NAV_ITEMS = [
  { path: '/', icon: '📊', label: 'Dashboard' },
  { path: '/subscriptions', icon: '🔔', label: 'Subscriptions' },
  { path: '/watch-history', icon: '▶️', label: 'Watch History' },
  { path: '/goals', icon: '🎯', label: 'Goals' },
  { path: '/analytics', icon: '📈', label: 'Analytics' },
]

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <div className="app-layout">
          <aside className="sidebar">
            <div className="sidebar-logo">
              <div className="logo-icon">▶</div>
              <div>
                <div className="logo-text">YT Tracker</div>
                <div className="logo-sub">Subscriptions & Watchtime</div>
              </div>
            </div>

            <nav className="sidebar-nav">
              <div className="nav-section-label">Main</div>
              {NAV_ITEMS.map(item => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === '/'}
                  className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                >
                  <span style={{ fontSize: '16px' }}>{item.icon}</span>
                  {item.label}
                </NavLink>
              ))}
            </nav>

            <div style={{ padding: '16px', borderTop: '1px solid var(--border)' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', textAlign: 'center' }}>
                YouTube Tracker v1.0
              </div>
            </div>
          </aside>

          <main className="main-content">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/subscriptions" element={<Subscriptions />} />
              <Route path="/watch-history" element={<WatchHistory />} />
              <Route path="/goals" element={<Goals />} />
              <Route path="/analytics" element={<Analytics />} />
            </Routes>
          </main>
        </div>
      </ToastProvider>
    </BrowserRouter>
  )
}
