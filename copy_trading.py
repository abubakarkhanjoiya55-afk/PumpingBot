"""
Multi-user copy trading — master trades (bot + manual) copy to all followers.
"""

import threading
import time
from datetime import datetime

from mt5_manager import mt5_manager, create_user_manager

BOT_MAGIC = 888888

# master_ticket -> {symbol, type, volume, copied_at}
_known_master_positions = {}
_copy_lock = threading.Lock()


def _get_pool_helpers():
    """Import pool helpers from main at runtime to avoid circular import."""
    import main
    return (main.pool_get, main.pool_is_ready, main.SessionLocal,
            main.Trade, main.User, main.MASTER_USER_ID, main.is_master_user)


def copy_trade_to_followers(master_user_id, symbol, trend, score, atr,
                            master_lot, master_balance, entry, sl, trade_mode,
                            master_ticket=None, source="BOT"):
    """Place proportional copy on every active follower account."""
    pool_get, pool_is_ready, SessionLocal, Trade, User, *_ = _get_pool_helpers()

    db = SessionLocal()
    try:
        followers = db.query(User).filter(
            User.bot_active == True,
            User.username != "admin",
            User.mt5_login != None,
        ).all()

        if not followers:
            return

        print(f"[COPY] {source}: {symbol} {trend} → {len(followers)} follower(s)")

        for follower in followers:
            try:
                if master_ticket:
                    existing = db.query(Trade).filter(
                        Trade.user_id == follower.id,
                        Trade.master_ticket == master_ticket,
                        Trade.status == "open",
                    ).first()
                    if existing:
                        continue

                conn = pool_get(follower.id)
                if conn is None or not pool_is_ready(follower.id):
                    if not follower.metaapi_account_id:
                        print(f"[COPY] ⚠️ {follower.username} — no MetaApi account")
                        continue
                    conn = create_user_manager(follower.metaapi_account_id)
                    import main
                    main.pool_add(follower.id, conn)
                    for _ in range(30):
                        if conn._ready:
                            break
                        time.sleep(2)
                    if not conn._ready:
                        print(f"[COPY] ⚠️ {follower.username} connection timeout")
                        continue

                follower_info = conn.account_info()
                if follower_info and master_balance > 0:
                    ratio = follower_info.balance / master_balance
                    follower_lot = max(0.01, round(master_lot * ratio, 2))
                else:
                    follower_lot = master_lot

                tick = conn.symbol_info_tick(symbol)
                if tick is None:
                    continue

                f_entry = tick.ask if trend == "BUY" else tick.bid
                f_sl = f_entry - atr if trend == "BUY" else f_entry + atr

                request = {
                    "action": conn.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": follower_lot,
                    "type": conn.ORDER_TYPE_BUY if trend == "BUY" else conn.ORDER_TYPE_SELL,
                    "price": f_entry,
                    "sl": f_sl,
                    "deviation": 50,
                    "magic": BOT_MAGIC,
                    "comment": f"PB_COPY_{source}_S{score}",
                    "type_time": conn.ORDER_TIME_GTC,
                    "type_filling": conn.ORDER_FILLING_IOC,
                }

                result = conn.order_send(request)
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
                    print(f"[COPY] ✅ {follower.username} {symbol} {trend} lot={follower_lot}")
                else:
                    print(f"[COPY] ❌ {follower.username} failed: {result.retcode}")

            except Exception as e:
                print(f"[COPY] ❌ {follower.username}: {e}")

    except Exception as e:
        print(f"[COPY] Error: {e}")
    finally:
        db.close()


def copy_close_to_followers(master_ticket, symbol):
    """When master closes a position, close matching follower positions."""
    pool_get, pool_is_ready, SessionLocal, Trade, User, *_ = _get_pool_helpers()

    db = SessionLocal()
    try:
        follower_trades = db.query(Trade).filter(
            Trade.master_ticket == master_ticket,
            Trade.status == "open",
        ).all()

        for ft in follower_trades:
            conn = pool_get(ft.user_id)
            if conn is None or not pool_is_ready(ft.user_id):
                ft.status = "closed"
                ft.closed_at = datetime.utcnow()
                continue

            positions = conn.positions_get(symbol=symbol)
            closed = False
            for pos in (positions or []):
                if pos.ticket == ft.mt5_ticket or (
                    pos.magic == BOT_MAGIC and "PB_COPY" in getattr(pos, "comment", "")
                ):
                    tick = conn.symbol_info_tick(symbol)
                    if tick is None:
                        break
                    price = tick.bid if pos.type == 0 else tick.ask
                    conn.order_send({
                        "action": conn.TRADE_ACTION_DEAL,
                        "symbol": symbol,
                        "volume": pos.volume,
                        "type": conn.ORDER_TYPE_SELL if pos.type == 0 else conn.ORDER_TYPE_BUY,
                        "position": pos.ticket,
                        "price": price,
                        "deviation": 50,
                        "magic": BOT_MAGIC,
                        "comment": "PB_COPY_CLOSE",
                        "type_time": conn.ORDER_TIME_GTC,
                        "type_filling": conn.ORDER_FILLING_IOC,
                    })
                    ft.status = "closed"
                    ft.profit = pos.profit
                    ft.close_price = price
                    ft.closed_at = datetime.utcnow()
                    closed = True
                    print(f"[COPY CLOSE] user={ft.user_id} {symbol} ticket={pos.ticket}")
                    break

            if not closed:
                ft.status = "closed"
                ft.closed_at = datetime.utcnow()

        db.commit()
    except Exception as e:
        print(f"[COPY CLOSE] Error: {e}")
    finally:
        db.close()


def _get_master_bot_tickets():
    """
    Master account ki apni bot-placed open trades ke tickets — DB se, kyunki
    kai brokers/MetaApi accounts magic number aur comment field preserve
    nahi karte (position data mein magic hamesha 0 wapas aata hai). Ticket
    hamesha reliable hota hai.
    """
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
    Background thread: when master bot is ON, detect new manual trades
    on master account and copy to all followers. Also sync closes.
    """
    print("[COPY WATCHER] Started — monitoring master manual trades")
    import main

    while True:
        try:
            master_id = main.MASTER_USER_ID
            if not master_id or not main.active_bots.get(master_id, False):
                time.sleep(5)
                continue

            if not mt5_manager._ready:
                time.sleep(5)
                continue

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
                        "PB_" in getattr(pos, "comment", "")
                    )
                    source = "BOT" if is_bot else "MANUAL"

                    # Bot trades already copied in run_user_bot — skip duplicates
                    if is_bot:
                        _known_master_positions[pos.ticket] = {
                            "symbol": pos.symbol, "type": trend,
                            "volume": pos.volume, "source": source,
                        }
                        continue

                    if not is_bot:
                        print(f"[COPY WATCHER] New MANUAL trade: {pos.symbol} {trend} ticket={pos.ticket}")
                        master_info = mt5_manager.account_info()
                        balance = master_info.balance if master_info else 1000

                        rates = mt5_manager.copy_rates_from_pos(
                            pos.symbol, mt5_manager.TIMEFRAME_M5, 0, 20)
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

                        threading.Thread(
                            target=copy_trade_to_followers,
                            args=(
                                master_id, pos.symbol, trend, 80, atr,
                                pos.volume, balance, entry, sl, "MANUAL",
                                pos.ticket, "MANUAL",
                            ),
                            daemon=True,
                        ).start()

                    _known_master_positions[pos.ticket] = {
                        "symbol": pos.symbol, "type": trend,
                        "volume": pos.volume, "source": source,
                    }

            # Detect closed positions
            with _copy_lock:
                closed_tickets = set(_known_master_positions.keys()) - current_tickets
                for ticket in closed_tickets:
                    info = _known_master_positions.pop(ticket, {})
                    sym = info.get("symbol", "")
                    if sym:
                        threading.Thread(
                            target=copy_close_to_followers,
                            args=(ticket, sym),
                            daemon=True,
                        ).start()

        except Exception as e:
            print(f"[COPY WATCHER] Error: {e}")

        time.sleep(3)


def start_copy_watcher():
    t = threading.Thread(target=manual_copy_watcher, daemon=True)
    t.start()
    print("[COPY WATCHER] Thread launched")
