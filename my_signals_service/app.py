"""
My Signals — standalone FastAPI service (separate Railway deploy).

PumpingBot se alag: sirf MEXC futures alerts PWA + scanner.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

# Standalone = serve PWA at site root (not /my-signals/...)
os.environ.setdefault("MY_SIGNALS_PREFIX", "")

from device_care.scanner import (  # noqa: E402
    router as my_signals_router,
    legacy_router as legacy_router,
    start_device_care_scanner,
    APP_PREFIX,
)

APP_VERSION = os.environ.get("MY_SIGNALS_VERSION", "4.2.1")

app = FastAPI(title="Crypto Pumping Signals", version=APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    }


# If somehow prefix is non-empty, send / → /my-signals/
if APP_PREFIX:
    @app.get("/")
    async def root_redirect():
        return RedirectResponse(url=f"{APP_PREFIX}/", status_code=307)


@app.on_event("startup")
async def on_startup():
    start_device_care_scanner()
    print(
        f"[CPS] Standalone service v{APP_VERSION} "
        f"prefix={APP_PREFIX or '/'} scanner started"
    )
