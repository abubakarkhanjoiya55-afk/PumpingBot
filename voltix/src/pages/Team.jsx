import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { api } from '../lib/api.js'
import { RANKS } from '../lib/constants.js'
import { formatUsd } from '../lib/format.js'

export default function Team() {
  const { user, team: teamRaw, claimGift, refresh } = useAuth()
  const [toast, setToast] = useState({ type: '', text: '' })
  const [myClaims, setMyClaims] = useState([])

  async function loadClaims() {
    try {
      const list = await api.myGifts()
      setMyClaims(Array.isArray(list) ? list : [])
    } catch {
      setMyClaims([])
    }
  }

  useEffect(() => {
    loadClaims()
  }, [])

  if (!teamRaw) {
    return (
      <main className="page">
        <h1 className="pageTitle">Team & Ranks</h1>
        <p className="pageSub">Loading…</p>
      </main>
    )
  }

  const team = teamRaw
  const claimedIds = new Set([
    ...(user?.claimedGifts || []),
    ...myClaims.filter((c) => c.status === 'PENDING' || c.status === 'FULFILLED').map((c) => c.giftId),
  ])

  async function onClaim(giftId, choice, label) {
    setToast({ type: '', text: '' })
    try {
      await claimGift(giftId, choice)
      await refresh?.()
      await loadClaims()
      setToast({ type: 'ok', text: `Claim sent: ${label}. Admin will see it in Gift claims.` })
    } catch (err) {
      setToast({ type: 'err', text: err?.message || 'Claim failed' })
    }
  }

  return (
    <main className="page">
      <h1 className="pageTitle">Team & Ranks</h1>
      <p className="pageSub">
        Build your network. Team deposits unlock higher ranks, bigger referral %, stake bonuses, and luxury
        gifts. Claim gifts when unlocked — admin gets notified.
      </p>
      <section className="card rankHero">
        <div className="statLabel">Your rank</div>
        <div className="rankName">{team.rank.name}</div>
        <p className="pageSub" style={{ margin: '0.35rem 0 0' }}>
          {team.rank.tagline}
        </p>
        <div className="rankMetaGrid">
          <div>
            <span>Team deposits</span>
            <strong className="goldText">{formatUsd(team.teamDeposits)}</strong>
          </div>
          <div>
            <span>Team size</span>
            <strong>{team.teamSize}</strong>
          </div>
          <div>
            <span>Direct</span>
            <strong>{team.directCount}</strong>
          </div>
          <div>
            <span>Referral cut</span>
            <strong className="goldText">{team.refPct}%</strong>
          </div>
        </div>
        {team.upcoming ? (
          <div className="rankProgress">
            <div className="rankProgressTop">
              <span>
                Next: {team.upcoming.name} ({formatUsd(team.upcoming.minTeam)})
              </span>
              <span>{formatUsd(team.needForNext)} to go</span>
            </div>
            <div className="rankBarTrack">
              <div className="rankBarFill" style={{ width: `${team.progressToNext}%` }} />
            </div>
          </div>
        ) : (
          <p className="hintDark">You are at the top Legend rank.</p>
        )}
      </section>
      {toast.text ? <div className={`toast ${toast.type}`}>{toast.text}</div> : null}
      <section style={{ marginTop: '1.25rem' }}>
        <h2 className="sectionMiniTitle">Luxury gift milestones</h2>
        <div className="list">
          {team.gifts.map((g) => {
            const pending = myClaims.find((c) => c.giftId === g.id && c.status === 'PENDING')
            const fulfilled = myClaims.find((c) => c.giftId === g.id && c.status === 'FULFILLED')
            const already = claimedIds.has(g.id)
            return (
              <article key={g.id} className={`card giftCard ${g.unlocked ? 'is-unlocked' : 'is-locked'}`}>
                <div className="giftTop">
                  <strong>{g.title}</strong>
                  <span className={g.unlocked ? 'giftBadge on' : 'giftBadge'}>
                    {fulfilled ? 'Fulfilled' : pending ? 'Pending' : g.unlocked ? 'Unlocked' : 'Locked'}
                  </span>
                </div>
                <p className="empty" style={{ margin: '0.35rem 0 0.55rem' }}>
                  Option A: <strong>{g.giftLabel}</strong>
                  <br />
                  Option B: <strong>{formatUsd(g.cashUsdt)} USDT</strong> cash
                </p>
                <div className="rankProgressTop">
                  <span>Need {formatUsd(g.minTeam)} team deposits</span>
                  <span>{g.unlocked ? 'Ready' : `${formatUsd(g.remaining)} left`}</span>
                </div>
                <div className="rankBarTrack">
                  <div className="rankBarFill" style={{ width: `${g.progress}%` }} />
                </div>
                {g.unlocked && !already ? (
                  <div className="giftChoiceRow">
                    <button
                      type="button"
                      className="btn btnGold"
                      onClick={() => onClaim(g.id, 'GIFT', g.giftLabel)}
                    >
                      Claim {g.giftLabel}
                    </button>
                    <button
                      type="button"
                      className="btn btnDark"
                      onClick={() => onClaim(g.id, 'USDT', `${formatUsd(g.cashUsdt)} USDT`)}
                    >
                      Claim {formatUsd(g.cashUsdt)} USDT
                    </button>
                  </div>
                ) : null}
                {pending ? (
                  <p className="hintDark" style={{ marginBottom: 0 }}>
                    Claimed: {pending.choiceLabel || pending.choice} — waiting for admin.
                  </p>
                ) : null}
              </article>
            )
          })}
        </div>
      </section>
      <section style={{ marginTop: '1.25rem' }}>
        <h2 className="sectionMiniTitle">All ranks</h2>
        <div className="list">
          {RANKS.map((r) => {
            const on = r.id === team.rank.id
            return (
              <div key={r.id} className={`listRow activityRow ${on ? 'rankRowOn' : ''}`}>
                <div>
                  <strong>
                    {r.name}
                    {on ? ' · YOU' : ''}
                  </strong>
                  <small>
                    From {formatUsd(r.minTeam)} team · Ref {r.refPct}% · Stake bonus +{r.yieldBonus}%
                  </small>
                </div>
                <strong className="goldText">{r.refPct}%</strong>
              </div>
            )
          })}
        </div>
      </section>
      <section style={{ marginTop: '1.25rem' }}>
        <h2 className="sectionMiniTitle">Your team members</h2>
        <div className="list">
          {team.members.map((m) => (
            <div key={m.email} className="listRow activityRow">
              <div>
                <strong>
                  {m.name} · L{m.depth}
                </strong>
                <small>
                  {m.email} · deposited {formatUsd(m.deposited)} · staked {formatUsd(m.staked)}
                </small>
              </div>
            </div>
          ))}
          {team.members.length ? null : (
            <div className="empty">
              No team yet. Share your referral link from Home.
            </div>
          )}
        </div>
      </section>
      <p className="hintDark">
        When your referral deposits and admin approves, you get your rank % (starts at 5%) in Available USDT.{' '}
        <Link to="/app/settings/about">About ranks & gifts</Link>
      </p>
    </main>
  )
}
