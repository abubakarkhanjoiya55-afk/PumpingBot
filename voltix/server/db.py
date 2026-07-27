"""SQLite persistence for Voltix accounts and admin queues."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DATA_DIR / "voltix.db"


def get_conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                data TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('user', 'admin')),
                created_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS deposit_requests (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS withdraw_requests (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS gift_claims (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_logs (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                at INTEGER NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    return json.loads(raw)


# ── users ────────────────────────────────────────────────────────────────────


def list_users() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT data FROM users ORDER BY email").fetchall()
        return [_loads(r["data"]) for r in rows]
    finally:
        conn.close()


def get_user(email: str) -> dict | None:
    e = str(email or "").strip().lower()
    conn = get_conn()
    try:
        row = conn.execute("SELECT data FROM users WHERE email = ?", (e,)).fetchone()
        return _loads(row["data"]) if row else None
    finally:
        conn.close()


def upsert_user(user: dict) -> dict:
    email = str(user["email"]).strip().lower()
    user["email"] = email
    password = str(user.get("password") or "")
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO users (email, password, data) VALUES (?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET password = excluded.password, data = excluded.data
            """,
            (email, password, _dumps(user)),
        )
        conn.commit()
        return user
    finally:
        conn.close()


def find_user_by_referral_code(code: str) -> dict | None:
    ref = str(code or "").strip().upper()
    if not ref:
        return None
    for u in list_users():
        if str(u.get("referralCode") or "").upper() == ref:
            return u
    return None


# ── sessions ─────────────────────────────────────────────────────────────────


def create_session(token: str, email: str, kind: str, created_at: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO sessions (token, email, kind, created_at) VALUES (?, ?, ?, ?)",
            (token, str(email).strip().lower(), kind, int(created_at)),
        )
        conn.commit()
    finally:
        conn.close()


def get_session(token: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT token, email, kind, created_at FROM sessions WHERE token = ?",
            (token,),
        ).fetchone()
        if not row:
            return None
        return {
            "token": row["token"],
            "email": row["email"],
            "kind": row["kind"],
            "created_at": row["created_at"],
        }
    finally:
        conn.close()


def delete_session(token: str) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


# ── JSON queue tables ─────────────────────────────────────────────────────────


def _list_json_table(table: str, order_key: str = "at") -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(f"SELECT data FROM {table}").fetchall()
        items = [_loads(r["data"]) for r in rows]
        items.sort(key=lambda x: Numberish(x.get(order_key, 0)), reverse=True)
        return items
    finally:
        conn.close()


def Numberish(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _get_json_row(table: str, row_id: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(f"SELECT data FROM {table} WHERE id = ?", (row_id,)).fetchone()
        return _loads(row["data"]) if row else None
    finally:
        conn.close()


def _upsert_json_row(table: str, row_id: str, data: dict) -> dict:
    conn = get_conn()
    try:
        conn.execute(
            f"""
            INSERT INTO {table} (id, data) VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET data = excluded.data
            """,
            (row_id, _dumps(data)),
        )
        conn.commit()
        return data
    finally:
        conn.close()


def list_deposits() -> list[dict]:
    return _list_json_table("deposit_requests")


def get_deposit(row_id: str) -> dict | None:
    return _get_json_row("deposit_requests", row_id)


def upsert_deposit(data: dict) -> dict:
    return _upsert_json_row("deposit_requests", data["id"], data)


def list_withdraws() -> list[dict]:
    return _list_json_table("withdraw_requests")


def get_withdraw(row_id: str) -> dict | None:
    return _get_json_row("withdraw_requests", row_id)


def upsert_withdraw(data: dict) -> dict:
    return _upsert_json_row("withdraw_requests", data["id"], data)


def list_gifts() -> list[dict]:
    return _list_json_table("gift_claims")


def get_gift(row_id: str) -> dict | None:
    return _get_json_row("gift_claims", row_id)


def upsert_gift(data: dict) -> dict:
    return _upsert_json_row("gift_claims", data["id"], data)


def list_admin_logs(limit: int = 200) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT data FROM admin_logs ORDER BY at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_loads(r["data"]) for r in rows]
    finally:
        conn.close()


def push_admin_log(entry: dict) -> dict:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO admin_logs (id, data, at) VALUES (?, ?, ?)",
            (entry["id"], _dumps(entry), int(entry.get("at") or 0)),
        )
        # Keep last 200
        conn.execute(
            """
            DELETE FROM admin_logs WHERE id NOT IN (
                SELECT id FROM admin_logs ORDER BY at DESC LIMIT 200
            )
            """
        )
        conn.commit()
        return entry
    finally:
        conn.close()
