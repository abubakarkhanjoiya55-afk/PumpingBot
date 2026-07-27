import { Link, Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export default function PublicShell() {
  const { isAuthed, ready } = useAuth()
  if (!ready) {
    return (
      <div className="bootScreen" aria-busy="true">
        Loading Voltix…
      </div>
    )
  }
  if (isAuthed) return <Navigate to="/app" replace />
  return (
    <div className="publicShell">
      <header className="topbar">
        <div className="topbarInner">
          <Link to="/" className="logo">
            Voltix
          </Link>
          <nav className="publicNav" aria-label="Primary">
            <Link to="/">Home</Link>
            <Link to="/about">About</Link>
            <Link to="/login">Stake</Link>
          </nav>
          <div className="topActions">
            <Link className="btn btnDark" to="/login">
              Login
            </Link>
            <Link className="btn btnGold" to="/register">
              Register
            </Link>
          </div>
        </div>
      </header>
      <div className="wrap">
        <Outlet />
      </div>
    </div>
  )
}
