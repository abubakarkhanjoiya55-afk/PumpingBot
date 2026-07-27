import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { formatUsd, formatVolt } from '../lib/format.js'
import { referralLink } from '../lib/referral.js'

function startOfDay(ts = Date.now()) {
  const d = new Date(ts)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

function sumPlanProfit(history, since = 0) {
  return (history || [])
    .filter((h) => h.type === 'PLAN_PROFIT' && Number(h.at || 0) >= since)
    .reduce((sum, h) => sum + Number(h.amount || 0), 0)
}

const EMPTY_TEAM = {
  teamDeposits: 0,
  teamSize: 0,
  directCount: 0,
  rank: { name: 'Scout', tagline: '', yieldBonus: 0 },
  refPct: 5,
  yieldBonus: 0,
  gifts: [],
}

export default function Dashboard() {
  const { user, team: teamRaw } = useAuth()
  const team = teamRaw || EMPTY_TEAM
  const active = (user?.staked || []).filter((s) => s.status === 'ACTIVE')
  const stakedTotal = active.reduce((sum, s) => sum + Number(s.amount || 0), 0)
  const history = user?.history || []
  const todayProfit = sumPlanProfit(history, startOfDay())
  const totalProfit = sumPlanProfit(history, 0)
  const recentProfit = history.filter((h) => h.type === 'PLAN_PROFIT').slice(0, 6)
  const nextGift = (team.gifts || []).find((g) => !g.unlocked) || (team.gifts || [])[(team.gifts || []).length - 1]


  return (
    <main className="page dashPage">
      <section className="heroBalance">
        <div className="heroBalanceTop">
          <div>
            <div className="statLabel">Total USDT power</div>
            <div className="heroBalanceValue">{formatUsd(Number(user?.usdtBalance || 0) + stakedTotal)}</div>
          </div>
          <div className="heroBadge">{team.rank.name}</div>
        </div>
        <div className="heroBalanceGrid">
          <div>
            <span>Available</span>
            <strong>{formatUsd(user?.usdtBalance)}</strong>
          </div>
          <div>
            <span>Staked</span>
            <strong>{formatUsd(stakedTotal)}</strong>
          </div>
          <div>
            <span>Volt coin</span>
            <strong>{formatVolt(user?.voltBalance)}</strong>
          </div>
        </div>
      </section>

      <section className="profitStrip">
        <article className="card profitCard daily">
          <div className="statLabel">Today’s profit</div>
          <div className="statValue gold">{formatUsd(todayProfit)}</div>
          <p className="empty" style={{ margin: '0.35rem 0 0' }}>
            Includes rank stake bonus (+{team.yieldBonus}%)
          </p>
        </article>
        <article className="card profitCard total">
          <div className="statLabel">Total profit</div>
          <div className="statValue gold">{formatUsd(totalProfit)}</div>
          <p className="empty" style={{ margin: '0.35rem 0 0' }}>
            All-time plan profits
          </p>
        </article>
      </section>

      <section className="card teamSnap">
        <div className="teamSnapTop">
          <div>
            <div className="statLabel">Team deposits</div>
            <div className="statValue gold">{formatUsd(team.teamDeposits)}</div>
            <p className="empty" style={{ margin: '0.35rem 0 0' }}>
              {team.teamSize} members · {team.directCount} direct · Ref {team.refPct}%
            </p>
          </div>
          <Link className="btn btnGold" to="/app/team">
            Open team
          </Link>
        </div>
        {nextGift ? (
          <div className="rankProgress" style={{ marginTop: '0.9rem' }}>
            <div className="rankProgressTop">
              <span>
                Next gift: {nextGift.title} ({formatUsd(nextGift.minTeam)})
              </span>
              <span>{nextGift.unlocked ? 'Unlocked' : `${formatUsd(nextGift.remaining)} left`}</span>
            </div>
            <div className="rankBarTrack">
              <div className="rankBarFill" style={{ width: `${nextGift.progress}%` }} />
            </div>
          </div>
        ) : null}
      </section>

      <section className="actionRail">
        <Link className="actionTile deposit" to="/app/deposit">
          <span className="actionIcon">↓</span>
          <strong>Deposit</strong>
          <small>BNB · TRC20 · Arb</small>
        </Link>
        <Link className="actionTile withdraw" to="/app/withdraw">
          <span className="actionIcon">↑</span>
          <strong>Withdraw</strong>
          <small>Cash out USDT</small>
        </Link>
        <Link className="actionTile stake" to="/app/plans">
          <span className="actionIcon">◆</span>
          <strong>Stake</strong>
          <small>4 yield plans</small>
        </Link>
        <Link className="actionTile about" to="/app/team">
          <span className="actionIcon">▣</span>
          <strong>Team</strong>
          <small>Ranks · Gifts</small>
        </Link>
      </section>

      <section className="dashSplit">
        <article className="card glassCard">
          <div className="statLabel">Active stakes</div>
          <div className="statValue">{active.length}</div>
          <p className="empty" style={{ margin: '0.4rem 0 0' }}>
            Locked in yield plans
          </p>
        </article>
        <article className="card glassCard">
          <div className="statLabel">Your rank</div>
          <div className="statValue">{team.rank.name}</div>
          <p className="empty" style={{ margin: '0.4rem 0 0' }}>
            {team.refPct}% referral · +{team.yieldBonus}% stake
          </p>
        </article>
      </section>

      <section className="card refHero">
        <div className="refHeroLeft">
          <div className="statLabel">Referral link</div>
          <div className="refLink">{referralLink(user?.referralCode)}</div>
          <p className="pageSub" style={{ margin: '0.45rem 0 0' }}>
            Invite friends · {team.refPct}% of their deposits + 200 Volt · grow team gifts
          </p>
        </div>
        <button
          type="button"
          className="btn btnGold"
          onClick={() => {
            const link = referralLink(user?.referralCode)
            if (link) navigator.clipboard?.writeText(link)
          }}
        >
          Copy link
        </button>
      </section>

      <section className="activityPanel">
        <div className="activityHead">
          <h2 className="sectionMiniTitle">Profit history</h2>
          <span className="liveDot">Plan yields</span>
        </div>
        <div className="list">
          {recentProfit.map((h) => (
            <div key={h.id} className="listRow activityRow">
              <div>
                <strong>Daily profit</strong>
                <small>{h.note || 'Plan profit credit'}</small>
              </div>
              <strong className="goldText">+{formatUsd(h.amount)}</strong>
            </div>
          ))}
          {recentProfit.length ? null : (
            <div className="empty">No profit credits yet — wait for admin daily yield.</div>
          )}
        </div>
      </section>

      <section className="activityPanel">
        <div className="activityHead">
          <h2 className="sectionMiniTitle">Market activity</h2>
          <span className="liveDot">Live ledger</span>
        </div>
        <div className="list">
          {history.slice(0, 8).map((h) => (
            <div key={h.id} className="listRow activityRow">
              <div>
                <strong>{h.type.replaceAll('_', ' ')}</strong>
                <small>{h.note}</small>
              </div>
              <strong className="goldText">
                {String(h.type).includes('VOLT') || String(h.type).includes('ZR')
                  ? formatVolt(h.amount)
                  : formatUsd(h.amount)}
              </strong>
            </div>
          ))}
          {history.length ? null : <div className="empty">No activity yet — deposit to begin.</div>}
        </div>
      </section>
    </main>
  )
}
