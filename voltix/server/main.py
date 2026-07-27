"""Voltix FastAPI backend — SQLite persistence + SPA static hosting."""

from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

import db

# ── Constants (match frontend src/lib/constants.js) ───────────────────────────

ADMIN_EMAIL = "admin@voltix.exchange"
ADMIN_PASSWORD = "VoltixAdmin@2026"
SIGNUP_VOLT = 1000
REF_VOLT = 200
DEFAULT_REF_PCT = 5
WITHDRAW_LOCK_DAYS = 10
WITHDRAW_LOCK_MS = WITHDRAW_LOCK_DAYS * 24 * 60 * 60 * 1000
WITHDRAW_LOCK_ENABLED = False  # don't block withdraws

PLANS = [
    {"id": 1, "name": "Plan 1", "tag": "Starter", "min": 10, "max": 100, "yieldMin": 6, "yieldMax": 8, "color": "#3ecf8e"},
    {"id": 2, "name": "Plan 2", "tag": "Growth", "min": 100, "max": 500, "yieldMin": 7, "yieldMax": 12, "color": "#c9a227"},
    {"id": 3, "name": "Plan 3", "tag": "Pro", "min": 500, "max": 2000, "yieldMin": 10, "yieldMax": 15, "color": "#e0b93c"},
    {"id": 4, "name": "Plan 4", "tag": "Prime", "min": 2000, "max": 10000, "yieldMin": 12, "yieldMax": 20, "color": "#f5d76e"},
]

RANKS = [
    {"id": "scout", "name": "Scout", "minTeam": 0, "refPct": 5, "yieldBonus": 0, "tagline": "Start building your Voltix team"},
    {"id": "bronze", "name": "Bronze", "minTeam": 500, "refPct": 6, "yieldBonus": 0.15, "tagline": "First promoters · +0.15% stake bonus"},
    {"id": "silver", "name": "Silver", "minTeam": 2000, "refPct": 7, "yieldBonus": 0.3, "tagline": "Growing network · +0.30% stake bonus"},
    {"id": "gold", "name": "Gold", "minTeam": 5000, "refPct": 8, "yieldBonus": 0.5, "tagline": "Strong leaders · +0.50% stake bonus"},
    {"id": "platinum", "name": "Platinum", "minTeam": 10000, "refPct": 9, "yieldBonus": 0.75, "tagline": "Elite builders · +0.75% stake bonus"},
    {"id": "diamond", "name": "Diamond", "minTeam": 20000, "refPct": 11, "yieldBonus": 1, "tagline": "Top earners · +1.00% stake bonus"},
    {"id": "crown", "name": "Crown", "minTeam": 40000, "refPct": 13, "yieldBonus": 1.25, "tagline": "Empire tier · +1.25% stake bonus"},
    {"id": "legend", "name": "Legend", "minTeam": 100000, "refPct": 15, "yieldBonus": 2, "tagline": "Voltix legends · +2.00% stake bonus"},
]

GIFTS = [
    {
        "id": "tier10k",
        "minTeam": 10000,
        "title": "$10,000 team milestone",
        "giftLabel": "Google Pixel 7",
        "cashUsdt": 350,
        "detail": "Choose Google Pixel 7 or 350 USDT cash — unlock at $10,000 team deposits",
    },
    {
        "id": "tier20k",
        "minTeam": 20000,
        "title": "$20,000 team milestone",
        "giftLabel": "Google Pixel 11",
        "cashUsdt": 700,
        "detail": "Choose Google Pixel 11 or 700 USDT cash — unlock at $20,000 team deposits",
    },
    {
        "id": "tier40k",
        "minTeam": 40000,
        "title": "$40,000 team milestone",
        "giftLabel": "iPhone 17 Pro",
        "cashUsdt": 1500,
        "detail": "Choose iPhone 17 Pro or 1,500 USDT cash — unlock at $40,000 team deposits",
    },
]

WITHDRAW_NETWORKS = [
    {"id": "bnb", "label": "BNB (BEP20)", "placeholder": "0x… BEP20 address"},
    {"id": "trc20", "label": "TRC20 (Tron)", "placeholder": "T… TRC20 address"},
    {"id": "arb", "label": "Arbitrum", "placeholder": "0x… Arbitrum address"},
]

DIST_DIR = Path(__file__).resolve().parent.parent / "dist"
VERSION = "1.0.0"

# ── Helpers ───────────────────────────────────────────────────────────────────


def now_ms() -> int:
    return int(time.time() * 1000)


def uid(prefix: str = "u") -> str:
    return f"{prefix}_{int(time.time() * 1000):x}_{secrets.token_hex(3)}"


def adm_id() -> str:
    return uid("adm")


def tx_id() -> str:
    return uid("tx")


def is_admin_email(email: str) -> bool:
    return str(email or "").strip().lower() == ADMIN_EMAIL


def get_plan(plan_id: Any) -> dict | None:
    try:
        pid = int(plan_id)
    except (TypeError, ValueError):
        return None
    for p in PLANS:
        if p["id"] == pid:
            return p
    return None


def plan_for_amount(amount: Any) -> dict | None:
    try:
        n = float(amount)
    except (TypeError, ValueError):
        return None
    for p in reversed(PLANS):
        if p["min"] <= n <= p["max"]:
            return p
    return None


def get_withdraw_network(network_id: str) -> dict | None:
    for n in WITHDRAW_NETWORKS:
        if n["id"] == network_id:
            return n
    return None


def public_user(user: dict | None) -> dict | None:
    if not user:
        return None
    out = {k: v for k, v in user.items() if k != "password"}
    return out


def personal_deposited(user: dict | None) -> float:
    if not user:
        return 0.0
    td = Number(user.get("totalDeposited"))
    if td > 0:
        return td
    total = 0.0
    for h in user.get("history") or []:
        if h.get("type") == "DEPOSIT":
            total += Number(h.get("amount"))
    return total


def Number(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def collect_downline(email: str, users: list[dict], max_depth: int = 8) -> list[dict]:
    root = str(email or "").lower()
    by_referrer: dict[str, list[dict]] = {}
    for u in users or []:
        ref = str(u.get("referrerEmail") or "").lower()
        if not ref:
            continue
        by_referrer.setdefault(ref, []).append(u)
    members: list[dict] = []
    frontier = [root]
    seen = {root}
    for depth in range(1, max_depth + 1):
        nxt: list[str] = []
        for e in frontier:
            for u in by_referrer.get(e) or []:
                m = str(u.get("email") or "").lower()
                if m in seen:
                    continue
                seen.add(m)
                members.append({"user": u, "depth": depth})
                nxt.append(m)
        frontier = nxt
        if not frontier:
            break
    return members


def team_deposit_total(email: str, users: list[dict]) -> float:
    total = 0.0
    for m in collect_downline(email, users):
        total += personal_deposited(m["user"])
    return round(total, 2)


def rank_for_team_deposits(team_deposits: float) -> dict:
    n = Number(team_deposits)
    rank = RANKS[0]
    for r in RANKS:
        if n >= r["minTeam"]:
            rank = r
    return rank


def next_rank(rank: dict) -> dict | None:
    ids = [r["id"] for r in RANKS]
    try:
        i = ids.index(rank["id"])
    except ValueError:
        return None
    if i >= len(RANKS) - 1:
        return None
    return RANKS[i + 1]


def rank_for_user(email: str, users: list[dict]) -> dict:
    return rank_for_team_deposits(team_deposit_total(email, users))


def build_team_stats(email: str) -> dict:
    users = db.list_users()
    f = str(email or "").lower()
    downline = collect_downline(f, users)
    direct = [m for m in downline if m["depth"] == 1]
    team_deposits = 0.0
    for m in downline:
        team_deposits += personal_deposited(m["user"])
    team_deposits = round(team_deposits, 2)
    rank = rank_for_team_deposits(team_deposits)
    upcoming = next_rank(rank)
    progress_to_next = (
        min(100, round((team_deposits / upcoming["minTeam"]) * 100)) if upcoming else 100
    )
    need_for_next = max(0, upcoming["minTeam"] - team_deposits) if upcoming else 0
    gifts = []
    for g in GIFTS:
        gifts.append(
            {
                **g,
                "unlocked": team_deposits >= g["minTeam"],
                "progress": min(100, round((team_deposits / g["minTeam"]) * 100)),
                "remaining": max(0, g["minTeam"] - team_deposits),
            }
        )
    members = []
    for m in downline:
        u = m["user"]
        active_staked = sum(
            Number(s.get("amount"))
            for s in (u.get("staked") or [])
            if str(s.get("status") or "").upper() == "ACTIVE"
        )
        members.append(
            {
                "name": u.get("name"),
                "email": u.get("email"),
                "depth": m["depth"],
                "deposited": personal_deposited(u),
                "staked": active_staked,
            }
        )
    return {
        "teamDeposits": team_deposits,
        "teamSize": len(downline),
        "directCount": len(direct),
        "rank": rank,
        "upcoming": upcoming,
        "progressToNext": progress_to_next,
        "needForNext": need_for_next,
        "gifts": gifts,
        "members": members,
        "refPct": rank["refPct"],
        "yieldBonus": rank["yieldBonus"],
    }


def err(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def bearer_token(authorization: Optional[str] = Header(None)) -> str:
    if not authorization:
        raise err(401, "Authorization required")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise err(401, "Invalid Authorization header")
    return parts[1]


def require_user(token: str = Depends(bearer_token)) -> dict:
    session = db.get_session(token)
    if not session or session["kind"] != "user":
        raise err(401, "Invalid or expired session")
    user = db.get_user(session["email"])
    if not user:
        raise err(401, "Account not found")
    return {"token": token, "user": user, "session": session}


def require_admin(token: str = Depends(bearer_token)) -> dict:
    session = db.get_session(token)
    if not session or session["kind"] != "admin":
        raise err(401, "Admin authorization required")
    return {"token": token, "session": session}


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Voltix", version=VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    db.init_db()


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": detail, "error": detail})


# ── Request models ────────────────────────────────────────────────────────────


class RegisterBody(BaseModel):
    name: Optional[str] = None
    email: str
    password: str
    referralCode: Optional[str] = None


class LoginBody(BaseModel):
    email: str
    password: str


class StakeBody(BaseModel):
    amount: float
    planId: Optional[int] = None


class DepositBody(BaseModel):
    amount: float
    networkId: str
    txHash: Optional[str] = None


class WithdrawBody(BaseModel):
    amount: float
    networkId: str
    address: str


class GiftClaimBody(BaseModel):
    giftId: str
    choice: str


class AdminLoginBody(BaseModel):
    email: str
    password: str


class RejectBody(BaseModel):
    reason: Optional[str] = ""


class ProfitBody(BaseModel):
    planId: int
    percent: float
    note: Optional[str] = ""


# ── Health ────────────────────────────────────────────────────────────────────


@app.get("/api/health")
def health():
    return {"ok": True, "version": VERSION}


# ── Auth ──────────────────────────────────────────────────────────────────────


@app.post("/api/auth/register")
def auth_register(body: RegisterBody):
    e = str(body.email or "").strip().lower()
    password = str(body.password or "")
    if not e or not password:
        raise err(400, "Email and password required")
    if is_admin_email(e):
        raise err(400, "This email is reserved for admin — use /admin/login")
    if db.get_user(e):
        raise err(400, "Account already exists — please login")

    referrer_email = ""
    ref = str(body.referralCode or "").strip().upper()
    if ref:
        referrer = db.find_user_by_referral_code(ref)
        if referrer:
            referrer_email = referrer["email"]
            referrer["voltBalance"] = Number(referrer.get("voltBalance")) + REF_VOLT
            referrer["referralCount"] = int(Number(referrer.get("referralCount"))) + 1
            referrer["history"] = [
                {
                    "id": uid(),
                    "type": "REF_VOLT",
                    "amount": REF_VOLT,
                    "note": f"Referral bonus for {e}",
                    "at": now_ms(),
                },
                *(referrer.get("history") or []),
            ]
            db.upsert_user(referrer)

    code = e[:4].upper() + secrets.token_hex(2).upper()
    user = {
        "id": uid(),
        "name": (str(body.name or "Investor").strip() or "Investor"),
        "email": e,
        "password": password,
        "referralCode": code,
        "referrerEmail": referrer_email,
        "usdtBalance": 0,
        "voltBalance": SIGNUP_VOLT,
        "totalDeposited": 0,
        "staked": [],
        "lastDepositAt": None,
        "lastWithdrawAt": None,
        "withdrawUnlockAt": None,
        "claimedGifts": [],
        "history": [
            {
                "id": uid(),
                "type": "SIGNUP_VOLT",
                "amount": SIGNUP_VOLT,
                "note": "Welcome Volt allocation",
                "at": now_ms(),
            }
        ],
        "createdAt": now_ms(),
    }
    db.upsert_user(user)
    token = secrets.token_urlsafe(32)
    db.create_session(token, e, "user", now_ms())
    return {"token": token, "user": public_user(user)}


@app.post("/api/auth/login")
def auth_login(body: LoginBody):
    e = str(body.email or "").strip().lower()
    if is_admin_email(e):
        raise err(400, "Admin account — open /admin/login instead")
    user = db.get_user(e)
    if not user:
        raise err(404, "Account not found")
    if str(user.get("password")) != str(body.password):
        raise err(401, "Wrong password")
    token = secrets.token_urlsafe(32)
    db.create_session(token, e, "user", now_ms())
    return {"token": token, "user": public_user(user)}


@app.post("/api/auth/logout")
def auth_logout(auth: dict = Depends(require_user)):
    db.delete_session(auth["token"])
    return {"ok": True}


@app.get("/api/me")
def me(auth: dict = Depends(require_user)):
    return public_user(auth["user"])


@app.get("/api/team")
def team(auth: dict = Depends(require_user)):
    return build_team_stats(auth["user"]["email"])


@app.get("/api/my/deposits")
def my_deposits(auth: dict = Depends(require_user)):
    email = auth["user"]["email"]
    rows = [r for r in db.list_deposits() if r.get("userEmail") == email]
    return rows[:40]


@app.get("/api/my/gifts")
def my_gifts(auth: dict = Depends(require_user)):
    email = auth["user"]["email"]
    rows = [r for r in db.list_gifts() if r.get("userEmail") == email]
    return rows[:40]


# ── User actions ──────────────────────────────────────────────────────────────


@app.post("/api/stake")
def stake(body: StakeBody, auth: dict = Depends(require_user)):
    user = auth["user"]
    amt = Number(body.amount)
    bal = Number(user.get("usdtBalance"))
    plan = get_plan(body.planId) if body.planId is not None else plan_for_amount(amt)
    if not plan:
        raise err(400, "Select a valid plan")
    if amt < plan["min"] or amt > plan["max"]:
        raise err(400, f"{plan['name']} accepts ${plan['min']}–${plan['max']} only")
    if amt > bal:
        raise err(400, "Deposit USDT first — insufficient balance")
    stake_row = {
        "id": tx_id(),
        "planId": plan["id"],
        "planName": plan["name"],
        "amount": amt,
        "yieldMin": plan["yieldMin"],
        "yieldMax": plan["yieldMax"],
        "startedAt": now_ms(),
        "status": "ACTIVE",
    }
    user["usdtBalance"] = round(bal - amt, 4)
    user["staked"] = [stake_row, *(user.get("staked") or [])]
    user["history"] = [
        {
            "id": tx_id(),
            "type": "STAKE",
            "amount": amt,
            "note": f"{plan['name']} · {plan['yieldMin']}–{plan['yieldMax']}% / mo",
            "at": now_ms(),
        },
        *(user.get("history") or []),
    ]
    db.upsert_user(user)
    return {"user": public_user(user), "stake": stake_row}


@app.post("/api/deposit")
def deposit(body: DepositBody, auth: dict = Depends(require_user)):
    user = auth["user"]
    network = get_withdraw_network(body.networkId)
    if not network:
        raise err(400, "Select the network you sent on")
    amt = Number(body.amount)
    if amt < 10:
        raise err(400, "Minimum deposit is 10 USDT")
    email = user["email"]
    pending = db.list_deposits()
    if any(
        d.get("userEmail") == email and d.get("status") == "PENDING" and Number(d.get("amount")) == amt
        for d in pending
    ):
        raise err(400, "Similar pending deposit already waiting for admin")
    row = {
        "id": adm_id(),
        "userEmail": email,
        "userName": user.get("name") or "",
        "amount": amt,
        "networkId": network["id"],
        "networkLabel": network["label"],
        "txHash": str(body.txHash or "").strip(),
        "status": "PENDING",
        "at": now_ms(),
        "reviewedAt": None,
    }
    db.upsert_deposit(row)
    user["history"] = [
        {
            "id": adm_id(),
            "type": "DEPOSIT_PENDING",
            "amount": amt,
            "note": f"Deposit request {network['label']} · waiting admin approval",
            "at": now_ms(),
            "requestId": row["id"],
        },
        *(user.get("history") or []),
    ]
    db.upsert_user(user)
    return {"request": row, "user": public_user(user)}


@app.post("/api/withdraw")
def withdraw(body: WithdrawBody, auth: dict = Depends(require_user)):
    user = auth["user"]
    amt = Number(body.amount)
    bal = Number(user.get("usdtBalance"))
    network = get_withdraw_network(body.networkId)
    addr = str(body.address or "").strip()
    if amt <= 0:
        raise err(400, "Enter a valid amount")
    if amt > bal:
        raise err(400, "Insufficient USDT balance")
    if not network:
        raise err(400, "Select a withdraw network")
    if not addr or len(addr) < 8:
        raise err(400, "Enter your payout wallet address")
    if WITHDRAW_LOCK_ENABLED:
        unlock = user.get("withdrawUnlockAt")
        if unlock and now_ms() < Number(unlock):
            raise err(400, "Withdraw lock is still active")
    now = now_ms()
    row = {
        "id": adm_id(),
        "userEmail": user["email"],
        "userName": user.get("name") or "",
        "amount": amt,
        "networkId": network["id"],
        "networkLabel": network["label"],
        "address": addr,
        "status": "PENDING",
        "at": now,
        "paidAt": None,
    }
    db.upsert_withdraw(row)
    user["usdtBalance"] = round(bal - amt, 4)
    user["lastWithdrawAt"] = now
    user["lastWithdrawAddress"] = addr
    user["lastWithdrawNetworkId"] = network["id"]
    user["history"] = [
        {
            "id": tx_id(),
            "type": "WITHDRAW",
            "amount": amt,
            "note": f"Withdraw {network['label']} · {addr[:6]}…{addr[-4:]} · pending admin",
            "at": now,
            "networkId": network["id"],
            "address": addr,
            "requestId": row["id"],
        },
        *(user.get("history") or []),
    ]
    db.upsert_user(user)
    return {"request": row, "user": public_user(user)}


@app.post("/api/gift/claim")
def gift_claim(body: GiftClaimBody, auth: dict = Depends(require_user)):
    user = auth["user"]
    gift = next((g for g in GIFTS if g["id"] == body.giftId), None)
    if not gift:
        raise err(400, "Invalid milestone")
    c = str(body.choice or "").upper()
    if c not in ("USDT", "GIFT"):
        raise err(400, "Choose USDT cash or physical gift")
    claimed = list(user.get("claimedGifts") or [])
    if body.giftId in claimed:
        raise err(400, "You already claimed this milestone")
    team = build_team_stats(user["email"])
    team_deposits = Number(team["teamDeposits"])
    if team_deposits < gift["minTeam"]:
        raise err(400, f"Need ${gift['minTeam']:,} team deposits to claim")
    for g in db.list_gifts():
        if (
            g.get("userEmail") == user["email"]
            and g.get("giftId") == body.giftId
            and g.get("status") == "PENDING"
        ):
            raise err(400, "Claim already pending — wait for admin")
    choice_label = f"{gift['cashUsdt']} USDT cash" if c == "USDT" else gift["giftLabel"]
    user["claimedGifts"] = [*claimed, body.giftId]
    user["history"] = [
        {
            "id": adm_id(),
            "type": "GIFT_CLAIM",
            "amount": gift["cashUsdt"] if c == "USDT" else gift["minTeam"],
            "note": f"Claimed {choice_label} · pending admin",
            "at": now_ms(),
            "giftId": body.giftId,
            "choice": c,
        },
        *(user.get("history") or []),
    ]
    db.upsert_user(user)
    row = {
        "id": adm_id(),
        "userEmail": user["email"],
        "userName": user.get("name") or "",
        "giftId": gift["id"],
        "giftTitle": gift["title"],
        "giftLabel": gift["giftLabel"],
        "cashUsdt": gift["cashUsdt"],
        "giftDetail": gift["detail"],
        "choice": c,
        "choiceLabel": choice_label,
        "teamDeposits": team_deposits,
        "rankName": (team.get("rank") or {}).get("name") or "",
        "status": "PENDING",
        "at": now_ms(),
        "fulfilledAt": None,
    }
    db.upsert_gift(row)
    return {"claim": row, "user": public_user(user)}


# ── Admin ─────────────────────────────────────────────────────────────────────


@app.post("/api/admin/login")
def admin_login(body: AdminLoginBody):
    email = str(body.email or "").strip().lower()
    if email != ADMIN_EMAIL or str(body.password) != ADMIN_PASSWORD:
        raise err(401, "Invalid admin credentials")
    # purge any accidental admin user row
    if db.get_user(ADMIN_EMAIL):
        conn = db.get_conn()
        try:
            conn.execute("DELETE FROM users WHERE email = ?", (ADMIN_EMAIL,))
            conn.commit()
        finally:
            conn.close()
    token = secrets.token_urlsafe(32)
    db.create_session(token, ADMIN_EMAIL, "admin", now_ms())
    return {"token": token}


@app.post("/api/admin/logout")
def admin_logout(auth: dict = Depends(require_admin)):
    db.delete_session(auth["token"])
    return {"ok": True}


def live_stakes_by_plan() -> list[dict]:
    users = [u for u in db.list_users() if not is_admin_email(u.get("email"))]
    out = []
    for plan in PLANS:
        stakes = 0
        amount = 0.0
        user_count = 0
        for u in users:
            active = [
                s
                for s in (u.get("staked") or [])
                if int(Number(s.get("planId"))) == plan["id"]
                and str(s.get("status") or "").upper() == "ACTIVE"
            ]
            if active:
                user_count += 1
                for s in active:
                    stakes += 1
                    amount += Number(s.get("amount"))
        out.append(
            {
                "planId": plan["id"],
                "planName": plan["name"],
                "tag": plan["tag"],
                "stakes": stakes,
                "amount": round(amount, 2),
                "users": user_count,
            }
        )
    return out


def platform_stats() -> dict:
    users = [u for u in db.list_users() if not is_admin_email(u.get("email"))]
    usdt = 0.0
    volt = 0.0
    staked = 0.0
    active_stakes = 0
    for u in users:
        usdt += Number(u.get("usdtBalance"))
        volt += Number(u.get("voltBalance"))
        for s in u.get("staked") or []:
            if str(s.get("status") or "").upper() == "ACTIVE":
                staked += Number(s.get("amount"))
                active_stakes += 1
    return {
        "users": len(users),
        "usdt": round(usdt, 2),
        "volt": round(volt, 0),
        "zr": round(volt, 0),
        "staked": round(staked, 2),
        "activeStakes": active_stakes,
    }


@app.get("/api/admin/overview")
def admin_overview(_auth: dict = Depends(require_admin)):
    deposits = db.list_deposits()
    withdraws = db.list_withdraws()
    gifts = db.list_gifts()
    return {
        "stats": platform_stats(),
        "liveStakes": live_stakes_by_plan(),
        "pendingDeposits": sum(1 for d in deposits if d.get("status") == "PENDING"),
        "pendingWithdraws": sum(1 for w in withdraws if w.get("status") == "PENDING"),
        "pendingGifts": sum(1 for g in gifts if g.get("status") == "PENDING"),
    }


@app.get("/api/admin/users")
def admin_users(_auth: dict = Depends(require_admin)):
    users = [u for u in db.list_users() if not is_admin_email(u.get("email"))]
    out = []
    for u in users:
        personal = personal_deposited(u)
        team_dep = team_deposit_total(u["email"], users)
        rank = rank_for_user(u["email"], users)
        active = [s for s in (u.get("staked") or []) if str(s.get("status") or "").upper() == "ACTIVE"]
        staked_total = sum(Number(s.get("amount")) for s in active)
        row = public_user(u) or {}
        row.update(
            {
                "personalDeposit": personal,
                "teamDeposit": team_dep,
                "rankName": rank["name"],
                "rankId": rank["id"],
                "refPct": rank["refPct"],
                "stakedTotal": staked_total,
                "activeStakeCount": len(active),
            }
        )
        out.append(row)
    return out


@app.get("/api/admin/deposits")
def admin_deposits(_auth: dict = Depends(require_admin)):
    return db.list_deposits()


@app.post("/api/admin/deposits/{deposit_id}/approve")
def admin_approve_deposit(deposit_id: str, _auth: dict = Depends(require_admin)):
    row = db.get_deposit(deposit_id)
    if not row:
        raise err(404, "Deposit request not found")
    if row.get("status") != "PENDING":
        raise err(400, "Request already reviewed")
    user = db.get_user(row["userEmail"])
    if not user:
        raise err(404, "User not found")
    amount = Number(row["amount"])
    now = now_ms()
    user["usdtBalance"] = round(Number(user.get("usdtBalance")) + amount, 4)
    user["totalDeposited"] = round(personal_deposited(user) + amount, 2)
    user["lastDepositAt"] = now
    if not user.get("withdrawUnlockAt"):
        user["withdrawUnlockAt"] = now + WITHDRAW_LOCK_MS
    tx_hash = row.get("txHash") or ""
    note_extra = f" · {tx_hash[:10]}…" if tx_hash else ""
    user["history"] = [
        {
            "id": adm_id(),
            "type": "DEPOSIT",
            "amount": amount,
            "note": f"Approved deposit · {row.get('networkLabel')}{note_extra}",
            "at": now,
            "requestId": row["id"],
        },
        *(user.get("history") or []),
    ]
    db.upsert_user(user)

    if user.get("referrerEmail"):
        ref = db.get_user(str(user["referrerEmail"]).lower())
        if ref:
            users = db.list_users()
            rank = rank_for_user(ref["email"], users)
            pct = Number(rank.get("refPct", DEFAULT_REF_PCT))
            commission = round((amount * pct) / 100, 2)
            ref["usdtBalance"] = round(Number(ref.get("usdtBalance")) + commission, 4)
            ref["history"] = [
                {
                    "id": adm_id(),
                    "type": "REF_DEPOSIT",
                    "amount": commission,
                    "note": f"{pct}% ({rank['name']}) of approved {amount} USDT from {user['email']}",
                    "at": now,
                },
                *(ref.get("history") or []),
            ]
            db.upsert_user(ref)

    row = {**row, "status": "APPROVED", "reviewedAt": now}
    db.upsert_deposit(row)
    return row


@app.post("/api/admin/deposits/{deposit_id}/reject")
def admin_reject_deposit(
    deposit_id: str,
    body: RejectBody | None = None,
    _auth: dict = Depends(require_admin),
):
    body = body or RejectBody()
    row = db.get_deposit(deposit_id)
    if not row:
        raise err(404, "Deposit request not found")
    if row.get("status") != "PENDING":
        raise err(400, "Request already reviewed")
    now = now_ms()
    reason = str(body.reason or "")
    row = {**row, "status": "REJECTED", "reviewedAt": now, "rejectReason": reason}
    db.upsert_deposit(row)
    user = db.get_user(row["userEmail"])
    if user:
        user["history"] = [
            {
                "id": adm_id(),
                "type": "DEPOSIT_REJECTED",
                "amount": row["amount"],
                "note": reason or "Deposit request rejected by admin",
                "at": now,
                "requestId": row["id"],
            },
            *(user.get("history") or []),
        ]
        db.upsert_user(user)
    return row


@app.get("/api/admin/withdraws")
def admin_withdraws(_auth: dict = Depends(require_admin)):
    return db.list_withdraws()


@app.post("/api/admin/withdraws/{withdraw_id}/paid")
def admin_withdraw_paid(withdraw_id: str, _auth: dict = Depends(require_admin)):
    row = db.get_withdraw(withdraw_id)
    if not row:
        raise err(404, "Request not found")
    if row.get("status") != "PENDING":
        raise err(400, "Request already reviewed")
    row = {**row, "status": "PAID", "paidAt": now_ms()}
    db.upsert_withdraw(row)
    return row


@app.post("/api/admin/withdraws/{withdraw_id}/reject")
def admin_withdraw_reject(
    withdraw_id: str,
    body: RejectBody | None = None,
    _auth: dict = Depends(require_admin),
):
    body = body or RejectBody()
    row = db.get_withdraw(withdraw_id)
    if not row:
        raise err(404, "Request not found")
    if row.get("status") != "PENDING":
        raise err(400, "Request already reviewed")
    now = now_ms()
    reason = str(body.reason or "")
    # restore balance
    user = db.get_user(row["userEmail"])
    if user:
        amt = Number(row.get("amount"))
        user["usdtBalance"] = round(Number(user.get("usdtBalance")) + amt, 4)
        user["history"] = [
            {
                "id": adm_id(),
                "type": "WITHDRAW_REJECTED",
                "amount": amt,
                "note": reason or "Withdraw request rejected — balance restored",
                "at": now,
                "requestId": row["id"],
            },
            *(user.get("history") or []),
        ]
        db.upsert_user(user)
    row = {**row, "status": "REJECTED", "rejectReason": reason, "rejectedAt": now}
    db.upsert_withdraw(row)
    return row


@app.get("/api/admin/gifts")
def admin_gifts(_auth: dict = Depends(require_admin)):
    return db.list_gifts()


@app.post("/api/admin/gifts/{gift_id}/fulfill")
def admin_gift_fulfill(gift_id: str, _auth: dict = Depends(require_admin)):
    row = db.get_gift(gift_id)
    if not row:
        raise err(404, "Claim not found")
    if row.get("status") != "PENDING":
        raise err(400, "Claim already reviewed")
    now = now_ms()
    row = {**row, "status": "FULFILLED", "fulfilledAt": now}
    db.upsert_gift(row)
    if row.get("choice") == "USDT":
        user = db.get_user(row["userEmail"])
        if user:
            cash = Number(row.get("cashUsdt"))
            user["usdtBalance"] = round(Number(user.get("usdtBalance")) + cash, 4)
            user["history"] = [
                {
                    "id": adm_id(),
                    "type": "GIFT_USDT",
                    "amount": cash,
                    "note": f"Milestone cash reward · {row.get('giftTitle')}",
                    "at": now,
                    "giftId": row.get("giftId"),
                },
                *(user.get("history") or []),
            ]
            db.upsert_user(user)
    return row


@app.post("/api/admin/gifts/{gift_id}/reject")
def admin_gift_reject(
    gift_id: str,
    body: RejectBody | None = None,
    _auth: dict = Depends(require_admin),
):
    body = body or RejectBody()
    row = db.get_gift(gift_id)
    if not row:
        raise err(404, "Claim not found")
    if row.get("status") != "PENDING":
        raise err(400, "Claim already reviewed")
    now = now_ms()
    reason = str(body.reason or "")
    row = {**row, "status": "REJECTED", "rejectReason": reason, "rejectedAt": now}
    db.upsert_gift(row)
    user = db.get_user(row["userEmail"])
    if user:
        user["claimedGifts"] = [g for g in (user.get("claimedGifts") or []) if g != row.get("giftId")]
        user["history"] = [
            {
                "id": adm_id(),
                "type": "GIFT_REJECTED",
                "amount": 0,
                "note": reason or "Gift claim rejected by admin",
                "at": now,
                "giftId": row.get("giftId"),
            },
            *(user.get("history") or []),
        ]
        db.upsert_user(user)
    return row


@app.post("/api/admin/profit")
def admin_profit(body: ProfitBody, _auth: dict = Depends(require_admin)):
    plan = get_plan(body.planId)
    if not plan:
        raise err(400, "Invalid plan")
    pct = Number(body.percent)
    if pct <= 0 or pct > 100:
        raise err(400, "Enter a profit % between 0 and 100")
    users = db.list_users()
    users_hit = 0
    stakes_hit = 0
    total_paid = 0.0
    note = str(body.note or "")
    for user in users:
        active = [
            s
            for s in (user.get("staked") or [])
            if int(Number(s.get("planId"))) == plan["id"]
            and str(s.get("status") or "").upper() == "ACTIVE"
        ]
        if not active:
            continue
        rank = rank_for_user(user["email"], users)
        effective = pct + Number(rank.get("yieldBonus"))
        credit = 0.0
        for stake in active:
            earned = round((Number(stake.get("amount")) * effective) / 100, 4)
            if earned <= 0:
                continue
            credit += earned
            stakes_hit += 1
            stake["earnedProfit"] = round(Number(stake.get("earnedProfit")) + earned, 4)
        if credit <= 0:
            continue
        users_hit += 1
        total_paid += credit
        user["usdtBalance"] = round(Number(user.get("usdtBalance")) + credit, 4)
        user["totalProfit"] = round(Number(user.get("totalProfit")) + credit, 4)
        bonus_note = f" + {rank['name']} bonus {rank['yieldBonus']}%" if rank.get("yieldBonus") else ""
        user["history"] = [
            {
                "id": adm_id(),
                "type": "PLAN_PROFIT",
                "amount": credit,
                "note": note
                or f"{plan['name']} {pct}%{bonus_note} · {time.strftime('%m/%d/%Y')}",
                "at": now_ms(),
                "planId": plan["id"],
            },
            *(user.get("history") or []),
        ]
        db.upsert_user(user)
    if stakes_hit == 0:
        raise err(
            400,
            f"No active stakes on {plan['name']}. Pick the plan users actually staked (see Live stakes below).",
        )
    entry = {
        "id": adm_id(),
        "type": "PLAN_PROFIT",
        "planId": plan["id"],
        "planName": plan["name"],
        "percent": pct,
        "usersHit": users_hit,
        "stakesHit": stakes_hit,
        "totalPaid": round(total_paid, 4),
        "note": note,
        "at": now_ms(),
    }
    db.push_admin_log(entry)
    return entry


@app.get("/api/admin/logs")
def admin_logs(_auth: dict = Depends(require_admin)):
    return db.list_admin_logs()


# ── SPA static files ──────────────────────────────────────────────────────────


class SPAStaticFiles(StaticFiles):
    """Serve dist assets with index.html fallback for client-side routes."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as ex:
            if ex.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


if DIST_DIR.is_dir():
    app.mount("/", SPAStaticFiles(directory=str(DIST_DIR), html=True), name="spa")
