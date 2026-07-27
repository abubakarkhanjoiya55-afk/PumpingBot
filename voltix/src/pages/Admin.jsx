import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import {
  isAdminAuthed,
  adminLogout,
  listAdminUsers,
  getAdminLogs,
  listWithdrawRequests,
  listGiftClaims,
  listDepositRequests,
  payoutPlanProfit,
  updateWithdrawStatus,
  updateGiftClaimStatus,
  approveDeposit,
  rejectDeposit,
} from '../lib/admin.js'
import { api } from '../lib/api.js'
import { ADMIN_EMAIL, PLANS } from '../lib/constants.js'
import { formatUsd, formatVolt, formatDate } from '../lib/format.js'

export default function Admin() {
  const navigate = useNavigate()
  const [planId, setPlanId] = useState(2)
  const [percent, setPercent] = useState('0.5')
  const [note, setNote] = useState('')
  const [toast, setToast] = useState({ type: '', text: '' })
  const [tick, setTick] = useState(0)
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState({ users: 0 })
  const [stakes, setStakes] = useState([])
  const [users, setUsers] = useState([])
  const [logs, setLogs] = useState([])
  const [withdraws, setWithdraws] = useState([])
  const [gifts, setGifts] = useState([])
  const [deposits, setDeposits] = useState([])

  const authed = isAdminAuthed()

  useEffect(() => {
    if (!authed) return
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        const [overview, usersList, logsList, withdrawsList, giftsList, depositsList] = await Promise.all([
          api.adminOverview(),
          listAdminUsers(),
          getAdminLogs(),
          listWithdrawRequests(),
          listGiftClaims(),
          listDepositRequests(),
        ])
        if (cancelled) return
        setStats(overview?.stats || { users: 0 })
        setStakes(overview?.liveStakes || overview?.stakes || [])
        setUsers(Array.isArray(usersList) ? usersList : [])
        setLogs(Array.isArray(logsList) ? logsList : [])
        setWithdraws(Array.isArray(withdrawsList) ? withdrawsList : [])
        setGifts(Array.isArray(giftsList) ? giftsList : [])
        setDeposits(Array.isArray(depositsList) ? depositsList : [])
      } catch (err) {
        if (!cancelled) {
          setToast({ type: 'err', text: err?.message || 'Failed to load admin data' })
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [tick, authed])

  if (!authed) return <Navigate to="/admin/login" replace />

  const pendingGifts = gifts.filter((g) => g.status === 'PENDING').length
  const pendingDeposits = deposits.filter((d) => d.status === 'PENDING').length
  const selectedStake = stakes.find((s) => s.planId === planId)

  async function onLogout() {
    await adminLogout()
    navigate('/admin/login', { replace: true })
  }

  async function onProfit(e) {
    e.preventDefault()
    setToast({ type: '', text: '' })
    try {
      const result = await payoutPlanProfit(planId, percent, note.trim())
      setToast({
        type: 'ok',
        text: `Paid ${formatUsd(result.totalPaid)} to ${result.usersHit} users (${result.stakesHit} stakes) on ${result.planName} @ ${result.percent}%`,
      })
      setTick((n) => n + 1)
    } catch (err) {
      setToast({ type: 'err', text: err?.message || 'Failed' })
    }
  }

  async function onWithdraw(id, status) {
    try {
      await updateWithdrawStatus(id, status)
      setTick((n) => n + 1)
    } catch (err) {
      setToast({ type: 'err', text: err?.message || 'Update failed' })
    }
  }

  async function onGift(id, status) {
    try {
      await updateGiftClaimStatus(id, status)
      setTick((n) => n + 1)
    } catch (err) {
      setToast({ type: 'err', text: err?.message || 'Update failed' })
    }
  }

  async function onDeposit(id, action) {
    setToast({ type: '', text: '' })
    try {
      if (action === 'APPROVE') {
        const row = await approveDeposit(id)
        setToast({
          type: 'ok',
          text: `Approved ${formatUsd(row.amount)} for ${row.userEmail} — balance + referral commission credited`,
        })
      } else {
        await rejectDeposit(id)
        setToast({ type: 'ok', text: 'Deposit request rejected — no balance credited' })
      }
      setTick((n) => n + 1)
    } catch (err) {
      setToast({ type: 'err', text: err?.message || 'Update failed' })
    }
  }

  return (
    <div className="adminShell">
      <header className="topbar">
        <div className="topbarInner">
          <Link to="/admin" className="logoBrand">
            <span className="logoMain">Volt</span>
            <span className="logoSub">Voltix Exchange · Admin</span>
          </Link>
          <div className="topActions">
            <span className="userChip">{ADMIN_EMAIL}</span>
            <button type="button" className="btn btnDark" onClick={onLogout}>
              Logout
            </button>
          </div>
        </div>
      </header>
      <main className="wrap page adminPage">
        <div className="pageHeadRow">
          <div>
            <h1 className="pageTitle">Control center</h1>
            <p className="pageSub">
              Manual approval system — deposits & referral % credit only after you approve.
            </p>
          </div>
        </div>
        {toast.text ? <div className={`toast ${toast.type}`}>{toast.text}</div> : null}

        {loading ? (
          <p className="pageSub">Loading…</p>
        ) : (
          <>
        <section className="adminStats">
          <article className="card glassCard">
            <div className="statLabel">Users</div>
            <div className="statValue">{stats.users}</div>
          </article>
          <article className="card glassCard">
            <div className="statLabel">Pending deposits</div>
            <div className="statValue">{pendingDeposits}</div>
          </article>
          <article className="card glassCard">
            <div className="statLabel">Pending withdraws</div>
            <div className="statValue">{withdraws.filter((w) => w.status === 'PENDING').length}</div>
          </article>
          <article className="card glassCard">
            <div className="statLabel">Gift claims</div>
            <div className="statValue">{pendingGifts}</div>
          </article>
        </section>

        <section style={{ margin: '1.25rem 0' }}>
          <h2 className="sectionMiniTitle">Deposit approvals ({pendingDeposits} pending)</h2>
          <p className="hintDark" style={{ marginTop: 0 }}>
            Approve only after you confirm the on-chain transfer. Approval credits user balance and pays
            referrer commission automatically.
          </p>
          <div className="list">
            {deposits.map((d) => (
              <article key={d.id} className="card wdRequestCard">
                <div className="wdRequestTop">
                  <div>
                    <strong>
                      {d.userName || 'User'} · {d.status}
                    </strong>
                    <small className="wdMeta">
                      {d.userEmail} · {formatDate(d.at)}
                    </small>
                  </div>
                  <strong className="goldText wdAmt">{formatUsd(d.amount)}</strong>
                </div>
                <div className="wdDetailGrid">
                  <div>
                    <span className="statLabel">Network</span>
                    <strong>{d.networkLabel || '—'}</strong>
                  </div>
                  <div>
                    <span className="statLabel">Tx / note</span>
                    <strong style={{ wordBreak: 'break-all', fontSize: '0.85rem' }}>{d.txHash || '—'}</strong>
                  </div>
                </div>
                {d.status === 'PENDING' ? (
                  <div className="adminWdBtns">
                    <button type="button" className="chipBtn" onClick={() => onDeposit(d.id, 'APPROVE')}>
                      Approve & credit
                    </button>
                    <button type="button" className="chipBtn" onClick={() => onDeposit(d.id, 'REJECT')}>
                      Reject
                    </button>
                  </div>
                ) : null}
              </article>
            ))}
            {deposits.length ? null : <div className="empty">No deposit requests yet.</div>}
          </div>
        </section>

        <section style={{ margin: '1.25rem 0' }}>
          <h2 className="sectionMiniTitle">Gift claim notifications ({pendingGifts} pending)</h2>
          <div className="list">
            {gifts.map((g) => (
              <article key={g.id} className="card wdRequestCard">
                <div className="wdRequestTop">
                  <div>
                    <strong>
                      {g.choiceLabel || g.giftTitle} · {g.status}
                    </strong>
                    <small className="wdMeta">
                      {g.userName} · {g.userEmail} · {formatDate(g.at)}
                    </small>
                  </div>
                  <strong className="goldText">{g.rankName || '—'}</strong>
                </div>
                <div className="wdDetailGrid">
                  <div>
                    <span className="statLabel">Team deposits</span>
                    <strong className="goldText">{formatUsd(g.teamDeposits)}</strong>
                  </div>
                  <div>
                    <span className="statLabel">User choice</span>
                    <strong>
                      {g.choice === 'USDT' ? `${formatUsd(g.cashUsdt)} USDT` : g.giftLabel || g.choiceLabel || 'Gift'}
                    </strong>
                  </div>
                </div>
                <p className="empty" style={{ margin: '0 0 0.65rem' }}>
                  {g.giftDetail}
                </p>
                {g.status === 'PENDING' ? (
                  <div className="adminWdBtns">
                    <button type="button" className="chipBtn" onClick={() => onGift(g.id, 'FULFILLED')}>
                      {g.choice === 'USDT' ? 'Pay USDT & fulfill' : 'Mark gift shipped'}
                    </button>
                    <button type="button" className="chipBtn" onClick={() => onGift(g.id, 'REJECTED')}>
                      Reject
                    </button>
                  </div>
                ) : null}
              </article>
            ))}
            {gifts.length ? null : (
              <div className="empty">No gift claims yet — users claim from Team page when unlocked.</div>
            )}
          </div>
        </section>

        <section style={{ margin: '1.25rem 0' }}>
          <h2 className="sectionMiniTitle">
            Withdraw requests ({withdraws.filter((w) => w.status === 'PENDING').length} pending)
          </h2>
          <div className="list">
            {withdraws.map((w) => (
              <article key={w.id} className="card wdRequestCard">
                <div className="wdRequestTop">
                  <div>
                    <strong>
                      {w.userName || 'User'} · {w.status}
                    </strong>
                    <small className="wdMeta">
                      {w.userEmail} · {formatDate(w.at)}
                    </small>
                  </div>
                  <strong className="goldText wdAmt">{formatUsd(w.amount)}</strong>
                </div>
                <div className="wdDetailGrid">
                  <div>
                    <span className="statLabel">Network</span>
                    <strong>{w.networkLabel || '— (old request)'}</strong>
                  </div>
                  <div>
                    <span className="statLabel">Amount</span>
                    <strong className="goldText">{formatUsd(w.amount)}</strong>
                  </div>
                </div>
                <div className="field" style={{ marginBottom: '0.65rem' }}>
                  <label>Payout address</label>
                  <code className="addrValue">{w.address || 'No address on this request'}</code>
                </div>
                <div className="adminWdBtns">
                  {w.address ? (
                    <button
                      type="button"
                      className="chipBtn"
                      onClick={() => navigator.clipboard?.writeText(w.address)}
                    >
                      Copy address
                    </button>
                  ) : null}
                  {w.status === 'PENDING' ? (
                    <>
                      <button type="button" className="chipBtn" onClick={() => onWithdraw(w.id, 'PAID')}>
                        Mark paid
                      </button>
                      <button type="button" className="chipBtn" onClick={() => onWithdraw(w.id, 'REJECTED')}>
                        Reject
                      </button>
                    </>
                  ) : null}
                </div>
              </article>
            ))}
            {withdraws.length ? null : (
              <div className="empty">No withdraw requests yet — they appear when a user withdraws.</div>
            )}
          </div>
        </section>

        <section className="card" style={{ marginBottom: '1rem' }}>
          <h2 className="sectionMiniTitle">Live stakes by plan</h2>
          <p className="hintDark" style={{ marginTop: 0 }}>
            Profit only goes to the plan you select. If this says 0 stakes, users will get $0.
          </p>
          <div className="list">
            {stakes.map((s) => (
              <button
                key={s.planId}
                type="button"
                className={`listRow activityRow planPickRow ${planId === s.planId ? 'is-on' : ''}`}
                onClick={() => setPlanId(s.planId)}
              >
                <div>
                  <strong>
                    {s.planName} · {s.tag}
                  </strong>
                  <small>
                    {s.users} users · {s.stakes} stakes
                  </small>
                </div>
                <strong className="goldText">{formatUsd(s.amount)}</strong>
              </button>
            ))}
          </div>
        </section>

        <form className="card stakePanel adminProfitCard" onSubmit={onProfit}>
          <h2 className="sectionMiniTitle">Add plan profit (today)</h2>
          <div className="adminFormGrid">
            <div className="field">
              <label htmlFor="planPick">Plan</label>
              <select id="planPick" value={planId} onChange={(e) => setPlanId(Number(e.target.value))}>
                {PLANS.map((p) => {
                  const live = stakes.find((s) => s.planId === p.id)
                  return (
                    <option key={p.id} value={p.id}>
                      {p.name} · {live?.stakes || 0} stakes · {formatUsd(live?.amount || 0)}
                    </option>
                  )
                })}
              </select>
            </div>
            <div className="field">
              <label htmlFor="pct">Profit % for this payout</label>
              <input
                id="pct"
                type="number"
                min="0.01"
                max="100"
                step="0.01"
                value={percent}
                onChange={(e) => setPercent(e.target.value)}
                required
              />
            </div>
          </div>
          {selectedStake ? (
            <p className="hintDark" style={{ marginTop: 0 }}>
              Selected: <strong>{selectedStake.planName}</strong> — {selectedStake.stakes} stakes ·{' '}
              {formatUsd(selectedStake.amount)}
              {selectedStake.stakes === 0 ? ' · WARNING: no stakes on this plan' : ''}
            </p>
          ) : null}
          <div className="field">
            <label htmlFor="note">Note (optional)</label>
            <input
              id="note"
              type="text"
              placeholder="e.g. Friday daily yield"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          <div className="quickAmounts">
            {['0.2', '0.5', '0.8', '1', '1.5'].map((p) => (
              <button key={p} type="button" className="chipBtn" onClick={() => setPercent(p)}>
                {p}%
              </button>
            ))}
          </div>
          <button className="btn btnGold btnBlock" type="submit">
            Credit profit to {PLANS.find((p) => p.id === planId)?.name} holders
          </button>
          {toast.text ? <div className={`toast ${toast.type}`}>{toast.text}</div> : null}
        </form>

        <section className="card" style={{ marginTop: '1rem' }}>
          <h2 className="sectionMiniTitle">Withdraw rule</h2>
          <p className="pageSub" style={{ marginBottom: 0 }}>
            <strong>Testing:</strong> 10-day lock is OFF. Users can withdraw available USDT/profits anytime.
            Re-enable later in <code>withdraw.js</code> → <code>WITHDRAW_LOCK_ENABLED = true</code>.
          </p>
        </section>

        <section style={{ marginTop: '1.25rem' }}>
          <h2 className="sectionMiniTitle">Profit history</h2>
          <div className="list">
            {logs.map((l) => (
              <div key={l.id} className="listRow activityRow">
                <div>
                  <strong>
                    {l.planName} · {l.percent}%
                  </strong>
                  <small>
                    {l.usersHit} users · {l.stakesHit} stakes · {formatDate(l.at)}
                    {l.note ? ` · ${l.note}` : ''}
                  </small>
                </div>
                <strong className="goldText">{formatUsd(l.totalPaid)}</strong>
              </div>
            ))}
            {logs.length ? null : <div className="empty">No profit payouts yet.</div>}
          </div>
        </section>

        <section style={{ marginTop: '1.25rem' }}>
          <h2 className="sectionMiniTitle">Users · deposits & team ({users.length})</h2>
          <div className="list adminUserList">
            {users.map((u) => (
              <article key={u.id || u.email} className="card wdRequestCard">
                <div className="wdRequestTop">
                  <div>
                    <strong>
                      {u.name} · {u.rankName}
                    </strong>
                    <small className="wdMeta">
                      {u.email} · ref {u.refPct}% · referrals {u.referralCount || 0}
                    </small>
                  </div>
                  <strong className="goldText">{formatUsd(u.usdtBalance)}</strong>
                </div>
                <div className="wdDetailGrid">
                  <div>
                    <span className="statLabel">Personal deposit</span>
                    <strong className="goldText">{formatUsd(u.personalDeposit)}</strong>
                  </div>
                  <div>
                    <span className="statLabel">Team deposit</span>
                    <strong className="goldText">{formatUsd(u.teamDeposit)}</strong>
                  </div>
                  <div>
                    <span className="statLabel">Staked</span>
                    <strong>{formatUsd(u.stakedTotal)}</strong>
                  </div>
                  <div>
                    <span className="statLabel">Profit earned</span>
                    <strong>{formatUsd(u.totalProfit || 0)}</strong>
                  </div>
                </div>
                <small className="wdMeta">
                  {formatVolt(u.voltBalance)} · unlock {formatDate(u.withdrawUnlockAt)}
                </small>
              </article>
            ))}
            {users.length ? null : <div className="empty">No registered users yet.</div>}
          </div>
        </section>
          </>
        )}
      </main>
    </div>
  )
}
