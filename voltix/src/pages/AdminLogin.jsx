import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import PasswordField from '../components/PasswordField.jsx'
import { ADMIN_EMAIL } from '../lib/constants.js'
import { adminLogin, isAdminAuthed, purgeAdminFromUsers } from '../lib/admin.js'

export default function AdminLogin() {
  const navigate = useNavigate()
  const [email, setEmail] = useState(ADMIN_EMAIL)
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')

  if (isAdminAuthed()) return <Navigate to="/admin" replace />

  function onSubmit(e) {
    e.preventDefault()
    setError('')
    try {
      adminLogin(email, password)
      purgeAdminFromUsers()
      navigate('/admin', { replace: true })
    } catch (err) {
      setError(err?.message || 'Login failed')
    }
  }

  return (
    <div className="adminShell">
      <header className="topbar">
        <div className="topbarInner">
          <Link to="/" className="logoBrand">
            <span className="logoMain">Volt</span>
            <span className="logoSub">Voltix Exchange · Admin</span>
          </Link>
        </div>
      </header>
      <main className="wrap page">
        <form className="card authCard adminAuthCard" onSubmit={onSubmit}>
          <h1 className="pageTitle">Admin login</h1>
          <p className="pageSub">
            Admin only — this login does not create a user account. Users register separately.
          </p>
          <div className="field">
            <label htmlFor="admEmail">Email</label>
            <input
              id="admEmail"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <PasswordField
            id="admPass"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            show={show}
            onToggle={() => setShow((s) => !s)}
            autoComplete="current-password"
          />
          <button className="btn btnGold btnBlock" type="submit">
            Enter admin panel
          </button>
          {error ? <div className="toast err">{error}</div> : null}
        </form>
      </main>
    </div>
  )
}
