"""Shared auth helper for the Windows VPS supervisor talking to the API."""

from __future__ import annotations

import os


# Fixed go-live secret — Windows VPS config.bat must use the same value.
# (Railway may have an old unknown VPS_SECRET; we ignore it so owner VPS just works.)
_DEFAULT_VPS_SECRET = "pumpingbot-vps-live-2026"


def vps_secret() -> str:
    # Allow rotate later: set VPS_SECRET_OVERRIDE=1 and VPS_SECRET=newvalue on Railway + VPS
    if os.environ.get("VPS_SECRET_OVERRIDE", "").strip().lower() in ("1", "true", "yes"):
        return (os.environ.get("VPS_SECRET") or _DEFAULT_VPS_SECRET).strip()
    return _DEFAULT_VPS_SECRET


def _check_secret(x_vps_secret: str | None):
    try:
        from fastapi import HTTPException
    except ImportError:
        class HTTPException(Exception):  # type: ignore
            def __init__(self, status_code, detail):
                self.status_code = status_code
                self.detail = detail
                super().__init__(detail)

    expected = vps_secret()
    if not expected:
        raise HTTPException(
            503,
            "VPS_SECRET not configured on server — set it in Railway env",
        )
    if not x_vps_secret or x_vps_secret != expected:
        raise HTTPException(401, "Invalid VPS secret")
    return True


try:
    from fastapi import Header

    def require_vps_secret(
        x_vps_secret: str | None = Header(default=None, alias="X-VPS-Secret"),
    ):
        return _check_secret(x_vps_secret)
except ImportError:
    def require_vps_secret(x_vps_secret: str | None = None):
        return _check_secret(x_vps_secret)
