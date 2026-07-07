/**
 * PumpingBot Dashboard App
 */
(function () {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  let pollTimer = null;
  let me = null;

  // ── Helpers ──────────────────────────────────────────────────────────────
  function showToast(msg, isError = false) {
    const t = $('#toast');
    t.textContent = msg;
    t.style.borderColor = isError ? 'var(--red)' : 'var(--green)';
    t.classList.remove('hidden');
    setTimeout(() => t.classList.add('hidden'), 3500);
  }

  function fmtMoney(n) {
    const v = Number(n) || 0;
    const s = v >= 0 ? '+' : '';
    return `$${Math.abs(v).toFixed(2)}`;
  }

  function fmtTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleString('en-PK', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: 'short' });
  }

  function profitClass(v) {
    return Number(v) >= 0 ? 'profit-pos' : 'profit-neg';
  }

  // ── Auth ─────────────────────────────────────────────────────────────────
  $$('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      $$('.tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const name = tab.dataset.tab;
      $('#login-form').classList.toggle('hidden', name !== 'login');
      $('#register-form').classList.toggle('hidden', name !== 'register');
      $('#auth-error').classList.add('hidden');
    });
  });

  $('#login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const err = $('#auth-error');
    err.classList.add('hidden');
    try {
      await API.login($('#login-username').value, $('#login-password').value);
      showDashboard();
    } catch (ex) {
      err.textContent = ex.message;
      err.classList.remove('hidden');
    }
  });

  $('#register-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const err = $('#auth-error');
    err.classList.add('hidden');
    try {
      const data = await API.register(
        $('#reg-username').value,
        $('#reg-email').value,
        $('#reg-password').value,
        $('#reg-referral').value || null
      );
      showToast(`Account created! Your referral code: ${data.referral_code}`);
      $$('.tab')[0].click();
      $('#login-username').value = $('#reg-username').value;
    } catch (ex) {
      err.textContent = ex.message;
      err.classList.remove('hidden');
    }
  });

  $('#btn-logout').addEventListener('click', () => {
    API.logout();
    stopPolling();
    $('#dashboard-screen').classList.add('hidden');
    $('#auth-screen').classList.remove('hidden');
  });

  // ── MT5 Connect ──────────────────────────────────────────────────────────
  $('#mt5-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const data = await API.connectMT5(
        parseInt($('#mt5-login').value),
        $('#mt5-password').value,
        $('#mt5-server').value
      );
      showToast(data.message);
      $('#mt5-password').value = '';
      await refreshDashboard();
    } catch (ex) {
      showToast(ex.message, true);
    }
  });

  $('#btn-disconnect-mt5').addEventListener('click', async () => {
    const login = $('#mt5-login').value;
    if (!confirm(`Disconnect MT5 account ${login || ''}?`)) return;
    try {
      const data = await API.disconnectMT5();
      showToast(data.message);
      $('#mt5-login').value = '';
      $('#mt5-password').value = '';
      $('#mt5-server').value = '';
      await refreshDashboard();
    } catch (ex) {
      showToast(ex.message, true);
    }
  });

  // ── Bot Controls ─────────────────────────────────────────────────────────
  $('#btn-start').addEventListener('click', async () => {
    try {
      const data = await API.startBot();
      showToast(data.message);
      await refreshDashboard();
    } catch (ex) {
      showToast(ex.message, true);
    }
  });

  $('#btn-stop').addEventListener('click', async () => {
    try {
      const data = await API.stopBot();
      showToast(data.message);
      await refreshDashboard();
    } catch (ex) {
      showToast(ex.message, true);
    }
  });

  $('#btn-copy-ref').addEventListener('click', () => {
    const code = $('#referral-code').textContent;
    navigator.clipboard.writeText(code).then(() => showToast('Referral code copied!'));
  });

  // ── Dashboard Refresh ────────────────────────────────────────────────────
  async function refreshDashboard() {
    try {
      me = await API.getMe();
      updateStats(me);

      const [positions, trades, signals] = await Promise.all([
        API.getOpenPositions(),
        API.getTrades(),
        API.getSignals(),
      ]);

      renderPositions(positions);
      renderTrades(trades);
      renderSignals(signals);

      if (me.is_admin) {
        await refreshAdmin();
      }
    } catch (ex) {
      if (ex.message.includes('401') || ex.message.includes('Invalid token')) {
        API.logout();
        showDashboard();
      }
    }
  }

  function updateStats(m) {
    $('#user-label').textContent = `${m.username} (${m.role})`;
    $('#stat-balance').textContent = fmtMoney(m.balance);
    $('#stat-equity').textContent = fmtMoney(m.equity);
    const profitEl = $('#stat-profit');
    profitEl.textContent = (m.floating_pl != null ? m.floating_pl : m.profit);
    profitEl.className = 'stat-value ' + profitClass(m.floating_pl ?? m.profit);

    const botEl = $('#stat-bot');
    botEl.textContent = m.bot_active ? 'ON' : 'OFF';
    botEl.className = 'stat-value ' + (m.bot_active ? 'stat-bot-on' : 'stat-bot-off');

    const badge = $('#conn-badge');
    if (m.mt5_ready) {
      badge.textContent = 'MT5 Connected';
      badge.className = 'badge badge-on';
    } else {
      badge.textContent = 'MT5 Disconnected';
      badge.className = 'badge badge-off';
    }

    $('#referral-code').textContent = m.referral_code || '—';
    $('#mt5-login').value = m.mt5_login || '';
    $('#mt5-server').value = m.mt5_server || '';
    $('#mt5-status').textContent = m.mt5_connected
      ? `Connected: ${m.mt5_login} @ ${m.mt5_server}`
      : 'Enter your MT5 credentials to connect';

    const connectBtn = $('#btn-connect-mt5');
    const disconnectBtn = $('#btn-disconnect-mt5');
    if (m.mt5_connected) {
      connectBtn.textContent = 'Connect New Account';
      disconnectBtn.classList.remove('hidden');
    } else {
      connectBtn.textContent = 'Connect MT5';
      disconnectBtn.classList.add('hidden');
    }

    $('#role-hint').textContent = m.role === 'master'
      ? 'Master account — your trades copy to all active followers.'
      : 'Follower account — master trades will mirror to your account.';

    const canStart = m.mt5_connected && (m.mt5_ready || m.role === 'follower');
    $('#btn-start').disabled = !canStart || m.bot_active;
    $('#btn-stop').disabled = !m.bot_active;

    const banner = $('#payment-banner');
    if (m.payment_status === 'pending' || m.payment_status === 'overdue') {
      banner.classList.remove('hidden');
      $('#payment-amount').textContent = fmtMoney(m.amount_owed);
    } else {
      banner.classList.add('hidden');
    }
  }

  function renderPositions(positions) {
    const body = $('#positions-body');
    $('#pos-count').textContent = positions.length;
    if (!positions.length) {
      body.innerHTML = '<tr><td colspan="7" class="empty">No open positions</td></tr>';
      return;
    }
    body.innerHTML = positions.map(p => `
      <tr>
        <td><strong>${p.symbol}</strong></td>
        <td class="type-${p.type.toLowerCase()}">${p.type}</td>
        <td>${p.lot}</td>
        <td>${p.open_price}</td>
        <td>${p.current_price}</td>
        <td>${p.score}</td>
        <td class="${profitClass(p.profit)}">${fmtMoney(p.profit)}</td>
      </tr>
    `).join('');
  }

  function renderTrades(trades) {
    const body = $('#trades-body');
    if (!trades.length) {
      body.innerHTML = '<tr><td colspan="6" class="empty">No trades yet</td></tr>';
      return;
    }
    body.innerHTML = trades.slice(0, 20).map(t => `
      <tr>
        <td><strong>${t.symbol}</strong></td>
        <td class="type-${t.trade_type.toLowerCase()}">${t.trade_type}</td>
        <td>${t.lot}</td>
        <td class="${profitClass(t.profit)}">${fmtMoney(t.profit)}</td>
        <td class="status-${t.status}">${t.status}</td>
        <td>${fmtTime(t.opened_at)}</td>
      </tr>
    `).join('');
  }

  function renderSignals(signals) {
    const body = $('#signals-body');
    if (!signals.length) {
      body.innerHTML = '<tr><td colspan="6" class="empty">No signals yet</td></tr>';
      return;
    }
    body.innerHTML = signals.slice(0, 20).map(s => `
      <tr>
        <td><strong>${s.symbol}</strong></td>
        <td class="type-${s.signal_type.toLowerCase()}">${s.signal_type}</td>
        <td>${s.score.toFixed(0)}</td>
        <td>${s.rsi.toFixed(1)}</td>
        <td>${s.adx.toFixed(1)}</td>
        <td>${fmtTime(s.created_at)}</td>
      </tr>
    `).join('');
  }

  // ── Admin ────────────────────────────────────────────────────────────────
  async function refreshAdmin() {
    try {
      const [stats, payments, users] = await Promise.all([
        API.getAdminStats(),
        API.getPendingPayments(),
        API.getAllUsers(),
      ]);

      $('#admin-stats').innerHTML = [
        ['Users', stats.total_users],
        ['Active Bots', stats.active_bots],
        ['Open Trades', stats.open_trades],
        ['Gross Profit', `$${stats.gross_profit}`],
        ['Pending $', `$${stats.pending_amount}`],
        ['Master Bal', `$${stats.master_balance}`],
      ].map(([lbl, val]) => `
        <div class="admin-stat"><div class="val">${val}</div><div class="lbl">${lbl}</div></div>
      `).join('');

      const payBody = $('#payments-body');
      if (!payments.length) {
        payBody.innerHTML = '<tr><td colspan="6" class="empty">No pending payments</td></tr>';
      } else {
        payBody.innerHTML = payments.map(p => `
          <tr>
            <td>${p.username}</td>
            <td>${p.email}</td>
            <td>$${p.admin_share}</td>
            <td>$${p.referrer_comm}</td>
            <td><strong>$${p.total_owed}</strong></td>
            <td><button class="btn btn-success btn-sm" onclick="confirmPay(${p.user_id})">Confirm</button></td>
          </tr>
        `).join('');
      }

      const usersBody = $('#users-body');
      usersBody.innerHTML = users.map(u => `
        <tr>
          <td>${u.username} ${u.user_id === 1 ? '👑' : ''}</td>
          <td>${u.mt5_login || '—'}</td>
          <td>$${u.balance.toFixed(2)}</td>
          <td>${u.bot_active ? '🟢' : '🔴'}</td>
          <td>${u.payment_status} ${u.amount_owed > 0 ? `($${u.amount_owed})` : ''}</td>
          <td>
            ${u.user_id !== 1 ? `
              <button class="btn btn-ghost btn-sm" onclick="toggleUserBot(${u.user_id})">${u.bot_active ? 'Stop' : 'Start'}</button>
              <button class="btn btn-danger btn-sm" onclick="deleteUser(${u.user_id}, '${u.username}')">Del</button>
            ` : '—'}
          </td>
        </tr>
      `).join('');
    } catch (ex) {
      console.error('Admin refresh error:', ex);
    }
  }

  window.confirmPay = async (userId) => {
    try {
      const data = await API.confirmPayment(userId);
      showToast(data.message);
      await refreshDashboard();
    } catch (ex) { showToast(ex.message, true); }
  };

  window.toggleUserBot = async (userId) => {
    try {
      const data = await API.toggleBot(userId);
      showToast(data.message);
      await refreshDashboard();
    } catch (ex) { showToast(ex.message, true); }
  };

  window.deleteUser = async (userId, username) => {
    if (!confirm(`Delete user "${username}"? This cannot be undone.`)) return;
    try {
      const data = await API.deleteUser(userId);
      showToast(data.message);
      await refreshDashboard();
    } catch (ex) { showToast(ex.message, true); }
  };

  // ── Polling ──────────────────────────────────────────────────────────────
  function startPolling() {
    stopPolling();
    pollTimer = setInterval(refreshDashboard, 5000);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  async function showDashboard() {
    if (!API.isLoggedIn()) {
      $('#auth-screen').classList.remove('hidden');
      $('#dashboard-screen').classList.add('hidden');
      return;
    }
    $('#auth-screen').classList.add('hidden');
    $('#dashboard-screen').classList.remove('hidden');
    await refreshDashboard();
    startPolling();

    try {
      me = await API.getMe();
      if (me.is_admin) {
        $('#admin-panel').classList.remove('hidden');
      }
    } catch (_) {}
  }

  // ── Init ─────────────────────────────────────────────────────────────────
  showDashboard();
})();
