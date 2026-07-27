import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import PasswordField from '../components/PasswordField.jsx'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await login({ email, password })
      navigate('/app', { replace: true })
    } catch (err) {
      setError(err?.message || 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="page">
      <form className="card authCard" onSubmit={onSubmit}>
        <h1 className="pageTitle">Login</h1>
        <p className="pageSub">Welcome back to Volt. Your account is saved on the server — reinstall and login anytime.</p>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <PasswordField
          id="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          show={show}
          onToggle={() => setShow((s) => !s)}
          autoComplete="current-password"
        />
        <button className="btn btnGold btnBlock" type="submit" disabled={busy}>
          {busy ? 'Logging in…' : 'Login'}
        </button>
        {error ? <div className="toast err">{error}</div> : null}
        <p className="authSwitch">
          New here? <Link to="/register">Create account</Link>
        </p>
      </form>
    </main>
  )
}
