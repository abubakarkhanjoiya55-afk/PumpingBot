"""
Device Care — MEXC multi-TF breakout PWA (trade nahi, sirf alarm).
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
SCAN_SEC = int(os.environ.get("DC_SCAN_SEC", "180"))
MIN_VOL = float(os.environ.get("DC_MIN_VOLUME", "500000"))
COOLDOWN_H = int(os.environ.get("DC_COOLDOWN_H", "8"))
TRIANGLE_WINDOW = int(os.environ.get("DC_TRIANGLE_WINDOW", "18"))
SYMBOL_CACHE_SEC = int(os.environ.get("DC_SYMBOL_CACHE_SEC", "3600"))

# Fiat, stablecoins, tokenized commodities — crypto breakout scan se bahar
STABLE_FIAT_BASES = frozenset({
    "USDC", "USDE", "USD1", "USDF", "DAI", "TUSD", "FDUSD", "BUSD",
    "EUR", "BRL", "EURI", "EURR", "GBP", "JPY", "AUD", "CAD", "CHF", "TRY",
    "XAUT", "PAXG",
})

_api_symbols_cache: set[str] | None = None
_symbol_meta_cache: dict[str, dict] | None = None
_symbol_cache_at: float = 0

TIMEFRAMES = [
    ("15m", "15M", 80),
    ("60m", "1H", 70),
    ("4h", "4H", 60),
    ("1d", "D1", 50),
]

router = APIRouter(prefix="/device-care", tags=["device-care"])
sse_clients: list[asyncio.Queue] = []
alert_history: list[dict] = []
cooldown: dict[str, float] = {}
_scan_task = None

scan_stats = {
    "totalCoins": 0,
    "scanned": 0,
    "currentCoin": "",
    "currentTimeframe": "",
    "phase": "starting",
    "lastScanAt": None,
    "lastDurationSec": 0,
    "alertsTotal": 0,
    "errors": 0,
    "timeframes": [tf[1] for tf in TIMEFRAMES],
    "patterns": ["S/R Breakout", "Triangle Breakout"],
    "exchange": "MEXC",
    "minVolumeUsdt": MIN_VOL,
    "lookback": LOOKBACK,
    "nextScanInSec": 0,
    "scannedCoins": [],
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
    return [_normalize_alert(a) for a in alert_history[:80]]


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
    if direction in ("BULLISH", "BUY"):
        direction = "UP"
    elif direction in ("BEARISH", "SELL"):
        direction = "DOWN"
    return {
        "id": alert.get("id"),
        "symbol": alert["symbol"],
        "direction": direction,
        "timeframe": alert.get("timeframe", ""),
        "pattern": alert.get("pattern", "Breakout"),
        "candleTime": alert.get("candleTime"),
        "close": alert.get("close"),
        "level": alert.get("level"),
        "volume": alert.get("volume", 0),
        "at": alert.get("alertedAt") or alert.get("at"),
    }


def _broadcast(alert: dict):
    alert["id"] = alert.get("id") or f"{alert['symbol']}-{alert.get('timeframe')}-{int(time.time()*1000)}"
    alert_history.insert(0, alert)
    del alert_history[80:]
    scan_stats["alertsTotal"] = len(alert_history)
    _push_sse({"type": "alert", "data": _normalize_alert(alert)})
    _broadcast_stats()


def _body_ok(highs, lows, closes, opens, idx: int) -> bool:
    body = abs(closes[idx] - opens[idx])
    ranges = [highs[j] - lows[j] for j in range(max(0, len(highs) - 12), len(highs) - 1)]
    avg = sum(ranges) / max(len(ranges), 1)
    return body >= avg * 0.3


def _slope(vals: list[float]) -> float:
    n = len(vals)
    if n < 2:
        return 0.0
    x = list(range(n))
    xm = sum(x) / n
    ym = sum(vals) / n
    num = sum((x[i] - xm) * (vals[i] - ym) for i in range(n))
    den = sum((x[i] - xm) ** 2 for i in range(n)) or 1
    return num / den


def detect_sr_breakout(ohlc: dict, lookback: int = LOOKBACK) -> dict | None:
    h, l, c, o, t = ohlc["highs"], ohlc["lows"], ohlc["closes"], ohlc["opens"], ohlc["times"]
    if len(c) < lookback + 3:
        return None
    i = -2
    # Reference levels must end before the closed candle being evaluated.
    rh = max(h[-lookback - 2:i])
    rl = min(l[-lookback - 2:i])
    if not _body_ok(h, l, c, o, i):
        return None
    if c[i] > rh and c[i - 1] <= rh:
        return {
            "side": "BUY", "direction": "UP", "pattern": "S/R Breakout",
            "patternDetail": "Resistance breakout",
            "level": rh, "close": c[i], "candleTime": t[i],
        }
    if c[i] < rl and c[i - 1] >= rl:
        return {
            "side": "SELL", "direction": "DOWN", "pattern": "S/R Breakout",
            "patternDetail": "Support breakdown",
            "level": rl, "close": c[i], "candleTime": t[i],
        }
    return None


def detect_triangle_breakout(ohlc: dict, window: int = TRIANGLE_WINDOW) -> dict | None:
    h, l, c, o, t = ohlc["highs"], ohlc["lows"], ohlc["closes"], ohlc["opens"], ohlc["times"]
    if len(c) < window + 3:
        return None

    i = -2
    # Triangle geometry is formed only by candles before the breakout candle.
    seg_h = h[-window - 2:i]
    seg_l = l[-window - 2:i]
    avg_price = sum(c[-window - 2:i]) / len(seg_h)
    if avg_price <= 0:
        return None

    high_slope = _slope(seg_h)
    low_slope = _slope(seg_l)
    high_span = max(seg_h) - min(seg_h)
    low_span = max(seg_l) - min(seg_l)
    flat_tol = avg_price * 0.012

    resistance = max(seg_h[-6:])
    support = min(seg_l[-6:])
    if not _body_ok(h, l, c, o, i):
        return None

    flat_high = high_span < avg_price * 0.02 and abs(high_slope) < avg_price * 0.0008
    flat_low = low_span < avg_price * 0.02 and abs(low_slope) < avg_price * 0.0008
    rising_low = low_slope > avg_price * 0.0005
    falling_high = high_slope < -avg_price * 0.0005
    converging = falling_high and rising_low

    if flat_high and rising_low and c[i] > resistance and c[i - 1] <= resistance:
        return {
            "side": "BUY", "direction": "UP", "pattern": "Triangle Breakout",
            "patternDetail": "Ascending triangle",
            "level": resistance, "close": c[i], "candleTime": t[i],
        }
    if flat_low and falling_high and c[i] < support and c[i - 1] >= support:
        return {
            "side": "SELL", "direction": "DOWN", "pattern": "Triangle Breakout",
            "patternDetail": "Descending triangle",
            "level": support, "close": c[i], "candleTime": t[i],
        }
    if converging:
        upper = max(seg_h[-4:])
        lower = min(seg_l[-4:])
        mid = (upper + lower) / 2
        inside_prev = lower <= c[i - 1] <= upper
        if inside_prev and c[i] > upper:
            return {
                "side": "BUY", "direction": "UP", "pattern": "Triangle Breakout",
                "patternDetail": "Symmetrical triangle UP",
                "level": upper, "close": c[i], "candleTime": t[i],
            }
        if inside_prev and c[i] < lower:
            return {
                "side": "SELL", "direction": "DOWN", "pattern": "Triangle Breakout",
                "patternDetail": "Symmetrical triangle DOWN",
                "level": lower, "close": c[i], "candleTime": t[i],
            }
    return None


def scan_ohlc(ohlc: dict) -> list[dict]:
    hits = []
    sr = detect_sr_breakout(ohlc)
    if sr:
        hits.append(sr)
    tri = detect_triangle_breakout(ohlc)
    if tri:
        hits.append(tri)
    return hits


async def _load_symbol_universe(client: httpx.AsyncClient) -> tuple[set[str], dict[str, dict]]:
    global _api_symbols_cache, _symbol_meta_cache, _symbol_cache_at
    if (
        _api_symbols_cache is not None
        and _symbol_meta_cache is not None
        and time.time() - _symbol_cache_at < SYMBOL_CACHE_SEC
    ):
        return _api_symbols_cache, _symbol_meta_cache

    r_default = await client.get("https://api.mexc.com/api/v3/defaultSymbols")
    r_default.raise_for_status()
    payload = r_default.json()
    api_syms = set(payload.get("data") or [])

    r_info = await client.get("https://api.mexc.com/api/v3/exchangeInfo")
    r_info.raise_for_status()
    meta = {s["symbol"]: s for s in r_info.json().get("symbols", [])}

    _api_symbols_cache = api_syms
    _symbol_meta_cache = meta
    _symbol_cache_at = time.time()
    print(f"[Device Care] MEXC API symbols loaded: {len(api_syms)} tradable")
    return api_syms, meta


def _is_crypto_spot_usdt(symbol: str, meta: dict[str, dict]) -> bool:
    """Sirf MEXC spot crypto/USDT — forex, stable, commodity exclude."""
    s = meta.get(symbol)
    if not s:
        return False
    if s.get("quoteAsset") != "USDT":
        return False
    if str(s.get("status")) != "1":
        return False
    if not s.get("isSpotTradingAllowed"):
        return False
    if "SPOT" not in s.get("permissions", []):
        return False
    if s.get("st"):
        return False
    if "(" in symbol or ")" in symbol or "_" in symbol:
        return False

    base = s.get("baseAsset", "")
    if base in STABLE_FIAT_BASES:
        return False
    if base.startswith(("GOLD", "SILVER", "OIL", "GAS")):
        return False
    return True


async def fetch_symbols(client: httpx.AsyncClient) -> list[tuple[str, float]]:
    api_syms, meta = await _load_symbol_universe(client)
    r = await client.get("https://api.mexc.com/api/v3/ticker/24hr")
    r.raise_for_status()
    rows = []
    skipped = 0
    for t in r.json():
        sym = t.get("symbol", "")
        if sym not in api_syms:
            continue
        if not _is_crypto_spot_usdt(sym, meta):
            skipped += 1
            continue
        vol = float(t.get("quoteVolume", 0))
        if vol >= MIN_VOL:
            rows.append((sym, vol))
    rows.sort(key=lambda x: x[1], reverse=True)
    print(f"[Device Care] Crypto USDT pairs: {len(rows)} (filtered {skipped} non-crypto/low-quality)")
    return rows


async def fetch_klines(client: httpx.AsyncClient, symbol: str, interval: str, limit: int) -> dict | None:
    r = await client.get(
        "https://api.mexc.com/api/v3/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
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
    print("[Device Care] Multi-TF scanner started (15M/1H/4H/D1)")
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            started = time.time()
            scan_stats["phase"] = "fetching_pairs"
            scan_stats["scanned"] = 0
            scan_stats["errors"] = 0
            scan_stats["scannedCoins"] = []
            _broadcast_stats()
            try:
                symbols = await fetch_symbols(client)
                scan_stats["phase"] = "scanning"
                scan_stats["totalCoins"] = len(symbols)
                print(f"[Device Care] Scanning {len(symbols)} pairs × {len(TIMEFRAMES)} TFs...")
                for i, (sym, vol) in enumerate(symbols):
                    scan_stats["currentCoin"] = sym
                    scan_stats["scanned"] = i
                    coin_hits = 0
                    coin_err = False
                    for interval, tf_label, limit in TIMEFRAMES:
                        scan_stats["currentTimeframe"] = tf_label
                        if i % 3 == 0:
                            _broadcast_stats()
                        ohlc = await fetch_klines(client, sym, interval, limit)
                        if not ohlc:
                            coin_err = True
                            scan_stats["errors"] += 1
                            await asyncio.sleep(0.05)
                            continue
                        for hit in scan_ohlc(ohlc):
                            key = f"{sym}:{tf_label}:{hit['pattern']}:{hit['direction']}"
                            if cooldown.get(key, 0) <= time.time():
                                cooldown[key] = time.time() + COOLDOWN_H * 3600
                                alert = {
                                    "symbol": sym,
                                    "timeframe": tf_label,
                                    "volume": vol,
                                    "alertedAt": int(time.time() * 1000),
                                    **hit,
                                }
                                coin_hits += 1
                                print(f"[Device Care] {sym} {tf_label} {hit['pattern']} {hit['direction']}")
                                _broadcast(alert)
                        await asyncio.sleep(0.05)
                    scan_stats["scannedCoins"].append({
                        "symbol": sym,
                        "hits": coin_hits,
                        "ok": not coin_err,
                    })
                    if len(scan_stats["scannedCoins"]) > 120:
                        scan_stats["scannedCoins"] = scan_stats["scannedCoins"][-120:]
                    _broadcast_stats()
                scan_stats["scanned"] = len(symbols)
                scan_stats["currentCoin"] = ""
                scan_stats["currentTimeframe"] = ""
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
