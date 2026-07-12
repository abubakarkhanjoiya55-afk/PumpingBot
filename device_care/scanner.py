"""
Device Care — MEXC Futures multi-TF alert PWA (trade nahi, sirf alarm).
Mount: /device-care

Sirf USDT-M futures (spot nahi).
Strategy:
  - 1H / 4H  → S/R Breakout + Triangle Breakout (alerts 1h baad clear)
  - D1 / 1W  → Dragonfly / Hammer / Doji — sirf jab uske BAAD last closed
               candle green close ho (confirmation). Alerts 8h baad clear.
Har alert ke sath: score (0–100), entry, SL, TP
"""
import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

STATIC = Path(__file__).parent / "static"
LOOKBACK = int(os.environ.get("DC_LOOKBACK", "20"))
SCAN_SEC = int(os.environ.get("DC_SCAN_SEC", "180"))
# Subah window mein tez scan — zyada coins jaldi dhoondne ke liye
MORNING_SCAN_SEC = int(os.environ.get("DC_MORNING_SCAN_SEC", "60"))
MORNING_START_HOUR = int(os.environ.get("DC_MORNING_START_HOUR", "5"))
MORNING_END_HOUR = int(os.environ.get("DC_MORNING_END_HOUR", "9"))
PKT_OFFSET_HOURS = int(os.environ.get("DC_PKT_OFFSET_HOURS", "5"))
MIN_VOL = float(os.environ.get("DC_MIN_VOLUME", "500000"))
TRIANGLE_WINDOW = int(os.environ.get("DC_TRIANGLE_WINDOW", "18"))
SYMBOL_CACHE_SEC = int(os.environ.get("DC_SYMBOL_CACHE_SEC", "3600"))
# Alert history TTL — triangles jaldi clear, candle patterns zyada der
BREAKOUT_ALERT_TTL_SEC = int(os.environ.get("DC_BREAKOUT_ALERT_TTL_SEC", "3600"))  # 1h
D1_PATTERN_ALERT_TTL_SEC = int(os.environ.get("DC_D1_ALERT_TTL_SEC", str(8 * 3600)))  # 8h

FUTURES_BASE = "https://contract.mexc.com"
CANDLE_PATTERNS = frozenset({"Dragonfly Doji", "Hammer", "Doji + Green"})
# Back-compat alias used by TTL helpers
D1_PATTERNS = CANDLE_PATTERNS
TRIANGLE_TFS = frozenset({"1H", "4H"})
CANDLE_TFS = frozenset({"D1", "1W"})

# Fiat, stablecoins, commodities — futures crypto scan se bahar
STABLE_FIAT_BASES = frozenset({
    "USDC", "USDE", "USD1", "USDF", "DAI", "TUSD", "FDUSD", "BUSD",
    "EUR", "BRL", "EURI", "EURR", "GBP", "JPY", "AUD", "CAD", "CHF", "TRY",
    "XAUT", "PAXG", "XAU", "XAG", "SILVER", "GOLD",
})

_api_symbols_cache: set[str] | None = None
_symbol_meta_cache: dict[str, dict] | None = None
_symbol_cache_at: float = 0

# MEXC futures interval names — 1H/4H triangles, D1/1W candle patterns
TIMEFRAMES = [
    ("Min60", "1H", 70),
    ("Hour4", "4H", 60),
    ("Day1", "D1", 50),
    ("Week1", "1W", 40),
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
    "patterns": [
        "S/R Breakout",
        "Triangle Breakout",
        "Dragonfly Doji",
        "Hammer",
        "Doji + Green",
    ],
    "strategy": {
        "1H": "S/R + Triangle Breakout",
        "4H": "S/R + Triangle Breakout",
        "D1": "Doji/Hammer + green close",
        "1W": "Doji/Hammer + green close",
    },
    "exchange": "MEXC Futures",
    "market": "futures",
    "minVolumeUsdt": MIN_VOL,
    "lookback": LOOKBACK,
    "nextScanInSec": 0,
    "scannedCoins": [],
    "morningWindow": False,
    "d1PatternsEnabled": False,
    "breakoutAlertTtlSec": BREAKOUT_ALERT_TTL_SEC,
    "d1AlertTtlSec": D1_PATTERN_ALERT_TTL_SEC,
}


def _static(name: str, cache_control: str = "public, max-age=3600"):
    p = STATIC / name
    if not p.is_file():
        raise HTTPException(status_code=404, detail="Static asset not found")
    return FileResponse(p, headers={"Cache-Control": cache_control})


@router.get("")
@router.get("/")
async def app_home():
    return _static("index.html", "no-cache")


@router.get("/manifest.json")
async def manifest():
    return _static("manifest.json", "no-cache")


@router.get("/sw.js")
async def sw():
    return _static("sw.js", "no-cache")


@router.get("/icon-192.svg")
async def icon192():
    return _static("icon-192.svg")


@router.get("/icon-512.svg")
async def icon512():
    return _static("icon-512.svg")


@router.get("/icon-192.png")
async def icon192_png():
    return _static("icon-192.png")


@router.get("/icon-512.png")
async def icon512_png():
    return _static("icon-512.png")


@router.get("/api/status")
async def status():
    prune_alert_history()
    return {"ok": True, "app": "Device Care", **scan_stats}


@router.get("/api/alerts")
async def alerts():
    prune_alert_history()
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
        "patternDetail": alert.get("patternDetail", ""),
        "candleTime": alert.get("candleTime"),
        "close": alert.get("close"),
        "level": alert.get("level"),
        "volume": alert.get("volume", 0),
        "score": alert.get("score"),
        "entry": alert.get("entry"),
        "sl": alert.get("sl"),
        "tp": alert.get("tp"),
        "riskReward": alert.get("riskReward"),
        "at": alert.get("alertedAt") or alert.get("at"),
    }


def _is_d1_pattern_alert(alert: dict) -> bool:
    return alert.get("pattern") in CANDLE_PATTERNS


def _alert_ttl_sec(alert: dict) -> int:
    """S/R + Triangle alerts 1h, candle patterns (D1/1W) 8h."""
    if _is_d1_pattern_alert(alert):
        return D1_PATTERN_ALERT_TTL_SEC
    return BREAKOUT_ALERT_TTL_SEC


def prune_alert_history(now: float | None = None) -> list[dict]:
    """
    Purani alerts history se hatao:
    - Breakouts (S/R, Triangle): 1 hour
    - Candle patterns (Dragonfly/Hammer/Doji+Green): 8 hours
    Returns list of removed alert ids (for SSE clear).
    """
    global alert_history
    t = now if now is not None else time.time()
    kept: list[dict] = []
    removed_ids: list[dict] = []
    for alert in alert_history:
        at_ms = alert.get("alertedAt") or alert.get("at") or 0
        age_sec = t - (at_ms / 1000.0)
        if age_sec >= _alert_ttl_sec(alert):
            removed_ids.append({"id": alert.get("id"), "symbol": alert.get("symbol")})
        else:
            kept.append(alert)
    if len(kept) != len(alert_history):
        alert_history[:] = kept
        scan_stats["alertsTotal"] = len(alert_history)
    return removed_ids


def _broadcast(alert: dict):
    alert["id"] = alert.get("id") or (
        f"{alert['symbol']}-{alert.get('timeframe')}-{alert.get('pattern')}-"
        f"{alert.get('direction')}-{alert.get('candleTime')}"
    )
    prune_alert_history()
    alert_history.insert(0, alert)
    del alert_history[80:]
    scan_stats["alertsTotal"] = len(alert_history)
    _push_sse({"type": "alert", "data": _normalize_alert(alert)})
    _broadcast_stats()


def _round_price(price: float) -> float:
    """Readable price rounding by magnitude."""
    p = abs(price)
    if p >= 1000:
        return round(price, 2)
    if p >= 100:
        return round(price, 3)
    if p >= 1:
        return round(price, 4)
    if p >= 0.01:
        return round(price, 6)
    return round(price, 8)


def _avg_range(ohlc: dict, look: int = 12) -> float:
    h, l = ohlc["highs"], ohlc["lows"]
    # Exclude forming candle (-1)
    end = len(h) - 1
    start = max(0, end - look)
    ranges = [h[j] - l[j] for j in range(start, end)]
    return sum(ranges) / max(len(ranges), 1)


def _body_strength(ohlc: dict, idx: int = -2) -> float:
    """Body vs recent avg range — 0..~2+."""
    body = abs(ohlc["closes"][idx] - ohlc["opens"][idx])
    avg = _avg_range(ohlc) or 0.0001
    return body / avg


def enrich_trade_plan(ohlc: dict, hit: dict) -> dict:
    """
    Attach score (0–100), entry, SL, TP.
    Stronger / cleaner signal → higher score → wider RR target.
    """
    i = -2
    h = ohlc["highs"]
    l = ohlc["lows"]
    c = ohlc["closes"]
    o = ohlc["opens"]
    direction = hit.get("direction", "UP")
    pattern = hit.get("pattern", "")
    detail = hit.get("patternDetail", "")
    level = float(hit.get("level") or c[i])
    close = float(hit.get("close") or c[i])
    entry = close
    candle_low = float(l[i])
    candle_high = float(h[i])
    avg_rng = _avg_range(ohlc) or abs(close) * 0.01
    body_str = _body_strength(ohlc, i)

    score = 50
    sl = candle_low
    buffer = max(avg_rng * 0.15, abs(close) * 0.001)

    if pattern == "Triangle Breakout":
        # Base by triangle type
        if "Ascending" in detail:
            score = 72
        elif "Descending" in detail:
            score = 72
        else:
            score = 60  # symmetrical
        # Breakout distance beyond level
        if direction == "UP":
            dist = (close - level) / (avg_rng or 0.0001)
            sl = min(float(hit.get("level") or candle_low), candle_low) - buffer
            # Prefer triangle support if available via level for descending/sym
            if "Ascending" in detail or "Symmetrical" in detail:
                # SL under recent swing low before breakout
                sl = min(l[-TRIANGLE_WINDOW - 2:i][-6:]) - buffer
        else:
            dist = (level - close) / (avg_rng or 0.0001)
            sl = max(float(hit.get("level") or candle_high), candle_high) + buffer
            if "Descending" in detail or "Symmetrical" in detail:
                sl = max(h[-TRIANGLE_WINDOW - 2:i][-6:]) + buffer
        score += min(18, int(dist * 10))
        score += min(12, int(body_str * 8))
        # Clean close beyond level
        if direction == "UP" and close > level * 1.002:
            score += 5
        if direction == "DOWN" and close < level * 0.998:
            score += 5

    elif pattern == "S/R Breakout":
        # Clean level break — slightly below triangle confidence baseline
        score = 68
        if direction == "UP":
            dist = (close - level) / (avg_rng or 0.0001)
            sl = candle_low - buffer
        else:
            dist = (level - close) / (avg_rng or 0.0001)
            sl = candle_high + buffer
        score += min(18, int(dist * 10))
        score += min(12, int(body_str * 8))
        if direction == "UP" and close > level * 1.002:
            score += 5
        if direction == "DOWN" and close < level * 0.998:
            score += 5

    elif pattern in CANDLE_PATTERNS:
        # Pattern candle is -3; confirmation (last closed) is -2
        _, _, _, _, body_p, rng_p, uw_p, lw_p = _candle_parts(ohlc, -3)
        _, _, _, _, body_g, rng_g, _, _ = _candle_parts(ohlc, -2)
        pattern_low = float(l[-3])
        conf_low = candle_low
        score = 70
        if pattern == "Dragonfly Doji":
            score = 78
            wick_ratio = lw_p / (rng_p or 0.0001)
            score += min(15, int(wick_ratio * 20))
            if uw_p / (rng_p or 0.0001) < 0.05:
                score += 4
        elif pattern == "Hammer":
            score = 74
            wick_ratio = lw_p / max(body_p, 0.0001)
            score += min(14, int(wick_ratio * 3))
        else:  # Doji + Green
            score = 72
            if body_p <= rng_p * 0.05:
                score += 5
            if lw_p >= rng_p * 0.4:
                score += 5
        # Green confirmation strength on last closed candle
        score += min(15, int(body_str * 10))
        if body_g >= rng_g * 0.4:
            score += 4
        if (close - conf_low) / (rng_g or 0.0001) > 0.7:
            score += 4
        sl = min(pattern_low, conf_low) - buffer

    score = max(1, min(100, int(score)))

    # RR scales with score: 1.5 @50 → ~3.0 @100
    rr = round(1.2 + (score / 100.0) * 2.0, 2)
    risk = abs(entry - sl)
    if risk <= 0:
        risk = avg_rng * 0.5 or abs(entry) * 0.01
        if direction == "UP":
            sl = entry - risk
        else:
            sl = entry + risk

    if direction == "UP":
        tp = entry + risk * rr
    else:
        tp = entry - risk * rr

    hit["score"] = score
    hit["entry"] = _round_price(entry)
    hit["sl"] = _round_price(sl)
    hit["tp"] = _round_price(tp)
    hit["riskReward"] = rr
    hit["close"] = _round_price(close)
    if hit.get("level") is not None:
        hit["level"] = _round_price(float(hit["level"]))
    return hit


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


def _pkt_now() -> datetime:
    """Pakistan Standard Time (UTC+5) — billing/scheduler ke saath consistent."""
    return datetime.utcnow() + timedelta(hours=PKT_OFFSET_HOURS)


def in_morning_window(now: datetime | None = None) -> bool:
    """Subah 5am–9am PKT — daily candle close ke baad D1 patterns pe zor."""
    t = now or _pkt_now()
    return MORNING_START_HOUR <= t.hour < MORNING_END_HOUR


def _candle_parts(
    ohlc: dict, idx: int
) -> tuple[float, float, float, float, float, float, float, float]:
    """Return open, high, low, close, body, range, upper_wick, lower_wick for candle idx."""
    o = ohlc["opens"][idx]
    h = ohlc["highs"][idx]
    l = ohlc["lows"][idx]
    c = ohlc["closes"][idx]
    body = abs(c - o)
    rng = h - l if h != l else 0.0001
    uw = h - max(o, c)
    lw = min(o, c) - l
    return o, h, l, c, body, rng, uw, lw


def _is_doji(body: float, rng: float, max_body_pct: float = 0.1) -> bool:
    """Small body relative to full range — classic doji."""
    return body <= rng * max_body_pct


def _is_green_confirmation(ohlc: dict, pattern_close: float, idx: int = -2) -> bool:
    """
    Last closed candle must be green and close above the pattern candle close.
    Yeh confirmation Dragonfly / Hammer / Doji — teeno pe apply hoti hai.
    """
    if len(ohlc["closes"]) < abs(idx):
        return False
    o_g, _, _, c_g, body_g, rng_g, _, _ = _candle_parts(ohlc, idx)
    if c_g <= o_g:
        return False
    if body_g < rng_g * 0.2:
        return False
    if c_g <= pattern_close:
        return False
    return True


def _dragonfly_shape_at(ohlc: dict, idx: int) -> dict | None:
    """Dragonfly Doji shape check at candle idx (no confirmation)."""
    if len(ohlc["closes"]) < abs(idx):
        return None
    o, h, l, c, body, rng, uw, lw = _candle_parts(ohlc, idx)
    if not _is_doji(body, rng):
        return None
    if lw < rng * 0.6:
        return None
    if uw > rng * 0.1:
        return None
    if body > 0 and lw < body * 2:
        return None
    return {
        "side": "BUY",
        "direction": "UP",
        "pattern": "Dragonfly Doji",
        "patternDetail": "Dragonfly doji + green close",
        "level": l,
        "close": c,
        "candleTime": ohlc["times"][idx],
        "_pattern_idx": idx,
        "_pattern_close": c,
    }


def _hammer_shape_at(ohlc: dict, idx: int) -> dict | None:
    """Hammer shape check at candle idx (no confirmation)."""
    if len(ohlc["closes"]) < abs(idx):
        return None
    o, h, l, c, body, rng, uw, lw = _candle_parts(ohlc, idx)
    if body <= 0:
        return None
    if _is_doji(body, rng):
        return None
    if lw < body * 2:
        return None
    if uw > body * 0.3:
        return None
    if lw < rng * 0.5:
        return None
    # Bullish preference on pattern candle itself
    if c < o and (c - l) < rng * 0.6:
        return None
    return {
        "side": "BUY",
        "direction": "UP",
        "pattern": "Hammer",
        "patternDetail": "Hammer + green close",
        "level": l,
        "close": c,
        "candleTime": ohlc["times"][idx],
        "_pattern_idx": idx,
        "_pattern_close": c,
    }


def detect_dragonfly_doji(ohlc: dict) -> dict | None:
    """
    Dragonfly Doji on candle -3, then last closed candle (-2) green close.
    User rule: pattern ke BAAD last 1D candle green close hui ho.
    """
    if len(ohlc["closes"]) < 4:
        return None
    shape = _dragonfly_shape_at(ohlc, -3)
    if not shape:
        return None
    if not _is_green_confirmation(ohlc, shape["_pattern_close"], -2):
        return None
    # Alert timestamps / levels follow confirmation candle (entry at green close)
    o_g, _, l_g, c_g, _, _, _, _ = _candle_parts(ohlc, -2)
    return {
        "side": "BUY",
        "direction": "UP",
        "pattern": "Dragonfly Doji",
        "patternDetail": "Dragonfly doji + green close",
        "level": min(float(shape["level"]), l_g),
        "close": c_g,
        "candleTime": ohlc["times"][-2],
    }


def detect_hammer(ohlc: dict) -> dict | None:
    """
    Hammer on candle -3, then last closed candle (-2) green close.
    User rule: pattern ke BAAD last 1D candle green close hui ho.
    """
    if len(ohlc["closes"]) < 4:
        return None
    shape = _hammer_shape_at(ohlc, -3)
    if not shape:
        return None
    if not _is_green_confirmation(ohlc, shape["_pattern_close"], -2):
        return None
    o_g, _, l_g, c_g, _, _, _, _ = _candle_parts(ohlc, -2)
    return {
        "side": "BUY",
        "direction": "UP",
        "pattern": "Hammer",
        "patternDetail": "Hammer + green close",
        "level": min(float(shape["level"]), l_g),
        "close": c_g,
        "candleTime": ohlc["times"][-2],
    }


def detect_doji_then_green(ohlc: dict) -> dict | None:
    """
    Two-candle sequence on closed candles:
    - Candle -3: plain doji (not already classified as dragonfly)
    - Candle -2: green candle that closed above doji close (confirmation)
    Same green-close rule as Dragonfly/Hammer.
    """
    if len(ohlc["closes"]) < 4:
        return None
    doji_i = -3
    green_i = -2
    _, _, _, c_doji, body_d, rng_d, _, _ = _candle_parts(ohlc, doji_i)

    if not _is_doji(body_d, rng_d):
        return None
    # Dragonfly is handled by detect_dragonfly_doji — avoid double alert
    if _dragonfly_shape_at(ohlc, doji_i):
        return None
    if not _is_green_confirmation(ohlc, c_doji, green_i):
        return None
    o_g, _, l_g, c_g, _, _, _, _ = _candle_parts(ohlc, green_i)
    return {
        "side": "BUY",
        "direction": "UP",
        "pattern": "Doji + Green",
        "patternDetail": "Doji then green close",
        "level": l_g,
        "close": c_g,
        "candleTime": ohlc["times"][green_i],
    }


def scan_candle_patterns(ohlc: dict) -> list[dict]:
    """
    D1/1W bullish candle patterns — har pattern ke baad last closed candle
    green close confirmation zaroori. One hit per pattern type max.
    """
    hits = []
    for detector in (detect_dragonfly_doji, detect_hammer, detect_doji_then_green):
        hit = detector(ohlc)
        if hit:
            hits.append(hit)
    return hits


# Back-compat alias
scan_d1_patterns = scan_candle_patterns


def scan_ohlc(ohlc: dict, *, timeframe: str = "", include_d1_patterns: bool = False) -> list[dict]:
    """
    TF-gated strategy:
      1H/4H → S/R Breakout + Triangle Breakout
      D1/1W → Dragonfly/Hammer/Doji + green close confirmation
    include_d1_patterns: legacy test flag for candle patterns when timeframe omitted.
    """
    hits: list[dict] = []
    tf = timeframe or ""

    run_breakouts = tf in TRIANGLE_TFS or (not tf and not include_d1_patterns)
    run_candles = tf in CANDLE_TFS or include_d1_patterns

    if run_breakouts:
        sr = detect_sr_breakout(ohlc)
        if sr:
            hits.append(enrich_trade_plan(ohlc, sr))
        tri = detect_triangle_breakout(ohlc)
        if tri:
            hits.append(enrich_trade_plan(ohlc, tri))
    if run_candles:
        for hit in scan_candle_patterns(ohlc):
            hits.append(enrich_trade_plan(ohlc, hit))
    return hits


async def _load_symbol_universe(client: httpx.AsyncClient) -> tuple[set[str], dict[str, dict]]:
    """MEXC USDT-M futures contracts only (spot API use nahi hota)."""
    global _api_symbols_cache, _symbol_meta_cache, _symbol_cache_at
    if (
        _api_symbols_cache is not None
        and _symbol_meta_cache is not None
        and time.time() - _symbol_cache_at < SYMBOL_CACHE_SEC
    ):
        return _api_symbols_cache, _symbol_meta_cache

    r = await client.get(f"{FUTURES_BASE}/api/v1/contract/detail")
    r.raise_for_status()
    payload = r.json()
    if not payload.get("success"):
        raise RuntimeError(f"MEXC futures detail failed: {payload.get('code')}")

    meta: dict[str, dict] = {}
    api_syms: set[str] = set()
    for c in payload.get("data") or []:
        sym = c.get("symbol") or ""
        if not _is_crypto_futures_usdt(c):
            continue
        meta[sym] = c
        api_syms.add(sym)

    _api_symbols_cache = api_syms
    _symbol_meta_cache = meta
    _symbol_cache_at = time.time()
    print(f"[Device Care] MEXC Futures USDT contracts loaded: {len(api_syms)}")
    return api_syms, meta


def _is_crypto_futures_usdt(contract: dict) -> bool:
    """Sirf active USDT-M crypto futures — spot/fiat/commodity/stocks exclude."""
    if not contract:
        return False
    symbol = contract.get("symbol") or ""
    if not symbol.endswith("_USDT"):
        return False
    if contract.get("quoteCoin") != "USDT":
        return False
    if contract.get("settleCoin") != "USDT":
        return False
    # state 0 = enabled
    if contract.get("state") not in (0, "0", None):
        return False
    if contract.get("apiAllowed") is False:
        return False
    if contract.get("isHidden"):
        return False
    # type 2 = stock/index/commodity style contracts on MEXC
    if contract.get("type") == 2:
        return False

    base = (contract.get("baseCoin") or "").upper()
    if base in STABLE_FIAT_BASES:
        return False
    if base.startswith(("GOLD", "SILVER", "OIL", "GAS", "USOIL", "UKOIL")):
        return False
    # Stock-like tickers: AMDSTOCK, NVIDIA, SPX500, etc.
    if "STOCK" in base or base.endswith(("500", "100", "30")):
        return False
    if any(x in base for x in ("SPX", "NAS", "DOW", "NIKKEI", "FTSE")):
        return False
    return True


async def fetch_symbols(client: httpx.AsyncClient) -> list[tuple[str, float]]:
    api_syms, _meta = await _load_symbol_universe(client)
    r = await client.get(f"{FUTURES_BASE}/api/v1/contract/ticker")
    r.raise_for_status()
    payload = r.json()
    if not payload.get("success"):
        raise RuntimeError(f"MEXC futures ticker failed: {payload.get('code')}")

    rows = []
    skipped = 0
    for t in payload.get("data") or []:
        sym = t.get("symbol", "")
        if sym not in api_syms:
            skipped += 1
            continue
        # amount24 = 24h turnover in quote (USDT)
        vol = float(t.get("amount24") or 0)
        if vol >= MIN_VOL:
            rows.append((sym, vol))
    rows.sort(key=lambda x: x[1], reverse=True)
    print(
        f"[Device Care] Futures USDT pairs: {len(rows)} "
        f"(skipped {skipped} non-crypto/low-quality)"
    )
    return rows


async def fetch_klines(
    client: httpx.AsyncClient, symbol: str, interval: str, limit: int
) -> dict | None:
    """MEXC futures klines — times are unix seconds; convert to ms for UI."""
    end = int(time.time())
    # Interval seconds for start window (fetch a bit more than limit)
    interval_sec = {
        "Min60": 60 * 60,
        "Hour4": 4 * 3600,
        "Day1": 86400,
        "Week1": 7 * 86400,
    }.get(interval, 3600)
    start = end - interval_sec * (limit + 5)
    r = await client.get(
        f"{FUTURES_BASE}/api/v1/contract/kline/{symbol}",
        params={"interval": interval, "start": start, "end": end},
    )
    if r.status_code != 200:
        return None
    payload = r.json()
    if not payload.get("success"):
        return None
    data = payload.get("data") or {}
    times = data.get("time") or []
    opens = data.get("open") or []
    highs = data.get("high") or []
    lows = data.get("low") or []
    closes = data.get("close") or []
    if not times or len(times) < LOOKBACK + 3:
        return None
    # Keep last `limit` candles; convert seconds → ms for frontend Date()
    n = min(len(times), limit)
    return {
        "opens": [float(x) for x in opens[-n:]],
        "highs": [float(x) for x in highs[-n:]],
        "lows": [float(x) for x in lows[-n:]],
        "closes": [float(x) for x in closes[-n:]],
        "times": [int(x) * 1000 for x in times[-n:]],
    }


async def scan_loop():
    print("[Device Care] Strategy: 1H/4H S/R+triangle · D1/1W doji/hammer (+ score/entry/SL/TP)")
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            started = time.time()
            morning = in_morning_window()
            scan_stats["morningWindow"] = morning
            scan_stats["d1PatternsEnabled"] = True
            wait_sec = MORNING_SCAN_SEC if morning else SCAN_SEC
            # Subah: D1/1W pehle — daily/weekly candle patterns jaldi milen
            tf_order = (
                list(reversed(TIMEFRAMES)) if morning else list(TIMEFRAMES)
            )
            # Cooldown: breakout keys 1h, candle pattern keys 8h
            for key, seen_at in list(cooldown.items()):
                is_candle = any(p in key for p in CANDLE_PATTERNS)
                ttl = D1_PATTERN_ALERT_TTL_SEC if is_candle else BREAKOUT_ALERT_TTL_SEC
                if seen_at < started - ttl:
                    del cooldown[key]
            removed = prune_alert_history(started)
            if removed:
                _push_sse({
                    "type": "alerts_cleared",
                    "data": {"ids": [r["id"] for r in removed if r.get("id")]},
                })
                _broadcast_stats()
            scan_stats["phase"] = "fetching_pairs"
            scan_stats["scanned"] = 0
            scan_stats["errors"] = 0
            scan_stats["scannedCoins"] = []
            _broadcast_stats()
            try:
                symbols = await fetch_symbols(client)
                scan_stats["phase"] = "scanning"
                scan_stats["totalCoins"] = len(symbols)
                mode = (
                    "MORNING D1/1W patterns"
                    if morning
                    else "1H/4H S/R+triangle + D1/1W patterns"
                )
                print(
                    f"[Device Care] Scanning {len(symbols)} futures × {len(TIMEFRAMES)} TFs "
                    f"({mode}, wait={wait_sec}s)..."
                )
                for i, (sym, vol) in enumerate(symbols):
                    scan_stats["currentCoin"] = sym
                    scan_stats["scanned"] = i
                    coin_hits = 0
                    coin_err = False
                    for interval, tf_label, limit in tf_order:
                        scan_stats["currentTimeframe"] = tf_label
                        if i % 3 == 0:
                            _broadcast_stats()
                        ohlc = await fetch_klines(client, sym, interval, limit)
                        if not ohlc:
                            coin_err = True
                            scan_stats["errors"] += 1
                            await asyncio.sleep(0.05)
                            continue
                        for hit in scan_ohlc(ohlc, timeframe=tf_label):
                            key = (
                                f"{sym}:{tf_label}:{hit['pattern']}:"
                                f"{hit['direction']}:{hit['candleTime']}"
                            )
                            if key not in cooldown:
                                cooldown[key] = time.time()
                                alert = {
                                    "symbol": sym,
                                    "timeframe": tf_label,
                                    "volume": vol,
                                    "alertedAt": int(time.time() * 1000),
                                    **hit,
                                }
                                coin_hits += 1
                                print(
                                    f"[Device Care] {sym} {tf_label} "
                                    f"{hit['pattern']} {hit['direction']} "
                                    f"score={hit.get('score')} "
                                    f"E={hit.get('entry')} SL={hit.get('sl')} TP={hit.get('tp')}"
                                )
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

            # Wait loop — also prune expired alerts so UI clears on schedule
            for remaining in range(wait_sec, 0, -1):
                scan_stats["nextScanInSec"] = remaining
                scan_stats["morningWindow"] = in_morning_window()
                if remaining % 10 == 0:
                    removed = prune_alert_history()
                    if removed:
                        _push_sse({
                            "type": "alerts_cleared",
                            "data": {"ids": [r["id"] for r in removed if r.get("id")]},
                        })
                    _broadcast_stats()
                await asyncio.sleep(1)


def start_device_care_scanner():
    global _scan_task
    if _scan_task is not None:
        return
    loop = asyncio.get_running_loop()
    _scan_task = loop.create_task(scan_loop())
    print("[Device Care] PWA → /device-care (MEXC Futures)")
