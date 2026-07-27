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

  function onSubmit(e) {
    e.preventDefault()
    setError('')
    try {
      login({ email, password })
      navigate('/app', { replace: true })
    } catch (err) {
      setError(err?.message || 'Login failed')
    }
  }

  return (
    <main className="page">
      <form className="card authCard" onSubmit={onSubmit}>
        <h1 className="pageTitle">Login</h1>
        <p className="pageSub">Welcome back to Voltix.</p>
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
        <button className="btn btnGold btnBlock" type="submit">
          Login
        </button>
        {error ? <div className="toast err">{error}</div> : null}
        <p className="authSwitch">
          New here? <Link to="/register">Create account</Link>
        </p>
      </form>
    </main>
  )
}
