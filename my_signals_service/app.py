"""
My Signals — standalone FastAPI service (separate Railway deploy).

PumpingBot se alag: crypto alert PWA + scanner + login/subscription.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

# Standalone = serve PWA at site root (not /my-signals/...)
os.environ.setdefault("MY_SIGNALS_PREFIX", "")

from device_care.auth_api import init_auth_db, router as auth_router  # noqa: E402
from device_care.scanner import (  # noqa: E402
    APP_PREFIX,
    legacy_router,
    router as my_signals_router,
    start_device_care_scanner,
)

APP_VERSION = os.environ.get("MY_SIGNALS_VERSION", "4.1.4")

app = FastAPI(title="Crypto Pumping Signals", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth + subscription at site root (PWA expects /token /me /register …)
app.include_router(auth_router)
# Alerts PWA + scanner API
app.include_router(my_signals_router)
app.include_router(legacy_router)


@app.get("/api")
@app.get("/health")
def health():
    return {
        "message": "Crypto Pumping Signals API",
        "version": APP_VERSION,
        "app": "crypto-pumping-signals",
        "prefix": APP_PREFIX or "/",
        "embedded_in_pumpingbot": False,
        "auth": True,
    }


# If somehow prefix is non-empty, send / → /my-signals/
if APP_PREFIX:

    @app.get("/")
    async def root_redirect():
        return RedirectResponse(url=f"{APP_PREFIX}/", status_code=307)


@app.on_event("startup")
async def on_startup():
    init_auth_db()
    start_device_care_scanner()
    print(
        f"[CPS] Standalone service v{APP_VERSION} "
        f"prefix={APP_PREFIX or '/'} auth+scanner started"
    )
