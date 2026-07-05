from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
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
from mt5_manager import mt5_manager, MT5Manager, find_or_create_metaapi_account, create_user_manager

SECRET_KEY = "goldbot-secret-key-2024"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

import os
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

DAILY_MAX_LOSS_PCT   = 0.02
DAILY_TRAIL_START    = 0.02
DAILY_TRAIL_GAP      = 0.01
RISK_PER_TRADE_PCT   = 0.002
MAX_OPEN_TRADES      = 5
MIN_SCORE            = 55
MASTER_USER_ID       = 1   # Admin = Master account (copy trading hub)
STRONG_SCORE         = 75
MAX_SPREAD_POINTS    = 2000
SYMBOL_MAX_SPREAD = {
    "XAUUSDm":  30000,
    "XAGUSDm":  5000,
    "BTCUSDm":  2000000,
    "ETHUSDm":  200000,
    "SOLUSDm":  200000,
    "EURUSDm":  2000,
    "GBPUSDm":  2000,
    "USDJPYm":  2000,
    "AUDUSDm":  2000,
    "USDCADm":  2000,
    "GBPJPYm":  8000,
    "NZDUSDm":  2000,
}
MIN_COOLDOWN_SEC     = 300
SCALP_ATR_MULT       = 0.5
HOLD_MIN_PROFIT      = 10.0
HOLD_TRAIL_PCT       = 0.70

TRAILING_LEVELS = [
    (2.0,  1.0), (5.0,  3.0), (8.0,  5.0), (10.0, 7.0),
    (12.0, 9.0), (15.0, 12.0), (18.0, 14.0), (20.0, 16.0),
    (25.0, 20.0), (30.0, 25.0), (40.0, 33.0), (50.0, 42.0),
]

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
    if user_id == MASTER_USER_ID:
        return mt5_manager   # Master ka singleton
    return user_connections.get(user_id)  # Follower ka pool connection

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


def get_profit_target(score, atr, symbol):
    info = mt5_manager.symbol_info(symbol)
    if info is None or atr == 0:
        return 5.0
    tick_value = info.trade_tick_value
    tick_size  = info.trade_tick_size
    if tick_value == 0 or tick_size == 0:
        return 5.0
    atr_ticks  = atr / tick_size
    atr_dollar = atr_ticks * tick_value * 0.01
    if score >= 75:
        mult = 2.0 if score >= 85 else 1.5
    else:
        mult = SCALP_ATR_MULT
    return round(max(2.0, min(150.0, atr_dollar * mult)), 2)

def get_locked_profit(current_profit):
    locked = None
    for trigger, lock in TRAILING_LEVELS:
        if current_profit >= trigger:
            locked = lock
    return locked

def is_scalp_trade(score):
    return score < STRONG_SCORE


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


# ─── Technical Indicators ─────────────────────────────────────────────────────

def ema(prices, period):
    if len(prices) < period:
        return [prices[-1]] * len(prices)
    k = 2.0 / (period + 1)
    result = [prices[0]]
    for p in prices[1:]:
        result.append(p * k + result[-1] * (1 - k))
    return result

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains  = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    return 100 - (100 / (1 + avg_gain / avg_loss))

def calc_stoch_rsi(closes, period=14, smooth=3):
    if len(closes) < period * 2:
        return 50, 50
    rsi_vals = []
    for i in range(period, len(closes)):
        rsi_vals.append(calc_rsi(closes[max(0, i-period):i+1], period))
    if len(rsi_vals) < period:
        return 50, 50
    recent = rsi_vals[-period:]
    min_r, max_r = min(recent), max(recent)
    if max_r == min_r:
        return 50, 50
    k = (rsi_vals[-1] - min_r) / (max_r - min_r) * 100
    d = sum([(r - min_r) / (max_r - min_r) * 100 for r in rsi_vals[-smooth:]]) / smooth
    return k, d

def calc_adx(highs, lows, closes, period=14):
    try:
        if len(closes) < period + 1:
            return 0
        tr_list, pdm_list, ndm_list = [], [], []
        for i in range(1, len(closes)):
            tr  = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
            pdm = max(highs[i]-highs[i-1], 0) if highs[i]-highs[i-1] > lows[i-1]-lows[i] else 0
            ndm = max(lows[i-1]-lows[i], 0)  if lows[i-1]-lows[i] > highs[i]-highs[i-1]  else 0
            tr_list.append(tr); pdm_list.append(pdm); ndm_list.append(ndm)
        atr = sum(tr_list[-period:]) / period
        if atr == 0:
            return 0
        pdi = (sum(pdm_list[-period:]) / period) / atr * 100
        ndi = (sum(ndm_list[-period:]) / period) / atr * 100
        return abs(pdi-ndi) / (pdi+ndi) * 100 if (pdi+ndi) > 0 else 0
    except:
        return 0

def calc_atr(highs, lows, closes, period=14):
    try:
        if len(closes) < period + 1:
            return 0
        tr_list = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]),
                       abs(lows[i]-closes[i-1])) for i in range(1, len(closes))]
        return sum(tr_list[-period:]) / period
    except:
        return 0

def calc_macd(closes):
    if len(closes) < 26:
        return 0, 0
    e12  = ema(closes, 12)
    e26  = ema(closes, 26)
    macd_line   = [a-b for a, b in zip(e12, e26)]
    signal_line = ema(macd_line, 9)
    hist = [m-s for m, s in zip(macd_line, signal_line)]
    return hist[-1], hist[-2] if len(hist) > 1 else hist[-1]

def calc_bollinger(closes, period=20, std_dev=2):
    if len(closes) < period:
        return closes[-1], closes[-1], closes[-1]
    recent = closes[-period:]
    mid    = sum(recent) / period
    std    = (sum((x-mid)**2 for x in recent) / period) ** 0.5
    return mid + std_dev*std, mid, mid - std_dev*std

def detect_candle_pattern(opens, highs, lows, closes):
    if len(closes) < 3:
        return None, None, 0
    o1,h1,l1,c1 = opens[-1],highs[-1],lows[-1],closes[-1]
    o2,h2,l2,c2 = opens[-2],highs[-2],lows[-2],closes[-2]
    o3,h3,l3,c3 = opens[-3],highs[-3],lows[-3],closes[-3]
    body1  = abs(c1-o1)
    body2  = abs(c2-o2)
    range1 = h1-l1 if h1 != l1 else 0.0001
    range2 = h2-l2 if h2 != l2 else 0.0001
    uw1 = h1 - max(o1,c1)
    lw1 = min(o1,c1) - l1
    if lw1 >= body1*2 and uw1 <= body1*0.3 and c1 > o1:
        return "Hammer","BUY",15
    if c2 < o2 and c1 > o1 and c1 > o2 and o1 < c2:
        return "Bullish Engulfing","BUY",20
    if c3 < o3 and body2 < range2*0.3 and c1 > o1 and c1 > (o3+c3)/2:
        return "Morning Star","BUY",18
    if c1 > o1 and body1 >= range1*0.85:
        return "Bullish Marubozu","BUY",12
    if c2 < o2 and c1 > o1 and o1 < l2 and c1 > (o2+c2)/2:
        return "Piercing Line","BUY",14
    if uw1 >= body1*2 and lw1 <= body1*0.3 and c1 < o1:
        return "Shooting Star","SELL",15
    if c2 > o2 and c1 < o1 and c1 < o2 and o1 > c2:
        return "Bearish Engulfing","SELL",20
    if c3 > o3 and body2 < range2*0.3 and c1 < o1 and c1 < (o3+c3)/2:
        return "Evening Star","SELL",18
    if c1 < o1 and body1 >= range1*0.85:
        return "Bearish Marubozu","SELL",12
    if c2 > o2 and c1 < o1 and o1 > h2 and c1 < (o2+c2)/2:
        return "Dark Cloud Cover","SELL",14
    return None, None, 0

def get_trend(symbol):
    r1h = mt5_manager.copy_rates_from_pos(symbol, mt5_manager.TIMEFRAME_H1, 0, 200)
    r4h = mt5_manager.copy_rates_from_pos(symbol, mt5_manager.TIMEFRAME_H4, 0, 100)
    if r1h is None or len(r1h) < 50:
        return "BUY", 15, 15
    closes1h = [r['close'] for r in r1h]
    highs1h  = [r['high']  for r in r1h]
    lows1h   = [r['low']   for r in r1h]
    e100 = ema(closes1h, min(100, len(closes1h)-1))
    e20  = ema(closes1h, 20)
    adx_1h = calc_adx(highs1h, lows1h, closes1h)
    price = closes1h[-1]
    if price > e100[-1] and e20[-1] > e100[-1]:
        trend = "BUY"
    elif price < e100[-1] and e20[-1] < e100[-1]:
        trend = "SELL"
    else:
        trend = "BUY" if e20[-1] > e20[-5] else "SELL"
    adx_4h = adx_1h
    if r4h is not None and len(r4h) >= 30:
        closes4h = [r['close'] for r in r4h]
        highs4h  = [r['high']  for r in r4h]
        lows4h   = [r['low']   for r in r4h]
        adx_4h   = calc_adx(highs4h, lows4h, closes4h)
    return trend, adx_4h, adx_1h

def calc_score(trend, adx_4h, adx_1h, rsi, stoch_k, stoch_d,
               macd_h, macd_h_prev, closes, e8, e21, e50,
               bb_upper, bb_lower, bb_mid, pattern_dir, pattern_bonus):
    score = 0
    price = closes[-1]
    score += 20
    if adx_4h >= 30:   score += 15
    elif adx_4h >= 20: score += 10
    elif adx_4h >= 15: score += 5
    if adx_1h >= 25:   score += 10
    elif adx_1h >= 15: score += 5
    if trend == "BUY"  and e8 > e21 > e50: score += 10
    elif trend == "SELL" and e8 < e21 < e50: score += 10
    elif trend == "BUY"  and e8 > e21: score += 5
    elif trend == "SELL" and e8 < e21: score += 5
    if trend == "BUY"  and stoch_k < 25 and stoch_k > stoch_d: score += 10
    elif trend == "SELL" and stoch_k > 75 and stoch_k < stoch_d: score += 10
    elif trend == "BUY"  and stoch_k < 40: score += 5
    elif trend == "SELL" and stoch_k > 60: score += 5
    if trend == "BUY"  and macd_h > 0 and macd_h > macd_h_prev: score += 10
    elif trend == "SELL" and macd_h < 0 and macd_h < macd_h_prev: score += 10
    elif trend == "BUY"  and macd_h_prev < 0 < macd_h: score += 7
    elif trend == "SELL" and macd_h_prev > 0 > macd_h: score += 7
    if trend == "BUY"  and price <= bb_lower: score += 5
    elif trend == "SELL" and price >= bb_upper: score += 5
    if pattern_dir == trend and pattern_bonus > 0:
        score += pattern_bonus
    return min(score, 100)

def get_risk_multiplier(score):
    """Score jitna strong — margin zyada, risk bhi proportional"""
    if score >= 90: return 3.0
    elif score >= 80: return 2.5
    elif score >= 70: return 2.0
    elif score >= 65: return 1.5
    else: return 1.0   # score 55-64: base risk

def calculate_lot(balance, atr, symbol, score=55):
    try:
        mult        = get_risk_multiplier(score)
        risk_amount = balance * RISK_PER_TRADE_PCT * mult
        info = mt5_manager.symbol_info(symbol)
        if info is None: return None
        tick_value = info.trade_tick_value
        tick_size  = info.trade_tick_size
        if atr == 0 or tick_value == 0 or tick_size == 0:
            return info.volume_min
        sl_ticks = atr / tick_size
        lot = risk_amount / (sl_ticks * tick_value)
        lot = max(info.volume_min, min(info.volume_max,
              round(lot / info.volume_step) * info.volume_step))
        return round(lot, 2)
    except:
        return None

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

def sync_manual_closes(user_id, balance):
    db = SessionLocal()
    try:
        open_trades = db.query(Trade).filter(
            Trade.user_id == user_id, Trade.status == "open").all()
        if not open_trades: return
        for trade in open_trades:
            sym_pos = mt5_manager.positions_get(symbol=trade.symbol)
            has_pos = any(p.magic == 888888 or "PB_" in getattr(p, "comment", "") for p in sym_pos) if sym_pos else False
            if not has_pos:
                trade.status    = "closed"
                trade.profit    = 0.0
                trade.closed_at = datetime.utcnow()
                db.commit()
                last_close_times[(user_id, trade.symbol)] = datetime.now()
    except Exception as e:
        print(f"[SYNC] {e}")
    finally:
        db.close()

def close_all_positions(user_id, reason, balance):
    positions = mt5_manager.positions_get()
    if not positions: return
    for pos in positions:
        if pos.magic == 888888 or "PB_" in getattr(pos, "comment", ""):
            tick = mt5_manager.symbol_info_tick(pos.symbol)
            done, profit = close_pos(pos, reason)
            if done and tick:
                cp = tick.bid if pos.type == 0 else tick.ask
                update_trade_closed(user_id, pos.symbol, profit, cp, pos.ticket)
                last_close_times[(user_id, pos.symbol)] = datetime.now()


# ─── FIX: Bot thread now waits on threading.Event (not polling loop) ──────────
def copy_to_followers(master_user_id, symbol, trend, score, atr, master_lot, master_balance, entry, sl, trade_mode):
    """Master trade ko sab active followers ke connections par copy karo"""
    db = SessionLocal()
    try:
        followers = db.query(User).filter(
            User.bot_active == True,
            User.id != master_user_id,
            User.mt5_login != None
        ).all()

        if not followers:
            return

        print(f"[COPY] Copying {symbol} {trend} to {len(followers)} follower(s)...")

        for follower in followers:
            try:
                # Connection pool se follower ka connection lo
                conn = pool_get(follower.id)

                if conn is None or not pool_is_ready(follower.id):
                    print(f"[COPY] ⚠️ {follower.username} not connected — skipping MT5, recording DB only")
                    # Sirf DB record karo
                    trade = Trade(
                        user_id=follower.id, symbol=symbol, trade_type=trend,
                        lot=master_lot, open_price=entry, score=score,
                        mt5_ticket=None, status="pending_copy")
                    db.add(trade); db.commit()
                    continue

                # Follower ka balance lo — proportional lot calculate karo
                follower_info = conn.account_info()
                if follower_info:
                    ratio = follower_info.balance / master_balance if master_balance > 0 else 1.0
                    follower_lot = max(0.01, round(master_lot * ratio, 2))
                else:
                    follower_lot = master_lot

                # Follower ke account par actual trade lagao
                tick = conn.symbol_info_tick(symbol)
                if tick is None:
                    print(f"[COPY] ⚠️ {follower.username} no tick for {symbol}")
                    continue

                f_entry = tick.ask if trend == "BUY" else tick.bid
                f_sl    = f_entry - atr if trend == "BUY" else f_entry + atr

                request = {
                    "action":       conn.TRADE_ACTION_DEAL,
                    "symbol":       symbol,
                    "volume":       follower_lot,
                    "type":         conn.ORDER_TYPE_BUY if trend == "BUY" else conn.ORDER_TYPE_SELL,
                    "price":        f_entry,
                    "sl":           f_sl,
                    "deviation":    50,
                    "magic":        888888,
                    "comment":      f"PB_COPY_{trade_mode}_S{score}",
                    "type_time":    conn.ORDER_TIME_GTC,
                    "type_filling": conn.ORDER_FILLING_IOC,
                }

                result = conn.order_send(request)
                if result.retcode == conn.TRADE_RETCODE_DONE:
                    trade = Trade(
                        user_id=follower.id, symbol=symbol, trade_type=trend,
                        lot=follower_lot, open_price=f_entry, score=score,
                        mt5_ticket=result.order, status="open")
                    db.add(trade); db.commit()
                    print(f"[COPY] ✅ {follower.username} {symbol} {trend} Lot:{follower_lot} Ticket:{result.order}")
                else:
                    print(f"[COPY] ❌ {follower.username} order failed: {result.retcode}")

            except Exception as e:
                print(f"[COPY] ❌ {follower.username} error: {e}")

    except Exception as e:
        print(f"[COPY] Error: {e}")
    finally:
        db.close()


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

            all_pos = mt5_manager.positions_get()
            bot_pos = [p for p in all_pos if p.magic == 888888 or "PB_" in getattr(p, "comment", "")] if all_pos else []

            for pos in bot_pos:
                current_profit = pos.profit
                ticket         = pos.ticket
                trade_type     = "BUY" if pos.type == 0 else "SELL"

                db = SessionLocal()
                tr = db.query(Trade).filter(Trade.mt5_ticket == ticket).first()
                score = tr.score if tr else 60
                db.close()

                rates5 = mt5_manager.copy_rates_from_pos(
                    pos.symbol, mt5_manager.TIMEFRAME_M5, 0, 50)
                atr = 0
                if rates5 is not None and len(rates5) > 14:
                    h5 = [r['high']  for r in rates5]
                    l5 = [r['low']   for r in rates5]
                    c5 = [r['close'] for r in rates5]
                    atr = calc_atr(h5, l5, c5)

                current_trend, current_adx_4h, current_adx_1h = get_trend(pos.symbol)
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
                    continue

                profit_target = get_profit_target(score, atr, pos.symbol)

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

            all_pos = mt5_manager.positions_get()
            bot_pos = [p for p in all_pos if p.magic == 888888 or "PB_" in getattr(p, "comment", "")] if all_pos else []

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

                tick     = mt5_manager.symbol_info_tick(symbol)
                sym_info = mt5_manager.symbol_info(symbol)
                if tick is None or sym_info is None:
                    print(f"[NO TICK] {symbol} — skipping (weekend/market closed?)")
                    continue

                spread = (tick.ask - tick.bid) / sym_info.point
                max_spread = SYMBOL_MAX_SPREAD.get(symbol, MAX_SPREAD_POINTS)
                if spread > max_spread:
                    print(f"[HIGH SPREAD] {symbol} spread={spread:.0f} max={max_spread}")
                    continue

                trend, adx_4h, adx_1h = get_trend(symbol)

                rates5 = mt5_manager.copy_rates_from_pos(
                    symbol, mt5_manager.TIMEFRAME_M5, 0, 100)
                if rates5 is None or len(rates5) < 30:
                    print(f"[NO DATA] {symbol} — got: {len(rates5) if rates5 else 'None'}")
                    continue

                opens5  = [r['open']  for r in rates5]
                highs5  = [r['high']  for r in rates5]
                lows5   = [r['low']   for r in rates5]
                closes5 = [r['close'] for r in rates5]

                e8_l  = ema(closes5, 8)
                e21_l = ema(closes5, 21)
                e50_l = ema(closes5, 50)
                rsi   = calc_rsi(closes5)
                stk, std = calc_stoch_rsi(closes5)
                atr   = calc_atr(highs5, lows5, closes5)
                mh, mhp = calc_macd(closes5)
                bbu, bbm, bbl = calc_bollinger(closes5)
                pname, pdir, pbonus = detect_candle_pattern(opens5, highs5, lows5, closes5)

                score = calc_score(
                    trend, adx_4h, adx_1h, rsi, stk, std,
                    mh, mhp, closes5,
                    e8_l[-1], e21_l[-1], e50_l[-1],
                    bbu, bbl, bbm, pdir, pbonus
                )

                trade_mode = "SCALP" if score < STRONG_SCORE else "HOLD"
                pinfo = f"| {pname}+{pbonus}" if pname else ""
                print(f"[{now.strftime('%H:%M')}] {symbol} {trend} {trade_mode} "
                      f"ADX4H:{adx_4h:.0f} ADX1H:{adx_1h:.0f} "
                      f"RSI:{rsi:.0f} Score:{score} {pinfo}")

                db = SessionLocal()
                sig = Signal(
                    symbol=symbol,
                    signal_type=trend if score >= MIN_SCORE else "WAIT",
                    score=score, ema_fast=e8_l[-1], ema_slow=e21_l[-1],
                    macd=mh, rsi=rsi, adx=adx_4h, price=closes5[-1])
                db.add(sig); db.commit(); db.close()

                if score < MIN_SCORE:
                    continue

                if pdir and pdir != trend and score < 70:
                    print(f"[SKIP] {symbol} pattern conflict")
                    continue

                lot = calculate_lot(balance, atr, symbol, score)
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
                    target = get_profit_target(score, atr, symbol)
                    print(f"[{trade_mode}] TRADE PLACED! {symbol} {trend} "
                          f"Score:{score} Target:${target} Lot:{lot}")
                    db = SessionLocal()
                    trade = Trade(
                        user_id=user_id, symbol=symbol, trade_type=trend,
                        lot=lot, open_price=entry, score=score,
                        mt5_ticket=result.order, status="open")
                    db.add(trade); db.commit(); db.close()

                    # COPY TRADING: Master trade ko sab followers ke pass bhejo
                    if user_id == MASTER_USER_ID:
                        threading.Thread(
                            target=copy_to_followers,
                            args=(user_id, symbol, trend, score, atr,
                                  lot, balance, entry, sl, trade_mode),
                            daemon=True
                        ).start()

                    all_pos = mt5_manager.positions_get()
                    bot_pos = [p for p in all_pos if p.magic == 888888 or "PB_" in getattr(p, "comment", "")] if all_pos else []
                else:
                    print(f"[FAIL] {symbol}: retcode={result.retcode}")
                    last_close_times[(user_id, symbol)] = now

                time.sleep(1)

            time.sleep(5)

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
            User.id != MASTER_USER_ID
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
                positions = conn.positions_get()
                for pos in (positions or []):
                    if pos.magic == 888888:
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
    if current_user.id != MASTER_USER_ID:
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

    # Bot restart karo
    active_bots[user.id] = True
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
    if current_user.id != MASTER_USER_ID:
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
    if current_user.id != MASTER_USER_ID:
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
    if current_user.id != MASTER_USER_ID:
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
    if current_user.id != MASTER_USER_ID:
        raise HTTPException(403, "Admin only")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.bot_active:
        active_bots[user.id] = False
        user.bot_active = False
        db.commit()
        return {"message": f"{user.username} bot stopped"}
    else:
        active_bots[user.id] = True
        user.bot_active = True
        db.commit()
        threading.Thread(
            target=run_user_bot_watchdog,
            args=(user.id, user.mt5_login, user.mt5_password, user.mt5_server),
            daemon=True
        ).start()
        return {"message": f"{user.username} bot started"}


@app.delete("/admin/delete-user/{user_id}")
def admin_delete_user(user_id: int,
                      current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    if current_user.id != MASTER_USER_ID:
        raise HTTPException(403, "Admin only")
    if user_id == MASTER_USER_ID:
        raise HTTPException(400, "Admin ko delete nahi kar sakte")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
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
def get_me(current_user: User = Depends(get_current_user)):
    info = mt5_manager.account_info()
    return {
        "username":      current_user.username,
        "email":         current_user.email,
        "mt5_connected": current_user.mt5_login is not None,
        "mt5_ready":     mt5_manager._ready,          # FIX: expose _ready to frontend
        "mt5_login":     current_user.mt5_login,
        "mt5_server":    current_user.mt5_server,
        "bot_active":    current_user.bot_active,
        "balance":       info.balance if info else 0,
        "profit":        info.profit  if info else 0,
        "equity":        info.equity  if info else 0,
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

    if current_user.id == MASTER_USER_ID:
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
        # ── Follower: credentials save karo, master connection use hoga ───
        print(f"[CONNECT] Follower {current_user.username} connecting...")
        current_user.mt5_login    = creds.mt5_login
        current_user.mt5_password = creds.mt5_password
        current_user.mt5_server   = creds.mt5_server
        db.commit()

        # Master connection se info lo
        info = mt5_manager.account_info()
        print(f"[CONNECT] ✅ Follower {current_user.username} credentials saved!")
        return {
            "message":   "MT5 Connected successfully!",
            "balance":   info.balance if info else 0,
            "mt5_ready": mt5_manager._ready,
            "role":      "follower"
        }

# FIX: start_bot checks _ready before launching thread
@app.post("/bot/start")
def start_bot(current_user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    if not current_user.mt5_login:
        raise HTTPException(400, "Connect MT5 first")
    if not mt5_manager._ready:
        raise HTTPException(400, "MetaApi not ready — reconnect MT5 first")
    if active_bots.get(current_user.id):
        return {"message": "Bot already running"}

    # FIX: Ensure the event is set before starting thread
    if mt5_manager._ready:
        metaapi_ready_event.set()

    active_bots[current_user.id] = True
    current_user.bot_active = True
    db.commit()
    threading.Thread(
        target=run_user_bot_watchdog,
        args=(current_user.id, current_user.mt5_login,
              current_user.mt5_password, current_user.mt5_server),
        daemon=True).start()
    return {"message": "PumpingBot started!"}

@app.post("/bot/stop")
def stop_bot(current_user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    active_bots[current_user.id] = False
    current_user.bot_active = False
    db.commit()
    return {"message": "Bot stopped"}

@app.get("/signals")
def get_signals(current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    return db.query(Signal).order_by(Signal.created_at.desc()).limit(50).all()

@app.get("/trades")
def get_trades(current_user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    return db.query(Trade).filter(
        Trade.user_id == current_user.id
    ).order_by(Trade.opened_at.desc()).limit(100).all()

@app.get("/open_positions")
def get_open_positions(current_user: User = Depends(get_current_user)):
    positions = mt5_manager.positions_get()
    if not positions: return []
    result = []
    for p in positions:
        is_bot = (
            p.magic == 888888 or
            "PB_" in getattr(p, "comment", "") or
            getattr(p, "magic", 0) == 888888
        )
        if not is_bot:
            continue
        # DB se extra info lo
        db = SessionLocal()
        tr = db.query(Trade).filter(Trade.mt5_ticket == p.ticket).first()
        score = tr.score if tr else 0
        open_price = tr.open_price if tr else getattr(p, "openPrice", 0)
        db.close()

        tick = mt5_manager.symbol_info_tick(p.symbol)
        current_price = (tick.bid if p.type == 0 else tick.ask) if tick else 0

        result.append({
            "ticket":      p.ticket,
            "symbol":      p.symbol,
            "profit":      round(p.profit, 2),
            "type":        "BUY" if p.type == 0 else "SELL",
            "lot":         getattr(p, "volume", 0),
            "open_price":  open_price,
            "current_price": current_price,
            "score":       score,
            "magic":       getattr(p, "magic", 0),
            "comment":     getattr(p, "comment", ""),
        })
    return result

# FIX: New endpoint to debug connection status
@app.get("/status")
def get_status(current_user: User = Depends(get_current_user)):
    info = mt5_manager.account_info()
    return {
        "metaapi_ready":    mt5_manager._ready,
        "event_set":        metaapi_ready_event.is_set(),
        "bot_active":       active_bots.get(current_user.id, False),
        "account_info_ok":  info is not None,
        "balance":          info.balance if info else None,
    }


# ─── FIX: Startup Event — passes credentials, sets metaapi_ready_event ────────
@app.on_event("startup")
async def startup_event():
    # Background scheduler start karo
    threading.Thread(target=daily_scheduler, daemon=True).start()
    print("[STARTUP] Daily scheduler started (8 PM notify, 9 PM pause)")

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
            User.id != MASTER_USER_ID,
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


@app.get("/")
def root():
    return {
        "message":       "PumpingBot Smart API",
        "metaapi_ready": mt5_manager._ready,
        "event_set":     metaapi_ready_event.is_set(),
    }