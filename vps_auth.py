"""Shared auth helper for the Windows VPS supervisor talking to the API."""

from __future__ import annotations

import os


def vps_secret() -> str:
    return (os.environ.get("VPS_SECRET") or "").strip()


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
