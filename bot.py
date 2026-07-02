from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional
import MetaTrader5 as mt5
import threading
import time

# ═══════════════════════════════════
# CONFIG
# ═══════════════════════════════════
SECRET_KEY = "goldbot-secret-key-2024"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

DATABASE_URL = "sqlite:///./goldbot.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

app = FastAPI(title="GoldBot Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════
# DATABASE MODELS
# ═══════════════════════════════════
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    mt5_login = Column(Integer, nullable=True)
    mt5_password = Column(String, nullable=True)
    mt5_server = Column(String, nullable=True)
    bot_active = Column(Boolean, default=False)
    balance = Column(Float, default=0.0)
    profit = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    symbol = Column(String)
    trade_type = Column(String)
    lot = Column(Float)
    open_price = Column(Float)
    close_price = Column(Float, nullable=True)
    sl = Column(Float)
    tp = Column(Float)
    profit = Column(Float, default=0.0)
    status = Column(String, default="open")
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

class Signal(Base):
    __tablename__ = "signals"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String)
    signal_type = Column(String)
    ema_fast = Column(Float)
    ema_slow = Column(Float)
    rsi = Column(Float)
    price = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# ═══════════════════════════════════
# PYDANTIC SCHEMAS
# ═══════════════════════════════════
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class MT5Credentials(BaseModel):
    mt5_login: int
    mt5_password: str
    mt5_server: str

class Token(BaseModel):
    access_token: str
    token_type: str

# ═══════════════════════════════════
# AUTH FUNCTIONS
# ═══════════════════════════════════
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_password_hash(password):
    return pwd_context.hash(password)

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

# ═══════════════════════════════════
# BOT LOGIC
# ═══════════════════════════════════
active_bots = {}

def run_user_bot(user_id: int, login: int, password: str, server: str):
    import pandas as pd
    
    SYMBOL = "XAUUSDm"
    LOT = 0.01
    EMA_FAST = 20
    EMA_SLOW = 50
    RSI_PERIOD = 14

    if not mt5.initialize(login=login, password=password, server=server):
        print(f"❌ User {user_id} MT5 connect failed")
        return

    print(f"✅ Bot started for user {user_id}")

    while active_bots.get(user_id, False):
        try:
            rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 200)
            if rates is None:
                time.sleep(30)
                continue

            df = pd.DataFrame(rates)
            df['ema_fast'] = df['close'].ewm(span=EMA_FAST).mean()
            df['ema_slow'] = df['close'].ewm(span=EMA_SLOW).mean()
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(RSI_PERIOD).mean()
            loss = -delta.where(delta < 0, 0).rolling(RSI_PERIOD).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))

            last = df.iloc[-1]
            prev = df.iloc[-2]

            signal = None
            if prev['ema_fast'] < prev['ema_slow'] and last['ema_fast'] > last['ema_slow'] and last['rsi'] < 60:
                signal = "BUY"
            elif prev['ema_fast'] > prev['ema_slow'] and last['ema_fast'] < last['ema_slow'] and last['rsi'] > 40:
                signal = "SELL"

            # Save signal to DB
            db = SessionLocal()
            sig = Signal(
                symbol=SYMBOL,
                signal_type=signal or "WAIT",
                ema_fast=float(last['ema_fast']),
                ema_slow=float(last['ema_slow']),
                rsi=float(last['rsi']),
                price=float(last['close'])
            )
            db.add(sig)
            db.commit()

            if signal:
                price = mt5.symbol_info_tick(SYMBOL).ask if signal == "BUY" else mt5.symbol_info_tick(SYMBOL).bid
                point = mt5.symbol_info(SYMBOL).point
                sl = price - 200*point if signal == "BUY" else price + 200*point
                tp = price + 400*point if signal == "BUY" else price - 400*point

                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": SYMBOL,
                    "volume": LOT,
                    "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
                    "price": price,
                    "sl": sl,
                    "tp": tp,
                    "deviation": 20,
                    "magic": 999999,
                    "comment": f"GoldBot_User{user_id}",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                result = mt5.order_send(request)
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    trade = Trade(
                        user_id=user_id,
                        symbol=SYMBOL,
                        trade_type=signal,
                        lot=LOT,
                        open_price=price,
                        sl=sl,
                        tp=tp
                    )
                    db.add(trade)
                    db.commit()
                    print(f"✅ Trade placed for user {user_id}: {signal} @ {price}")

            db.close()
            time.sleep(60)

        except Exception as e:
            print(f"⚠️ Bot error user {user_id}: {e}")
            time.sleep(10)

    mt5.shutdown()
    print(f"🛑 Bot stopped for user {user_id}")

# ═══════════════════════════════════
# API ROUTES
# ═══════════════════════════════════

@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=get_password_hash(user.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully"}

@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Wrong username or password")
    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}

@app.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    info = mt5.account_info() if current_user.mt5_login else None
    return {
        "username": current_user.username,
        "email": current_user.email,
        "mt5_connected": current_user.mt5_login is not None,
        "mt5_login": current_user.mt5_login,
        "mt5_server": current_user.mt5_server,
        "bot_active": current_user.bot_active,
        "balance": info.balance if info else 0,
        "profit": info.profit if info else 0,
        "equity": info.equity if info else 0,
    }

@app.post("/connect-mt5")
def connect_mt5(creds: MT5Credentials, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not mt5.initialize(login=creds.mt5_login, password=creds.mt5_password, server=creds.mt5_server):
        raise HTTPException(status_code=400, detail=f"MT5 connection failed: {mt5.last_error()}")
    info = mt5.account_info()
    current_user.mt5_login = creds.mt5_login
    current_user.mt5_password = creds.mt5_password
    current_user.mt5_server = creds.mt5_server
    db.commit()
    return {"message": f"Connected to MT5: {info.name}", "balance": info.balance}

@app.post("/bot/start")
def start_bot(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.mt5_login:
        raise HTTPException(status_code=400, detail="Connect MT5 first")
    if active_bots.get(current_user.id):
        return {"message": "Bot already running"}
    active_bots[current_user.id] = True
    current_user.bot_active = True
    db.commit()
    thread = threading.Thread(
        target=run_user_bot,
        args=(current_user.id, current_user.mt5_login, current_user.mt5_password, current_user.mt5_server),
        daemon=True
    )
    thread.start()
    return {"message": "Bot started successfully!"}

@app.post("/bot/stop")
def stop_bot(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    active_bots[current_user.id] = False
    current_user.bot_active = False
    db.commit()
    return {"message": "Bot stopped"}

@app.get("/signals")
def get_signals(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    signals = db.query(Signal).order_by(Signal.created_at.desc()).limit(20).all()
    return signals

@app.get("/trades")
def get_trades(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    trades = db.query(Trade).filter(Trade.user_id == current_user.id).order_by(Trade.opened_at.desc()).all()
    return trades

@app.get("/")
def root():
    return {"message": "GoldBot Platform API", "status": "running"}