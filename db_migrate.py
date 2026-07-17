"""SQLite / Postgres schema migration — missing columns auto-add."""

from sqlalchemy import text, inspect


USER_COLUMNS = {
    "metaapi_account_id": "VARCHAR",
    "referral_code": "VARCHAR",
    "referred_by": "INTEGER",
    "daily_profit_owed": "FLOAT DEFAULT 0.0",
    "referral_owed": "FLOAT DEFAULT 0.0",
    "payment_status": "VARCHAR DEFAULT 'clear'",
    "last_payment_at": "DATETIME",
    "subscription_status": "VARCHAR DEFAULT 'expired'",
    "subscription_expires_at": "DATETIME",
    "payment_screenshot": "VARCHAR",
    "subscription_fee_owed": "FLOAT DEFAULT 20.0",
}

TRADE_COLUMNS = {
    "mt5_ticket": "INTEGER",
    "master_ticket": "INTEGER",
    "score": "FLOAT DEFAULT 0.0",
}


def migrate_schema(engine):
    """Add any missing columns so old goldbot.db works with new code."""
    insp = inspect(engine)
    if not insp.has_table("users"):
        return

    existing_user = {c["name"] for c in insp.get_columns("users")}
    with engine.begin() as conn:
        for col, col_type in USER_COLUMNS.items():
            if col not in existing_user:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {col_type}"))
                print(f"[MIGRATE] users.{col} added")

    if insp.has_table("trades"):
        existing_trade = {c["name"] for c in insp.get_columns("trades")}
        with engine.begin() as conn:
            for col, col_type in TRADE_COLUMNS.items():
                if col not in existing_trade:
                    conn.execute(text(f"ALTER TABLE trades ADD COLUMN {col} {col_type}"))
                    print(f"[MIGRATE] trades.{col} added")

    print("[MIGRATE] Schema up to date")
