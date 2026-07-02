from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from datetime import datetime

Base = declarative_base()


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
    high_water_mark = Column(Float, nullable=True)

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

    profit = Column(Float, default=0.0)
    score = Column(Float, default=0.0)

    status = Column(String, default="open")

    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String)
    signal_type = Column(String)

    score = Column(Float)

    ema_fast = Column(Float)
    ema_slow = Column(Float)

    macd = Column(Float)
    rsi = Column(Float)
    adx = Column(Float)

    price = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)