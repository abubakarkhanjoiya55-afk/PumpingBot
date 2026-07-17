import { useState, useEffect, useCallback } from 'react';
import {
  login, register, setToken, getToken,
  fetchDashboard, connectMT5, disconnectMT5, startBot, stopBot, API_URL,
  uploadPaymentScreenshot, fetchAdminStats, fetchAdminUsers, fetchPendingPayments,
  confirmPayment, rejectPayment, toggleUserBot, deleteUser, paymentScreenshotUrl,
} from './api';

function fmt(n) {
  return `$${Number(n || 0).toFixed(2)}`;
}

function getFloatingPl(me) {
  if (!me) return 0;
  if (me.floating_pl != null && me.floating_pl !== 0) return me.floating_pl;
  if (me.profit != null && me.profit !== 0) return me.profit;
  return (me.equity || 0) - (me.balance || 0);
}

function LoginPage({ onLogin }) {
  const [tab, setTab] = useState('login');
  const [err, setErr] = useState('');
  const [form, setForm] = useState({ username: '', email: '', password: '', referral: '' });

  const submit = async (e) => {
    e.preventDefault();
    setErr('');
    try {
      if (tab === 'login') {
        await login(form.email, form.password);
      } else {
        await register(form.username, form.email, form.password, form.referral);
        await login(form.email, form.password);
      }
      onLogin();
    } catch (ex) {
      setErr(ex.response?.data?.detail || ex.message || 'Login failed');
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <h1>⚡ PumpingBot</h1>
        <p style={{ textAlign: 'center', color: '#888', fontSize: '.85rem', marginBottom: '1rem' }}>
          $20 / 30 days · Email account
        </p>
        <div style={{ display: 'flex', gap: '.5rem', marginBottom: '1rem' }}>
          <button type="button" onClick={() => setTab('login')}
            style={{ flex: 1, padding: '.5rem', background: tab === 'login' ? '#f0b90b' : '#333', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
            Login
          </button>
          <button type="button" onClick={() => setTab('register')}
            style={{ flex: 1, padding: '.5rem', background: tab === 'register' ? '#f0b90b' : '#333', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
            Register
          </button>
        </div>
        <form onSubmit={submit}>
          {tab === 'register' && (
            <input placeholder="Username" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} required />
          )}
          <input
            placeholder={tab === 'login' ? 'Email or Username' : 'Email'}
            type={tab === 'register' ? 'email' : 'text'}
            value={form.email}
            onChange={e => setForm({ ...form, email: e.target.value })}
            required={tab === 'register' || tab === 'login'}
          />
          <input placeholder="Password" type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} required />
          {tab === 'register' && (
            <input placeholder="Referral code (optional)" value={form.referral} onChange={e => setForm({ ...form, referral: e.target.value })} />
          )}
          <button type="submit">{tab === 'login' ? 'Login' : 'Create Account'}</button>
        </form>
        {err && <p className="error">{err}</p>}
        <p style={{ fontSize: '.75rem', color: '#666', marginTop: '1rem', textAlign: 'center' }}>API: {API_URL}</p>
      </div>
    </div>
  );
}

function SubscriptionPage({ me, onRefresh }) {
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState('');
  const status = me?.subscription_status || 'expired';
  const fee = me?.subscription_fee ?? 20;

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setMsg('');
    try {
      const res = await uploadPaymentScreenshot(file);
      setMsg(res.message || 'Uploaded');
      await onRefresh();
    } catch (ex) {
      setMsg(ex.response?.data?.detail || ex.message);
    }
    setUploading(false);
  };

  return (
    <>
      <h1>💳 Subscription</h1>
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Status</div>
          <div className={`stat-value ${status === 'active' ? 'green' : 'red'}`}>{status}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Fee</div>
          <div className="stat-value">{fmt(fee)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Package</div>
          <div className="stat-value" style={{ fontSize: '1.1rem' }}>{me?.subscription_days || 30} days</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Expires</div>
          <div className="stat-value" style={{ fontSize: '1rem' }}>
            {me?.subscription_expires_at ? new Date(me.subscription_expires_at).toLocaleDateString() : '—'}
          </div>
        </div>
      </div>

      {status !== 'active' && (
        <div className="warn-banner">
          Package inactive / expired. <strong>${fee}</strong> admin ({me?.admin_email || 'admin'}) ko pay karke
          neeche payment screenshot upload karo. Admin approve karega tab hi signal bot start hoga.
        </div>
      )}
      {status === 'pending_review' && (
        <div className="warn-banner">Screenshot uploaded — admin approval ka wait.</div>
      )}
      {status === 'active' && (
        <div className="warn-banner" style={{ borderColor: '#00ff88', color: '#00ff88' }}>
          Subscription active — signals/bot use kar sakte ho.
        </div>
      )}

      <div className="sub-upload-card">
        <h2>Payment screenshot upload</h2>
        <p>Pay ${fee} → screenshot yahan bhejo → admin approve → 30 din package open.</p>
        <input type="file" accept="image/*,.pdf" onChange={onFile} disabled={uploading || me?.is_admin} />
        {uploading && <p>Uploading…</p>}
        {msg && <p className="error" style={{ color: '#00ff88' }}>{msg}</p>}
        {me?.has_payment_screenshot && <p style={{ color: '#888', marginTop: '.5rem' }}>Last screenshot on file ✓</p>}
      </div>
    </>
  );
}

function AdminPage() {
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [pending, setPending] = useState([]);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    try {
      const [s, u, p] = await Promise.all([
        fetchAdminStats(), fetchAdminUsers(), fetchPendingPayments(),
      ]);
      setStats(s);
      setUsers(u);
      setPending(p);
    } catch (ex) {
      setErr(ex.response?.data?.detail || ex.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <>
      <h1>⚡ Admin Panel</h1>
      {err && <p className="error">{err}</p>}
      {stats && (
        <div className="stats-grid">
          <div className="stat-card"><div className="stat-label">Users</div><div className="stat-value">{stats.total_users}</div></div>
          <div className="stat-card"><div className="stat-label">Active Subs</div><div className="stat-value green">{stats.active_subscriptions ?? '—'}</div></div>
          <div className="stat-card"><div className="stat-label">Pending Pay</div><div className="stat-value">{stats.pending_payment}</div></div>
          <div className="stat-card"><div className="stat-label">Fee</div><div className="stat-value">{fmt(stats.subscription_fee ?? 20)}</div></div>
          <div className="stat-card"><div className="stat-label">Active Bots</div><div className="stat-value">{stats.active_bots}</div></div>
          <div className="stat-card"><div className="stat-label">Pending $</div><div className="stat-value">{fmt(stats.pending_amount)}</div></div>
        </div>
      )}

      <h2 style={{ margin: '1.5rem 0 .75rem' }}>Pending payments / screenshots</h2>
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>User</th><th>Email</th><th>Fee</th><th>Status</th><th>SS</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {pending.map(p => (
              <tr key={p.user_id}>
                <td><strong>{p.username}</strong></td>
                <td>{p.email}</td>
                <td>{fmt(p.total_owed || p.subscription_fee)}</td>
                <td>{p.subscription_status || p.status}</td>
                <td>
                  {p.payment_screenshot
                    ? <a href={paymentScreenshotUrl(p.user_id)} target="_blank" rel="noreferrer"
                        onClick={async (e) => {
                          e.preventDefault();
                          const r = await fetch(paymentScreenshotUrl(p.user_id), {
                            headers: { Authorization: `Bearer ${getToken()}` },
                          });
                          const blob = await r.blob();
                          window.open(URL.createObjectURL(blob), '_blank');
                        }}>View</a>
                    : '—'}
                </td>
                <td style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap' }}>
                  <button className="btn-start" style={{ padding: '.35rem .7rem', fontSize: '.8rem' }}
                    onClick={async () => { await confirmPayment(p.user_id); load(); }}>
                    Approve
                  </button>
                  <button className="btn-stop" style={{ padding: '.35rem .7rem', fontSize: '.8rem' }}
                    onClick={async () => { await rejectPayment(p.user_id); load(); }}>
                    Reject
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {pending.length === 0 && <p className="empty">No pending payments</p>}
      </div>

      <h2 style={{ margin: '1.5rem 0 .75rem' }}>All users</h2>
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>User</th><th>Email</th><th>Sub</th><th>Expires</th><th>Bot</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.user_id}>
                <td><strong>{u.username}</strong></td>
                <td>{u.email}</td>
                <td className={u.subscription_status === 'active' ? 'green' : 'red'}>{u.subscription_status}</td>
                <td>{u.subscription_expires_at ? new Date(u.subscription_expires_at).toLocaleDateString() : '—'}</td>
                <td>{u.bot_active ? 'ON' : 'OFF'}</td>
                <td style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap' }}>
                  <button className="btn-start" style={{ padding: '.3rem .6rem', fontSize: '.75rem' }}
                    onClick={async () => { await toggleUserBot(u.user_id); load(); }}>
                    Toggle Bot
                  </button>
                  {u.username !== 'admin' && (
                    <button className="btn-stop" style={{ padding: '.3rem .6rem', fontSize: '.75rem' }}
                      onClick={async () => {
                        if (!confirm(`Delete ${u.username}?`)) return;
                        await deleteUser(u.user_id); load();
                      }}>
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(!!getToken());
  const [page, setPage] = useState('dashboard');
  const [me, setMe] = useState(null);
  const [signals, setSignals] = useState([]);
  const [trades, setTrades] = useState([]);
  const [positions, setPositions] = useState([]);
  const [mt5, setMt5] = useState({ mt5_login: '', mt5_password: '', mt5_server: '' });
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!getToken()) return;
    try {
      const data = await fetchDashboard();
      setMe(data.me);
      setSignals(data.signals || []);
      setTrades(data.trades || []);
      setPositions(data.positions || []);
    } catch (ex) {
      if (ex.response?.status === 401) { setToken(null); setAuthed(false); }
    }
  }, []);

  useEffect(() => {
    if (!authed) return;
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [authed, refresh]);

  useEffect(() => {
    if (!me?.mt5_connected) return;
    setMt5(prev => ({
      mt5_login: me.mt5_login != null ? String(me.mt5_login) : prev.mt5_login,
      mt5_server: me.mt5_server || prev.mt5_server,
      mt5_password: prev.mt5_password,
    }));
  }, [me?.mt5_login, me?.mt5_server, me?.mt5_connected]);

  const logout = () => { setToken(null); setAuthed(false); };

  const openTrades = trades.filter(t => t.status === 'open');
  const closedTrades = trades
    .filter(t => t.status === 'closed')
    .sort((a, b) => new Date(b.closed_at || b.opened_at) - new Date(a.closed_at || a.opened_at));
  const floatingPl = getFloatingPl(me);
  const openCount = Math.max(me?.open_trades_count ?? 0, openTrades.length, positions.length);
  const netPl = closedTrades.reduce((s, t) => s + (t.profit || 0), 0);
  const isAdmin = me?.is_admin || me?.username === 'admin';
  const isFollower = me?.role === 'follower';
  const subActive = isAdmin || me?.subscription_status === 'active';
  const canStartBot = me?.mt5_connected && (me?.mt5_ready || isFollower) && subActive;

  const posProfit = (trade) => {
    const byTicket = positions.find(x => x.ticket === trade.mt5_ticket);
    if (byTicket) return byTicket.profit;
    const bySymbol = positions.find(x => x.symbol === trade.symbol);
    return bySymbol ? bySymbol.profit : (trade.profit ?? null);
  };

  const latestSignal = signals[0];

  const nav = [
    { id: 'dashboard', icon: '📊', label: 'Dashboard' },
    { id: 'subscription', icon: '💳', label: 'Subscription' },
    { id: 'mt5', icon: '🔗', label: 'MT5' },
    { id: 'signals', icon: '📡', label: 'Signals' },
    { id: 'open', icon: '🔴', label: 'Open Trades' },
    { id: 'closed', icon: '✅', label: 'Closed Trades' },
    ...(isAdmin ? [
      { id: 'divider', divider: true },
      { id: 'admin-dash', icon: '⚡', label: 'Admin Panel' },
    ] : []),
  ];

  if (!authed) return <LoginPage onLogin={() => setAuthed(true)} />;

  return (
    <div className="dashboard">
      <div className="sidebar">
        <div className="logo">⚡ PumpingBot</div>
        {nav.map(item => item.divider
          ? <div key="div" className="nav-divider">────────</div>
          : (
            <div key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`}
              onClick={() => setPage(item.id)}>
              <span>{item.icon}</span> {item.label}
            </div>
          )
        )}
        <div style={{ padding: '1rem 1.5rem', marginTop: 'auto' }}>
          <button className="btn-logout" onClick={logout}>Logout</button>
        </div>
      </div>

      <div className="main">
        {page === 'dashboard' && (
          <>
            <h1>Dashboard</h1>
            <div style={{ display: 'flex', gap: '.75rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
              <span className={me?.mt5_ready ? 'badge-on' : 'badge-off'} style={{ padding: '.35rem .75rem', borderRadius: 6, fontSize: '.85rem' }}>
                {me?.mt5_ready ? 'MT5 Live' : me?.mt5_connected ? 'MT5 Syncing…' : 'MT5 Not Connected'}
              </span>
              <span className={subActive ? 'badge-on' : 'badge-off'} style={{ padding: '.35rem .75rem', borderRadius: 6, fontSize: '.85rem' }}>
                Sub: {me?.subscription_status || 'expired'}
              </span>
              {me?.role && (
                <span style={{ padding: '.35rem .75rem', borderRadius: 6, fontSize: '.85rem', background: '#222', color: '#ccc' }}>
                  {me.role === 'master' ? 'Master — trades copy to followers' : 'Follower — master trades mirror here'}
                </span>
              )}
            </div>
            {!subActive && (
              <div className="warn-banner">
                Subscription inactive. <strong>Subscription</strong> page se ${me?.subscription_fee ?? 20} payment screenshot upload karo.
              </div>
            )}
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-label">Balance</div>
                <div className="stat-value">{fmt(me?.balance)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Equity</div>
                <div className="stat-value">{fmt(me?.equity)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Floating P/L</div>
                <div className={`stat-value ${floatingPl >= 0 ? 'green' : 'red'}`}>{fmt(floatingPl)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Net P&L</div>
                <div className={`stat-value ${netPl >= 0 ? 'green' : 'red'}`}>{fmt(netPl)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Open Trades</div>
                <div className="stat-value">{openCount}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Closed Trades</div>
                <div className="stat-value">{closedTrades.length}</div>
              </div>
            </div>

            {!me?.mt5_connected && (
              <div className="warn-banner">
                ⚠️ Pehle <strong>MT5</strong> page se account connect karo, phir Start Bot dabao.
              </div>
            )}

            <div className="bot-bar">
              <div>
                <div className="bot-status">
                  <div className={`dot ${me?.bot_active ? '' : 'off'}`} />
                  <strong>{me?.bot_active ? 'Bot Running' : 'Bot Stopped'}</strong>
                </div>
                {latestSignal && (
                  <div className="signal-info">
                    {latestSignal.symbol} | Signal: {latestSignal.signal_type} |
                    Score: {latestSignal.score?.toFixed?.(0)} | Price: {latestSignal.price}
                  </div>
                )}
              </div>
              {me?.bot_active
                ? <button className="btn-stop" onClick={async () => { await stopBot(); refresh(); }}>⏹ Stop Bot</button>
                : (
                  <button
                    className="btn-start"
                    disabled={!canStartBot}
                    title={!subActive ? 'Active subscription required' : (!canStartBot ? 'Connect MT5 first' : '')}
                    onClick={async () => {
                      try {
                        await startBot();
                        refresh();
                      } catch (ex) {
                        alert(ex.response?.data?.detail || ex.message);
                      }
                    }}
                  >
                    ▶ Start Bot
                  </button>
                )
              }
            </div>
          </>
        )}

        {page === 'subscription' && <SubscriptionPage me={me} onRefresh={refresh} />}
        {page === 'admin-dash' && isAdmin && <AdminPage />}

        {page === 'open' && (
          <>
            <h1>🔴 Open Trades ({openCount})</h1>
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th><th>Symbol</th><th>Type</th><th>Lot</th>
                    <th>Open Price</th><th>P/L</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {openTrades.map(t => {
                    const pl = posProfit(t);
                    return (
                      <tr key={t.id} className="row-open">
                        <td>{new Date(t.opened_at).toLocaleTimeString()}</td>
                        <td><strong>{t.symbol}</strong></td>
                        <td className={t.trade_type === 'BUY' ? 'green' : 'red'}><strong>{t.trade_type}</strong></td>
                        <td>{t.lot}</td>
                        <td>{t.open_price?.toFixed?.(2) ?? t.open_price}</td>
                        <td className={pl == null ? '' : pl >= 0 ? 'green' : 'red'}>
                          <strong>{pl == null ? '-' : fmt(pl)}</strong>
                        </td>
                        <td><span className="badge-open">OPEN</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {openCount === 0 && <p className="empty">No open trades.</p>}
            </div>
          </>
        )}

        {page === 'closed' && (
          <>
            <h1>✅ Closed Trades ({closedTrades.length})</h1>
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Closed</th><th>Symbol</th><th>Type</th><th>Lot</th>
                    <th>Open</th><th>Close</th><th>Profit</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {closedTrades.slice(0, 100).map(t => (
                    <tr key={t.id}>
                      <td>{new Date(t.closed_at || t.opened_at).toLocaleString()}</td>
                      <td><strong>{t.symbol}</strong></td>
                      <td className={t.trade_type === 'BUY' ? 'green' : 'red'}>{t.trade_type}</td>
                      <td>{t.lot}</td>
                      <td>{t.open_price?.toFixed?.(2) ?? t.open_price ?? '-'}</td>
                      <td>{t.close_price?.toFixed?.(2) ?? t.close_price ?? '-'}</td>
                      <td className={(t.profit || 0) >= 0 ? 'green' : 'red'}>{fmt(t.profit)}</td>
                      <td><span className={(t.profit || 0) >= 0 ? 'badge-profit' : 'badge-loss'}>{(t.profit || 0) >= 0 ? 'PROFIT' : 'LOSS'}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {closedTrades.length === 0 && <p className="empty">No closed trades yet.</p>}
            </div>
          </>
        )}

        {page === 'signals' && (
          <>
            <h1>📡 Signals (4H + 1D)</h1>
            <p style={{ color: '#888', marginBottom: '1rem', fontSize: '.9rem' }}>
              App signals Device Care (/device-care) pe LIVE 4H/1D breakouts se aate hain.
              Score 90+ app band ho tab bhi ntfy push milta hai.
            </p>
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr><th>Symbol</th><th>Signal</th><th>Score</th><th>RSI</th><th>ADX</th><th>Time</th></tr>
                </thead>
                <tbody>
                  {signals.slice(0, 30).map(s => (
                    <tr key={s.id}>
                      <td><strong>{s.symbol}</strong></td>
                      <td className={s.signal_type === 'BUY' ? 'green' : s.signal_type === 'SELL' ? 'red' : ''}>{s.signal_type}</td>
                      <td>{s.score?.toFixed(0)}</td>
                      <td>{s.rsi?.toFixed(1)}</td>
                      <td>{s.adx?.toFixed(1)}</td>
                      <td>{new Date(s.created_at).toLocaleTimeString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {page === 'mt5' && (
          <>
            <h1>MT5 Connection</h1>
            <p className="mt5-hint">
              Multiple accounts? <strong>Disconnect</strong> karo, phir naya login connect karo.
            </p>

            {me?.mt5_connected ? (
              <div className="mt5-status-card">
                <div className="mt5-status-header">
                  <span className="mt5-status-icon">{me.mt5_ready ? '✅' : '⏳'}</span>
                  <strong className={me.mt5_ready ? 'green' : ''}>
                    {me.mt5_ready ? 'MT5 Connected' : 'MT5 Syncing…'}
                  </strong>
                </div>
                <div className="mt5-status-details">
                  <p><span>Login:</span> {me.mt5_login}</p>
                  <p><span>Server:</span> {me.mt5_server}</p>
                  <p><span>Balance:</span> {fmt(me.balance)}</p>
                </div>
                {!me.mt5_ready && (
                  <p className="mt5-sync-note">
                    MetaApi connecting — balance $0 ho sakta hai 1–2 minute tak.
                  </p>
                )}
                <button
                  type="button"
                  className="btn-disconnect btn-disconnect-lg"
                  disabled={loading}
                  onClick={async () => {
                    if (!confirm(`Disconnect MT5 account ${me.mt5_login}?`)) return;
                    setLoading(true);
                    try {
                      await disconnectMT5();
                      setMt5({ mt5_login: '', mt5_password: '', mt5_server: '' });
                      await refresh();
                    } catch (ex) {
                      alert(ex.response?.data?.detail || ex.message);
                    }
                    setLoading(false);
                  }}
                >
                  Disconnect MT5
                </button>
              </div>
            ) : (
              <div className="mt5-status-card mt5-status-off">
                <strong>MT5 Not Connected</strong>
                <p className="mt5-sync-note">Neeche credentials daal kar connect karo.</p>
              </div>
            )}

            {isFollower && me?.mt5_connected && (
              <p className="mt5-hint">
                Copy trading ke liye Dashboard par <strong>Start Bot</strong> dabao.
              </p>
            )}

            <h2 className="mt5-form-title">{me?.mt5_connected ? 'Connect New Account' : 'Connect MT5'}</h2>
            <form className="mt5-form" onSubmit={async (e) => {
              e.preventDefault();
              setLoading(true);
              try {
                await connectMT5({
                  mt5_login: parseInt(mt5.mt5_login),
                  mt5_password: mt5.mt5_password,
                  mt5_server: mt5.mt5_server,
                });
                setMt5(prev => ({ ...prev, mt5_password: '' }));
                await refresh();
              } catch (ex) {
                alert(ex.response?.data?.detail || ex.message);
              }
              setLoading(false);
            }}>
              <input placeholder="MT5 Login" value={mt5.mt5_login} onChange={e => setMt5({ ...mt5, mt5_login: e.target.value })} required />
              <input placeholder="MT5 Password" type="password" value={mt5.mt5_password} onChange={e => setMt5({ ...mt5, mt5_password: e.target.value })} required />
              <input placeholder="Server (e.g. Exness-MT5Trial16)" value={mt5.mt5_server} onChange={e => setMt5({ ...mt5, mt5_server: e.target.value })} required />
              <button type="submit" className="btn-connect" disabled={loading}>
                {loading ? 'Connecting...' : me?.mt5_connected ? 'Connect New Account' : 'Connect MT5'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
