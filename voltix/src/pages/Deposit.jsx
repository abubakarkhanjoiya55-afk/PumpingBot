import { useMemo, useState } from 'react'
import { useAuth } from '../context/AuthContext.jsx'
import { DEPOSIT_WALLETS, WITHDRAW_NETWORKS } from '../lib/constants.js'
import { listDepositRequests } from '../lib/admin.js'
import { formatUsd } from '../lib/format.js'

export default function Deposit() {
  const { user, deposit, refresh } = useAuth()
  const [amount, setAmount] = useState('100')
  const [networkId, setNetworkId] = useState('trc20')
  const [txHash, setTxHash] = useState('')
  const [toast, setToast] = useState({ type: '', text: '' })
  const [copiedId, setCopiedId] = useState('')
  const [tick, setTick] = useState(0)
  const requests = useMemo(
    () => listDepositRequests().filter((r) => r.userEmail === user?.email).slice(0, 8),
    [user?.email, tick],
  )

  async function copyAddr(address, id) {
    try {
      await navigator.clipboard.writeText(address)
      setCopiedId(id)
      setTimeout(() => setCopiedId(''), 1600)
    } catch {
      setToast({ type: 'err', text: 'Copy failed — long-press the address' })
    }
  }

  function onSubmit(e) {
    e.preventDefault()
    setToast({ type: '', text: '' })
    try {
      deposit({ amount, networkId, txHash })
      refresh?.()
      setTick((n) => n + 1)
      setToast({
        type: 'ok',
        text: `Deposit request submitted for ${formatUsd(amount)}. Balance & referral commission credit only after admin approval.`,
      })
      setTxHash('')
    } catch (err) {
      setToast({ type: 'err', text: err?.message || 'Deposit failed' })
    }
  }

  return (
    <main className="page">
      <h1 className="pageTitle">Deposit USDT</h1>
      <p className="pageSub">
        Send USDT to a Voltix address, then submit a request. This is not auto-chain credit — admin must
        approve before balance and referral % are added.
      </p>
      <article className="card cardStrong balanceStrip">
        <div>
          <div className="statLabel">Available balance (approved only)</div>
          <div className="statValue gold">{formatUsd(user?.usdtBalance)}</div>
        </div>
      </article>
      <section className="addrStack">
        <h2 className="sectionMiniTitle">Deposit addresses</h2>
        {DEPOSIT_WALLETS.map((w) => (
          <article key={w.id} className="card addrCard">
            <div className="addrHead">
              <strong>{w.network}</strong>
              <span>{w.asset}</span>
            </div>
            <p className="addrHint">{w.hint}</p>
            <code className="addrValue">{w.address}</code>
            <button type="button" className="btn btnDark btnBlock" onClick={() => copyAddr(w.address, w.id)}>
              {copiedId === w.id ? 'Copied' : 'Copy address'}
            </button>
          </article>
        ))}
      </section>
      <form className="card stakePanel" onSubmit={onSubmit}>
        <h2 className="sectionMiniTitle">Submit deposit for admin approval</h2>
        <div className="field">
          <label htmlFor="dep">USDT amount sent</label>
          <input
            id="dep"
            type="number"
            min="10"
            step="1"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="depNet">Network used</label>
          <select id="depNet" value={networkId} onChange={(e) => setNetworkId(e.target.value)} required>
            {WITHDRAW_NETWORKS.map((n) => (
              <option key={n.id} value={n.id}>
                {n.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="tx">Tx hash / note (optional)</label>
          <input
            id="tx"
            type="text"
            value={txHash}
            onChange={(e) => setTxHash(e.target.value)}
            placeholder="Paste transaction hash if you have it"
            autoComplete="off"
          />
        </div>
        <p className="empty">
          Minimum 10 USDT. Referral commission is paid to your upline only after admin approves.
        </p>
        <button className="btn btnGold btnBlock" type="submit">
          Submit for admin approval
        </button>
        {toast.text ? <div className={`toast ${toast.type}`}>{toast.text}</div> : null}
      </form>
      <section style={{ marginTop: '1.25rem' }}>
        <h2 className="sectionMiniTitle">Your deposit requests</h2>
        <div className="list">
          {requests.map((r) => (
            <div key={r.id} className="listRow activityRow">
              <div>
                <strong>
                  {formatUsd(r.amount)} · {r.status}
                </strong>
                <small>
                  {r.networkLabel}
                  {r.txHash ? ` · ${r.txHash.slice(0, 14)}…` : ''}
                </small>
              </div>
            </div>
          ))}
          {requests.length ? null : <div className="empty">No deposit requests yet.</div>}
        </div>
      </section>
    </main>
  )
}
