import { useState, useEffect, useCallback } from 'react';
import {
  login, register, setToken, getToken,
  fetchDashboard, connectMT5, disconnectMT5, startBot, stopBot, API_URL,
  uploadPaymentScreenshot, fetchAdminStats, fetchAdminUsers, fetchPendingPayments,
  confirmPayment, rejectPayment, toggleUserBot, deleteUser, paymentScreenshotUrl,
  fetchAgentToken, fetchAgentSetup, adminDailyUnlock, adminDailyUnlockAllClear, eaDownloadUrl, eaInstallerUrl,
  fetchApiInfo, applyAppUpdate,
} from './api';

function fmt(n, me) {
  const v = Number(n || 0);
  if (me?.is_cent_account) {
    return `$${v.toFixed(2)} (cent)`;
  }
  return `$${v.toFixed(2)}`;
}

function fmtTradePl(n, me) {
  if (n == null || n === '') return '-';
  const v = Number(n);
  if (Number.isNaN(v)) return '-';
  return fmt(v, me);
}

function plBadge(n) {
  if (n == null || n === '') return <span className="badge-open">N/A</span>;
  const v = Number(n);
  if (Number.isNaN(v) || v === 0) return <span className="badge-open">FLAT</span>;
  return v > 0
    ? <span className="badge-profit">PROFIT</span>
    : <span className="badge-loss">LOSS</span>;
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
          $10 / 30 days · 24h free trial
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
  const fee = me?.subscription_fee ?? 10;
  const sharePct = me?.admin_profit_share_pct ?? 25;
  const dailyOwed = me?.daily_profit_owed ?? 0;
  const unlocked = !!me?.daily_unlocked_today;

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setMsg('');
    try {
      const kind = dailyOwed > 0 ? 'daily_share' : 'auto';
      const res = await uploadPaymentScreenshot(file, kind);
      setMsg(res.message || 'Uploaded');
      await onRefresh();
    } catch (ex) {
      setMsg(ex.response?.data?.detail || ex.message);
    }
    setUploading(false);
  };

  return (
    <>
      <h1>💳 Payment (Daily {sharePct}%)</h1>
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Today unlock</div>
          <div className={`stat-value ${unlocked ? 'green' : 'red'}`}>{unlocked ? 'YES' : 'LOCKED'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">25% due</div>
          <div className="stat-value">{fmt(dailyOwed)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Pay status</div>
          <div className="stat-value" style={{ fontSize: '1rem' }}>{me?.payment_status || 'clear'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">PKT date</div>
          <div className="stat-value" style={{ fontSize: '1rem' }}>{me?.pkt_today || '—'}</div>
        </div>
      </div>

      {!unlocked && (
        <div className="warn-banner">
          Aaj trades <strong>locked</strong>. Daily profit ka <strong>{sharePct}%</strong> admin ko bhejo,
          screenshot upload karo → Admin <strong>Approve</strong>. Phir Start Bot.
        </div>
      )}
      {unlocked && dailyOwed <= 0 && (
        <div className="warn-banner" style={{ borderColor: '#00ff88', color: '#00ff88' }}>
          Aaj unlock hai — PC agent ON + Start Bot se copy trades lagenge.
          Raat ko agar profit aaya to {sharePct}% bill + dubara approve.
        </div>
      )}
      {dailyOwed > 0 && (
        <div className="warn-banner">
          Amount due: <strong>{fmt(dailyOwed)}</strong> ({sharePct}% admin share).
          USDT BEP20: <code style={{ wordBreak: 'break-all' }}>{me?.admin_usdt_bep20 || '—'}</code>
          <br />Admin: {me?.admin_email || '—'}
        </div>
      )}
      {status === 'pending_review' || me?.payment_status === 'pending_review' ? (
        <div className="warn-banner">Screenshot uploaded — admin approval ka wait.</div>
      ) : null}

      <div className="sub-upload-card">
        <h2>Payment screenshot upload</h2>
        <p>
          {dailyOwed > 0
            ? `Pay ${fmt(dailyOwed)} (daily ${sharePct}%) → screenshot → admin approve → trades unlock.`
            : `Agar bill pending ho to ${sharePct}% bhejo. Optional package fee $${fee} bhi yahan SS se clear ho sakti hai.`}
        </p>
        <input type="file" accept="image/*,.pdf" onChange={onFile} disabled={uploading || me?.is_admin} />
        {uploading && <p>Uploading…</p>}
        {msg && <p className="error" style={{ color: '#00ff88' }}>{msg}</p>}
        {me?.has_payment_screenshot && <p style={{ color: '#888', marginTop: '.5rem' }}>Last screenshot on file ✓</p>}
      </div>
    </>
  );
}

function PcSetupPage({ me, onRefresh }) {
  const [setup, setSetup] = useState(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    let cancelled = false;
    fetchAgentSetup()
      .then(async (s) => {
        if (cancelled) return;
        setSetup(s);
        await onRefresh();
      })
      .catch((ex) => {
        if (!cancelled) setErr(ex.response?.data?.detail || ex.message);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const token = setup?.ea_token || me?.ea_token || '';
  const copyToken = async () => {
    if (!token) return;
    try {
      await navigator.clipboard.writeText(token);
      alert('Token copied! Ab PumpingBotSetup.bat chalao aur jab pooche paste karo.');
    } catch (_) {
      alert(token);
    }
  };

  return (
    <>
      <h1>💻 PC Setup</h1>
      <div className="warn-banner" style={{ borderColor: '#00ff88' }}>
        <strong>Asaan tarika:</strong> Installer ZIP download → Setup.bat → token paste.
        Installer EA + WebRequest khud laga dega. Rozana sirf MT5 + AutoTrading ON.
      </div>
      {err && <p className="error">{err}</p>}

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">EA status</div>
          <div className={`stat-value ${(me?.ea_online || me?.agent_online || me?.vps_ready) ? 'green' : 'red'}`}>
            {(me?.ea_online || me?.agent_online || me?.vps_ready) ? 'ONLINE' : 'OFFLINE'}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">MT5 login</div>
          <div className="stat-value" style={{ fontSize: '1rem' }}>{me?.mt5_login || '—'}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Today unlock</div>
          <div className={`stat-value ${me?.daily_unlocked_today ? 'green' : 'red'}`}>
            {me?.daily_unlocked_today ? 'YES' : 'NO'}
          </div>
        </div>
      </div>

      <div className="sub-upload-card" style={{ marginBottom: '1rem' }}>
        <h2>1) Installer (recommended)</h2>
        <p>Pehle MT5 page pe account save karo, phir:</p>
        <div style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
          <a className="btn-start" href={eaInstallerUrl()} style={{ display: 'inline-block', textDecoration: 'none' }}>
            Download Installer (ZIP)
          </a>
          <button type="button" className="btn-start" disabled={!token} onClick={copyToken}>
            Copy EA Token
          </button>
        </div>
        {token ? (
          <textarea
            readOnly
            value={token}
            rows={2}
            style={{ width: '100%', background: '#111', color: '#eee', border: '1px solid #333', borderRadius: 8, padding: 8 }}
          />
        ) : (
          <p style={{ color: '#f59e0b' }}>MT5 connect ke baad token yahan aayega.</p>
        )}
        <ol style={{ paddingLeft: '1.2rem', lineHeight: 1.7, color: '#ddd', marginTop: '1rem' }}>
          <li>ZIP unzip karo</li>
          <li><strong>PumpingBotSetup.bat</strong> double-click</li>
          <li>Token paste</li>
          <li>MT5 → AutoTrading ON → PumpingBotFollower chart pe drag (ek dafa)</li>
        </ol>
      </div>

      <div className="sub-upload-card">
        <h2>2) Advanced (manual EA only)</h2>
        <a className="btn-start" href={eaDownloadUrl()} style={{ display: 'inline-block', textDecoration: 'none' }}>
          Download EA (.mq5) only
        </a>
        <p style={{ color: '#888', marginTop: 8 }}>
          Detail: <code>USER_PC_SETUP.md</code>
          {setup?.server_url ? <> · Server: <code>{setup.server_url}</code></> : null}
        </p>
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
          <div className="stat-card"><div className="stat-label">Fee</div><div className="stat-value">{fmt(stats.subscription_fee ?? 10)}</div></div>
          <div className="stat-card"><div className="stat-label">Active Bots</div><div className="stat-value">{stats.active_bots}</div></div>
          <div className="stat-card"><div className="stat-label">Pending $</div><div className="stat-value">{fmt(stats.pending_amount)}</div></div>
        </div>
      )}

      <div style={{ margin: '1rem 0', display: 'flex', gap: '.5rem', flexWrap: 'wrap' }}>
        <button
          type="button"
          className="btn-start"
          onClick={async () => {
            const r = await adminDailyUnlockAllClear();
            alert(r.message || 'Done');
            load();
          }}
        >
          Unlock all ($0 owed) today
        </button>
      </div>

      <h2 style={{ margin: '1.5rem 0 .75rem' }}>Pending payments / screenshots</h2>
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>User</th><th>Email</th><th>Amount</th><th>Kind</th><th>Status</th><th>SS</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {pending.map(p => (
              <tr key={p.user_id}>
                <td><strong>{p.username}</strong></td>
                <td>{p.email}</td>
                <td>{fmt(p.total_owed || p.subscription_fee)}</td>
                <td>{p.payment_kind || '—'}</td>
                <td>{p.status || p.subscription_status}</td>
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
                  <button className="btn-start" style={{ padding: '.35rem .7rem', fontSize: '.8rem', background: '#2563eb' }}
                    onClick={async () => { await adminDailyUnlock(p.user_id); load(); }}>
                    Unlock today
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
                    onClick={async () => { await adminDailyUnlock(u.user_id); load(); }}>
                    Unlock
                  </button>
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
  const [botBusy, setBotBusy] = useState(false);
  const [botMsg, setBotMsg] = useState('');
  const [appVersion, setAppVersion] = useState('');
  const [updateReady, setUpdateReady] = useState(false);
  const [updating, setUpdating] = useState(false);

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
    let alive = true;
    const check = async () => {
      try {
        const info = await fetchApiInfo();
        if (!alive) return;
        const ver = String(info?.version || '');
        setAppVersion(ver);
        const seen = localStorage.getItem('pb_seen_version') || '';
        if (ver && seen && ver !== seen) setUpdateReady(true);
        if (ver && !seen) localStorage.setItem('pb_seen_version', ver);
      } catch (_) { /* ignore */ }
    };
    check();
    const t = setInterval(check, 60000);
    return () => { alive = false; clearInterval(t); };
  }, [authed]);

  const onUpdateApp = async () => {
    setUpdating(true);
    try {
      const info = await fetchApiInfo();
      if (info?.version) localStorage.setItem('pb_seen_version', String(info.version));
    } catch (_) { /* ignore */ }
    await applyAppUpdate();
  };

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
  // Merge DB open rows + live agent positions (orphans without DB row yet)
  const openTickets = new Set(openTrades.map(t => Number(t.mt5_ticket)).filter(Boolean));
  const liveOnly = (positions || []).filter(p => p?.ticket && !openTickets.has(Number(p.ticket)));
  const openCount = Math.max(me?.open_trades_count ?? 0, openTrades.length, positions.length);
  const netPl = closedTrades.reduce((s, t) => s + (t.profit || 0), 0);
  const isAdmin = me?.is_admin || me?.username === 'admin';
  const isFollower = me?.role === 'follower';
  const subActive = isAdmin || me?.subscription_status === 'active' || me?.subscription_status === 'trial';
  const mt5Live = !!(me?.mt5_ready || me?.vps_ready || me?.agent_online);
  const dailyOk = isAdmin || !!me?.daily_unlocked_today;
  const canStartBot = !!(me?.mt5_connected && dailyOk && (me?.daily_profit_owed || 0) <= 0);
  const startBlockedReason = !me?.mt5_connected
    ? 'Pehle MT5 connect karo'
    : (!dailyOk
      ? 'Aaj admin unlock / 25% approve chahiye'
      : ((me?.daily_profit_owed || 0) > 0 ? 'Pehle daily 25% clear karo' : ''));

  const toggleBot = async (wantOn) => {
    setBotBusy(true);
    setBotMsg('');
    try {
      const res = wantOn ? await startBot() : await stopBot();
      // Prefer server truth — agent mode keeps vps_desired on Stop; Start may
      // return bot_active=true while agent_online=false (VPS still booting).
      setMe(prev => prev ? {
        ...prev,
        bot_active: res?.bot_active ?? wantOn,
        vps_desired: res?.vps_desired ?? wantOn,
        vps_status: res?.vps_status ?? (wantOn ? 'starting' : 'stopping'),
        vps_ready: wantOn
          ? (res?.agent_online === true ? true : false)
          : prev.vps_ready,
      } : prev);
      const msg = res?.message || (wantOn ? 'Bot started' : 'Bot stopped');
      setBotMsg(msg);
      if (wantOn && res?.agent_online === false) {
        alert(msg);
      }
      await refresh();
    } catch (ex) {
      const detail = ex.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail
        : (Array.isArray(detail) ? detail.map(d => d.msg || d).join(', ') : null)
        || ex.message
        || 'Bot toggle failed';
      setBotMsg(msg);
      alert(msg);
      await refresh();
    }
    setBotBusy(false);
  };

  const posProfit = (trade) => {
    const byTicket = positions.find(x => Number(x.ticket) === Number(trade.mt5_ticket));
    if (byTicket) return byTicket.profit;
    const bySymbol = positions.find(x => x.symbol === trade.symbol);
    if (bySymbol) return bySymbol.profit;
    return trade.profit ?? null;
  };

  const latestSignal = signals[0];

  const nav = [
    { id: 'dashboard', icon: '📊', label: 'Dashboard' },
    { id: 'subscription', icon: '💳', label: 'Payment' },
    { id: 'pc-setup', icon: '💻', label: 'PC Setup' },
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
        {appVersion && <div className="app-ver">v{appVersion}</div>}
        {nav.map(item => item.divider
          ? <div key="div" className="nav-divider">────────</div>
          : (
            <div key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`}
              onClick={() => setPage(item.id)}>
              <span>{item.icon}</span> {item.label}
            </div>
          )
        )}
        <div className="sidebar-footer">
          <button
            type="button"
            className={`btn-update ${updateReady ? 'pulse' : ''}`}
            disabled={updating}
            onClick={onUpdateApp}
          >
            {updating ? 'Updating…' : (updateReady ? 'Update Available' : 'Update App')}
          </button>
          <button type="button" className="btn-logout" onClick={logout}>Logout</button>
        </div>
      </div>

      <div className="main">
        {updateReady && (
          <div className="update-banner">
            <div>
              <strong>Naya update ready hai</strong>
              <p>Naya bot version install karne ke liye Update dabao.</p>
            </div>
            <button type="button" className="btn-update" disabled={updating} onClick={onUpdateApp}>
              {updating ? 'Updating…' : 'Update Now'}
            </button>
          </div>
        )}
        {page === 'dashboard' && (
          <>
            <h1>Dashboard</h1>
            <div style={{ display: 'flex', gap: '.75rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
              <span className={mt5Live ? 'badge-on' : 'badge-off'} style={{ padding: '.35rem .75rem', borderRadius: 6, fontSize: '.85rem' }}>
                {mt5Live ? 'MT5 Live (PC)' : me?.mt5_connected ? 'PC Agent offline…' : 'MT5 Not Connected'}
              </span>
              <span className={dailyOk ? 'badge-on' : 'badge-off'} style={{ padding: '.35rem .75rem', borderRadius: 6, fontSize: '.85rem' }}>
                Today: {dailyOk ? 'Unlocked' : 'Locked'}
              </span>
              {me?.role && (
                <span style={{ padding: '.35rem .75rem', borderRadius: 6, fontSize: '.85rem', background: '#222', color: '#ccc' }}>
                  {me.role === 'master' ? 'Master — trades copy to followers' : 'Follower — copy on your PC agent'}
                </span>
              )}
            </div>
            {!dailyOk && (
              <div className="warn-banner">
                Aaj trades locked. <strong>Payment</strong> page se daily 25% screenshot → admin Approve
                (ya admin Daily Unlock). Phir <strong>PC Setup</strong> + Start Bot.
              </div>
            )}
            {(me?.daily_profit_owed || 0) > 0 && (
              <div className="warn-banner">
                Daily 25% due: <strong>{fmt(me.daily_profit_owed)}</strong> — Payment page pe upload karo.
              </div>
            )}
            {me?.subscription_status === 'trial' && (
              <div className="warn-banner" style={{ borderColor: '#60a5fa' }}>
                🎁 Free trial / pehla din — ~{Math.max(0, Math.floor((me.trial_remaining_seconds || 0) / 3600))}h left.
              </div>
            )}
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-label">Balance</div>
                <div className="stat-value">{fmt(me?.balance, me)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Equity</div>
                <div className="stat-value">{fmt(me?.equity, me)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Floating P/L</div>
                <div className={`stat-value ${floatingPl >= 0 ? 'green' : 'red'}`}>{fmt(floatingPl, me)}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Net P&L</div>
                <div className={`stat-value ${netPl >= 0 ? 'green' : 'red'}`}>{fmt(netPl, me)}</div>
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
                ⚠️ Pehle <strong>MT5</strong> connect + <strong>PC Setup</strong> pe agent chalao, phir Start Bot.
              </div>
            )}
            {me?.mt5_connected && !mt5Live && (
              <div className="warn-banner">
                EA offline — Exness MT5 open karo, Algo ON, PumpingBot EA chart pe (dekhó <strong>PC Setup</strong>).
              </div>
            )}

            <div className="bot-bar">
              <div>
                <div className="bot-status">
                  <div className={`dot ${me?.bot_active ? '' : 'off'}`} />
                  <strong>{me?.bot_active ? 'Bot Running' : 'Bot Stopped'}</strong>
                  {me?.vps_status && (
                    <span className="vps-pill">{me.vps_status}</span>
                  )}
                </div>
                {botMsg && <div className="signal-info">{botMsg}</div>}
                {latestSignal && (
                  <div className="signal-info">
                    {latestSignal.symbol} | Signal: {latestSignal.signal_type} |
                    Score: {latestSignal.score?.toFixed?.(0)} | Price: {latestSignal.price}
                  </div>
                )}
              </div>
              {me?.bot_active
                ? (
                  <button
                    className="btn-stop"
                    disabled={botBusy}
                    onClick={() => toggleBot(false)}
                  >
                    {botBusy ? 'Stopping…' : 'Stop Bot'}
                  </button>
                )
                : (
                  <button
                    className="btn-start"
                    disabled={botBusy || !canStartBot}
                    title={startBlockedReason}
                    onClick={() => toggleBot(true)}
                  >
                    {botBusy ? 'Starting…' : 'Start Bot'}
                  </button>
                )
              }
            </div>
            {!canStartBot && !me?.bot_active && startBlockedReason && (
              <div className="warn-banner">{startBlockedReason}</div>
            )}
          </>
        )}

        {page === 'subscription' && <SubscriptionPage me={me} onRefresh={refresh} />}
        {page === 'pc-setup' && <PcSetupPage me={me} onRefresh={refresh} />}
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
                          <strong>{pl == null ? '-' : fmtTradePl(pl, me)}</strong>
                        </td>
                        <td><span className="badge-open">OPEN</span></td>
                      </tr>
                    );
                  })}
                  {liveOnly.map(p => {
                    const pl = p.profit;
                    return (
                      <tr key={`live-${p.ticket}`} className="row-open">
                        <td>—</td>
                        <td><strong>{p.symbol}</strong></td>
                        <td className={p.type === 'BUY' ? 'green' : 'red'}><strong>{p.type}</strong></td>
                        <td>{p.lot}</td>
                        <td>{p.open_price?.toFixed?.(2) ?? p.open_price ?? '-'}</td>
                        <td className={pl == null ? '' : pl >= 0 ? 'green' : 'red'}>
                          <strong>{pl == null ? '-' : fmtTradePl(pl, me)}</strong>
                        </td>
                        <td><span className="badge-open">LIVE</span></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {openTrades.length === 0 && liveOnly.length === 0 && <p className="empty">No open trades.</p>}
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
                      <td className={(t.profit || 0) >= 0 ? 'green' : 'red'}>{fmtTradePl(t.profit, me)}</td>
                      <td>{plBadge(t.profit)}</td>
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
              App signals <strong>My Signals</strong> (/my-signals) pe LIVE 4H/1D breakouts se aate hain.
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
              Yahan login <strong>save</strong> hota hai. Trades aapke PC pe <strong>Exness MT5 + PumpingBot EA</strong> se
              lagenge — <strong>PC Setup</strong> dekho (ek dafa EA). Rozana bas MT5 + Algo ON.
            </p>

            {me?.mt5_connected ? (
              <div className="mt5-status-card">
                <div className="mt5-status-header">
                  <span className="mt5-status-icon">{mt5Live ? '✅' : '⏳'}</span>
                  <strong className={mt5Live ? 'green' : ''}>
                    {mt5Live ? 'MT5 / EA Connected' : 'Saved — Exness MT5 + EA chalao'}
                  </strong>
                </div>
                <div className="mt5-status-details">
                  <p><span>Login:</span> {me.mt5_login}</p>
                  <p><span>Server:</span> {me.mt5_server}</p>
                  <p><span>Balance:</span> {fmt(me.balance, me)}</p>
                  {me.is_cent_account && (
                    <p><span>Type:</span> Cent account ({me.account_currency || 'USC'})</p>
                  )}
                  {me.hosting_mode && <p><span>Host:</span> {me.hosting_mode}</p>}
                </div>
                {!mt5Live && (
                  <p className="mt5-sync-note">
                    PC Setup se EA download + token → chart pe lagao → AutoTrading ON.
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
                <p className="mt5-sync-note">
                  Neeche login/password/server daalo — mobile se bas itna.
                  Phir Dashboard → Start Bot.
                </p>
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
