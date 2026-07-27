import { Link } from 'react-router-dom'
import { PLANS } from '../lib/constants.js'
import { formatUsd } from '../lib/format.js'

export default function Home() {
  return (
    <main className="page">
      <section className="heroPublic">
        <h1>Voltix</h1>
        <p>
          USDT staking, Volt coin rewards, team ranks, referral earnings, and milestone gifts — Pixel 7,
          Pixel 11, or iPhone 17 Pro (or USDT cash). Register once and stay logged in until you log out.
        </p>
        <div className="heroActions">
          <Link className="btn btnGold" to="/register">
            Create account
          </Link>
          <Link className="btn btnGhost" to="/login">
            Login
          </Link>
        </div>
      </section>
      <section className="page">
        <h2 className="pageTitle">4 staking plans</h2>
        <p className="pageSub">Pick a plan by USDT range. Monthly target yield rises with larger plans.</p>
        <div className="grid4">
          {PLANS.map((plan) => (
            <article key={plan.id} className="card planCard" style={{ '--accent': plan.color }}>
              <div className="planTag">{plan.tag}</div>
              <div className="planYield">
                {plan.yieldMin}–{plan.yieldMax}%
              </div>
              <div className="planRange">
                {formatUsd(plan.min)} – {formatUsd(plan.max)} USDT
              </div>
              <Link className="btn btnDark btnBlock" to="/register">
                Start with {plan.name}
              </Link>
            </article>
          ))}
        </div>
      </section>
      <section className="page">
        <div className="grid2">
          <article className="card cardStrong">
            <div className="statLabel">New user</div>
            <div className="statValue gold">1,000 Volt</div>
            <p className="pageSub" style={{ marginBottom: 0 }}>
              Free Volt coin on every successful registration.
            </p>
          </article>
          <article className="card cardStrong">
            <div className="statLabel">Referral</div>
            <div className="statValue gold">200 Volt + 5%</div>
            <p className="pageSub" style={{ marginBottom: 0 }}>
              200 Volt coin per invite · 5% of referral deposits paid to you.
            </p>
          </article>
        </div>
      </section>
    </main>
  )
}
