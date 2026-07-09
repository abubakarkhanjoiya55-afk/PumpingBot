"""
Device Care — MEXC 4H breakout PWA (trade nahi, sirf alarm).
Mount: /device-care
"""
import asyncio
import json
import os
import time
from pathlib import Path

import httpx
from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse

STATIC = Path(__file__).parent / "static"
LOOKBACK = int(os.environ.get("DC_LOOKBACK", "20"))
SCAN_SEC = int(os.environ.get("DC_SCAN_SEC", "120"))
MIN_VOL = float(os.environ.get("DC_MIN_VOLUME", "500000"))
COOLDOWN_H = int(os.environ.get("DC_COOLDOWN_H", "8"))

router = APIRouter(prefix="/device-care", tags=["device-care"])
sse_clients: list[asyncio.Queue] = []
alert_history: list[dict] = []
cooldown: dict[str, float] = {}
_scan_task = None

scan_stats = {
    "totalCoins": 0,
    "scanned": 0,
    "currentCoin": "",
    "phase": "starting",
    "lastScanAt": None,
    "lastDurationSec": 0,
    "alertsTotal": 0,
    "errors": 0,
    "timeframe": "4H",
    "exchange": "MEXC",
    "minVolumeUsdt": MIN_VOL,
    "lookback": LOOKBACK,
    "nextScanInSec": 0,
}


def _static(name: str):
    p = STATIC / name
    return FileResponse(p) if p.exists() else None


@router.get("")
@router.get("/")
async def app_home():
    f = _static("index.html")
    if f:
        return f
    return {"app": "Device Care", "status": "static missing"}


@router.get("/manifest.json")
async def manifest():
    return _static("manifest.json")


@router.get("/sw.js")
async def sw():
    return _static("sw.js")


@router.get("/icon-192.svg")
async def icon192():
    return _static("icon-192.svg")


@router.get("/icon-512.svg")
async def icon512():
    return _static("icon-512.svg")


@router.get("/api/status")
async def status():
    return {"ok": True, "app": "Device Care", **scan_stats}


@router.get("/api/alerts")
async def alerts():
    return alert_history[:80]


async def _sse_stream():
    q: asyncio.Queue = asyncio.Queue()
    sse_clients.append(q)
    try:
        q.put_nowait({"type": "stats", "data": dict(scan_stats)})
    except Exception:
        pass

    async def gen():
        try:
            yield ": connected\n\n"
            while True:
                msg = await q.get()
                yield f"data: {json.dumps(msg)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if q in sse_clients:
                sse_clients.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/events")
@router.get("/api/stream")
async def events():
    return await _sse_stream()


def _push_sse(payload: dict):
    for q in list(sse_clients):
        try:
            q.put_nowait(payload)
        except Exception:
            pass


def _broadcast_stats():
    _push_sse({"type": "stats", "data": dict(scan_stats)})


def _normalize_alert(alert: dict) -> dict:
    direction = alert.get("direction", "")
    if direction == "BULLISH":
        direction = "UP"
    elif direction == "BEARISH":
        direction = "DOWN"
    return {
        "symbol": alert["symbol"],
        "direction": direction,
        "close": alert.get("close"),
        "volume": alert.get("volume", 0),
        "at": alert.get("alertedAt") or alert.get("at"),
        "side": alert.get("side"),
        "level": alert.get("level"),
    }


def _broadcast(alert: dict):
    alert_history.insert(0, alert)
    del alert_history[80:]
    scan_stats["alertsTotal"] = len(alert_history)
    _push_sse({"type": "alert", "data": _normalize_alert(alert)})
    _broadcast_stats()


def detect_breakout(ohlc: dict) -> dict | None:
    h, l, c, o, t = ohlc["highs"], ohlc["lows"], ohlc["closes"], ohlc["opens"], ohlc["times"]
    if len(c) < LOOKBACK + 3:
        return None
    rh = max(h[-LOOKBACK - 1:-1])
    rl = min(l[-LOOKBACK - 1:-1])
    i = -2
    body = abs(c[i] - o[i])
    ranges = [h[j] - l[j] for j in range(max(0, len(h) - 12), len(h) - 1)]
    avg = sum(ranges) / max(len(ranges), 1)
    if c[i] > rh and c[i - 1] <= rh and body >= avg * 0.35:
        return {"side": "BUY", "direction": "BULLISH", "level": rh, "close": c[i],
                "rangeHigh": rh, "rangeLow": rl, "candleTime": t[i], "strength": 50}
    if c[i] < rl and c[i - 1] >= rl and body >= avg * 0.35:
        return {"side": "SELL", "direction": "BEARISH", "level": rl, "close": c[i],
                "rangeHigh": rh, "rangeLow": rl, "candleTime": t[i], "strength": 50}
    return None


async def fetch_symbols(client: httpx.AsyncClient) -> list[str]:
    r = await client.get("https://api.mexc.com/api/v3/ticker/24hr")
    r.raise_for_status()
    rows = []
    for t in r.json():
        sym = t.get("symbol", "")
        if sym.endswith("USDT") and "_" not in sym:
            vol = float(t.get("quoteVolume", 0))
            if vol >= MIN_VOL:
                rows.append((sym, vol))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


async def fetch_klines(client: httpx.AsyncClient, symbol: str) -> dict | None:
    r = await client.get(
        "https://api.mexc.com/api/v3/klines",
        params={"symbol": symbol, "interval": "4h", "limit": 60},
    )
    if r.status_code != 200:
        return None
    data = r.json()
    if not data or len(data) < LOOKBACK + 3:
        return None
    return {
        "opens": [float(x[1]) for x in data],
        "highs": [float(x[2]) for x in data],
        "lows": [float(x[3]) for x in data],
        "closes": [float(x[4]) for x in data],
        "times": [int(x[0]) for x in data],
    }


async def scan_loop():
    print("[Device Care] Scanner started")
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            started = time.time()
            scan_stats["phase"] = "fetching_pairs"
            scan_stats["scanned"] = 0
            scan_stats["errors"] = 0
            _broadcast_stats()
            try:
                symbols = await fetch_symbols(client)
                scan_stats["phase"] = "scanning"
                scan_stats["totalCoins"] = len(symbols)
                print(f"[Device Care] Scanning {len(symbols)} pairs...")
                for i, (sym, vol) in enumerate(symbols):
                    scan_stats["currentCoin"] = sym
                    scan_stats["scanned"] = i
                    if i % 5 == 0:
                        _broadcast_stats()
                    ohlc = await fetch_klines(client, sym)
                    if not ohlc:
                        scan_stats["errors"] += 1
                        await asyncio.sleep(0.08)
                        continue
                    hit = detect_breakout(ohlc)
                    if hit:
                        key = f"{sym}:{hit['direction']}"
                        if cooldown.get(key, 0) <= time.time():
                            cooldown[key] = time.time() + COOLDOWN_H * 3600
                            alert = {
                                "symbol": sym, **hit,
                                "volume": vol,
                                "alertedAt": int(time.time() * 1000),
                            }
                            print(f"[Device Care] BREAKOUT {sym} {hit['side']}")
                            _broadcast(alert)
                    await asyncio.sleep(0.08)
                scan_stats["scanned"] = len(symbols)
                scan_stats["currentCoin"] = ""
                scan_stats["lastScanAt"] = int(time.time() * 1000)
                scan_stats["lastDurationSec"] = round(time.time() - started)
                scan_stats["phase"] = "waiting"
                _broadcast_stats()
            except Exception as e:
                scan_stats["phase"] = "error"
                print(f"[Device Care] scan error: {e}")
                _broadcast_stats()

            for remaining in range(SCAN_SEC, 0, -1):
                scan_stats["nextScanInSec"] = remaining
                if remaining % 10 == 0:
                    _broadcast_stats()
                await asyncio.sleep(1)


def start_device_care_scanner():
    global _scan_task
    if _scan_task is not None:
        return
    loop = asyncio.get_running_loop()
    _scan_task = loop.create_task(scan_loop())
    print("[Device Care] PWA → /device-care")
