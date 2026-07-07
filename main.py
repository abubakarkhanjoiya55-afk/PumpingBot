from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from jose import JWTError, jwt
from datetime import datetime, timedelta
from pydantic import BaseModel
import bcrypt as _bcrypt
import threading
import time
import asyncio
import smtplib
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from mt5_manager import mt5_manager, MT5Manager, find_or_create_metaapi_account, create_user_manager, MASTER_ACCOUNT_ID
from db_migrate import migrate_schema
from copy_trading import copy_trade_to_followers, start_copy_watcher
from trading_engine import (
    DAILY_MAX_LOSS_PCT, DAILY_TRAIL_START, DAILY_TRAIL_GAP,
    RISK_PER_TRADE_PCT, MAX_OPEN_TRADES, MAX_TRADES_PER_SYMBOL, MIN_SCORE, STRONG_SCORE,
    MAX_SPREAD_POINTS, SYMBOL_MAX_SPREAD, MIN_COOLDOWN_SEC,
    SCALP_ATR_MULT, HOLD_MIN_PROFIT, HOLD_TRAIL_PCT, TRAILING_LEVELS,
    ema, calc_rsi, calc_stoch_rsi, calc_adx, calc_atr, calc_macd, calc_bollinger,
    get_trend, get_profit_target, get_locked_profit, is_scalp_trade,
    calculate_lot, analyze_symbol, should_take_trade,
    get_htf_atr, calc_margin_used, profit_to_price,
)

ELITE_SCORE          = 90     # is se upar: TP ka wait, sirf SL trail ho
MARGIN_PROFIT_MULT   = 2.0    # profit >= margin * 2 → jaldi book (score < 90)
ELITE_SL_LOCK_PCT    = 0.70   # score >= 90: peak profit ka 70% broker SL par lock
ELITE_MIN_PEAK       = 5.0    # itna peak profit banne ke baad hi SL lock start ho

import os
SECRET_KEY = os.environ.get("SECRET_KEY", "goldbot-secret-key-2024")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./goldbot.db")

# Email config — Railway environment variables se
EMAIL_USER  = os.environ.get("EMAIL_USER",  "pumpingbot333@gmail.com")
EMAIL_PASS  = os.environ.get("EMAIL_PASS",  "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "pumpingbot333@gmail.com")
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI(title="PumpingBot Platform")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

SYMBOLS = [
    "XAUUSDm", "XAGUSDm", "BTCUSDm", "ETHUSDm", "SOLUSDm",
    "EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm", "USDCADm", "GBPJPYm", "NZDUSDm",
]

API_VERSION = "3.3.1"   # Railway deploy verify — curl /api should show this version
MASTER_USER_ID = None   # Set at startup from admin username

def is_master_user(user):
    return user is not None and user.username == "admin"

# ─── FIX: Global threading.Event for proper thread synchronization ────────────
# Bot thread waits on this event — set ONLY when MetaApi _ready=True
metaapi_ready_event = threading.Event()
active_bots         = {}
last_close_times    = {}
# ─────────────────────────────────────────────────────────────────────────────

# ─── CONNECTION POOL: Har user ka alag MT5 connection ─────────────────────────
# user_id → mt5_connection_object
# Master (user_id=1) = mt5_manager (existing singleton)
# Followers = unka apna connection object (same class as mt5_manager)
user_connections     = {}   # {user_id: connection_object}
user_ready_events    = {}   # {user_id: threading.Event}

def pool_get(user_id):
    """User ka connection lo — master ke liye mt5_manager use karo"""
    if MASTER_USER_ID is not None and user_id == MASTER_USER_ID:
        return mt5_manager
    return user_connections.get(user_id)

def pool_add(user_id, connection):
    """Naya user connected — uska connection pool mein add karo"""
    user_connections[user_id] = connection
    ev = threading.Event()
    user_ready_events[user_id] = ev
    print(f"[POOL] User {user_id} connection added. Pool size: {len(user_connections)+1}")

def pool_remove(user_id):
    """User disconnect hua — pool se hata do"""
    user_connections.pop(user_id, None)
    user_ready_events.pop(user_id, None)
    print(f"[POOL] User {user_id} connection removed. Pool size: {len(user_connections)+1}")

def pool_is_ready(user_id):
    """Check karo user ka connection ready hai ya nahi"""
    conn = pool_get(user_id)
    if conn is None:
        return False
    return getattr(conn, '_ready', False)
# ─────────────────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"
    id               = Column(Integer, primary_key=True, index=True)
    username         = Column(String, unique=True, index=True)
    email            = Column(String, unique=True, index=True)
    hashed_password  = Column(String)
    mt5_login        = Column(Integer, nullable=True)
    mt5_password     = Column(String, nullable=True)
    mt5_server       = Column(String, nullable=True)
    bot_active          = Column(Boolean, default=False)
    high_water_mark     = Column(Float, nullable=True)
    metaapi_account_id  = Column(String, nullable=True)
    # Referral system
    referral_code       = Column(String, nullable=True, unique=True)
    referred_by         = Column(Integer, nullable=True)   # user_id jo refer kiya
    # Payment tracking
    daily_profit_owed   = Column(Float, default=0.0)       # 25% admin share pending
    referral_owed       = Column(Float, default=0.0)       # 5% referrer commission
    payment_status      = Column(String, default="clear")  # clear / pending / overdue
    last_payment_at     = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)

class Trade(Base):
    __tablename__ = "trades"
    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer)
    symbol      = Column(String)
    trade_type  = Column(String)
    lot         = Column(Float)
    open_price  = Column(Float)
    close_price = Column(Float, nullable=True)
    profit      = Column(Float, default=0.0)
    score       = Column(Float, default=0.0)
    mt5_ticket  = Column(Integer, nullable=True)
    master_ticket = Column(Integer, nullable=True)  # master position ticket for copy sync
    status      = Column(String, default="open")
    opened_at   = Column(DateTime, default=datetime.utcnow)
    closed_at   = Column(DateTime, nullable=True)

class Signal(Base):
    __tablename__ = "signals"
    id          = Column(Integer, primary_key=True, index=True)
    symbol      = Column(String)
    signal_type = Column(String)
    score       = Column(Float)
    ema_fast    = Column(Float)
    ema_slow    = Column(Float)
    macd        = Column(Float)
    rsi         = Column(Float)
    adx         = Column(Float)
    price       = Column(Float)
    created_at  = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)
migrate_schema(engine)


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    referral_code: str = None   # Refer karne wale ka code (optional)

class MT5Credentials(BaseModel):
    mt5_login: int
    mt5_password: str
    mt5_server: str

class Token(BaseModel):
    access_token: str
    token_type: str

class SignalOut(BaseModel):
    id: int
    symbol: str
    signal_type: str
    score: float
    ema_fast: float
    ema_slow: float
    macd: float
    rsi: float
    adx: float
    price: float
    created_at: datetime

    class Config:
        from_attributes = True

class TradeOut(BaseModel):
    id: int
    user_id: int
    symbol: str
    trade_type: str
    lot: float
    open_price: float
    close_price: float | None = None
    profit: float
    score: float
    mt5_ticket: int | None = None
    master_ticket: int | None = None
    status: str
    opened_at: datetime
    closed_at: datetime | None = None

    class Config:
        from_attributes = True


def ensure_user_connection(user):
    """Har user ka apna MT5 connection — follower ke liye pool se, warna reconnect."""
    if is_master_user(user):
        return mt5_manager
    conn = pool_get(user.id)
    if conn is not None:
        return conn
    if user.metaapi_account_id:
        print(f"[POOL] Reconnecting follower {user.username} from saved MetaApi id")
        conn = create_user_manager(user.metaapi_account_id)
        pool_add(user.id, conn)
        return conn
    return None


def user_connection(user):
    """Har user ka apna MT5 connection — master ya follower (no master fallback)."""
    return ensure_user_connection(user)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_password_hash(password):
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()

def verify_password(plain, hashed):
    return _bcrypt.checkpw(plain.encode(), hashed.encode())

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ─── Position management (indicators in trading_engine.py) ─────────────────────

def close_pos(pos, reason=""):
    try:
        tick = mt5_manager.symbol_info_tick(pos.symbol)
        if tick is None: return False, 0
        price = tick.bid if pos.type == 0 else tick.ask
        request = {
            "action":       mt5_manager.TRADE_ACTION_DEAL,
            "symbol":       pos.symbol,
            "volume":       pos.volume,
            "type":         mt5_manager.ORDER_TYPE_SELL if pos.type == 0 else mt5_manager.ORDER_TYPE_BUY,
            "position":     pos.ticket,
            "price":        price,
            "deviation":    50,
            "magic":        888888,
            "comment":      f"PB_{reason}",
            "type_time":    mt5_manager.ORDER_TIME_GTC,
            "type_filling": mt5_manager.ORDER_FILLING_IOC,
        }
        result = mt5_manager.order_send(request)
        return result.retcode == mt5_manager.TRADE_RETCODE_DONE, pos.profit
    except:
        return False, 0

def update_trade_closed(user_id, symbol, profit, close_price, ticket=None):
    db = SessionLocal()
    try:
        query = db.query(Trade).filter(Trade.user_id == user_id, Trade.status == "open")
        t = query.filter(Trade.mt5_ticket == ticket).first() if ticket else \
            query.filter(Trade.symbol == symbol).first()
        if t:
            t.status      = "closed"
            t.profit      = float(profit)
            t.close_price = float(close_price)
            t.closed_at   = datetime.utcnow()
            db.commit()
    except Exception as e:
        print(f"[DB] {e}")
    finally:
        db.close()

def get_platform_fee(profit, user_id, current_balance):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user: return 0
        hwm = float(user.high_water_mark) if user.high_water_mark else current_balance - profit
        if current_balance > hwm:
            fee = profit * 0.25
            user.high_water_mark = current_balance
            db.commit()
            return max(0, fee)
        return 0
    except:
        return 0
    finally:
        db.close()

# ─── Bot position identification ────────────────────────────────────────────
# NOTE: kai brokers/MetaApi demo accounts magic number aur comment field
# preserve NAHI karte (position data mein magic hamesha 0 aata hai, comment
# missing hota hai). Isliye magic/comment par bharosa nahi kar sakte — apni
# trades ko humesha DB ke mt5_ticket se identify karo (reliable, broker-agnostic).
def _as_int_ticket(ticket):
    """MetaApi position ids arrive as strings, DB stores ints — normalize both sides."""
    try:
        return int(ticket)
    except (TypeError, ValueError):
        return None


def fetch_position_closed_profit(conn, ticket):
    """MetaApi deal history se closed trade ka real profit + close price."""
    if not conn or not ticket:
        return None, None
    deals = conn.deals_get_by_position(ticket)
    if not deals:
        return None, None

    total_profit = 0.0
    close_price = None
    for d in deals:
        if not isinstance(d, dict):
            continue
        total_profit += float(d.get('profit', 0) or 0)
        total_profit += float(d.get('swap', 0) or 0)
        total_profit += float(d.get('commission', 0) or 0)
        entry = d.get('entryType', d.get('entry', ''))
        if entry in ('DEAL_ENTRY_OUT', 'DEAL_ENTRY_INOUT', 'DEAL_ENTRY_OUT_BY') or d.get('price'):
            close_price = d.get('price') or close_price

    if total_profit == 0 and close_price is None:
        return None, None
    return round(total_profit, 2), close_price


def backfill_closed_trade_profit(conn, trade, db=None, commit=False):
    """DB closed trade jiska profit 0 hai — MetaApi se actual profit set karo."""
    if not trade or trade.status != 'closed' or not trade.mt5_ticket:
        return False
    if trade.profit not in (None, 0, 0.0):
        return False

    profit, close_price = fetch_position_closed_profit(conn, trade.mt5_ticket)
    if profit is None:
        return False

    trade.profit = profit
    if close_price and not trade.close_price:
        trade.close_price = float(close_price)
    if db and commit:
        db.commit()
    return True

def get_open_bot_tickets(user_id):
    db = SessionLocal()
    try:
        rows = db.query(Trade.mt5_ticket).filter(
            Trade.user_id == user_id,
            Trade.status == "open",
            Trade.mt5_ticket != None,
        ).all()
        return {r[0] for r in rows}
    finally:
        db.close()

def is_bot_position(pos, bot_tickets):
    ticket_int = _as_int_ticket(pos.ticket)
    return (
        (ticket_int is not None and ticket_int in bot_tickets) or
        pos.magic == 888888 or
        "PB_" in getattr(pos, "comment", "")
    )

def get_bot_positions(user_id, mgr):
    all_pos = mgr.positions_get()
    if not all_pos:
        return []
    bot_tickets = get_open_bot_tickets(user_id)
    return [p for p in all_pos if is_bot_position(p, bot_tickets)]


def get_live_positions(user_id, conn):
    """Live MT5 positions for API — DB tickets se match, warna sab live positions."""
    all_pos = conn.positions_get() if conn else []
    if not all_pos:
        return []

    bot_tickets = get_open_bot_tickets(user_id)
    matched = [p for p in all_pos if is_bot_position(p, bot_tickets)]
    if matched:
        return matched

    db = SessionLocal()
    try:
        db_open = db.query(Trade).filter(
            Trade.user_id == user_id, Trade.status == "open"
        ).count()
    finally:
        db.close()

    # MetaApi kai brokers par magic/comment 0 hota hai — DB mein open trades hon to sab dikhao
    if db_open > 0 or len(all_pos) > 0:
        return all_pos
    return []


def _position_to_api_dict(p, conn, user_id):
    db = SessionLocal()
    try:
        tr = db.query(Trade).filter(Trade.mt5_ticket == _as_int_ticket(p.ticket)).first()
        score = tr.score if tr else 0
        open_price = tr.open_price if tr else getattr(p, "open_price", 0) or getattr(p, "openPrice", 0) or 0
    finally:
        db.close()

    tick = conn.symbol_info_tick(p.symbol) if conn else None
    current_price = (tick.bid if p.type == 0 else tick.ask) if tick else 0

    return {
        "ticket":        p.ticket,
        "symbol":        p.symbol,
        "profit":        round(p.profit, 2),
        "type":          "BUY" if p.type == 0 else "SELL",
        "lot":           getattr(p, "volume", 0),
        "open_price":    open_price,
        "current_price": current_price,
        "score":         score,
        "magic":         getattr(p, "magic", 0),
        "comment":       getattr(p, "comment", ""),
    }


def reconcile_trades_with_mt5(user_id, conn):
    """
  Har live MT5 position ke liye DB mein alag open trade row — ticket primary key.
    Vercel frontend OPEN TRADES = /trades jahan status=='open'.
    """
    if not conn or not getattr(conn, "_ready", False):
        return
    live = conn.positions_get() or []
    live_map = {}
    for p in live:
        ticket = _as_int_ticket(p.ticket)
        if ticket:
            live_map[ticket] = p

    db = SessionLocal()
    try:
        # Har live position → open trade upsert (6 positions = 6 DB rows)
        for ticket, p in live_map.items():
            tr = db.query(Trade).filter(
                Trade.user_id == user_id, Trade.mt5_ticket == ticket
            ).first()
            open_price = getattr(p, "open_price", 0) or 0
            if tr:
                tr.status = "open"
                tr.closed_at = None
                tr.close_price = None
                tr.symbol = p.symbol
                tr.trade_type = "BUY" if p.type == 0 else "SELL"
                tr.lot = getattr(p, "volume", tr.lot) or 0.01
                tr.profit = round(p.profit, 2)
                if open_price:
                    tr.open_price = open_price
            else:
                db.add(Trade(
                    user_id=user_id,
                    symbol=p.symbol,
                    trade_type="BUY" if p.type == 0 else "SELL",
                    lot=getattr(p, "volume", 0.01) or 0.01,
                    open_price=open_price,
                    profit=round(p.profit, 2),
                    mt5_ticket=ticket,
                    status="open",
                ))

        # Broker pe nahi — DB open → closed (MetaApi se profit backfill)
        for tr in db.query(Trade).filter(
            Trade.user_id == user_id, Trade.status == "open"
        ).all():
            ticket = _as_int_ticket(tr.mt5_ticket)
            if ticket not in live_map:
                profit, close_price = fetch_position_closed_profit(conn, ticket)
                if profit is not None:
                    tr.profit = profit
                if close_price:
                    tr.close_price = float(close_price)
                tr.status = "closed"
                if not tr.closed_at:
                    tr.closed_at = datetime.utcnow()

        db.commit()
        n_open = db.query(Trade).filter(
            Trade.user_id == user_id, Trade.status == "open"
        ).count()
        print(f"[RECONCILE] user={user_id} live={len(live_map)} db_open={n_open}")
    except Exception as e:
        print(f"[RECONCILE] {e}")
        db.rollback()
    finally:
        db.close()


def sync_manual_closes(user_id, balance):
    conn = pool_get(user_id) if user_id != MASTER_USER_ID else mt5_manager
    if conn is None:
        conn = mt5_manager
    reconcile_trades_with_mt5(user_id, conn)

def close_all_positions(user_id, reason, balance):
    positions = get_bot_positions(user_id, mt5_manager)
    if not positions: return
    for pos in positions:
        tick = mt5_manager.symbol_info_tick(pos.symbol)
        done, profit = close_pos(pos, reason)
        if done and tick:
            cp = tick.bid if pos.type == 0 else tick.ask
            update_trade_closed(user_id, pos.symbol, profit, cp, _as_int_ticket(pos.ticket))
            last_close_times[(user_id, pos.symbol)] = datetime.now()


# ─── Bot thread waits on threading.Event ──────────────────────────────────────

def run_user_bot(user_id, login, password, server):
    print("=" * 60)
    print(f"[BOT] Thread started — waiting for MetaApi ready event...")
    print("=" * 60)

    # FIX: Use threading.Event.wait() — reliable, no missed signals
    # Waits up to 120 seconds for startup_event to set metaapi_ready_event
    is_ready = metaapi_ready_event.wait(timeout=120)

    if not is_ready or not mt5_manager._ready:
        print("[BOT] MetaApi NOT ready after 120s timeout — aborting bot thread")
        active_bots[user_id] = False
        db = SessionLocal()
        try:
            u = db.query(User).filter(User.id == user_id).first()
            if u:
                u.bot_active = False
                db.commit()
        finally:
            db.close()
        return

    print(f"[BOT] MetaApi ready! _ready={mt5_manager._ready} — PumpingBot Starting!")
    # ──────────────────────────────────────────────────────────────────────────

    daily_start_balance = None
    last_date           = None
    high_water_mark     = None
    locked_profits      = {}
    peak_profits        = {}
    elite_sl_locked     = {}   # ticket -> last broker-side SL price we set (score>=90 trades)
    daily_peak_pnl      = 0.0
    day_locked_out      = False
    first_cycle         = True

    while active_bots.get(user_id, False):
        try:
            info = mt5_manager.account_info()
            if info is None:
                print("[BOT] account_info None - waiting...")
                time.sleep(10)
                continue

            balance = info.balance
            equity  = info.equity
            now     = datetime.now()

            if last_date != now.date():
                daily_start_balance = balance
                last_date           = now.date()
                daily_peak_pnl      = 0.0
                day_locked_out      = False
                locked_profits      = {}
                peak_profits        = {}
                print(f"[DAY] New day! Balance: ${balance:.2f}")

            if daily_start_balance is None:
                daily_start_balance = balance
            if high_water_mark is None or balance > high_water_mark:
                high_water_mark = balance

            if first_cycle:
                first_cycle = False
                print(f"[BOT] First cycle — Balance: ${balance:.2f}, Equity: ${equity:.2f}")
                time.sleep(5)
                continue

            print("=" * 60)
            print(f"Balance: {balance}")
            print(f"Equity : {equity}")
            print(f"Daily Start Balance: {daily_start_balance}")
            print("=" * 60)

            daily_pnl_equity = (equity - daily_start_balance) / daily_start_balance

            if daily_pnl_equity > daily_peak_pnl:
                daily_peak_pnl = daily_pnl_equity

            current_lock = 0.0
            if daily_peak_pnl >= DAILY_TRAIL_START:
                current_lock = daily_peak_pnl - DAILY_TRAIL_GAP

            if not day_locked_out and current_lock > 0 and daily_pnl_equity < current_lock:
                print(f"[LOCK] Profit lock triggered! Closing all positions!")
                close_all_positions(user_id, "ProfitLock", balance)
                day_locked_out = True
                time.sleep(60)
                continue

            if daily_pnl_equity <= -DAILY_MAX_LOSS_PCT:
                print(f"[STOP] Daily max loss hit! Closing all positions!")
                close_all_positions(user_id, "MaxLoss", balance)
                day_locked_out = True
                time.sleep(600)
                continue

            bot_pos = get_bot_positions(user_id, mt5_manager)

            for pos in bot_pos:
                current_profit = pos.profit
                ticket         = _as_int_ticket(pos.ticket)
                trade_type     = "BUY" if pos.type == 0 else "SELL"

                db = SessionLocal()
                tr = db.query(Trade).filter(Trade.mt5_ticket == ticket).first()
                score      = tr.score if tr else 60
                trade_lot  = tr.lot if tr else getattr(pos, "volume", 0)
                open_price = tr.open_price if tr else getattr(pos, "openPrice", 0)
                db.close()

                # SL/TP ab 1H volatility ke hisab se — entry timeframe ka tight ATR nahi
                atr = get_htf_atr(pos.symbol, mt5_manager)
                if atr is None:
                    rates15 = mt5_manager.copy_rates_from_pos(
                        pos.symbol, mt5_manager.TIMEFRAME_M15, 0, 50)
                    atr = 0
                    if rates15 is not None and len(rates15) > 14:
                        h5 = [r['high']  for r in rates15]
                        l5 = [r['low']   for r in rates15]
                        c5 = [r['close'] for r in rates15]
                        atr = calc_atr(h5, l5, c5)

                current_trend, current_adx_4h, current_adx_1h, _ = get_trend(pos.symbol, mt5_manager)
                trend_reversed = (trade_type == "BUY"  and current_trend == "SELL") or \
                                 (trade_type == "SELL" and current_trend == "BUY")

                if trend_reversed:
                    tick = mt5_manager.symbol_info_tick(pos.symbol)
                    done, profit = close_pos(pos, "TrendExit")
                    if done and tick:
                        cp = tick.bid if pos.type == 0 else tick.ask
                        update_trade_closed(user_id, pos.symbol, profit, cp, ticket)
                        last_close_times[(user_id, pos.symbol)] = now
                        status = "Profit" if profit > 0 else "Loss cut"
                        print(f"[TREND EXIT] {pos.symbol} {status}: ${profit:.2f}")
                        locked_profits.pop(ticket, None)
                        peak_profits.pop(ticket, None)
                        elite_sl_locked.pop(ticket, None)
                    continue

                if current_profit < 0 and current_adx_1h < 15 and current_adx_4h < 15:
                    tick = mt5_manager.symbol_info_tick(pos.symbol)
                    done, profit = close_pos(pos, "DeadMomentum")
                    if done and tick:
                        cp = tick.bid if pos.type == 0 else tick.ask
                        update_trade_closed(user_id, pos.symbol, profit, cp, ticket)
                        last_close_times[(user_id, pos.symbol)] = now
                        print(f"[DEAD EXIT] {pos.symbol} Loss cut: ${profit:.2f}")
                        locked_profits.pop(ticket, None)
                        peak_profits.pop(ticket, None)
                        elite_sl_locked.pop(ticket, None)
                    continue

                # ── Munasib profit rule: agar profit margin se double ho jaye to book karo ──
                # (score >= 90 wali "elite" trades ke liye ye rule skip — unko TP tak wait karne do)
                if score < ELITE_SCORE and current_profit > 0:
                    margin_used = calc_margin_used(trade_lot, pos.symbol, open_price, mt5_manager)
                    if margin_used and margin_used > 0 and current_profit >= margin_used * MARGIN_PROFIT_MULT:
                        tick = mt5_manager.symbol_info_tick(pos.symbol)
                        done, profit = close_pos(pos, "DoubleMarginTP")
                        if done and tick:
                            cp = tick.bid if pos.type == 0 else tick.ask
                            update_trade_closed(user_id, pos.symbol, profit, cp, ticket)
                            last_close_times[(user_id, pos.symbol)] = now
                            get_platform_fee(profit, user_id, balance)
                            print(f"[DOUBLE MARGIN TP] {pos.symbol} Margin:${margin_used:.2f} "
                                  f"Profit:${profit:.2f} (2x+ margin — booked)")
                            peak_profits.pop(ticket, None)
                            locked_profits.pop(ticket, None)
                            elite_sl_locked.pop(ticket, None)
                        continue

                # ── Elite trades (score >= 90): TP ka wait karo, sirf SL upar trail karo ──
                if score >= ELITE_SCORE:
                    if current_profit > peak_profits.get(ticket, 0):
                        peak_profits[ticket] = current_profit
                    peak = peak_profits.get(ticket, 0)

                    if peak >= ELITE_MIN_PEAK:
                        target_lock = peak * ELITE_SL_LOCK_PCT
                        new_sl = profit_to_price(open_price, trade_type, target_lock,
                                                  trade_lot, pos.symbol, mt5_manager)
                        if new_sl is not None:
                            last_sl = elite_sl_locked.get(ticket)
                            improves = (
                                last_sl is None or
                                (trade_type == "BUY"  and new_sl > last_sl) or
                                (trade_type == "SELL" and new_sl < last_sl)
                            )
                            if improves:
                                ok = mt5_manager.modify_position(ticket, sl=new_sl)
                                if ok:
                                    elite_sl_locked[ticket] = new_sl
                                    print(f"[ELITE SL LOCK] {pos.symbol} ticket={ticket} "
                                          f"SL→{new_sl:.5f} (locking 70% of peak ${peak:.2f})")

                    # TP hit ho jaye to normal HoldTP se close ho jayega (neeche common logic)

                profit_target = get_profit_target(score, atr, pos.symbol, mt5_manager)

                if score >= ELITE_SCORE:
                    # Elite: sirf real TP ya trend/dead-momentum exit — koi internal early trail nahi
                    if current_profit >= profit_target:
                        tick = mt5_manager.symbol_info_tick(pos.symbol)
                        done, profit = close_pos(pos, "EliteTP")
                        if done and tick:
                            cp = tick.bid if pos.type == 0 else tick.ask
                            update_trade_closed(user_id, pos.symbol, profit, cp, ticket)
                            last_close_times[(user_id, pos.symbol)] = now
                            get_platform_fee(profit, user_id, balance)
                            print(f"[ELITE TP] {pos.symbol} ${profit:.2f}")
                            peak_profits.pop(ticket, None)
                            elite_sl_locked.pop(ticket, None)
                        continue
                    continue

                if is_scalp_trade(score):
                    # Peak track karo scalp ke liye bhi
                    if current_profit > peak_profits.get(ticket, 0):
                        peak_profits[ticket] = current_profit
                    peak = peak_profits.get(ticket, 0)

                    # $10+ profit par 70% trail (scalp bhi HOLD jaisa behave kare)
                    if peak >= HOLD_MIN_PROFIT:
                        trail_lock = peak * HOLD_TRAIL_PCT   # 70% lock
                        if current_profit < trail_lock:
                            tick = mt5_manager.symbol_info_tick(pos.symbol)
                            done, profit = close_pos(pos, "ScalpTrail70")
                            if done and tick:
                                cp = tick.bid if pos.type == 0 else tick.ask
                                update_trade_closed(user_id, pos.symbol, profit, cp, ticket)
                                last_close_times[(user_id, pos.symbol)] = now
                                get_platform_fee(max(0, profit), user_id, balance)
                                print(f"[SCALP TRAIL 70%] {pos.symbol} Peak:${peak:.2f} Close:${profit:.2f}")
                                peak_profits.pop(ticket, None)
                                locked_profits.pop(ticket, None)
                            continue

                    if current_profit >= profit_target:
                        tick = mt5_manager.symbol_info_tick(pos.symbol)
                        done, profit = close_pos(pos, "ScalpTP")
                        if done and tick:
                            cp = tick.bid if pos.type == 0 else tick.ask
                            update_trade_closed(user_id, pos.symbol, profit, cp, ticket)
                            last_close_times[(user_id, pos.symbol)] = now
                            get_platform_fee(profit, user_id, balance)
                            print(f"[SCALP TP] {pos.symbol} ${profit:.2f}")
                            peak_profits.pop(ticket, None)
                        continue
                    locked = get_locked_profit(current_profit)
                    if locked is not None:
                        prev = locked_profits.get(ticket, 0)
                        if locked > prev:
                            locked_profits[ticket] = locked
                        curr_locked = locked_profits.get(ticket, 0)
                        if curr_locked > 0 and current_profit < curr_locked:
                            tick = mt5_manager.symbol_info_tick(pos.symbol)
                            done, profit = close_pos(pos, "ScalpTrail")
                            if done and tick:
                                cp = tick.bid if pos.type == 0 else tick.ask
                                update_trade_closed(user_id, pos.symbol, profit, cp, ticket)
                                last_close_times[(user_id, pos.symbol)] = now
                                print(f"[SCALP TRAIL] {pos.symbol} ${profit:.2f}")
                                locked_profits.pop(ticket, None)
                                peak_profits.pop(ticket, None)
                            continue
                else:
                    if current_profit > peak_profits.get(ticket, 0):
                        peak_profits[ticket] = current_profit
                    peak = peak_profits.get(ticket, 0)
                    if peak >= HOLD_MIN_PROFIT:
                        trail_lock = peak * HOLD_TRAIL_PCT
                        if current_profit < trail_lock:
                            tick = mt5_manager.symbol_info_tick(pos.symbol)
                            done, profit = close_pos(pos, "HoldTrail")
                            if done and tick:
                                cp = tick.bid if pos.type == 0 else tick.ask
                                update_trade_closed(user_id, pos.symbol, profit, cp, ticket)
                                last_close_times[(user_id, pos.symbol)] = now
                                get_platform_fee(max(0, profit), user_id, balance)
                                print(f"[HOLD TRAIL] {pos.symbol} Peak:${peak:.2f} Close:${profit:.2f}")
                                peak_profits.pop(ticket, None)
                            continue
                    if current_profit >= profit_target:
                        tick = mt5_manager.symbol_info_tick(pos.symbol)
                        done, profit = close_pos(pos, "HoldTP")
                        if done and tick:
                            cp = tick.bid if pos.type == 0 else tick.ask
                            update_trade_closed(user_id, pos.symbol, profit, cp, ticket)
                            last_close_times[(user_id, pos.symbol)] = now
                            get_platform_fee(profit, user_id, balance)
                            print(f"[HOLD TP] {pos.symbol} ${profit:.2f}")
                            peak_profits.pop(ticket, None)
                        continue

            sync_manual_closes(user_id, balance)

            if day_locked_out:
                time.sleep(30)
                continue

            bot_pos = get_bot_positions(user_id, mt5_manager)

            if len(bot_pos) >= MAX_OPEN_TRADES:
                time.sleep(5)
                continue

            print(f"[SCAN] Scanning {len(SYMBOLS)} symbols...")

            for symbol in SYMBOLS:
                if len(bot_pos) >= MAX_OPEN_TRADES:
                    break

                last_close = last_close_times.get((user_id, symbol))
                if last_close and (now - last_close).total_seconds() < MIN_COOLDOWN_SEC:
                    continue

                sym_pos = [p for p in bot_pos if p.symbol == symbol]
                if sym_pos:
                    continue

                analysis = analyze_symbol(symbol, mt5_manager)
                if analysis is None or analysis.get("skip"):
                    reason = analysis.get("reason", "unknown") if analysis else "none"
                    if reason == "spread":
                        print(f"[HIGH SPREAD] {symbol} spread={analysis.get('spread', 0):.0f}")
                    elif reason == "no_data":
                        print(f"[NO DATA] {symbol}")
                    else:
                        print(f"[NO TICK] {symbol}")
                    continue

                trend = analysis["trend"]
                score = analysis["score"]
                trade_mode = analysis["trade_mode"]
                atr = analysis["atr"]
                adx_4h = analysis["adx_4h"]
                adx_1h = analysis["adx_1h"]
                rsi = analysis["rsi"]
                tick = analysis["tick"]
                pname = analysis.get("pattern_name")
                pbonus = analysis.get("pattern_bonus", 0)

                pinfo = f"| {pname}+{pbonus}" if pname else ""
                print(f"[{now.strftime('%H:%M')}] {symbol} {trend} {trade_mode} "
                      f"ADX4H:{adx_4h:.0f} ADX1H:{adx_1h:.0f} "
                      f"RSI:{rsi:.0f} Score:{score} HTF:{analysis['htf_aligned']} {pinfo}")

                db = SessionLocal()
                sig = Signal(
                    symbol=symbol,
                    signal_type=trend if score >= MIN_SCORE else "WAIT",
                    score=score, ema_fast=analysis["e8"], ema_slow=analysis["e21"],
                    macd=analysis["macd"], rsi=rsi, adx=adx_4h,
                    price=analysis["closes15"][-1])
                db.add(sig); db.commit(); db.close()

                ok, skip_reason = should_take_trade(analysis)
                if not ok:
                    if skip_reason not in ("skip",):
                        print(f"[SKIP] {symbol} — {skip_reason}")
                    continue

                lot = calculate_lot(balance, atr, symbol, score, mt5_manager)
                if lot is None:
                    continue

                entry = tick.ask if trend == "BUY" else tick.bid
                sl    = entry - atr if trend == "BUY" else entry + atr

                request = {
                    "action":       mt5_manager.TRADE_ACTION_DEAL,
                    "symbol":       symbol,
                    "volume":       lot,
                    "type":         mt5_manager.ORDER_TYPE_BUY if trend == "BUY"
                                    else mt5_manager.ORDER_TYPE_SELL,
                    "price":        entry,
                    "sl":           sl,
                    "deviation":    50,
                    "magic":        888888,
                    "comment":      f"PB_{trade_mode}_S{score}",
                    "type_time":    mt5_manager.ORDER_TIME_GTC,
                    "type_filling": mt5_manager.ORDER_FILLING_IOC,
                }

                result = mt5_manager.order_send(request)
                if result.retcode == mt5_manager.TRADE_RETCODE_DONE:
                    target = get_profit_target(score, atr, symbol, mt5_manager)
                    print(f"[{trade_mode}] TRADE PLACED! {symbol} {trend} "
                          f"Score:{score} Target:${target} Lot:{lot}")
                    db = SessionLocal()
                    trade = Trade(
                        user_id=user_id, symbol=symbol, trade_type=trend,
                        lot=lot, open_price=entry, score=score,
                        mt5_ticket=result.order, master_ticket=result.order,
                        status="open")
                    db.add(trade); db.commit(); db.close()

                    if user_id == MASTER_USER_ID:
                        threading.Thread(
                            target=copy_trade_to_followers,
                            args=(user_id, symbol, trend, score, atr,
                                  lot, balance, entry, sl, trade_mode,
                                  result.order, "BOT"),
                            daemon=True
                        ).start()

                    bot_pos = get_bot_positions(user_id, mt5_manager)
                else:
                    print(f"[FAIL] {symbol}: retcode={result.retcode}")
                    last_close_times[(user_id, symbol)] = now

                time.sleep(1)

            time.sleep(60)

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[ERROR] {e}")
            time.sleep(10)

    print("[BOT] Stopped cleanly")


def run_user_bot_watchdog(user_id, login, password, server):
    """24/7 watchdog — bot crash ho toh 30s baad restart kare"""
    while active_bots.get(user_id, False):
        try:
            run_user_bot(user_id, login, password, server)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[WATCHDOG] Bot crashed: {e} — restarting in 30s...")
            time.sleep(30)
        if not active_bots.get(user_id, False):
            break
    print("[WATCHDOG] Bot fully stopped")


# ─── API Endpoints ─────────────────────────────────────────────────────────────

# ─── EMAIL FUNCTION ───────────────────────────────────────────────────────────
def send_email(to_email, subject, html_body):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_USER
        msg["To"]      = to_email
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, to_email, msg.as_string())
        print(f"[EMAIL] Sent to {to_email}: {subject}")
        return True
    except Exception as e:
        print(f"[EMAIL] Failed: {e}")
        return False


# ─── DAILY PROFIT CALCULATOR ──────────────────────────────────────────────────
def calculate_daily_profits():
    """Har user ka daily profit calculate karo — 25% admin + 5% referrer"""
    db = SessionLocal()
    try:
        users = db.query(User).filter(
            User.bot_active == True,
            User.username != "admin"
        ).all()

        for user in users:
            # Aaj ki closed trades se profit nikalo
            today = datetime.utcnow().date()
            today_trades = db.query(Trade).filter(
                Trade.user_id == user.id,
                Trade.status  == "closed",
                Trade.profit  > 0,
            ).all()

            # Sirf aaj ki trades
            today_profit = sum(
                t.profit for t in today_trades
                if t.closed_at and t.closed_at.date() == today
            )

            if today_profit <= 0:
                continue

            admin_share    = round(today_profit * 0.25, 2)
            referrer_share = 0.0

            # 5% referrer commission
            if user.referred_by:
                referrer_share = round(today_profit * 0.05, 2)

            user.daily_profit_owed += admin_share
            user.referral_owed     += referrer_share
            user.payment_status     = "pending"

            print(f"[PROFIT] {user.username}: Profit=${today_profit:.2f} "
                  f"Admin={admin_share:.2f} Referrer={referrer_share:.2f}")

        db.commit()
    except Exception as e:
        print(f"[PROFIT CALC] Error: {e}")
    finally:
        db.close()


def send_payment_notifications():
    """8 PM PKT — sab pending users ko notification bhejo"""
    db = SessionLocal()
    try:
        pending_users = db.query(User).filter(
            User.payment_status == "pending",
            User.daily_profit_owed > 0
        ).all()

        for user in pending_users:
            total_owed = round(user.daily_profit_owed + user.referral_owed, 2)
            html = f"""
            <div style="font-family:Arial;max-width:600px;margin:auto;padding:20px;
                        background:#1a1a2e;color:#fff;border-radius:10px;">
                <h2 style="color:#f0b90b;">⚠️ PumpingBot — Payment Required</h2>
                <p>Hello <b>{user.username}</b>,</p>
                <p>Aaj ki trading ke liye payment pending hai:</p>
                <table style="width:100%;border-collapse:collapse;margin:15px 0;">
                    <tr style="background:#16213e;">
                        <td style="padding:10px;border:1px solid #333;">Admin Share (25%)</td>
                        <td style="padding:10px;border:1px solid #333;color:#f0b90b;">
                            <b>${user.daily_profit_owed:.2f}</b></td>
                    </tr>
                    <tr>
                        <td style="padding:10px;border:1px solid #333;">Referrer Commission (5%)</td>
                        <td style="padding:10px;border:1px solid #333;">
                            ${user.referral_owed:.2f}</td>
                    </tr>
                    <tr style="background:#16213e;">
                        <td style="padding:10px;border:1px solid #333;"><b>Total</b></td>
                        <td style="padding:10px;border:1px solid #333;color:#00ff88;">
                            <b>${total_owed:.2f}</b></td>
                    </tr>
                </table>
                <p style="color:#ff4444;font-weight:bold;">
                    ⏰ 9 PM PKT tak payment nahi ki toh bot pause ho jayega!
                </p>
                <p>Admin ko payment karein: <b>{ADMIN_EMAIL}</b></p>
                <p style="color:#888;font-size:12px;">PumpingBot Trading Platform</p>
            </div>"""
            send_email(user.email, "⚠️ PumpingBot Payment Due — Bot paused at 9 PM", html)

            # Admin ko bhi notify karo
            admin_html = f"""
            <div style="font-family:Arial;padding:20px;background:#1a1a2e;color:#fff;">
                <h3 style="color:#f0b90b;">💰 Payment Pending: {user.username}</h3>
                <p>User: <b>{user.email}</b></p>
                <p>Amount: <b>${total_owed:.2f}</b></p>
                <p>Admin Share: ${user.daily_profit_owed:.2f}</p>
                <p>Referrer Share: ${user.referral_owed:.2f}</p>
            </div>"""
            send_email(ADMIN_EMAIL, f"💰 Payment Pending: {user.username} — ${total_owed:.2f}", admin_html)

    except Exception as e:
        print(f"[NOTIFY] Error: {e}")
    finally:
        db.close()


def pause_unpaid_bots():
    """9 PM PKT — payment pending users ka bot pause karo"""
    db = SessionLocal()
    try:
        overdue_users = db.query(User).filter(
            User.payment_status == "pending",
            User.daily_profit_owed > 0
        ).all()

        for user in overdue_users:
            user.bot_active     = False
            user.payment_status = "overdue"
            active_bots[user.id] = False

            # Sab positions close karo
            conn = pool_get(user.id)
            if conn and conn._ready:
                positions = get_bot_positions(user.id, conn)
                for pos in positions:
                    conn.order_send({
                        "action":       conn.TRADE_ACTION_DEAL,
                        "symbol":       pos.symbol,
                        "volume":       pos.volume,
                        "type":         conn.ORDER_TYPE_SELL if pos.type == 0 else conn.ORDER_TYPE_BUY,
                        "position":     pos.ticket,
                        "price":        0,
                        "deviation":    50,
                        "magic":        888888,
                        "comment":      "PB_PaymentOverdue",
                        "type_time":    conn.ORDER_TIME_GTC,
                        "type_filling": conn.ORDER_FILLING_IOC,
                    })

            print(f"[PAUSE] {user.username} bot paused — payment overdue")

            # User ko final warning email
            html = f"""
            <div style="font-family:Arial;padding:20px;background:#1a1a2e;color:#fff;">
                <h2 style="color:#ff4444;">🚫 Bot Paused — Payment Overdue</h2>
                <p>Hello <b>{user.username}</b>,</p>
                <p>Payment time pe nahi mili — aapka bot pause kar diya gaya hai.</p>
                <p>Amount due: <b>${(user.daily_profit_owed + user.referral_owed):.2f}</b></p>
                <p>Payment karne ke baad admin se contact karein bot resume karne ke liye.</p>
                <p>Admin: <b>{ADMIN_EMAIL}</b></p>
            </div>"""
            send_email(user.email, "🚫 PumpingBot — Bot Paused (Payment Overdue)", html)

        db.commit()
    except Exception as e:
        print(f"[PAUSE] Error: {e}")
    finally:
        db.close()


def daily_scheduler():
    """24/7 background scheduler — PKT time check karta hai"""
    print("[SCHEDULER] Started — watching for 8 PM and 9 PM PKT")
    notified_today  = None
    paused_today    = None

    while True:
        try:
            # PKT = UTC + 5
            now_pkt = datetime.utcnow() + timedelta(hours=5)
            today   = now_pkt.date()

            # 8 PM PKT — profit calculate + notification
            if now_pkt.hour == 20 and now_pkt.minute < 5 and notified_today != today:
                print("[SCHEDULER] 8 PM PKT — calculating profits and sending notifications")
                calculate_daily_profits()
                send_payment_notifications()
                notified_today = today

            # 9 PM PKT — unpaid bots pause
            if now_pkt.hour == 21 and now_pkt.minute < 5 and paused_today != today:
                print("[SCHEDULER] 9 PM PKT — pausing unpaid bots")
                pause_unpaid_bots()
                paused_today = today

        except Exception as e:
            print(f"[SCHEDULER] Error: {e}")

        time.sleep(60)  # Har minute check karo


# ─── PAYMENT CONFIRM ENDPOINT ─────────────────────────────────────────────────
@app.post("/admin/confirm-payment/{user_id}")
def confirm_payment(user_id: int,
                    current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Admin payment confirm kare — bot resume ho jata hai"""
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    paid_amount = user.daily_profit_owed + user.referral_owed

    # Referrer ko commission transfer karo
    if user.referred_by and user.referral_owed > 0:
        referrer = db.query(User).filter(User.id == user.referred_by).first()
        if referrer:
            print(f"[COMMISSION] {referrer.username} ko ${user.referral_owed:.2f} commission")

    user.daily_profit_owed = 0.0
    user.referral_owed     = 0.0
    user.payment_status    = "clear"
    user.last_payment_at   = datetime.utcnow()
    user.bot_active        = True
    db.commit()

    # Bot restart — master only runs trading engine
    active_bots[user.id] = True
    if is_master_user(user) and user.mt5_login:
        threading.Thread(
            target=run_user_bot_watchdog,
            args=(user.id, user.mt5_login, user.mt5_password, user.mt5_server),
            daemon=True
        ).start()

    # User ko confirmation email
    html = f"""
    <div style="font-family:Arial;padding:20px;background:#1a1a2e;color:#fff;">
        <h2 style="color:#00ff88;">✅ Payment Confirmed — Bot Resumed!</h2>
        <p>Hello <b>{user.username}</b>,</p>
        <p>Aapki payment confirm ho gayi — bot dobara active ho gaya hai!</p>
        <p>Amount paid: <b>${paid_amount:.2f}</b></p>
        <p>Happy Trading! 🚀</p>
    </div>"""
    send_email(user.email, "✅ PumpingBot — Payment Confirmed, Bot Resumed!", html)

    return {"message": f"Payment confirmed for {user.username}, bot resumed!"}


@app.get("/admin/pending-payments")
def get_pending_payments(current_user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """Admin sab pending payments dekhe"""
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")

    users = db.query(User).filter(User.daily_profit_owed > 0).all()
    return [{
        "user_id":       u.id,
        "username":      u.username,
        "email":         u.email,
        "admin_share":   round(u.daily_profit_owed, 2),
        "referrer_comm": round(u.referral_owed, 2),
        "total_owed":    round(u.daily_profit_owed + u.referral_owed, 2),
        "status":        u.payment_status,
        "bot_active":    u.bot_active,
    } for u in users]


@app.get("/admin/users")
def get_all_users(current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")
    users = db.query(User).all()
    result = []
    for u in users:
        conn = pool_get(u.id)
        info = conn.account_info() if conn and conn._ready else None
        result.append({
            "user_id":       u.id,
            "username":      u.username,
            "email":         u.email,
            "mt5_login":     u.mt5_login,
            "mt5_server":    u.mt5_server,
            "bot_active":    u.bot_active,
            "balance":       info.balance if info else 0,
            "equity":        info.equity if info else 0,
            "payment_status": u.payment_status,
            "amount_owed":   round((u.daily_profit_owed or 0) + (u.referral_owed or 0), 2),
            "referral_code": u.referral_code,
            "referred_by":   u.referred_by,
            "joined":        u.created_at.isoformat() if u.created_at else None,
        })
    return result


@app.get("/admin/stats")
def get_admin_stats(current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")

    total_users    = db.query(User).count()
    active_bots    = db.query(User).filter(User.bot_active == True).count()
    pending_pay    = db.query(User).filter(User.payment_status == "pending").count()
    overdue_pay    = db.query(User).filter(User.payment_status == "overdue").count()
    total_trades   = db.query(Trade).count()
    open_trades    = db.query(Trade).filter(Trade.status == "open").count()
    closed_trades  = db.query(Trade).filter(Trade.status == "closed").count()

    total_profit   = db.query(Trade).filter(Trade.status == "closed", Trade.profit > 0).all()
    gross_profit   = sum(t.profit for t in total_profit)
    admin_earned   = gross_profit * 0.25

    pending_users  = db.query(User).filter(User.daily_profit_owed > 0).all()
    total_pending  = sum((u.daily_profit_owed or 0) + (u.referral_owed or 0) for u in pending_users)

    master_info = mt5_manager.account_info()

    return {
        "total_users":    total_users,
        "active_bots":    active_bots,
        "pending_payment": pending_pay,
        "overdue_payment": overdue_pay,
        "total_trades":   total_trades,
        "open_trades":    open_trades,
        "closed_trades":  closed_trades,
        "gross_profit":   round(gross_profit, 2),
        "admin_earned":   round(admin_earned, 2),
        "pending_amount": round(total_pending, 2),
        "master_balance": master_info.balance if master_info else 0,
        "master_equity":  master_info.equity if master_info else 0,
    }


@app.post("/admin/toggle-bot/{user_id}")
def admin_toggle_bot(user_id: int,
                     current_user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """Admin kisi bhi user ka bot start/stop kare"""
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.bot_active:
        active_bots[user.id] = False
        user.bot_active = False
        db.commit()
        return {"message": f"{user.username} bot stopped"}
    active_bots[user.id] = True
    user.bot_active = True
    db.commit()
    if is_master_user(user) and user.mt5_login:
        threading.Thread(
            target=run_user_bot_watchdog,
            args=(user.id, user.mt5_login, user.mt5_password, user.mt5_server),
            daemon=True).start()
    return {"message": f"{user.username} copy trading activated"}


@app.delete("/admin/delete-user/{user_id}")
def admin_delete_user(user_id: int,
                      current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if is_master_user(user):
        raise HTTPException(400, "Admin ko delete nahi kar sakte")
    active_bots[user_id] = False
    pool_remove(user_id)
    db.query(Trade).filter(Trade.user_id == user_id).delete()
    db.delete(user)
    db.commit()
    return {"message": f"{user.username} deleted"}


@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(400, "Username already exists")
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(400, "Email already exists")

    # Referral code check
    referred_by_id = None
    if user.referral_code:
        referrer = db.query(User).filter(User.referral_code == user.referral_code).first()
        if referrer:
            referred_by_id = referrer.id
            print(f"[REFERRAL] {user.username} referred by {referrer.username}")

    # Naye user ka unique referral code generate karo
    new_code = str(uuid.uuid4())[:8].upper()

    new_user = User(
        username      = user.username,
        email         = user.email,
        hashed_password = get_password_hash(user.password),
        referral_code = new_code,
        referred_by   = referred_by_id,
    )
    db.add(new_user)
    db.commit()

    # Welcome email
    html = f"""
    <div style="font-family:Arial;padding:20px;background:#1a1a2e;color:#fff;border-radius:10px;">
        <h2 style="color:#f0b90b;">🚀 Welcome to PumpingBot!</h2>
        <p>Hello <b>{user.username}</b>, account ban gaya!</p>
        <p>Apna referral code share karo — har referred user ki profit ka <b>5% commission</b> milega:</p>
        <h3 style="color:#00ff88;letter-spacing:3px;">{new_code}</h3>
        <p>Steps: MT5 connect karo → Bot start karo → Profits kamao!</p>
    </div>"""
    send_email(user.email, "🚀 Welcome to PumpingBot!", html)

    return {"message": "User created successfully", "referral_code": new_code}

@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(401, "Wrong username or password")
    return {"access_token": create_access_token({"sub": user.username}), "token_type": "bearer"}

@app.get("/me")
def get_me(current_user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    conn = user_connection(current_user)
    reconcile_trades_with_mt5(current_user.id, conn)
    info = conn.account_info() if conn and conn._ready else None
    role = "master" if is_master_user(current_user) else "follower"
    amount_owed = round((current_user.daily_profit_owed or 0) + (current_user.referral_owed or 0), 2)

    balance = info.balance if info else 0
    equity  = info.equity  if info else 0
    # MetaApi profit field aksar 0 hota hai — floating P/L = equity - balance
    floating_pl = round(equity - balance, 2) if info else 0

    open_trades_db = db.query(Trade).filter(
        Trade.user_id == current_user.id, Trade.status == "open"
    ).count()
    live_positions = get_live_positions(current_user.id, conn) if conn else []
    open_trades_count = max(open_trades_db, len(live_positions))

    return {
        "username":          current_user.username,
        "email":             current_user.email,
        "user_id":           current_user.id,
        "is_admin":          is_master_user(current_user),
        "role":              role,
        "mt5_connected":     current_user.mt5_login is not None,
        "mt5_ready":         mt5_manager._ready if is_master_user(current_user) else pool_is_ready(current_user.id),
        "mt5_login":         current_user.mt5_login,
        "mt5_server":        current_user.mt5_server,
        "bot_active":        current_user.bot_active,
        "balance":           balance,
        "profit":            floating_pl,
        "floating_pl":       floating_pl,
        "equity":            equity,
        "open_trades_count": open_trades_count,
        "referral_code":     current_user.referral_code,
        "payment_status":    current_user.payment_status or "clear",
        "amount_owed":       amount_owed,
    }

@app.post("/connect-mt5")
async def connect_mt5(creds: MT5Credentials,
                      current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """
    Master (admin): existing MetaApi account use karta hai
    Follower: MetaApi mein unka account dhundta hai ya naya banata hai
    Har bar file update karne ki zaroorat nahi!
    """
    print(f"[CONNECT] User {current_user.username} connecting login={creds.mt5_login}")

    if current_user.mt5_login and current_user.mt5_login != creds.mt5_login:
        active_bots[current_user.id] = False
        current_user.bot_active = False
        print(f"[CONNECT] Switching account {current_user.mt5_login} → {creds.mt5_login}")

    if is_master_user(current_user):
        # ── Master: existing connection use karo ──────────────────────────
        metaapi_ready_event.clear()
        mt5_manager.initialize()

        for i in range(45):
            if mt5_manager._ready:
                metaapi_ready_event.set()
                break
            await asyncio.sleep(2)

        if not mt5_manager._ready:
            raise HTTPException(400, "MetaApi timeout — try again in 30s")

        info = mt5_manager.account_info()
        current_user.mt5_login           = creds.mt5_login
        current_user.mt5_password        = creds.mt5_password
        current_user.mt5_server          = creds.mt5_server
        current_user.metaapi_account_id  = MASTER_ACCOUNT_ID
        db.commit()
        return {
            "message":   f"Master connected: {info.name if info else 'OK'}",
            "balance":   info.balance if info else 0,
            "mt5_ready": True,
            "role":      "master"
        }

    else:
        # ── Follower: MetaApi account create/find + connection pool ───────
        print(f"[CONNECT] Follower {current_user.username} — setting up MetaApi...")
        account_id = await find_or_create_metaapi_account(
            creds.mt5_login, creds.mt5_password, creds.mt5_server)
        if not account_id:
            raise HTTPException(400, "MetaApi account setup failed — check credentials")

        pool_remove(current_user.id)
        conn = create_user_manager(account_id)
        pool_add(current_user.id, conn)

        for i in range(45):
            if conn._ready:
                break
            await asyncio.sleep(2)

        follower_info = conn.account_info()
        current_user.mt5_login = creds.mt5_login
        current_user.mt5_password = creds.mt5_password
        current_user.mt5_server = creds.mt5_server
        current_user.metaapi_account_id = account_id
        db.commit()

        print(f"[CONNECT] ✅ Follower {current_user.username} connected! MetaApi={account_id[:8]}... ready={conn._ready}")
        if not conn._ready:
            return {
                "message":   "Account linked — MetaApi is still syncing (1–2 min). Refresh dashboard shortly.",
                "balance":   follower_info.balance if follower_info else 0,
                "mt5_ready": False,
                "role":      "follower",
            }
        return {
            "message":   f"Connected: {follower_info.name if follower_info else 'OK'}",
            "balance":   follower_info.balance if follower_info else 0,
            "mt5_ready": True,
            "role":      "follower",
        }


@app.post("/disconnect-mt5")
def disconnect_mt5(current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Current MT5 account disconnect — doosra account connect karne ke liye."""
    if not current_user.mt5_login:
        raise HTTPException(400, "No MT5 account connected")

    prev_login = current_user.mt5_login
    prev_server = current_user.mt5_server

    active_bots[current_user.id] = False
    current_user.bot_active = False

    if is_master_user(current_user):
        metaapi_ready_event.clear()
        mt5_manager._ready = False
    else:
        pool_remove(current_user.id)

    current_user.mt5_login = None
    current_user.mt5_password = None
    current_user.mt5_server = None
    current_user.metaapi_account_id = None
    db.commit()

    print(f"[DISCONNECT] {current_user.username} disconnected MT5 {prev_login}@{prev_server}")
    return {
        "message": "MT5 disconnected — ab doosra account connect kar sakte ho",
        "mt5_connected": False,
        "mt5_ready": False,
    }


# FIX: start_bot checks _ready before launching thread
@app.post("/bot/start")
def start_bot(current_user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    if not current_user.mt5_login:
        raise HTTPException(400, "Connect MT5 first")

    active_bots[current_user.id] = True
    current_user.bot_active = True
    db.commit()

    if is_master_user(current_user):
        if not mt5_manager._ready:
            raise HTTPException(400, "MetaApi not ready — reconnect MT5 first")
        if mt5_manager._ready:
            metaapi_ready_event.set()
        threading.Thread(
            target=run_user_bot_watchdog,
            args=(current_user.id, current_user.mt5_login,
                  current_user.mt5_password, current_user.mt5_server),
            daemon=True).start()
        return {"message": "Master PumpingBot started — trades will copy to all active users!"}

    # Follower: copy-trading mode only — no independent bot thread
    conn = pool_get(current_user.id)
    if conn is None and current_user.metaapi_account_id:
        conn = create_user_manager(current_user.metaapi_account_id)
        pool_add(current_user.id, conn)
    return {"message": "Copy trading activated — master trades will mirror to your account!"}

@app.post("/bot/stop")
def stop_bot(current_user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    active_bots[current_user.id] = False
    current_user.bot_active = False
    db.commit()
    return {"message": "Bot stopped"}

@app.get("/signals", response_model=list[SignalOut])
def get_signals(current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    return db.query(Signal).order_by(Signal.created_at.desc()).limit(50).all()

@app.get("/trades", response_model=list[TradeOut])
def get_trades(current_user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    conn = user_connection(current_user)
    reconcile_trades_with_mt5(current_user.id, conn)
    trades = db.query(Trade).filter(
        Trade.user_id == current_user.id
    ).order_by(
        Trade.closed_at.desc().nullslast(),
        Trade.opened_at.desc()
    ).limit(500).all()

    if conn and conn._ready:
        live_map = {_as_int_ticket(p.ticket): p for p in (conn.positions_get() or [])}
        backfilled = 0
        for t in trades:
            if t.status == "open" and t.mt5_ticket:
                p = live_map.get(_as_int_ticket(t.mt5_ticket))
                if p:
                    t.profit = round(p.profit, 2)
            elif t.status == "closed" and backfilled < 25:
                if backfill_closed_trade_profit(conn, t, db):
                    backfilled += 1
        if backfilled:
            db.commit()

    return trades

@app.get("/open_positions")
def get_open_positions(current_user: User = Depends(get_current_user)):
    conn = user_connection(current_user)
    reconcile_trades_with_mt5(current_user.id, conn)
    positions = conn.positions_get() if conn else []
    if not positions:
        positions = []
    return [_position_to_api_dict(p, conn, current_user.id) for p in positions]

# FIX: New endpoint to debug connection status
@app.get("/status")
def get_status(current_user: User = Depends(get_current_user)):
    conn = user_connection(current_user)
    ready = mt5_manager._ready if is_master_user(current_user) else pool_is_ready(current_user.id)
    info = conn.account_info() if conn and ready else None
    return {
        "metaapi_ready":    ready,
        "event_set":        metaapi_ready_event.is_set(),
        "bot_active":       active_bots.get(current_user.id, False),
        "account_info_ok":  info is not None,
        "balance":          info.balance if info else None,
        "role":             "master" if is_master_user(current_user) else "follower",
    }


# ─── FIX: Startup Event — passes credentials, sets metaapi_ready_event ────────
@app.on_event("startup")
async def startup_event():
    migrate_schema(engine)
    threading.Thread(target=daily_scheduler, daemon=True).start()
    start_copy_watcher()
    print("[STARTUP] Daily scheduler + copy watcher started")

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == "admin").first()
        if not existing:
            new_user = User(
                username="admin",
                email="test123@gmail.com",
                hashed_password=get_password_hash("Test123"),
                mt5_login=474114625,
                mt5_password="Tradingdemo.123",
                mt5_server="Exness-MT5Trial15"
            )
            db.add(new_user)
            db.commit()
            print("[STARTUP] Admin user created!")
        else:
            print("[STARTUP] Admin user already exists!")

        global MASTER_USER_ID
        admin_user = db.query(User).filter(User.username == "admin").first()
        if admin_user:
            MASTER_USER_ID = admin_user.id
            print(f"[STARTUP] MASTER_USER_ID = {MASTER_USER_ID} (admin)")

        # FIX: Get admin user and pass credentials to initialize()
        # (previously called with no args — this was the root cause!)
        user = db.query(User).filter(User.username == "admin").first()
        if user and user.mt5_login:
            print(f"[STARTUP] Initializing MetaApi with login={user.mt5_login} server={user.mt5_server}")
            mt5_manager.initialize(
                login=user.mt5_login,
                password=user.mt5_password,
                server=user.mt5_server
            )
        else:
            print("[STARTUP] No credentials found — calling initialize() without args")
            mt5_manager.initialize()

        # FIX: Wait up to 90 seconds (was 45 iterations of 2s = 90s)
        print("[STARTUP] Waiting for MetaApi _ready...")
        for i in range(45):
            if mt5_manager._ready:
                break
            await asyncio.sleep(2)
            if i % 5 == 0:
                print(f"[STARTUP] Still waiting... {i*2}s elapsed")

        print(f"[STARTUP] MetaApi _ready = {mt5_manager._ready}")

        if mt5_manager._ready:
            # FIX: Set the threading.Event so bot thread can proceed
            metaapi_ready_event.set()
            print("[STARTUP] metaapi_ready_event SET ✓")
        else:
            print("[STARTUP] MetaApi NOT ready — bot will NOT auto-start")
            print("[STARTUP] Go to MT5 page → Connect → then Start Bot manually")

        # Auto-start bot only when MetaApi is confirmed ready
        user = db.query(User).filter(User.username == "admin").first()
        if user and mt5_manager._ready and not active_bots.get(user.id):
            active_bots[user.id] = True
            user.bot_active = True
            db.commit()
            threading.Thread(
                target=run_user_bot_watchdog,
                args=(user.id, user.mt5_login,
                      user.mt5_password, user.mt5_server),
                daemon=True).start()
            print("[STARTUP] PumpingBot auto-started!")
        elif not mt5_manager._ready:
            print("[STARTUP] Auto-start skipped — MetaApi not ready")
            print("[STARTUP] Use /connect-mt5 then /bot/start after deployment")

        # ── Followers ko bhi reconnect karo (restart ke baad) ─────────────
        followers = db.query(User).filter(
            User.bot_active == True,
            User.username != "admin",
            User.metaapi_account_id != None
        ).all()

        for follower in followers:
            try:
                print(f"[STARTUP] Reconnecting follower: {follower.username}")
                conn = create_user_manager(follower.metaapi_account_id)
                pool_add(follower.id, conn)
                print(f"[STARTUP] Follower {follower.username} reconnected ✅")
            except Exception as fe:
                print(f"[STARTUP] Follower {follower.username} reconnect failed: {fe}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[STARTUP] Error: {e}")
    finally:
        db.close()


@app.get("/api")
def api_root():
    return {
        "message":       "PumpingBot Smart API",
        "version":       API_VERSION,
        "metaapi_ready": mt5_manager._ready,
        "event_set":     metaapi_ready_event.is_set(),
    }


import os as _os
_CLIENT_DIST = _os.path.join(_os.path.dirname(__file__), "client", "dist")
_FRONTEND_DIR = _os.path.join(_os.path.dirname(__file__), "frontend")


def _frontend_index():
    """React build (client/dist) prefer karo, warna simple frontend/."""
    for base in (_CLIENT_DIST, _FRONTEND_DIR):
        index = _os.path.join(base, "index.html")
        if _os.path.isfile(index):
            return index, base
    return None, None


@app.get("/")
def serve_frontend():
    index, _ = _frontend_index()
    if index:
        return FileResponse(index)
    return {
        "message":       "PumpingBot Smart API",
        "version":       API_VERSION,
        "metaapi_ready": mt5_manager._ready,
        "event_set":     metaapi_ready_event.is_set(),
    }


_idx, _dist = _frontend_index()
if _dist == _CLIENT_DIST and _os.path.isdir(_CLIENT_DIST):
    _assets = _os.path.join(_CLIENT_DIST, "assets")
    if _os.path.isdir(_assets):
        app.mount("/assets", StaticFiles(directory=_assets), name="react-assets")
elif _os.path.isdir(_FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")