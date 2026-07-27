import { useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext.jsx'
import { PLANS, getPlan } from '../lib/constants.js'
import { formatUsd } from '../lib/format.js'

export default function Plans() {
  const { user, stake } = useAuth()
  const [planId, setPlanId] = useState(1)
  const [amount, setAmount] = useState('50')
  const [toast, setToast] = useState({ type: '', text: '' })
  const plan = useMemo(() => getPlan(planId), [planId])

  function selectPlan(p) {
    setPlanId(p.id)
    setAmount(String(p.min))
    setToast({ type: '', text: '' })
  }

  function onSubmit(e) {
    e.preventDefault()
    setToast({ type: '', text: '' })
    const amt = Number(amount)
    if (!plan) {
      setToast({ type: 'err', text: 'Select a plan first' })
      return
    }
    if (!Number.isFinite(amt) || amt < plan.min || amt > plan.max) {
      setToast({ type: 'err', text: `${plan.name} accepts ${formatUsd(plan.min)} – ${formatUsd(plan.max)} only` })
      return
    }
    try {
      stake(amt, planId)
      setToast({ type: 'ok', text: `Staked ${formatUsd(amt)} in ${plan.name}` })
    } catch (err) {
      setToast({ type: 'err', text: err?.message || 'Stake failed' })
    }
  }

  return (
    <main className="page">
      <div className="pageHeadRow">
        <div>
          <h1 className="pageTitle">Stake USDT</h1>
          <p className="pageSub">
            Available: <strong className="goldText">{formatUsd(user?.usdtBalance)}</strong>
          </p>
        </div>
      </div>
      <p className="hintDark" style={{ marginTop: 0 }}>
        Tap a plan card to select it, then enter an amount inside that plan’s range.
      </p>
      <div className="grid4">
        {PLANS.map((p) => {
          const selected = planId === p.id
          return (
            <button
              key={p.id}
              type="button"
              className={`card planCard planSelect ${selected ? 'is-selected' : ''}`}
              style={{ '--accent': p.color }}
              onClick={() => selectPlan(p)}
            >
              <div className="planTop">
                <div className="planTag">
                  {p.name} · {p.tag}
                </div>
                {selected ? <span className="planSelectedBadge">Selected</span> : null}
              </div>
              <div className="planYield">
                {p.yieldMin}–{p.yieldMax}%
              </div>
              <div className="planRange">
                {formatUsd(p.min)} – {formatUsd(p.max)}
              </div>
              <div className="planFoot">Monthly target yield</div>
            </button>
          )
        })}
      </div>
      <form className="card stakePanel" onSubmit={onSubmit}>
        <h2 className="sectionMiniTitle">Start stake</h2>
        <div className="selectedPlanBanner">
          <span>
            Selected: <strong>{plan?.name}</strong>
          </span>
          <span className="goldText">
            {plan?.yieldMin}–{plan?.yieldMax}% / month
          </span>
        </div>
        <div className="field">
          <label htmlFor="stakeAmt">
            USDT amount ({formatUsd(plan?.min)} – {formatUsd(plan?.max)})
          </label>
          <input
            id="stakeAmt"
            type="number"
            min={plan?.min || 10}
            max={plan?.max || 1e4}
            step="1"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        </div>
        <div className="quickAmounts">
          {[plan?.min, Math.round(((plan?.min || 0) + (plan?.max || 0)) / 2), plan?.max]
            .filter(Boolean)
            .map((n) => (
              <button key={n} type="button" className="chipBtn" onClick={() => setAmount(String(n))}>
                {formatUsd(n)}
              </button>
            ))}
        </div>
        <button className="btn btnGold btnBlock" type="submit">
          Confirm stake · {plan?.name}
        </button>
        {toast.text ? <div className={`toast ${toast.type}`}>{toast.text}</div> : null}
      </form>
      <section style={{ marginTop: '1.25rem' }}>
        <h2 className="sectionMiniTitle">Your stakes</h2>
        <div className="list">
          {(user?.staked || []).map((s) => (
            <div key={s.id} className="listRow stakeRow">
              <div>
                <strong>
                  {s.planName} · {s.status}
                </strong>
                <small>
                  {s.yieldMin}–{s.yieldMax}% / mo
                </small>
              </div>
              <strong className="goldText">{formatUsd(s.amount)}</strong>
            </div>
          ))}
          {user?.staked?.length ? null : <div className="empty">No active stakes yet.</div>}
        </div>
      </section>
    </main>
  )
}
