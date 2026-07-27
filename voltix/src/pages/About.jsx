import { Link } from 'react-router-dom'
import { RANKS, GIFTS } from '../lib/constants.js'
import { formatUsd } from '../lib/format.js'

export default function About({ publicMode = false }) {
  const plansTo = publicMode ? '/register' : '/app/plans'
  const teamTo = publicMode ? '/register' : '/app/team'
  const backTo = publicMode ? '/' : '/app/settings'

  return (
    <main className="page">
      <h1 className="pageTitle">About Voltix</h1>
      <p className="pageSub">
        This app is <strong>Voltix</strong> — USDT staking, VOLT rewards, team ranks, and milestone gifts.
        Our larger platform, <strong>Voltix Exchange</strong>, is a separate crypto + forex project.
      </p>
      <article className="card aboutBlock">
        <h3>This project · Voltix</h3>
        <p>
          Stake USDT across 4 plans, grow a referral team, climb ranks for higher earnings, and unlock
          luxury gifts from team deposits.
        </p>
      </article>
      <article className="card aboutBlock cardStrong" style={{ marginTop: '0.85rem' }}>
        <h3>Voltix Exchange</h3>
        <p>
          Our real, full-scale trading platform — <strong>crypto and forex</strong> in one place. Separate
          product — coming soon.
        </p>
        <span className="pillSoon">Coming soon</span>
      </article>
      <article className="card aboutBlock" style={{ marginTop: '0.85rem' }}>
        <h3>Team ranks · higher % earnings</h3>
        <p>
          Your <strong>team total deposits</strong> set your rank. Higher rank = higher referral cut on team
          deposits + extra stake yield bonus when admin posts daily profit.
        </p>
        <div className="list" style={{ marginTop: '0.85rem' }}>
          {RANKS.map((r) => (
            <div key={r.id} className="listRow activityRow">
              <div>
                <strong>{r.name}</strong>
                <small>
                  From {formatUsd(r.minTeam)} team · Ref {r.refPct}% · Stake +{r.yieldBonus}%
                </small>
              </div>
            </div>
          ))}
        </div>
      </article>
      <article className="card aboutBlock" style={{ marginTop: '0.85rem' }}>
        <h3>Luxury gift plan</h3>
        <p>
          Hit team deposit targets, then choose <strong>USDT cash</strong> or the <strong>physical gift</strong>:
        </p>
        <div className="list" style={{ marginTop: '0.85rem' }}>
          {GIFTS.map((g) => (
            <div key={g.id} className="listRow activityRow">
              <div>
                <strong>{g.title}</strong>
                <small>
                  {formatUsd(g.minTeam)} team · {g.giftLabel} or {formatUsd(g.cashUsdt)} USDT
                </small>
              </div>
            </div>
          ))}
        </div>
      </article>
      <article className="card aboutBlock" style={{ marginTop: '0.85rem' }}>
        <h3>Volt Coin</h3>
        <p>
          Every new user gets <strong>1,000 VOLT</strong>. Referrals earn <strong>200 VOLT</strong> plus
          rank-based % of deposits.
        </p>
      </article>
      <div className="heroActions" style={{ marginTop: '1.2rem' }}>
        <Link className="btn btnGold" to={teamTo}>
          {publicMode ? 'Join & build team' : 'Open Team & Ranks'}
        </Link>
        <Link className="btn btnDark" to={plansTo}>
          Stake plans
        </Link>
        <Link className="btn btnGhost" to={backTo}>
          {publicMode ? 'Back home' : 'Back to Settings'}
        </Link>
      </div>
    </main>
  )
}
