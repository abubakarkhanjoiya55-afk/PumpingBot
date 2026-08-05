"""
PumpingBot Local MT5 Agent (Windows)

- Connects to Railway/server via WebSocket (no MetaAPI)
- Followers: execute COPY_OPEN / COPY_CLOSE instantly
- Master: runs M1 candle-pattern strategy locally, then server
  broadcasts to all followers in parallel

Usage:
  set SERVER_URL=https://your-app.up.railway.app
  set ACCESS_TOKEN=<jwt from /token>
  set MT5_LOGIN=...
  set MT5_PASSWORD=...
  set MT5_SERVER=...
  set AGENT_ROLE=master   # or follower
  set BOT_ACTIVE=1        # 1 only after user Start Bot
  python agent.py
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

# Windows cp1252 consoles raise UnicodeEncodeError on arrows / special dashes.
# Force safe printing even when the log file / console is legacy-encoded.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

_builtin_print = print


def print(*args, **kwargs):  # noqa: A001 - shadow builtin intentionally
    try:
        _builtin_print(*args, **kwargs)
    except UnicodeEncodeError:
        text = " ".join(str(a) for a in args)
        text = text.encode("ascii", "replace").decode("ascii")
        kwargs.pop("file", None)
        _builtin_print(text, **kwargs)


import requests

try:
    import websocket  # websocket-client
except ImportError:
    print("Install: pip install websocket-client requests")
    sys.exit(1)

# Allow importing trading_engine from repo root + local_agent helpers
ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = Path(__file__).resolve().parent
for p in (str(AGENT_DIR), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from mt5_local import LocalMT5  # noqa: E402

BOT_MAGIC = 888888
HEARTBEAT_SEC = 5
MASTER_SCAN_SEC = 3
TINY_USD = 50.0
# Never use more than this fraction of free margin on one entry
MAX_MARGIN_FRAC = 0.25
# Pause new entries if free margin (USD) below this
MIN_FREE_MARGIN_USD = 3.0
# Schedule: Mon-Fri = Gold only; Sat-Sun = BTC + ETH only
GOLD_STEMS = ("XAUUSD", "GOLD")
CRYPTO_STEMS = ("BTCUSD", "ETHUSD", "BTCUSDT", "ETHUSDT")


def _is_weekend(now: Optional[datetime] = None) -> bool:
    """Saturday/Sunday (local VPS clock). weekday: Mon=0 ... Sun=6."""
    d = now or datetime.now()
    return d.weekday() >= 5


def _symbol_matches(symbol: str, stems: tuple[str, ...]) -> bool:
    u = (symbol or "").upper()
    return any(stem in u for stem in stems)


def active_trade_symbols(all_symbols: list[str], now: Optional[datetime] = None) -> list[str]:
    """
    Mon-Fri -> Gold only.
    Sat-Sun -> BTC + ETH only (gold market closed / user rule).
    """
    weekend = _is_weekend(now)
    stems = CRYPTO_STEMS if weekend else GOLD_STEMS
    picked = [s for s in all_symbols if _symbol_matches(s, stems)]
    if picked:
        return picked
    # Fallbacks if SYMBOLS env omitted the right instruments
    suf = "c" if any(s.endswith("c") for s in all_symbols) else "m"
    if weekend:
        return [f"BTCUSD{suf}", f"ETHUSD{suf}"]
    return [f"XAUUSD{suf}"]


def _ws_url(server_url: str, token: str) -> str:
    u = urlparse(server_url.rstrip("/"))
    scheme = "wss" if u.scheme == "https" else "ws"
    netloc = u.netloc or u.path
    return urlunparse((scheme, netloc, "/ws/agent", "", f"token={token}", ""))


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name, default)
    return v if v not in (None, "") else default


class PumpingAgent:
    def __init__(self):
        self.server_url = _env("SERVER_URL", "http://127.0.0.1:8000")
        self.token = _env("ACCESS_TOKEN") or _env("TOKEN")
        self.role = (_env("AGENT_ROLE", "follower") or "follower").lower()
        self.bot_active = (_env("BOT_ACTIVE", "1") or "1").strip() in ("1", "true", "True", "yes")
        self.login = int(_env("MT5_LOGIN", "0") or 0)
        self.password = _env("MT5_PASSWORD", "")
        self.server = _env("MT5_SERVER", "")
        self.mt5_path = _env("MT5_PATH")
        # Default: demo/standard USD (*m). Set ACCOUNT_TYPE=cent for USC.
        self.account_type = (_env("ACCOUNT_TYPE", "standard") or "standard").strip().lower()
        default_symbols = (
            "XAUUSDc,BTCUSDc,ETHUSDc"
            if self.account_type in ("cent", "cents", "usc")
            else "XAUUSDm,BTCUSDm,ETHUSDm"
        )
        self.symbols = [
            s.strip() for s in (_env("SYMBOLS", default_symbols) or "").split(",")
            if s.strip()
        ]
        self.prefer_suffix = "c" if self.account_type in ("cent", "cents", "usc") else "m"

        if not self.token:
            raise SystemExit("ACCESS_TOKEN missing - login via /token and set it")
        if not self.login or not self.password or not self.server:
            raise SystemExit("MT5_LOGIN / MT5_PASSWORD / MT5_SERVER required")

        self.mt5 = LocalMT5(self.login, self.password, self.server, self.mt5_path)
        self.ws: Optional[websocket.WebSocketApp] = None
        self._stop = threading.Event()
        self._master_open = {}  # master_ticket -> local info (master role)
        self._copy_map = {}  # master_ticket -> local ticket
        self._ws_lock = threading.Lock()

    # -- MT5 ------------------------------------------------------------
    def connect_mt5(self) -> bool:
        ok = self.mt5.connect()
        if ok:
            # Resolve *c / *m against what this broker account actually has
            resolved = self.mt5.resolve_symbols(self.symbols, prefer_suffix=self.prefer_suffix)
            if resolved:
                self.symbols = resolved
            print(f"[AGENT] ACCOUNT_TYPE={self.account_type} symbols={self.symbols}")
            today = active_trade_symbols(self.symbols)
            mode = "WEEKEND BTC/ETH" if _is_weekend() else "WEEKDAY GOLD"
            print(f"[AGENT] Schedule={mode} active={today}")
            acc = self.mt5.account()
            if acc.get("is_cent"):
                print(f"[AGENT] Cent/USC account detected currency={acc.get('currency')}")
            # Kill leftover broker SL/TP so old positions cannot SL-close in loss
            cleared = self.mt5.clear_all_bot_sl_tp(BOT_MAGIC)
            if cleared:
                print(f"[AGENT] Cleared SL/TP on {cleared} open bot position(s)")
        return ok

    # -- WebSocket ------------------------------------------------------
    def start_ws(self):
        url = _ws_url(self.server_url, self.token)
        print(f"[AGENT] Connecting {url} as {self.role}")

        def on_open(ws):
            acc = self.mt5.account()
            hello = {
                "type": "hello",
                "role": self.role,
                "login": self.login,
                "server": self.server,
                "balance": acc.get("balance", 0),
                "equity": acc.get("equity", 0),
                "currency": acc.get("currency", ""),
                "is_cent": bool(acc.get("is_cent")),
                "ready": self.mt5.ready,
            }
            ws.send(json.dumps(hello))
            print(f"[AGENT] Hello sent role={self.role} ready={self.mt5.ready} "
                  f"bal={acc.get('balance')} {acc.get('currency')}")

        def on_message(ws, message):
            try:
                msg = json.loads(message)
            except Exception:
                return
            self.handle_command(msg)

        def on_error(ws, error):
            print(f"[AGENT] WS error: {error}")

        def on_close(ws, status, msg):
            print(f"[AGENT] WS closed status={status} {msg}")

        def _run_ws():
            while not self._stop.is_set():
                self.ws = websocket.WebSocketApp(
                    url,
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                )
                try:
                    self.ws.run_forever(ping_interval=20, ping_timeout=10)
                except Exception as e:
                    print(f"[AGENT] WS loop error: {e}")
                if self._stop.is_set():
                    break
                print("[AGENT] WS disconnected - reconnect in 3s")
                time.sleep(3)

        threading.Thread(target=_run_ws, daemon=True, name="agent-ws").start()

    def send(self, payload: dict):
        with self._ws_lock:
            if self.ws and self.ws.sock and self.ws.sock.connected:
                self.ws.send(json.dumps(payload))

    def reply(self, req_id: str, **kwargs):
        body = {"type": "ack", "req_id": req_id, **kwargs}
        self.send(body)

    # -- Commands from server -------------------------------------------
    def handle_command(self, msg: dict):
        mtype = msg.get("type")
        req_id = msg.get("req_id")

        if mtype == "welcome":
            if "bot_active" in msg:
                self.bot_active = bool(msg.get("bot_active"))
                print(f"[AGENT] welcome bot_active={self.bot_active}")
            return

        if mtype == "set_bot_active":
            self.bot_active = bool(msg.get("bot_active"))
            print(f"[AGENT] set_bot_active -> {self.bot_active}")
            if req_id:
                self.reply(req_id, ok=True, bot_active=self.bot_active)
            return

        if mtype == "ping":
            acc = self.mt5.account()
            self.send({
                "type": "pong",
                "balance": acc.get("balance", 0),
                "equity": acc.get("equity", 0),
                "currency": acc.get("currency", ""),
                "is_cent": bool(acc.get("is_cent")),
                "ready": self.mt5.ready,
                "bot_active": self.bot_active,
                "positions": len(self.mt5.positions()),
            })
            return

        if mtype == "copy_open":
            self._cmd_copy_open(msg, req_id)
            return

        if mtype == "copy_close":
            self._cmd_copy_close(msg, req_id)
            return

        if mtype == "master_start":
            self.bot_active = True
            print("[AGENT] Master strategy START - entries ON")
            self.reply(req_id, ok=True, bot_active=True)
            return

        if mtype == "master_stop":
            # Pause entries only - do NOT kill the whole agent process
            self.bot_active = False
            print("[AGENT] Master strategy STOP - entries OFF (agent stays online)")
            self.reply(req_id, ok=True, bot_active=False)
            return

    def _cmd_copy_open(self, msg: dict, req_id: str):
        t0 = time.perf_counter()
        symbol = msg["symbol"]
        side = msg["side"]
        master_ticket = int(msg.get("master_ticket") or 0)
        master_lot = float(msg.get("master_lot") or 0.01)
        master_balance = float(msg.get("master_balance") or 0)
        score = float(msg.get("score") or 50)
        sl = float(msg.get("sl") or 0)
        entry = float(msg.get("entry") or 0)

        if master_ticket and master_ticket in self._copy_map:
            self.reply(req_id, ok=True, skip=True, ticket=self._copy_map[master_ticket])
            return

        acc = self.mt5.account()
        bal = acc.get("balance") or 0
        if master_balance > 0 and bal > 0:
            lot = max(0.01, round(master_lot * (bal / master_balance), 2))
        else:
            lot = max(0.01, master_lot)
        if score >= 90:
            lot = round(lot * 1.15, 2)
        elif score >= 70:
            lot = round(lot * 1.08, 2)

        # Recalculate SL distance from master entry if provided
        local_sl = 0.0
        tick = self.mt5.symbol_tick(symbol)
        if tick and sl and entry:
            dist = abs(entry - sl)
            price = tick.ask if side == "BUY" else tick.bid
            local_sl = price - dist if side == "BUY" else price + dist

        result = self.mt5.market_order(
            symbol=symbol,
            side=side,
            volume=lot,
            sl=0.0,
            tp=0.0,
            magic=BOT_MAGIC,
            comment=f"PB_COPY_M{master_ticket}"[:31],
        )
        ms = (time.perf_counter() - t0) * 1000
        if result.get("ok"):
            self._copy_map[master_ticket] = result["ticket"]
            print(f"[COPY OPEN] {symbol} {side} lot={lot} ticket={result['ticket']} {ms:.0f}ms")
            self.reply(
                req_id, ok=True, ticket=result["ticket"], lot=lot,
                price=result.get("price"), ms=ms,
            )
        else:
            print(f"[COPY OPEN FAIL] {symbol} {result} {ms:.0f}ms")
            self.reply(req_id, ok=False, error=result.get("error"), ms=ms)

    def _cmd_copy_close(self, msg: dict, req_id: str):
        t0 = time.perf_counter()
        master_ticket = int(msg.get("master_ticket") or 0)
        symbol = msg.get("symbol") or ""
        local_ticket = self._copy_map.get(master_ticket)

        if local_ticket:
            result = self.mt5.close_position(local_ticket, comment="PB_COPY_CLOSE")
        else:
            result = self.mt5.close_by_master_link(master_ticket, symbol)

        ms = (time.perf_counter() - t0) * 1000
        if result.get("ok"):
            self._copy_map.pop(master_ticket, None)
            print(f"[COPY CLOSE] master={master_ticket} {ms:.0f}ms")
            self.reply(req_id, ok=True, ms=ms, profit=result.get("profit"))
        else:
            print(f"[COPY CLOSE FAIL] {result} {ms:.0f}ms")
            self.reply(req_id, ok=False, error=result.get("error"), ms=ms)

    # -- Heartbeat ------------------------------------------------------
    def heartbeat_loop(self):
        while not self._stop.is_set():
            try:
                acc = self.mt5.account()
                self.send({
                    "type": "heartbeat",
                    "balance": acc.get("balance", 0),
                    "equity": acc.get("equity", 0),
                    "currency": acc.get("currency", ""),
                    "is_cent": bool(acc.get("is_cent")),
                    "ready": self.mt5.ready,
                    "positions": self.mt5.positions(),
                })
            except Exception as e:
                print(f"[AGENT] heartbeat error: {e}")
            self._stop.wait(HEARTBEAT_SEC)

    # -- Master strategy (local, fastest) -------------------------------
    def master_loop(self):
        from trading_engine import (
            analyze_symbol, trade_eligible, calculate_lot, calc_breakout_sl,
            MAX_OPEN_TRADES, MAX_TRADES_PER_SYMBOL,
            MIN_COOLDOWN_SEC, STRONG_COOLDOWN_SEC, SCAN_INTERVAL_SEC,
            SESSION_MAX_DD_PCT, STRONG_SCORE, MASTER_AUTO_CLOSE, MASTER_PROFIT_ONLY,
            MARGIN_PROFIT_TRIGGER, HOLD_TRAIL_PCT, is_gold_symbol,
        )

        print(
            f"[MASTER] DEMO/STRICT: gold=strong-trend->FAST_SCALP  "
            f"max_open={MAX_OPEN_TRADES} cooldown={MIN_COOLDOWN_SEC}s "
            f"profit_only_close={MASTER_AUTO_CLOSE} account={self.account_type}"
        )
        last_close = {}
        session_start_equity = None
        entries_halted = False
        bridge = MasterMT5Bridge(self.mt5)
        _tiny_warned = False

        while not self._stop.is_set():
            try:
                if not self.mt5.ready:
                    time.sleep(2)
                    continue

                open_pos = [p for p in self.mt5.positions() if p.get("magic") == BOT_MAGIC]
                self._master_manage_positions(open_pos, bridge)

                if not self.bot_active:
                    if int(time.time()) % 60 < SCAN_INTERVAL_SEC:
                        print("[MASTER] bot_active=OFF - waiting for Start Bot")
                    time.sleep(SCAN_INTERVAL_SEC)
                    continue

                acc = self.mt5.account()
                balance = acc.get("balance") or 0
                equity = float(acc.get("equity") or balance or 0)
                free_margin = float(acc.get("free_margin") or 0)
                is_cent = bool(acc.get("is_cent"))
                bal_usd = (float(balance) / 100.0) if is_cent else float(balance)
                free_usd = (free_margin / 100.0) if is_cent else free_margin
                if session_start_equity is None and equity > 0:
                    session_start_equity = equity
                if session_start_equity and equity < session_start_equity * (1.0 - SESSION_MAX_DD_PCT):
                    if not entries_halted:
                        print(
                            f"[MASTER HALT] equity {equity:.2f} hit {SESSION_MAX_DD_PCT*100:.0f}% DD "
                            f"from {session_start_equity:.2f} - STOPPING NEW ENTRIES"
                        )
                        entries_halted = True
                    time.sleep(10)
                    continue

                # Free margin too thin -> broker will stop-out any new trade
                if free_usd < MIN_FREE_MARGIN_USD:
                    if not _tiny_warned:
                        print(
                            f"[MASTER HALT] free_margin~${free_usd:.2f} too low - "
                            f"no new entries (broker stop-out risk)"
                        )
                        _tiny_warned = True
                    time.sleep(15)
                    continue
                _tiny_warned = False

                if len(open_pos) >= MAX_OPEN_TRADES:
                    time.sleep(SCAN_INTERVAL_SEC)
                    continue

                now = time.time()
                opened_this_cycle = False
                scan_symbols = active_trade_symbols(self.symbols)
                # Log schedule once per mode change
                mode = "WEEKEND BTC/ETH" if _is_weekend() else "WEEKDAY GOLD"
                if getattr(self, "_last_schedule_mode", None) != mode:
                    self._last_schedule_mode = mode
                    print(f"[MASTER] Schedule -> {mode} symbols={scan_symbols}")

                for symbol in scan_symbols:
                    if opened_this_cycle:
                        break
                    open_pos = [p for p in self.mt5.positions() if p.get("magic") == BOT_MAGIC]
                    if len(open_pos) >= MAX_OPEN_TRADES:
                        break
                    if sum(1 for p in open_pos if p["symbol"] == symbol) >= MAX_TRADES_PER_SYMBOL:
                        continue
                    cd_need = float(last_close.get(symbol + "_cd") or MIN_COOLDOWN_SEC)
                    if symbol in last_close and now - last_close[symbol] < cd_need:
                        continue

                    analysis = analyze_symbol(symbol, bridge)
                    if not analysis or analysis.get("skip"):
                        continue
                    ok, reason = trade_eligible(analysis)
                    if not ok:
                        continue

                    trend = analysis["trend"]
                    score = analysis["score"]
                    trade_mode = analysis.get("trade_mode") or "SCALP"
                    strong_trend = bool(analysis.get("strong_trend"))
                    atr = analysis.get("atr") or 0
                    levels = analysis.get("breakout_levels") or {}
                    tick = analysis["tick"]
                    entry = tick.ask if trend == "BUY" else tick.bid
                    sl_for_size = calc_breakout_sl(symbol, trend, entry, levels, bridge)
                    if sl_for_size is None:
                        sl_for_size = entry - atr if trend == "BUY" else entry + atr
                    lot = calculate_lot(balance, atr, symbol, score, bridge,
                                        sl_distance=abs(entry - sl_for_size))
                    if not lot:
                        continue
                    info = bridge.symbol_info(symbol)
                    vmin = float(getattr(info, "volume_min", 0.01) or 0.01)
                    if bal_usd < TINY_USD:
                        lot = vmin
                    lot = max(vmin, float(lot))

                    needed = self.mt5.order_margin(symbol, trend, lot)
                    if needed is None:
                        from trading_engine import calc_margin_used
                        needed = calc_margin_used(lot, symbol, entry, bridge) or 0
                    if free_margin > 0 and needed > free_margin * MAX_MARGIN_FRAC:
                        print(
                            f"[MASTER SKIP] {symbol} lot={lot} needs margin={needed:.2f} "
                            f"but free={free_margin:.2f} (>{MAX_MARGIN_FRAC*100:.0f}% cap)"
                        )
                        continue

                    result = self.mt5.market_order(
                        symbol=symbol,
                        side=trend,
                        volume=lot,
                        sl=0.0,
                        tp=0.0,
                        magic=BOT_MAGIC,
                        comment=f"PB_{trade_mode[:6]}_{int(score)}"[:31],
                    )
                    if not result.get("ok"):
                        print(f"[MASTER FAIL] {symbol} {result}")
                        continue

                    ticket = result["ticket"]
                    from trading_engine import calc_margin_used
                    margin = needed or calc_margin_used(lot, symbol, entry, bridge) or 0
                    try:
                        self.mt5.clear_sl_tp(ticket)
                    except Exception:
                        pass
                    print(
                        f"[MASTER OPEN] {symbol} {trend} mode={trade_mode} "
                        f"score={score} strong={strong_trend} lot={lot} "
                        f"ticket={ticket} margin={margin:.2f} NO_SL profit_scalp_only"
                    )
                    self._master_open[ticket] = {
                        "symbol": symbol, "side": trend, "lot": lot,
                        "entry": entry, "sl": None, "score": score,
                        "atr": atr, "levels": levels, "margin_used": margin,
                        "opened_at": time.time(), "trade_mode": trade_mode,
                        "strong_trend": strong_trend, "peak_profit": 0.0,
                    }
                    cd = STRONG_COOLDOWN_SEC if (strong_trend and is_gold_symbol(symbol)) else MIN_COOLDOWN_SEC
                    last_close[symbol] = time.time()
                    last_close[symbol + "_cd"] = cd
                    opened_this_cycle = True

                    self.send({
                        "type": "master_trade_open",
                        "master_ticket": ticket,
                        "symbol": symbol,
                        "side": trend,
                        "lot": lot,
                        "balance": balance,
                        "entry": entry,
                        "sl": 0,
                        "score": score,
                        "atr": atr,
                        "source": "BOT",
                        "trade_mode": trade_mode,
                    })

                time.sleep(SCAN_INTERVAL_SEC or MASTER_SCAN_SEC)
            except Exception as e:
                print(f"[MASTER] loop error: {e}")
                time.sleep(2)

    def _master_manage_positions(self, open_pos, bridge):
        """
        Sync closed tickets + profit-only fast scalp exits.
        Never closes a losing trade (MASTER_PROFIT_ONLY).
        """
        from trading_engine import (
            MASTER_AUTO_CLOSE, MASTER_PROFIT_ONLY, MARGIN_PROFIT_TRIGGER,
            HOLD_TRAIL_PCT, STRONG_SCORE, is_gold_symbol,
        )

        live_tickets = {p["ticket"] for p in open_pos}
        for ticket in list(self._master_open.keys()):
            if ticket not in live_tickets:
                info = self._master_open.pop(ticket)
                deal = self.mt5.deal_close_reason(ticket)
                reason = deal.get("reason") or "BrokerClose"
                profit = deal.get("profit")
                if profit is None:
                    profit = info.get("last_profit")
                print(
                    f"[MASTER SYNC CLOSE] {info.get('symbol')} ticket={ticket} "
                    f"reason={reason} profit={profit}"
                )
                if reason in ("StopOut", "StopLoss", "VMargin"):
                    print(f"[WARN] Broker forced close ({reason}) - NOT bot.")
                self.send({
                    "type": "master_trade_close",
                    "master_ticket": ticket,
                    "symbol": info["symbol"],
                    "reason": reason,
                    "profit": profit,
                })

        for pos in open_pos:
            ticket = pos["ticket"]
            meta = self._master_open.get(ticket) or {
                "symbol": pos["symbol"],
                "side": "BUY" if pos["type"] == 0 else "SELL",
                "score": 60,
                "lot": pos["volume"],
                "entry": pos["price_open"],
                "trade_mode": "SCALP",
                "strong_trend": False,
                "peak_profit": 0.0,
            }
            profit = float(pos["profit"] or 0)
            meta["last_profit"] = profit
            peak = float(meta.get("peak_profit") or 0)
            if profit > peak:
                meta["peak_profit"] = profit
                peak = profit
            self._master_open[ticket] = meta

            # Strip broker SL/TP - loss exits stay owner/broker only
            if float(pos.get("sl") or 0) or float(pos.get("tp") or 0):
                try:
                    self.mt5.clear_sl_tp(ticket)
                except Exception as e:
                    print(f"[WARN] clear SL/TP error ticket={ticket}: {e}")

            if not MASTER_AUTO_CLOSE:
                continue
            if MASTER_PROFIT_ONLY and profit <= 0:
                continue

            score = float(meta.get("score") or 0)
            strong = bool(meta.get("strong_trend")) or score >= STRONG_SCORE
            mode = (meta.get("trade_mode") or "").upper()
            margin = float(meta.get("margin_used") or 0)
            # Fast scalp: quicker TP when strong gold trend
            tp_frac = MARGIN_PROFIT_TRIGGER
            if strong or mode == "FAST_SCALP" or is_gold_symbol(meta.get("symbol") or ""):
                tp_frac = min(tp_frac, 0.35)

            if margin > 0 and profit >= margin * tp_frac:
                self._master_close(ticket, meta, "FastScalpTP")
                continue
            if peak > 0 and profit >= max(0.5, peak * 0.25):
                # Giveback trail - lock scalp after peak
                if profit <= peak * HOLD_TRAIL_PCT and peak >= (margin * 0.2 if margin else 1.0):
                    self._master_close(ticket, meta, "FastScalpTrail")
                    continue

    def _master_close(self, ticket: int, meta: dict, reason: str):
        result = self.mt5.close_position(ticket, comment=f"PB_{reason}"[:31])
        if result.get("ok"):
            self._master_open.pop(ticket, None)
            print(f"[MASTER CLOSE] {meta.get('symbol')} ticket={ticket} {reason}")
            self.send({
                "type": "master_trade_close",
                "master_ticket": ticket,
                "symbol": meta.get("symbol"),
                "reason": reason,
                "profit": result.get("profit"),
            })

    def run(self):
        if not self.connect_mt5():
            raise SystemExit("MT5 connect failed")
        self.start_ws()
        threading.Thread(target=self.heartbeat_loop, daemon=True, name="heartbeat").start()
        if self.role == "master":
            self.master_loop()
        else:
            print("[AGENT] Follower mode - waiting for copy commands")
            while not self._stop.is_set():
                time.sleep(1)


class _Tick:
    def __init__(self, bid, ask):
        self.bid = bid
        self.ask = ask


class _SymInfo:
    def __init__(self, info):
        self.trade_tick_value = float(getattr(info, "trade_tick_value", 1) or 1)
        self.trade_tick_size = float(getattr(info, "trade_tick_size", 0.01) or 0.01)
        self.volume_min = float(getattr(info, "volume_min", 0.01) or 0.01)
        self.volume_max = float(getattr(info, "volume_max", 100) or 100)
        self.volume_step = float(getattr(info, "volume_step", 0.01) or 0.01)
        self.point = float(getattr(info, "point", 0.00001) or 0.00001)
        self.contract_size = float(getattr(info, "trade_contract_size", 100000) or 100000)


class _AccInfo:
    def __init__(self, d):
        self.balance = d.get("balance", 0)
        self.equity = d.get("equity", 0)
        self.leverage = d.get("leverage", 100)


class MasterMT5Bridge:
    """Adapt LocalMT5 to the interface trading_engine expects."""

    TIMEFRAME_M1 = "1m"
    TIMEFRAME_M5 = "5m"
    TIMEFRAME_M15 = "15m"
    TIMEFRAME_H1 = "1h"
    TIMEFRAME_H4 = "4h"
    TIMEFRAME_D1 = "1d"

    def __init__(self, local: LocalMT5):
        self._local = local
        self._mt5 = local._mt5
        self._ready = local.ready
        self.TIMEFRAME_M1 = self._mt5.TIMEFRAME_M1
        self.TIMEFRAME_M5 = getattr(self._mt5, "TIMEFRAME_M5", self._mt5.TIMEFRAME_M1)
        self.TIMEFRAME_M15 = self._mt5.TIMEFRAME_M15
        self.TIMEFRAME_H1 = self._mt5.TIMEFRAME_H1
        self.TIMEFRAME_H4 = self._mt5.TIMEFRAME_H4
        self.TIMEFRAME_D1 = self._mt5.TIMEFRAME_D1

    def symbol_info_tick(self, symbol):
        t = self._local.symbol_tick(symbol)
        if not t:
            return None
        return _Tick(t.bid, t.ask)

    def symbol_info(self, symbol):
        info = self._mt5.symbol_info(symbol)
        if not info:
            return None
        return _SymInfo(info)

    def account_info(self):
        return _AccInfo(self._local.account())

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        return self._local.copy_rates(symbol, timeframe, count)


def login_token(server_url: str, username: str, password: str) -> str:
    r = requests.post(
        f"{server_url.rstrip('/')}/token",
        data={"username": username, "password": password},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


if __name__ == "__main__":
    # Optional: USERNAME/PASSWORD to fetch token automatically
    if not _env("ACCESS_TOKEN") and not _env("TOKEN"):
        user = _env("USERNAME")
        pw = _env("PASSWORD")
        server = _env("SERVER_URL", "http://127.0.0.1:8000")
        if user and pw:
            tok = login_token(server, user, pw)
            os.environ["ACCESS_TOKEN"] = tok
            print("[AGENT] Token fetched via /token")
    PumpingAgent().run()
