import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { WITHDRAW_NETWORKS, getWithdrawNetwork } from '../lib/constants.js'
import { formatUsd } from '../lib/format.js'

export default function Withdraw() {
  const { user, withdraw } = useAuth()
  const [amount, setAmount] = useState('50')
  const [networkId, setNetworkId] = useState(user?.lastWithdrawNetworkId || 'trc20')
  const [address, setAddress] = useState(user?.lastWithdrawAddress || '')
  const [toast, setToast] = useState({ type: '', text: '' })
  const network = getWithdrawNetwork(networkId)
  const totalProfit = (user?.history || [])
    .filter((h) => h.type === 'PLAN_PROFIT')
    .reduce((sum, h) => sum + Number(h.amount || 0), 0)

  async function onSubmit(e) {
    e.preventDefault()
    setToast({ type: '', text: '' })
    try {
      await withdraw({ amount, networkId, address })
      setToast({
        type: 'ok',
        text: `Request sent: ${formatUsd(amount)} on ${network?.label}. Admin will pay to your address.`,
      })
    } catch (err) {
      setToast({ type: 'err', text: err?.message || 'Withdraw failed' })
    }
  }

  return (
    <main className="page">
      <h1 className="pageTitle">Withdraw</h1>
      <p className="pageSub">Enter amount, network, and your wallet address. Admin sees the full request.</p>
      <article className="card cardStrong">
        <div className="statLabel">Available USDT</div>
        <div className="statValue gold">{formatUsd(user?.usdtBalance)}</div>
      </article>
      <article className="card" style={{ marginTop: '0.85rem' }}>
        <div className="statLabel">Total profit earned</div>
        <div className="statValue gold">{formatUsd(totalProfit)}</div>
        <p className="empty" style={{ margin: '0.4rem 0 0' }}>
          Profits credit to Available — withdraw them with your payout address below.
        </p>
      </article>
      <form className="card stakePanel" onSubmit={onSubmit}>
        <h2 className="sectionMiniTitle">Payout details</h2>
        <div className="field">
          <label htmlFor="wd">USDT amount</label>
          <input
            id="wd"
            type="number"
            min="1"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="wdNet">Network</label>
          <select id="wdNet" value={networkId} onChange={(e) => setNetworkId(e.target.value)} required>
            {WITHDRAW_NETWORKS.map((n) => (
              <option key={n.id} value={n.id}>
                {n.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="wdAddr">Your wallet address</label>
          <input
            id="wdAddr"
            type="text"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder={network?.placeholder || 'Payout address'}
            required
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <p className="hintDark" style={{ marginTop: 0 }}>
          Use the same network as your wallet. Wrong network can mean lost funds.
        </p>
        <button className="btn btnGold btnBlock" type="submit">
          Submit withdraw request
        </button>
        {toast.text ? <div className={`toast ${toast.type}`}>{toast.text}</div> : null}
      </form>
      <p className="hintDark">
        Need USDT? <Link to="/app/deposit">Deposit here</Link>.
      </p>
    </main>
  )
}
