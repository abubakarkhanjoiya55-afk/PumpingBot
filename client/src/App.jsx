import { useState, useEffect, useCallback } from 'react';
import {
  login, register, setToken, getToken,
  fetchDashboard, connectMT5, startBot, stopBot, API_URL,
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
        await login(form.username, form.password);
      } else {
        await register(form.username, form.email, form.password, form.referral);
        await login(form.username, form.password);
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
          <input placeholder="Username" value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} required />
          {tab === 'register' && (
            <input placeholder="Email" type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} required />
          )}
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

  const logout = () => { setToken(null); setAuthed(false); };

  const openTrades = trades.filter(t => t.status === 'open');
  const closedTrades = trades.filter(t => t.status === 'closed');
  const floatingPl = getFloatingPl(me);
  const openCount = Math.max(me?.open_trades_count ?? 0, openTrades.length, positions.length);
  const netPl = closedTrades.reduce((s, t) => s + (t.profit || 0), 0);
  const isAdmin = me?.is_admin || me?.username === 'admin';

  const posProfit = (trade) => {
    const byTicket = positions.find(x => x.ticket === trade.mt5_ticket);
    if (byTicket) return byTicket.profit;
    const bySymbol = positions.find(x => x.symbol === trade.symbol);
    return bySymbol ? bySymbol.profit : (trade.profit ?? null);
  };

  const latestSignal = signals[0];

  const nav = [
    { id: 'dashboard', icon: '📊', label: 'Dashboard' },
    { id: 'mt5', icon: '🔗', label: 'MT5' },
    { id: 'signals', icon: '📡', label: 'Signals' },
    { id: 'open', icon: '🔴', label: 'Open Trades' },
    { id: 'closed', icon: '✅', label: 'Closed Trades' },
    ...(isAdmin ? [
      { id: 'divider', divider: true },
      { id: 'admin-dash', icon: '⚡', label: 'Admin Stats' },
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

            <div className="bot-bar">
              <div>
                <div className="bot-status">
                  <div className={`dot ${me?.bot_active ? '' : 'off'}`} />
                  <strong>{me?.bot_active ? 'Bot Running' : 'Bot Stopped'}</strong>
                </div>
                {latestSignal && (
                  <div className="signal-info">
                    {latestSignal.symbol} | Signal: {latestSignal.signal_type} |
                    RSI: {latestSignal.rsi?.toFixed(1)} | Price: {latestSignal.price}
                  </div>
                )}
              </div>
              {me?.bot_active
                ? <button className="btn-stop" onClick={async () => { await stopBot(); refresh(); }}>⏹ Stop Bot</button>
                : <button className="btn-start" onClick={async () => { await startBot(); refresh(); }}>▶ Start Bot</button>
              }
            </div>
          </>
        )}

        {page === 'open' && (
          <>
            <h1>🔴 Open Trades ({openCount})</h1>
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th><th>Symbol</th><th>Type</th><th>Lot</th>
                    <th>Open Price</th><th>P&L</th><th>Status</th>
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
                    <th>Time</th><th>Symbol</th><th>Type</th><th>Lot</th><th>Profit</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {closedTrades.slice(0, 50).map(t => (
                    <tr key={t.id}>
                      <td>{new Date(t.opened_at).toLocaleTimeString()}</td>
                      <td><strong>{t.symbol}</strong></td>
                      <td className={t.trade_type === 'BUY' ? 'green' : 'red'}>{t.trade_type}</td>
                      <td>{t.lot}</td>
                      <td className={t.profit >= 0 ? 'green' : 'red'}>{fmt(t.profit)}</td>
                      <td><span className={t.profit >= 0 ? 'badge-profit' : 'badge-loss'}>{t.profit >= 0 ? 'PROFIT' : 'LOSS'}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {page === 'signals' && (
          <>
            <h1>📡 Signals</h1>
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
            {me?.mt5_connected && (
              <div className="connected-card">
                ✅ Connected: {me.mt5_login} @ {me.mt5_server}
              </div>
            )}
            <form className="mt5-form" onSubmit={async (e) => {
              e.preventDefault();
              setLoading(true);
              try {
                await connectMT5({
                  mt5_login: parseInt(mt5.mt5_login),
                  mt5_password: mt5.mt5_password,
                  mt5_server: mt5.mt5_server,
                });
                await refresh();
              } catch (ex) {
                alert(ex.response?.data?.detail || ex.message);
              }
              setLoading(false);
            }}>
              <input placeholder="MT5 Login" value={mt5.mt5_login} onChange={e => setMt5({ ...mt5, mt5_login: e.target.value })} required />
              <input placeholder="MT5 Password" type="password" value={mt5.mt5_password} onChange={e => setMt5({ ...mt5, mt5_password: e.target.value })} required />
              <input placeholder="Server" value={mt5.mt5_server} onChange={e => setMt5({ ...mt5, mt5_server: e.target.value })} required />
              <button type="submit" disabled={loading}>{loading ? 'Connecting...' : 'Connect MT5'}</button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
