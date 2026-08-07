"""
Crypto Pumping Signals — auth + subscription API for standalone service.

Provides the endpoints the PWA calls at site root:
  /register /token /me /subscription/... /admin/... /referral/...
"""

from __future__ import annotations

import os
import shutil
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    create_engine,
    or_,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# ── Config ──────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "crypto-pumping-signals-secret-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24)))

SUBSCRIPTION_FEE_USD = float(os.environ.get("SUBSCRIPTION_FEE_USD", "10"))
SUBSCRIPTION_DAYS = int(os.environ.get("SUBSCRIPTION_DAYS", "30"))
FREE_TRIAL_HOURS = int(os.environ.get("FREE_TRIAL_HOURS", "24"))
REFERRAL_COMMISSION_USD = float(os.environ.get("REFERRAL_COMMISSION_USD", "3"))
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "pumpingbot333@gmail.com")
ADMIN_USDT_BEP20 = os.environ.get(
    "ADMIN_USDT_BEP20",
    "0x906fdfced22b23f79e04415d6534386baf4f2e8e",
)

ADMIN99_USERNAME = "Admin99"
ADMIN99_PASSWORD = os.environ.get("ADMIN99_PASSWORD", "Goku.k.g99")
ADMIN99_EMAIL = os.environ.get("ADMIN99_EMAIL", "admin99@mysignals.app")
ADMIN_USERNAMES = frozenset({ADMIN99_USERNAME})

DATA_DIR = Path(__file__).parent / "data"
UPLOAD_DIR = Path(__file__).parent / "uploads"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{(DATA_DIR / 'signals_users.db').resolve()}",
)
# Railway Postgres uses postgres:// — SQLAlchemy wants postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
router = APIRouter(tags=["cps-auth"])


# ── Models ──────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "cps_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    subscription_status = Column(String, default="expired")
    subscription_expires_at = Column(DateTime, nullable=True)
    subscription_fee_owed = Column(Float, default=10.0)
    payment_status = Column(String, default="clear")
    payment_screenshot = Column(String, nullable=True)

    referral_code = Column(String, unique=True, nullable=True, index=True)
    referred_by = Column(Integer, nullable=True)
    referral_balance = Column(Float, default=0.0)
    referral_wallet = Column(String, nullable=True)
    referral_owed = Column(Float, default=0.0)

    bot_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReferralWithdraw(Base):
    __tablename__ = "cps_referral_withdraws"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    amount = Column(Float)
    wallet_address = Column(String)
    status = Column(String, default="pending")  # pending / approved / rejected
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


# ── Schemas ─────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    referral_code: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ReferralWalletIn(BaseModel):
    wallet_address: str


class ReferralWithdrawIn(BaseModel):
    amount: float
    wallet_address: str | None = None


# ── Helpers ─────────────────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_password_hash(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict, expires_minutes: int | None = None) -> str:
    to_encode = data.copy()
    if expires_minutes is not None and int(expires_minutes) <= 0:
        expire = datetime.utcnow() + timedelta(days=3650)
    else:
        minutes = ACCESS_TOKEN_EXPIRE_MINUTES if expires_minutes is None else int(expires_minutes)
        expire = datetime.utcnow() + timedelta(minutes=minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def is_master_user(user: User | None) -> bool:
    return user is not None and user.username in ADMIN_USERNAMES


def refresh_subscription_status(user: User) -> str:
    if user is None:
        return "expired"
    if is_master_user(user):
        user.subscription_status = "active"
        return "active"
    status = (user.subscription_status or "expired").lower()
    if status == "pending_review":
        return "pending_review"
    expires = user.subscription_expires_at
    now = datetime.utcnow()
    if status == "trial":
        if expires and expires > now:
            return "trial"
        user.subscription_status = "expired"
        user.payment_status = "overdue"
        user.subscription_fee_owed = SUBSCRIPTION_FEE_USD
        return "expired"
    if status == "active" and expires and expires > now:
        return "active"
    if status == "active" and (not expires or expires <= now):
        user.subscription_status = "expired"
        user.payment_status = "overdue"
        user.subscription_fee_owed = SUBSCRIPTION_FEE_USD
        return "expired"
    user.subscription_status = status if status in ("expired", "pending_review") else "expired"
    return user.subscription_status


def start_free_trial(user: User, hours: int | None = None) -> None:
    hrs = FREE_TRIAL_HOURS if hours is None else hours
    now = datetime.utcnow()
    user.subscription_status = "trial"
    user.subscription_expires_at = now + timedelta(hours=hrs)
    user.payment_status = "clear"
    user.subscription_fee_owed = SUBSCRIPTION_FEE_USD
    user.bot_active = False


def activate_subscription(user: User, days: int | None = None) -> None:
    d = SUBSCRIPTION_DAYS if days is None else days
    now = datetime.utcnow()
    user.subscription_expires_at = now + timedelta(days=d)
    user.subscription_status = "active"
    user.payment_status = "clear"
    user.subscription_fee_owed = 0.0


def generate_referral_code(db: Session) -> str:
    for _ in range(16):
        code = str(uuid.uuid4())[:8].upper()
        if not db.query(User).filter(User.referral_code == code).first():
            return code
    return uuid.uuid4().hex[:8].upper()


def ensure_referral_code(user: User, db: Session) -> str:
    if getattr(user, "referral_code", None):
        return user.referral_code
    code = generate_referral_code(db)
    user.referral_code = code
    db.commit()
    db.refresh(user)
    return code


def build_invite_url(request: Request | None, code: str) -> str:
    if not code:
        return ""
    base = (os.environ.get("PUBLIC_BASE_URL") or os.environ.get("MY_SIGNALS_URL") or "").rstrip("/")
    if not base and request is not None:
        proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
        host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
        if host:
            if proto != "https" and "railway.app" in host:
                proto = "https"
            base = f"{proto}://{host}".rstrip("/")
    if not base:
        return f"/?ref={code}"
    return f"{base}/?ref={code}"


def _normalize_bep20(addr: str) -> str:
    a = (addr or "").strip()
    if not a.startswith("0x") or len(a) != 42:
        raise HTTPException(400, "Valid USDT BEP20 address chahiye (0x… 42 chars)")
    return a


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(401, "Invalid token")
    except JWTError:
        raise HTTPException(401, "Invalid token")
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(401, "User not found")
    db.refresh(user)
    return user


def ensure_admin99(db: Session) -> None:
    """Create / repair Admin99 — only admin account."""
    admin = db.query(User).filter(User.username == ADMIN99_USERNAME).first()
    if admin is None:
        admin = User(
            username=ADMIN99_USERNAME,
            email=ADMIN99_EMAIL,
            hashed_password=get_password_hash(ADMIN99_PASSWORD),
            subscription_status="active",
            payment_status="clear",
            subscription_fee_owed=0.0,
            referral_code=generate_referral_code(db),
        )
        db.add(admin)
        db.commit()
        print(f"[CPS Auth] Created {ADMIN99_USERNAME}")
    else:
        # Keep password in sync with env on boot
        if not verify_password(ADMIN99_PASSWORD, admin.hashed_password):
            admin.hashed_password = get_password_hash(ADMIN99_PASSWORD)
        admin.email = ADMIN99_EMAIL
        admin.subscription_status = "active"
        admin.payment_status = "clear"
        if not admin.referral_code:
            admin.referral_code = generate_referral_code(db)
        db.commit()

    # Remove legacy "admin" if present
    legacy = db.query(User).filter(User.username == "admin").first()
    if legacy:
        db.delete(legacy)
        db.commit()
        print("[CPS Auth] Removed legacy admin user")


def init_auth_db() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_admin99(db)
    finally:
        db.close()


# ── Routes ──────────────────────────────────────────────────────────
@router.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(400, "Username already exists")
    if db.query(User).filter(User.email == user.email).first():
        raise HTTPException(400, "Email already exists")

    referred_by_id = None
    if user.referral_code:
        referrer = db.query(User).filter(User.referral_code == user.referral_code).first()
        if referrer:
            referred_by_id = referrer.id

    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=get_password_hash(user.password),
        referral_code=generate_referral_code(db),
        referred_by=referred_by_id,
        subscription_fee_owed=SUBSCRIPTION_FEE_USD,
        bot_active=False,
    )
    start_free_trial(new_user)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "message": f"User created — {FREE_TRIAL_HOURS}h free trial started",
        "referral_code": new_user.referral_code,
        "subscription_fee": SUBSCRIPTION_FEE_USD,
        "subscription_days": SUBSCRIPTION_DAYS,
        "referral_commission": REFERRAL_COMMISSION_USD,
        "admin_usdt_bep20": ADMIN_USDT_BEP20,
        "subscription_status": "trial",
        "trial_hours": FREE_TRIAL_HOURS,
        "subscription_expires_at": new_user.subscription_expires_at.isoformat()
        if new_user.subscription_expires_at
        else None,
    }


@router.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    ident = (form_data.username or "").strip()
    user = db.query(User).filter(or_(User.email == ident, User.username == ident)).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(401, "Wrong email/username or password")
    refresh_subscription_status(user)
    db.commit()
    if is_master_user(user):
        token = create_access_token(
            {"sub": user.username, "role": "admin"},
            expires_minutes=0,
        )
    else:
        token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
def get_me(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub_status = refresh_subscription_status(current_user)
    ref_code = ensure_referral_code(current_user, db)
    db.commit()

    expires_at = current_user.subscription_expires_at
    trial_remaining_sec = 0
    if sub_status == "trial" and expires_at:
        trial_remaining_sec = max(0, int((expires_at - datetime.utcnow()).total_seconds()))

    return {
        "username": current_user.username,
        "email": current_user.email,
        "user_id": current_user.id,
        "is_admin": is_master_user(current_user),
        "role": "master" if is_master_user(current_user) else "follower",
        "mt5_connected": False,
        "mt5_ready": False,
        "vps_ready": False,
        "vps_status": "n/a",
        "trading_backend": "signals_only",
        "bot_active": False,
        "balance": 0,
        "equity": 0,
        "open_trades_count": 0,
        "referral_code": ref_code,
        "invite_url": build_invite_url(request, ref_code),
        "payment_status": current_user.payment_status or "clear",
        "amount_owed": (
            (current_user.subscription_fee_owed or SUBSCRIPTION_FEE_USD)
            if sub_status not in ("active", "trial")
            else 0
        ),
        "subscription_status": sub_status,
        "subscription_expires_at": expires_at.isoformat() if expires_at else None,
        "subscription_fee": SUBSCRIPTION_FEE_USD,
        "subscription_days": SUBSCRIPTION_DAYS,
        "trial_hours": FREE_TRIAL_HOURS,
        "is_trial": sub_status == "trial",
        "trial_remaining_seconds": trial_remaining_sec,
        "has_payment_screenshot": bool(current_user.payment_screenshot),
        "admin_email": ADMIN_EMAIL,
        "admin_usdt_bep20": ADMIN_USDT_BEP20,
        "referral_commission": REFERRAL_COMMISSION_USD,
        "referral_balance": round(current_user.referral_balance or 0, 2),
        "referral_wallet": current_user.referral_wallet,
    }


@router.post("/subscription/upload-screenshot")
async def upload_payment_screenshot(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if is_master_user(current_user):
        raise HTTPException(400, "Admin ko payment upload ki zaroorat nahi")

    content_type = (file.content_type or "").lower()
    name = (file.filename or "").lower()
    if not content_type.startswith("image/") and not content_type.endswith("pdf"):
        if not any(name.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf")):
            raise HTTPException(400, "Sirf image/PDF screenshot upload karein")

    ext = Path(file.filename or "shot.png").suffix.lower() or ".png"
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf"):
        ext = ".png"
    fname = f"user{current_user.id}_{int(time.time())}{ext}"
    dest = UPLOAD_DIR / fname
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    user = db.query(User).filter(User.id == current_user.id).first()
    user.payment_screenshot = str(dest)
    user.subscription_status = "pending_review"
    user.payment_status = "pending_review"
    user.subscription_fee_owed = SUBSCRIPTION_FEE_USD
    user.bot_active = False
    db.commit()
    return {
        "message": "Screenshot uploaded — admin approve karega tab package active hoga",
        "subscription_status": "pending_review",
        "fee": SUBSCRIPTION_FEE_USD,
    }


@router.get("/admin/payment-screenshot/{user_id}")
def get_payment_screenshot(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.payment_screenshot:
        raise HTTPException(404, "Screenshot not found")
    path = Path(user.payment_screenshot)
    if not path.is_file():
        raise HTTPException(404, "Screenshot file missing")
    return FileResponse(path)


@router.post("/admin/confirm-payment/{user_id}")
def confirm_payment(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")

    referral_credited = 0.0
    if user.referred_by:
        referrer = db.query(User).filter(User.id == user.referred_by).first()
        if referrer and not is_master_user(referrer):
            referrer.referral_balance = round(
                (referrer.referral_balance or 0) + REFERRAL_COMMISSION_USD, 2
            )
            referral_credited = REFERRAL_COMMISSION_USD

    activate_subscription(user)
    db.commit()
    return {
        "message": f"Payment confirmed — {user.username} active",
        "subscription_status": "active",
        "subscription_expires_at": user.subscription_expires_at.isoformat()
        if user.subscription_expires_at
        else None,
        "referral_credited": referral_credited,
        "admin_share": round(SUBSCRIPTION_FEE_USD - (referral_credited or 0), 2),
    }


@router.post("/admin/reject-payment/{user_id}")
def reject_payment(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    user.subscription_status = "expired"
    user.payment_status = "rejected"
    user.subscription_fee_owed = SUBSCRIPTION_FEE_USD
    user.payment_screenshot = None
    user.bot_active = False
    db.commit()
    return {"message": f"Payment rejected for {user.username}"}


@router.get("/admin/pending-payments")
def pending_payments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")
    users = db.query(User).filter(User.subscription_status == "pending_review").all()
    result = []
    for u in users:
        fee = u.subscription_fee_owed or SUBSCRIPTION_FEE_USD
        result.append({
            "user_id": u.id,
            "username": u.username,
            "email": u.email,
            "subscription_status": u.subscription_status,
            "subscription_fee": fee,
            "total_owed": fee,
            "payment_screenshot": bool(u.payment_screenshot),
            "joined": u.created_at.isoformat() if u.created_at else None,
        })
    return result


@router.get("/admin/users")
def get_all_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")
    users = db.query(User).all()
    result = []
    for u in users:
        sub = refresh_subscription_status(u)
        result.append({
            "user_id": u.id,
            "username": u.username,
            "email": u.email,
            "bot_active": False,
            "balance": 0,
            "equity": 0,
            "payment_status": u.payment_status,
            "amount_owed": (
                (u.subscription_fee_owed or SUBSCRIPTION_FEE_USD)
                if sub not in ("active", "trial")
                else 0
            ),
            "subscription_status": sub,
            "subscription_expires_at": u.subscription_expires_at.isoformat()
            if u.subscription_expires_at
            else None,
            "payment_screenshot": bool(u.payment_screenshot),
            "subscription_fee": u.subscription_fee_owed or SUBSCRIPTION_FEE_USD,
            "referral_code": u.referral_code,
            "referred_by": u.referred_by,
            "referral_balance": round(u.referral_balance or 0, 2),
            "referral_wallet": u.referral_wallet,
            "joined": u.created_at.isoformat() if u.created_at else None,
        })
    db.commit()
    return result


@router.get("/admin/stats")
def get_admin_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")
    total_users = db.query(User).count()
    pending_pay = db.query(User).filter(User.subscription_status == "pending_review").count()
    overdue_pay = db.query(User).filter(User.subscription_status == "expired").count()
    active_subs = db.query(User).filter(User.subscription_status.in_(["active", "trial"])).count()
    trial_users = db.query(User).filter(User.subscription_status == "trial").count()
    return {
        "total_users": total_users,
        "active_bots": 0,
        "active_subscriptions": active_subs,
        "trial_users": trial_users,
        "subscription_fee": SUBSCRIPTION_FEE_USD,
        "subscription_days": SUBSCRIPTION_DAYS,
        "trial_hours": FREE_TRIAL_HOURS,
        "referral_commission": REFERRAL_COMMISSION_USD,
        "admin_usdt_bep20": ADMIN_USDT_BEP20,
        "pending_payment": pending_pay,
        "overdue_payment": overdue_pay,
        "total_trades": 0,
        "open_trades": 0,
        "closed_trades": 0,
        "gross_profit": 0,
        "admin_earned": round(active_subs * SUBSCRIPTION_FEE_USD, 2),
        "pending_amount": round(pending_pay * SUBSCRIPTION_FEE_USD, 2),
        "pending_referral_withdraws": db.query(ReferralWithdraw).filter(
            ReferralWithdraw.status == "pending"
        ).count(),
    }


@router.post("/admin/toggle-bot/{user_id}")
def toggle_bot(
    user_id: int,
    current_user: User = Depends(get_current_user),
):
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")
    # Signals-only service — no MT5 bot to toggle
    return {"message": "Signals service — MT5 bot yahan nahi hai", "bot_active": False}


@router.post("/admin/delete-user/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if is_master_user(user):
        raise HTTPException(400, "Admin ko delete nahi kar sakte")
    name = user.username
    db.query(ReferralWithdraw).filter(ReferralWithdraw.user_id == user_id).delete()
    db.delete(user)
    db.commit()
    return {"message": f"{name} deleted"}


@router.post("/referral/wallet")
def set_referral_wallet(
    body: ReferralWalletIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == current_user.id).first()
    user.referral_wallet = _normalize_bep20(body.wallet_address)
    db.commit()
    return {"message": "Wallet saved", "referral_wallet": user.referral_wallet}


@router.post("/referral/withdraw")
def request_referral_withdraw(
    body: ReferralWithdrawIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if is_master_user(current_user):
        raise HTTPException(400, "Admin referral withdraw nahi karta")
    user = db.query(User).filter(User.id == current_user.id).first()
    bal = round(user.referral_balance or 0, 2)
    amount = round(float(body.amount or 0), 2)
    if amount <= 0:
        raise HTTPException(400, "Amount 0 se zyada hona chahiye")
    if amount > bal:
        raise HTTPException(400, f"Balance sirf ${bal:.2f} hai")
    wallet = _normalize_bep20(body.wallet_address or user.referral_wallet or "")
    pending = db.query(ReferralWithdraw).filter(
        ReferralWithdraw.user_id == user.id,
        ReferralWithdraw.status == "pending",
    ).first()
    if pending:
        raise HTTPException(400, "Pehle wali withdraw request pending hai — admin approve ka wait")

    user.referral_balance = round(bal - amount, 2)
    user.referral_wallet = wallet
    req = ReferralWithdraw(
        user_id=user.id,
        amount=amount,
        wallet_address=wallet,
        status="pending",
    )
    db.add(req)
    db.commit()
    return {"message": "Withdraw request submitted", "amount": amount, "wallet": wallet}


@router.get("/referral/withdraws")
def my_referral_withdraws(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ReferralWithdraw)
        .filter(ReferralWithdraw.user_id == current_user.id)
        .order_by(ReferralWithdraw.id.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "amount": r.amount,
            "wallet_address": r.wallet_address,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/admin/referral-withdraws")
def admin_referral_withdraws(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")
    rows = db.query(ReferralWithdraw).order_by(ReferralWithdraw.id.desc()).all()
    out = []
    for r in rows:
        u = db.query(User).filter(User.id == r.user_id).first()
        out.append({
            "id": r.id,
            "user_id": r.user_id,
            "username": u.username if u else "?",
            "email": u.email if u else "",
            "amount": r.amount,
            "wallet_address": r.wallet_address,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return out


@router.post("/admin/referral-withdraws/{req_id}/approve")
def approve_referral_withdraw(
    req_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")
    req = db.query(ReferralWithdraw).filter(ReferralWithdraw.id == req_id).first()
    if not req:
        raise HTTPException(404, "Request not found")
    if req.status != "pending":
        raise HTTPException(400, f"Already {req.status}")
    req.status = "approved"
    req.resolved_at = datetime.utcnow()
    db.commit()
    return {"message": "Approved", "id": req.id}


@router.post("/admin/referral-withdraws/{req_id}/reject")
def reject_referral_withdraw(
    req_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_master_user(current_user):
        raise HTTPException(403, "Admin only")
    req = db.query(ReferralWithdraw).filter(ReferralWithdraw.id == req_id).first()
    if not req:
        raise HTTPException(404, "Request not found")
    if req.status != "pending":
        raise HTTPException(400, f"Already {req.status}")
    user = db.query(User).filter(User.id == req.user_id).first()
    if user:
        user.referral_balance = round((user.referral_balance or 0) + req.amount, 2)
    req.status = "rejected"
    req.resolved_at = datetime.utcnow()
    db.commit()
    return {"message": "Rejected — balance restored", "id": req.id}
