import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { referralLink } from '../lib/referral.js'

export default function Settings() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function onLogout() {
    logout()
    navigate('/', { replace: true })
  }

  function copyRef() {
    const link = referralLink(user?.referralCode)
    if (link) navigator.clipboard?.writeText(link).catch(() => {})
  }

  return (
    <main className="page">
      <h1 className="pageTitle">Settings</h1>
      <p className="pageSub">{user?.email}</p>
      <div className="settingsList">
        <Link to="/app/team">
          Team & Ranks<span>Deposits · Gifts →</span>
        </Link>
        <Link to="/app/settings/about">
          About<span>A Voltix Exchange project →</span>
        </Link>
        <button type="button" onClick={copyRef}>
          Referral link
          <span>Copy</span>
        </button>
        <button type="button" className="dangerRow" onClick={onLogout}>
          Logout<span>Session ends only here</span>
        </button>
      </div>
      <p className="hintDark refLinkHint">{referralLink(user?.referralCode)}</p>
      <p className="hintDark">
        Bottom menu: Home, Stake, Team, Deposit, Withdraw. Settings via your name (top right).
      </p>
      <p className="hintDark">
        Testing: withdraw lock is off — available USDT/profits can be withdrawn anytime.
      </p>
    </main>
  )
}
