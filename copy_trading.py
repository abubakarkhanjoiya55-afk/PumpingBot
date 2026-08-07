"""
Fast multi-user copy trading — master + followers open/close in parallel.

Preferred path: local MT5 agents over WebSocket (no MetaAPI).
Optional fallback: MetaAPI when USE_METAAPI=1.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import threading
import time
from datetime import datetime

from mt5_manager import mt5_manager, create_user_manager

BOT_MAGIC = 888888
MAX_WORKERS = 32
WATCHER_POLL_SEC = 0.35
CONNECT_WAIT_TRIES = 40
CONNECT_WAIT_STEP = 0.25  # ~10s max cold connect

# agent = local Windows MT5 agents (default, free, fast, scales)
# metaapi = legacy cloud terminals (paid)
TRADING_BACKEND = os.environ.get("TRADING_BACKEND", "agent").strip().lower()
USE_METAAPI = os.environ.get("USE_METAAPI", "0").strip().lower() in (
    "1", "true", "yes", "on"
)

_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="copy")
_known_master_positions = {}
_copy_lock = threading.Lock()


def agent_mode_enabled() -> bool:
    return TRADING_BACKEND == "agent" or not USE_METAAPI


def _persist_agent_open_results(results, symbol, trend, score, master_ticket,
                                SessionLocal, Trade):
    """Save successful agent ACKs into trades table."""
    db = SessionLocal()
    try:
        for r in results or []:
            if not r.get("ok") or r.get("skip"):
                continue
            user_id = r.get("user_id")
            ticket = r.get("ticket")
            if not user_id or not ticket:
                continue
            existing = db.query(Trade).filter(
                Trade.user_id == user_id,
                Trade.master_ticket == master_ticket,
                Trade.status == "open",
            ).first()
            if existing:
                continue
            db.add(Trade(
                user_id=user_id,
                symbol=symbol,
                trade_type=trend,
                lot=float(r.get("lot") or 0.01),
                open_price=float(r.get("price") or 0),
                score=score or 0,
                mt5_ticket=int(ticket),
                master_ticket=master_ticket,
                status="open",
            ))
        db.commit()
    except Exception as e:
        print(f"[COPY AGENT] persist open error: {e}")
    finally:
        db.close()


def fanout_open_via_agents(symbol, trend, score, atr, master_lot, master_balance,
                           entry, sl, master_ticket, source="BOT"):
    """
    COPY_OPEN to:
      1) Python WS agents (if online)
      2) MT5 EA queue for everyone else unlocked (user PC — Exness MT5 only)
    """
    from agent_hub import agent_hub
    from ea_queue import ea_queue
    import main as main_mod
    pool_get, pool_is_ready, SessionLocal, Trade, User, *_ = _get_pool_helpers()

    db = SessionLocal()
    try:
        candidates = db.query(User).filter(
            User.mt5_login != None,
            User.username.notin_(["admin", "Admin99"]),
        ).all()
        # Auto-enable bot_active for unlocked EA users so they receive copies
        # without pressing Start Bot every day.
        for u in candidates:
            if main_mod.follower_can_copy(u):
                continue
            # Soft path: unlocked today + clear pay + mt5 → treat as copy-ready
            if (
                (u.daily_unlock_date or "") == main_mod.pkt_today()
                and (u.daily_profit_owed or 0) <= 0
                and (u.payment_status or "clear").lower() == "clear"
                and u.mt5_login
            ):
                u.bot_active = True
        db.commit()
        candidates = db.query(User).filter(
            User.mt5_login != None,
            User.username.notin_(["admin", "Admin99"]),
        ).all()
        active_ids = {u.id for u in candidates if main_mod.follower_can_copy(u)}
        skipped = [u.username for u in candidates if u.id not in active_ids]
        if skipped:
            print(f"[COPY] Locked / not unlocked today (skip): {', '.join(skipped[:12])}")
    finally:
        db.close()

    payload = {
        "type": "copy_open",
        "symbol": symbol,
        "side": trend,
        "score": score,
        "atr": atr,
        "master_lot": master_lot,
        "master_balance": master_balance,
        "entry": entry,
        "sl": sl,
        "master_ticket": master_ticket,
        "source": source,
    }

    ws_online = {s.user_id for s in agent_hub.online_followers(require_ready=False)}
    ws_targets = active_ids & ws_online
    results = []
    if ws_targets:
        results = agent_hub.broadcast_sync(
            payload,
            roles={"follower"},
            only_user_ids=ws_targets,
            require_ready=False,
            timeout=2.5,
        )
        _persist_agent_open_results(
            results, symbol, trend, score, master_ticket, SessionLocal, Trade
        )

    # EA queue for unlocked users not already handled by WS agent
    ea_targets = active_ids - ws_targets
    if ea_targets:
        n = ea_queue.enqueue(ea_targets, payload)
        print(f"[COPY EA] queued copy_open for {n} EA followers (master={master_ticket})")
    if not ws_targets and not ea_targets:
        print("[COPY] No unlocked followers (WS or EA)")
    return results


def fanout_close_via_agents(master_ticket, symbol):
    """Broadcast COPY_CLOSE to WS agents + EA queue."""
    from agent_hub import agent_hub
    from ea_queue import ea_queue
    pool_get, pool_is_ready, SessionLocal, Trade, User, *_ = _get_pool_helpers()
    import main as main_mod

    close_payload = {
        "type": "copy_close",
        "master_ticket": master_ticket,
        "symbol": symbol,
    }

    results = agent_hub.broadcast_sync(
        close_payload,
        roles={"follower"},
        require_ready=False,
        timeout=2.5,
    )

    db = SessionLocal()
    try:
        # Queue close for EA users who still have this master ticket open
        open_rows = db.query(Trade).filter(
            Trade.master_ticket == master_ticket,
            Trade.status == "open",
        ).all()
        ws_ids = {r.get("user_id") for r in (results or []) if r.get("user_id")}
        ea_ids = {row.user_id for row in open_rows if row.user_id not in ws_ids}
        # Also any online EA followers
        ea_ids |= (ea_queue.online_user_ids() - ws_ids)
        if ea_ids:
            ea_queue.enqueue(ea_ids, close_payload)
            print(f"[COPY EA] queued copy_close master={master_ticket} users={len(ea_ids)}")

        rows = open_rows
        by_user = {r.get("user_id"): r for r in (results or []) if r.get("user_id")}
        for row in rows:
            ack = by_user.get(row.user_id)
            if not ack:
                continue  # EA will ack later via /ea/ack
            row.status = "closed"
            row.closed_at = datetime.utcnow()
            if ack.get("profit") is not None:
                row.profit = float(ack.get("profit") or 0)
        db.commit()
    except Exception as e:
        print(f"[COPY AGENT] persist close error: {e}")
    finally:
        db.close()
    return results


def _get_pool_helpers():
    """Import pool helpers from main at runtime to avoid circular import."""
    import main
    return (main.pool_get, main.pool_is_ready, main.SessionLocal,
            main.Trade, main.User, main.MASTER_USER_ID, main.is_master_user)


def _follower_query(db, User):
    return db.query(User).filter(
        User.bot_active == True,
        User.username != "admin",
        User.mt5_login != None,
    ).all()


def ensure_follower_ready(follower, pool_get, pool_is_ready):
    """Return a ready connection, or None. Never blocks the fan-out for long."""
    conn = pool_get(follower.id)
    if conn is not None and pool_is_ready(follower.id):
        return conn

    if not follower.metaapi_account_id:
        print(f"[COPY] ⚠️ {follower.username} — no MetaApi account")
        return None

    if conn is None:
        conn = create_user_manager(follower.metaapi_account_id)
        import main
        main.pool_add(follower.id, conn)

    for _ in range(CONNECT_WAIT_TRIES):
        if getattr(conn, "_ready", False):
            return conn
        time.sleep(CONNECT_WAIT_STEP)

    print(f"[COPY] ⚠️ {follower.username} connection timeout")
    return None


def warmup_followers():
    """Pre-connect every active follower so open/close fan-out has zero connect lag."""
    pool_get, pool_is_ready, SessionLocal, _Trade, User, *_ = _get_pool_helpers()
    db = SessionLocal()
    try:
        followers = _follower_query(db, User)
        if not followers:
            return 0

        def _warm(f):
            return ensure_follower_ready(f, pool_get, pool_is_ready) is not None

        ok = 0
        futs = [_executor.submit(_warm, f) for f in followers]
        for fut in as_completed(futs):
            try:
                if fut.result():
                    ok += 1
            except Exception as e:
                print(f"[COPY WARMUP] {e}")
        print(f"[COPY WARMUP] {ok}/{len(followers)} follower connection(s) ready")
        return ok
    finally:
        db.close()


def _follower_lot(conn, master_lot, master_balance, score=50):
    """Balance-proportional lot; higher score nudges size up slightly."""
    info = conn.account_info()
    if info and master_balance > 0:
        ratio = info.balance / master_balance
        lot = master_lot * ratio
    else:
        lot = master_lot

    if score >= 90:
        lot *= 1.15
    elif score >= 70:
        lot *= 1.08

    return max(0.01, round(lot, 2))


def _open_one_follower(follower, symbol, trend, score, atr, master_lot,
                       master_balance, entry, sl, master_ticket, source,
                       pool_get, pool_is_ready, SessionLocal, Trade):
    """Place one follower market order. Runs inside the shared executor."""
    t0 = time.perf_counter()
    db = SessionLocal()
    try:
        if master_ticket:
            existing = db.query(Trade).filter(
                Trade.user_id == follower.id,
                Trade.master_ticket == master_ticket,
                Trade.status == "open",
            ).first()
            if existing:
                return {"user": follower.username, "ok": True, "skip": True}

        conn = ensure_follower_ready(follower, pool_get, pool_is_ready)
        if conn is None:
            return {"user": follower.username, "ok": False, "error": "not_ready"}

        follower_lot = _follower_lot(conn, master_lot, master_balance, score)
        tick = conn.symbol_info_tick(symbol)
        if tick is None:
            return {"user": follower.username, "ok": False, "error": "no_tick"}

        f_entry = tick.ask if trend == "BUY" else tick.bid
        sl_dist = abs(entry - sl) if sl and entry else (atr or 1.0)
        f_sl = f_entry - sl_dist if trend == "BUY" else f_entry + sl_dist

        request = {
            "action": conn.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": follower_lot,
            "type": conn.ORDER_TYPE_BUY if trend == "BUY" else conn.ORDER_TYPE_SELL,
            "price": f_entry,
            "sl": f_sl,
            "deviation": 80,
            "magic": BOT_MAGIC,
            "comment": f"PB_COPY_{source}_S{int(score or 0)}",
            "type_time": conn.ORDER_TIME_GTC,
            "type_filling": conn.ORDER_FILLING_IOC,
        }

        result = conn.order_send(request)
        if result.retcode != conn.TRADE_RETCODE_DONE:
            # One immediate retry with fresh price — no long sleep
            tick2 = conn.symbol_info_tick(symbol)
            if tick2:
                f_entry = tick2.ask if trend == "BUY" else tick2.bid
                request["price"] = f_entry
                request["sl"] = f_entry - sl_dist if trend == "BUY" else f_entry + sl_dist
            result = conn.order_send(request)

        ms = (time.perf_counter() - t0) * 1000
        if result.retcode == conn.TRADE_RETCODE_DONE:
            trade = Trade(
                user_id=follower.id,
                symbol=symbol,
                trade_type=trend,
                lot=follower_lot,
                open_price=f_entry,
                score=score or 0,
                mt5_ticket=result.order,
                master_ticket=master_ticket,
                status="open",
            )
            db.add(trade)
            db.commit()
            print(f"[COPY] ✅ {follower.username} {symbol} {trend} "
                  f"lot={follower_lot} in {ms:.0f}ms")
            return {"user": follower.username, "ok": True, "ms": ms, "ticket": result.order}

        print(f"[COPY] ❌ {follower.username} failed retcode={result.retcode} ({ms:.0f}ms)")
        return {"user": follower.username, "ok": False, "error": result.retcode, "ms": ms}
    except Exception as e:
        print(f"[COPY] ❌ {follower.username}: {e}")
        return {"user": follower.username, "ok": False, "error": str(e)}
    finally:
        db.close()


def copy_trade_to_followers(master_user_id, symbol, trend, score, atr,
                            master_lot, master_balance, entry, sl, trade_mode,
                            master_ticket=None, source="BOT"):
    """Place proportional copies on every active follower — all in parallel."""
    # Preferred: local agents (no MetaAPI)
    if agent_mode_enabled():
        from agent_hub import agent_hub
        if agent_hub.online_followers(require_ready=False):
            print(f"[COPY] AGENT fan-out {source}: {symbol} {trend}")
            return fanout_open_via_agents(
                symbol, trend, score, atr, master_lot, master_balance,
                entry, sl, master_ticket, source,
            )
        if not USE_METAAPI:
            print("[COPY] No online agents and MetaAPI disabled — skip")
            return []

    if not USE_METAAPI:
        print("[COPY] MetaAPI disabled — enable agents or USE_METAAPI=1")
        return []

    pool_get, pool_is_ready, SessionLocal, Trade, User, *_ = _get_pool_helpers()
    db = SessionLocal()
    try:
        followers = _follower_query(db, User)
        if not followers:
            return []

        print(f"[COPY] MetaAPI {source}: {symbol} {trend} → {len(followers)} PARALLEL")
        t0 = time.perf_counter()

        warm_futs = [
            _executor.submit(ensure_follower_ready, f, pool_get, pool_is_ready)
            for f in followers
        ]
        for fut in as_completed(warm_futs):
            try:
                fut.result()
            except Exception:
                pass

        futs = [
            _executor.submit(
                _open_one_follower, f, symbol, trend, score, atr, master_lot,
                master_balance, entry, sl, master_ticket, source,
                pool_get, pool_is_ready, SessionLocal, Trade,
            )
            for f in followers
        ]
        results = []
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                results.append({"ok": False, "error": str(e)})

        total_ms = (time.perf_counter() - t0) * 1000
        ok_n = sum(1 for r in results if r.get("ok"))
        print(f"[COPY] Done {ok_n}/{len(followers)} in {total_ms:.0f}ms total")
        return results
    except Exception as e:
        print(f"[COPY] Error: {e}")
        return []
    finally:
        db.close()


def schedule_copy_trade(*args, **kwargs):
    """Non-blocking fan-out — returns Future immediately."""
    return _executor.submit(copy_trade_to_followers, *args, **kwargs)


def _close_one_follower_trade(ft, symbol, pool_get, pool_is_ready, SessionLocal, Trade):
    """Close one follower DB trade on its MT5 account."""
    t0 = time.perf_counter()
    db = SessionLocal()
    try:
        row = db.query(Trade).filter(Trade.id == ft.id, Trade.status == "open").first()
        if row is None:
            return {"user_id": ft.user_id, "ok": True, "skip": True}

        conn = pool_get(ft.user_id)
        if conn is None or not pool_is_ready(ft.user_id):
            row.status = "closed"
            row.closed_at = datetime.utcnow()
            db.commit()
            return {"user_id": ft.user_id, "ok": False, "error": "not_ready_marked_closed"}

        positions = conn.positions_get(symbol=symbol) or []
        closed = False
        for pos in positions:
            comment = getattr(pos, "comment", "") or ""
            if pos.ticket == ft.mt5_ticket or (
                pos.magic == BOT_MAGIC and "PB_COPY" in comment
            ):
                tick = conn.symbol_info_tick(symbol)
                if tick is None:
                    break
                price = tick.bid if pos.type == 0 else tick.ask
                result = conn.order_send({
                    "action": conn.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": pos.volume,
                    "type": conn.ORDER_TYPE_SELL if pos.type == 0 else conn.ORDER_TYPE_BUY,
                    "position": pos.ticket,
                    "price": price,
                    "deviation": 80,
                    "magic": BOT_MAGIC,
                    "comment": "PB_COPY_CLOSE",
                    "type_time": conn.ORDER_TIME_GTC,
                    "type_filling": conn.ORDER_FILLING_IOC,
                })
                row.status = "closed"
                row.profit = pos.profit
                row.close_price = price
                row.closed_at = datetime.utcnow()
                closed = result.retcode == conn.TRADE_RETCODE_DONE
                ms = (time.perf_counter() - t0) * 1000
                print(f"[COPY CLOSE] user={ft.user_id} {symbol} "
                      f"ticket={pos.ticket} ok={closed} {ms:.0f}ms")
                break

        if not closed and row.status == "open":
            # Position already gone on broker — mark closed
            row.status = "closed"
            row.closed_at = datetime.utcnow()

        db.commit()
        return {"user_id": ft.user_id, "ok": True}
    except Exception as e:
        print(f"[COPY CLOSE] user={ft.user_id}: {e}")
        return {"user_id": ft.user_id, "ok": False, "error": str(e)}
    finally:
        db.close()


def copy_close_to_followers(master_ticket, symbol):
    """Close all follower positions linked to master_ticket — in parallel."""
    if agent_mode_enabled():
        print(f"[COPY CLOSE] AGENT fan-out master={master_ticket} {symbol}")
        results = fanout_close_via_agents(master_ticket, symbol)
        if results is not None and not USE_METAAPI:
            return results
        if results:
            return results

    pool_get, pool_is_ready, SessionLocal, Trade, User, *_ = _get_pool_helpers()
    db = SessionLocal()
    try:
        follower_trades = db.query(Trade).filter(
            Trade.master_ticket == master_ticket,
            Trade.status == "open",
        ).all()
        if not follower_trades:
            return []

        snapshots = [
            type("FT", (), {
                "id": ft.id,
                "user_id": ft.user_id,
                "mt5_ticket": ft.mt5_ticket,
            })()
            for ft in follower_trades
        ]
        print(f"[COPY CLOSE] MetaAPI master={master_ticket} {symbol} → "
              f"{len(snapshots)} PARALLEL")
        t0 = time.perf_counter()

        futs = [
            _executor.submit(
                _close_one_follower_trade, snap, symbol,
                pool_get, pool_is_ready, SessionLocal, Trade,
            )
            for snap in snapshots
        ]
        results = []
        for fut in as_completed(futs):
            try:
                results.append(fut.result())
            except Exception as e:
                results.append({"ok": False, "error": str(e)})

        print(f"[COPY CLOSE] Done in {(time.perf_counter() - t0) * 1000:.0f}ms")
        return results
    except Exception as e:
        print(f"[COPY CLOSE] Error: {e}")
        return []
    finally:
        db.close()


def schedule_close_followers(master_ticket, symbol):
    """Kick follower closes immediately without blocking the master close path."""
    if not master_ticket:
        return None
    return _executor.submit(copy_close_to_followers, master_ticket, symbol)


def parallel_open_master_and_followers(
    master_user_id, symbol, trend, score, atr, master_lot, master_balance,
    entry, sl, trade_mode, master_request, source="BOT",
):
    """
    Fire master + all follower market orders at the same moment.
    Returns (master_result, follower_results).
    Followers are linked to master_ticket as soon as master fills.
    """
    pool_get, pool_is_ready, SessionLocal, Trade, User, *_ = _get_pool_helpers()

    db = SessionLocal()
    try:
        followers = _follower_query(db, User)
    finally:
        db.close()

    # Warm followers before the bang
    warm_futs = [
        _executor.submit(ensure_follower_ready, f, pool_get, pool_is_ready)
        for f in followers
    ]
    for fut in as_completed(warm_futs):
        try:
            fut.result()
        except Exception:
            pass

    master_ticket_box = {"ticket": None}

    def _do_master():
        t0 = time.perf_counter()
        result = mt5_manager.order_send(master_request)
        if result and result.retcode == mt5_manager.TRADE_RETCODE_DONE:
            master_ticket_box["ticket"] = result.order
        print(f"[SYNC OPEN] MASTER {symbol} {trend} "
              f"ret={getattr(result, 'retcode', None)} "
              f"in {(time.perf_counter() - t0) * 1000:.0f}ms")
        return result

    def _do_follower(follower):
        # Fire IMMEDIATELY with master — do not wait for master fill.
        # master_ticket is backfilled below once master order returns.
        return _open_one_follower(
            follower, symbol, trend, score, atr, master_lot, master_balance,
            entry, sl, None, source, pool_get, pool_is_ready, SessionLocal, Trade,
        )

    t0 = time.perf_counter()
    master_fut = _executor.submit(_do_master)
    follower_futs = [_executor.submit(_do_follower, f) for f in followers]

    master_result = master_fut.result()
    follower_results = []
    for fut in as_completed(follower_futs):
        try:
            follower_results.append(fut.result())
        except Exception as e:
            follower_results.append({"ok": False, "error": str(e)})

    # Link follower rows → master ticket (orders already sent in parallel)
    ticket = master_ticket_box["ticket"]
    if ticket:
        db = SessionLocal()
        try:
            for fr in follower_results:
                fticket = fr.get("ticket")
                if not fticket:
                    continue
                row = db.query(Trade).filter(
                    Trade.mt5_ticket == fticket,
                    Trade.status == "open",
                ).first()
                if row:
                    row.master_ticket = ticket
            db.commit()
        finally:
            db.close()

        with _copy_lock:
            _known_master_positions[ticket] = {
                "symbol": symbol, "type": trend,
                "volume": master_lot, "source": source,
            }

    print(f"[SYNC OPEN] Fan-out complete in {(time.perf_counter() - t0) * 1000:.0f}ms "
          f"(followers={len(follower_results)})")
    return master_result, follower_results


def parallel_close_master_and_followers(master_pos, reason="SyncClose"):
    """
    Close master + all linked followers in the same instant.
    Returns (master_ok, master_profit, follower_results).
    """
    import main

    ticket = main._as_int_ticket(master_pos.ticket)
    symbol = master_pos.symbol

    def _close_master():
        return main.close_pos_master_only(master_pos, reason)

    # Kick followers first (submitted before awaiting master)
    follower_fut = _executor.submit(copy_close_to_followers, ticket, symbol)
    master_fut = _executor.submit(_close_master)

    master_ok, master_profit = False, 0
    try:
        master_ok, master_profit = master_fut.result()
    except Exception as e:
        print(f"[SYNC CLOSE] master error: {e}")

    follower_results = []
    try:
        follower_results = follower_fut.result()
    except Exception as e:
        print(f"[SYNC CLOSE] followers error: {e}")

    return master_ok, master_profit, follower_results


def _get_master_bot_tickets():
    """Master account bot-placed open trade tickets from DB."""
    import main
    master_id = main.MASTER_USER_ID
    if not master_id:
        return set()
    db = main.SessionLocal()
    try:
        rows = db.query(main.Trade.mt5_ticket).filter(
            main.Trade.user_id == master_id,
            main.Trade.status == "open",
            main.Trade.mt5_ticket != None,
        ).all()
        return {r[0] for r in rows}
    finally:
        db.close()


def manual_copy_watcher():
    """
    Fast background watcher for MASTER manual trades + missed closes.
    Polls ~3x/sec so close sync stays near real-time as a safety net.
    Primary close path is parallel_close / schedule_close_followers.
    """
    print("[COPY WATCHER] Started — fast poll "
          f"every {WATCHER_POLL_SEC}s")
    import main

    last_warm = 0.0
    while True:
        try:
            master_id = main.MASTER_USER_ID
            if not master_id or not main.active_bots.get(master_id, False):
                time.sleep(2)
                continue

            if not mt5_manager._ready:
                time.sleep(1)
                continue

            # Keep follower sockets warm every 30s
            now = time.time()
            if now - last_warm > 30:
                _executor.submit(warmup_followers)
                last_warm = now

            positions = mt5_manager.positions_get() or []
            current_tickets = set()
            bot_tickets = _get_master_bot_tickets()

            for pos in positions:
                current_tickets.add(pos.ticket)
                trend = "BUY" if pos.type == 0 else "SELL"

                with _copy_lock:
                    if pos.ticket in _known_master_positions:
                        continue

                    is_bot = (
                        pos.ticket in bot_tickets or
                        pos.magic == BOT_MAGIC or
                        "PB_" in (getattr(pos, "comment", "") or "")
                    )
                    source = "BOT" if is_bot else "MANUAL"

                    if is_bot:
                        _known_master_positions[pos.ticket] = {
                            "symbol": pos.symbol, "type": trend,
                            "volume": pos.volume, "source": source,
                        }
                        continue

                    print(f"[COPY WATCHER] New MANUAL trade: "
                          f"{pos.symbol} {trend} ticket={pos.ticket}")
                    master_info = mt5_manager.account_info()
                    balance = master_info.balance if master_info else 1000

                    rates = mt5_manager.copy_rates_from_pos(
                        pos.symbol, getattr(mt5_manager, "TIMEFRAME_M1", "1m"), 0, 30)
                    atr = 1.0
                    if rates and len(rates) > 5:
                        from trading_engine import calc_atr
                        h = [r["high"] for r in rates]
                        l = [r["low"] for r in rates]
                        c = [r["close"] for r in rates]
                        atr = calc_atr(h, l, c) or 1.0

                    tick = mt5_manager.symbol_info_tick(pos.symbol)
                    entry = tick.ask if trend == "BUY" else tick.bid if tick else 0
                    sl = entry - atr if trend == "BUY" else entry + atr

                    schedule_copy_trade(
                        master_id, pos.symbol, trend, 80, atr,
                        pos.volume, balance, entry, sl, "MANUAL",
                        pos.ticket, "MANUAL",
                    )

                    _known_master_positions[pos.ticket] = {
                        "symbol": pos.symbol, "type": trend,
                        "volume": pos.volume, "source": source,
                    }

            # Safety net: if master position vanished, close followers ASAP
            with _copy_lock:
                closed_tickets = set(_known_master_positions.keys()) - current_tickets
                for ticket in closed_tickets:
                    info = _known_master_positions.pop(ticket, {})
                    sym = info.get("symbol", "")
                    if sym:
                        schedule_close_followers(ticket, sym)

        except Exception as e:
            print(f"[COPY WATCHER] Error: {e}")

        time.sleep(WATCHER_POLL_SEC)


def start_copy_watcher():
    t = threading.Thread(target=manual_copy_watcher, daemon=True, name="copy-watcher")
    t.start()
    _executor.submit(warmup_followers)
    print("[COPY WATCHER] Thread launched (parallel fan-out mode)")
