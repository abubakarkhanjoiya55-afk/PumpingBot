import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import PasswordField from '../components/PasswordField.jsx'

export default function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [referralCode, setReferralCode] = useState(params.get('ref') || '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function onSubmit(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await register({ name, email, password, referralCode })
      navigate('/app', { replace: true })
    } catch (err) {
      setError(err?.message || 'Registration failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="page">
      <form className="card authCard" onSubmit={onSubmit}>
        <h1 className="pageTitle">Register</h1>
        <p className="pageSub">Get 1,000 Volt coin on signup. Account is stored on the server — you can login again after reinstall.</p>
        <div className="field">
          <label htmlFor="name">Full name</label>
          <input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
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
          autoComplete="new-password"
          minLength={6}
        />
        <div className="field">
          <label htmlFor="ref">Referral code (optional)</label>
          <input
            id="ref"
            value={referralCode}
            onChange={(e) => setReferralCode(e.target.value)}
            placeholder="Friend’s code"
          />
        </div>
        <button className="btn btnGold btnBlock" type="submit" disabled={busy}>
          {busy ? 'Creating…' : 'Create account'}
        </button>
        {error ? <div className="toast err">{error}</div> : null}
        <p className="authSwitch">
          Already have an account? <Link to="/login">Login</Link>
        </p>
      </form>
    </main>
  )
}
