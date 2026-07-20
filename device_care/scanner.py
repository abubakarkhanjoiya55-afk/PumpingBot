"""
My Signals — MEXC Futures multi-TF alert PWA (trade nahi, sirf alarm).
Mount: /my-signals  (legacy alias: /device-care)

Sirf USDT-M futures (spot nahi).
Strategy:
  - S/R Breakout only when level also exists on 4H + 1D + 1W (HTF confluence)
  - After breakout → Retest Wait (limit at level) + later Retest Complete
  - SL from prior breakout/swing area (last move), not just candle extreme
  - 5m / 15m / 1h / 4H / D1 / 1W toggles (default: 4H+1D+1W)
  - 1h / 4H / D1 → Triangle Breakout
  - D1 → Doji/Hammer patterns
Score >= 90 → ntfy push (app band ho tab bhi phone par alert).
"""
import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, RedirectResponse
from pydantic import BaseModel

APP_NAME = "My Signals"
APP_PREFIX = "/my-signals"
LEGACY_PREFIX = "/device-care"

STATIC = Path(__file__).parent / "static"
DATA_DIR = Path(__file__).parent / "data"
ALERT_STORE = DATA_DIR / "alerts.json"
COOLDOWN_STORE = DATA_DIR / "cooldown.json"
PENDING_RETEST_STORE = DATA_DIR / "pending_retests.json"
LOOKBACK = int(os.environ.get("DC_LOOKBACK", "20"))
SCAN_SEC = int(os.environ.get("DC_SCAN_SEC", "60"))
# Subah window mein tez scan — zyada coins jaldi dhoondne ke liye
MORNING_SCAN_SEC = int(os.environ.get("DC_MORNING_SCAN_SEC", "40"))
MORNING_START_HOUR = int(os.environ.get("DC_MORNING_START_HOUR", "5"))
MORNING_END_HOUR = int(os.environ.get("DC_MORNING_END_HOUR", "9"))
PKT_OFFSET_HOURS = int(os.environ.get("DC_PKT_OFFSET_HOURS", "5"))
MIN_VOL = float(os.environ.get("DC_MIN_VOLUME", "300000"))
TRIANGLE_WINDOW = int(os.environ.get("DC_TRIANGLE_WINDOW", "18"))
SYMBOL_CACHE_SEC = int(os.environ.get("DC_SYMBOL_CACHE_SEC", "3600"))
# Alert history TTL — triangles jaldi clear, candle patterns zyada der
BREAKOUT_ALERT_TTL_SEC = int(os.environ.get("DC_BREAKOUT_ALERT_TTL_SEC", "3600"))  # 1h history
D1_PATTERN_ALERT_TTL_SEC = int(os.environ.get("DC_D1_ALERT_TTL_SEC", str(8 * 3600)))  # 8h
STRONG_SCORE = int(os.environ.get("DC_STRONG_SCORE", "90"))
RETEST_TTL_SEC = int(os.environ.get("DC_RETEST_TTL_SEC", str(24 * 3600)))
RETEST_TOUCH_TOL = float(os.environ.get("DC_RETEST_TOUCH_TOL", "0.008"))
# Same signal dubara na aaye — pattern-wise cooldown (candleTime/LIVE ignore)
PATTERN_COOLDOWN_SEC = {
    "S/R Breakout": int(os.environ.get("DC_SR_COOLDOWN_SEC", str(6 * 3600))),
    "Retest Wait": int(os.environ.get("DC_RETEST_WAIT_COOLDOWN_SEC", str(6 * 3600))),
    "Retest Complete": int(os.environ.get("DC_RETEST_DONE_COOLDOWN_SEC", str(12 * 3600))),
    "Triangle Breakout": int(os.environ.get("DC_TRI_COOLDOWN_SEC", str(4 * 3600))),
    "Dragonfly Doji": D1_PATTERN_ALERT_TTL_SEC,
    "Hammer": D1_PATTERN_ALERT_TTL_SEC,
    "Doji + Green": D1_PATTERN_ALERT_TTL_SEC,
}
# Pending retests after S/R breakout: key -> meta
pending_retests: dict[str, dict] = {}
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "pumpingbot-signals")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TITLE = os.environ.get("NTFY_TITLE", "My Signals")

FUTURES_BASE = "https://contract.mexc.com"
CANDLE_PATTERNS = frozenset({"Dragonfly Doji", "Hammer", "Doji + Green"})
# Back-compat alias used by TTL helpers
D1_PATTERNS = CANDLE_PATTERNS
# User kisi bhi TF ko on/off kar sakta hai
BREAKOUT_TFS = frozenset({"5m", "15m", "1h", "4H", "D1", "1W"})
TRIANGLE_TFS = frozenset({"1h", "4H", "D1"})
CANDLE_TFS = frozenset({"D1"})
SIGNAL_CAPABLE_TFS = frozenset({"5m", "15m", "1h", "4H", "D1", "1W"})
# S/R must align on these higher timeframes (fake breakout filter)
CONFLUENCE_TFS = ("4H", "D1", "1W")
CONFLUENCE_FETCH = [
    ("Hour4", "4H", 60),
    ("Day1", "D1", 50),
    ("Week1", "1W", 40),
]
SR_CONFLUENCE_TOL = float(os.environ.get("DC_SR_CONFLUENCE_TOL", "0.015"))  # 1.5%

# Fiat, stablecoins, commodities — futures crypto scan se bahar
STABLE_FIAT_BASES = frozenset({
    "USDC", "USDE", "USD1", "USDF", "DAI", "TUSD", "FDUSD", "BUSD",
    "EUR", "BRL", "EURI", "EURR", "GBP", "JPY", "AUD", "CAD", "CHF", "TRY",
    "XAUT", "PAXG", "XAU", "XAG", "SILVER", "GOLD",
})

_api_symbols_cache: set[str] | None = None
_symbol_meta_cache: dict[str, dict] | None = None
_symbol_cache_at: float = 0

# Saari TFs scan ho sakti hain — default 4H+D1 ON, baaki user on kare
TIMEFRAMES = [
    ("Min5", "5m", 80),
    ("Min15", "15m", 80),
    ("Min60", "1h", 70),
    ("Hour4", "4H", 60),
    ("Day1", "D1", 50),
    ("Week1", "1W", 40),
]

TF_BUTTONS = [
    {"id": "5m", "label": "5m", "capable": True},
    {"id": "15m", "label": "15m", "capable": True},
    {"id": "1h", "label": "1H", "capable": True},
    {"id": "4H", "label": "4H", "capable": True},
    {"id": "D1", "label": "1D", "capable": True},
    {"id": "1W", "label": "1W", "capable": True},
]
enabled_tfs: dict[str, bool] = {
    "5m": False,
    "15m": False,
    "1h": False,
    "4H": True,
    "D1": True,
    "1W": True,
}

router = APIRouter(prefix=APP_PREFIX, tags=["my-signals"])
legacy_router = APIRouter(prefix=LEGACY_PREFIX, tags=["my-signals-legacy"])
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
    "appName": APP_NAME,
    "timeframes": [tf[1] for tf in TIMEFRAMES],
    "tfButtons": TF_BUTTONS,
    "enabledTfs": dict(enabled_tfs),
    "patterns": [
        "S/R Breakout",
        "Retest Wait",
        "Retest Complete",
        "Triangle Breakout",
        "Dragonfly Doji",
        "Hammer",
        "Doji + Green",
    ],
    "strategy": {
        "5m": "S/R LIVE (user toggle)",
        "15m": "S/R LIVE (user toggle)",
        "1h": "S/R LIVE + Triangle (user toggle)",
        "4H": "S/R LIVE + Triangle (user toggle)",
        "D1": "S/R LIVE + Triangle + Doji/Hammer (user toggle)",
    },
    "exchange": "MEXC Futures",
    "market": "futures",
    "minVolumeUsdt": MIN_VOL,
    "lookback": LOOKBACK,
    "nextScanInSec": 0,
    "scannedCoins": [],
    "morningWindow": False,
    "d1PatternsEnabled": True,
    "breakoutAlertTtlSec": BREAKOUT_ALERT_TTL_SEC,
    "d1AlertTtlSec": D1_PATTERN_ALERT_TTL_SEC,
    "strongScore": STRONG_SCORE,
    "ntfyEnabled": bool(NTFY_TOPIC),
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


class TfToggle(BaseModel):
    timeframe: str
    enabled: bool


@router.get("/api/status")
async def status():
    prune_alert_history()
    scan_stats["enabledTfs"] = dict(enabled_tfs)
    scan_stats["tfButtons"] = TF_BUTTONS
    return {"ok": True, "app": APP_NAME, **scan_stats}


@router.get("/api/alerts")
async def alerts():
    prune_alert_history()
    return [_normalize_alert(a) for a in alert_history[:80]]


@router.get("/api/timeframes")
async def get_timeframes():
    return {
        "buttons": TF_BUTTONS,
        "enabled": dict(enabled_tfs),
        "signalCapable": sorted(SIGNAL_CAPABLE_TFS),
        "note": "S/R signals sirf jab level 4H+1D+1W pe align ho. TF on/off: 5m–1W.",
    }


@router.post("/api/timeframes")
async def set_timeframe(body: TfToggle):
    tf = body.timeframe
    if tf not in enabled_tfs:
        raise HTTPException(400, f"Unknown timeframe: {tf}")
    if tf not in SIGNAL_CAPABLE_TFS:
        raise HTTPException(400, f"{tf} supported nahi")
    if not body.enabled:
        others_on = [k for k, v in enabled_tfs.items() if k != tf and v]
        if not others_on:
            raise HTTPException(400, "Kam az kam 1 timeframe on rakhni zaroori hai")
    enabled_tfs[tf] = bool(body.enabled)
    scan_stats["enabledTfs"] = dict(enabled_tfs)
    _broadcast_stats()
    return {"ok": True, "enabled": dict(enabled_tfs)}


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
        "advice": alert.get("advice"),
        "stage": alert.get("stage"),
        "at": alert.get("alertedAt") or alert.get("at"),
    }


def _is_d1_pattern_alert(alert: dict) -> bool:
    return alert.get("pattern") in CANDLE_PATTERNS


def _alert_ttl_sec(alert: dict) -> int:
    """S/R + Triangle + retest alerts 1h (retest wait can live longer via pending), candles 8h."""
    if _is_d1_pattern_alert(alert):
        return D1_PATTERN_ALERT_TTL_SEC
    if alert.get("pattern") in ("Retest Wait", "Retest Complete"):
        return max(BREAKOUT_ALERT_TTL_SEC, 2 * 3600)
    return BREAKOUT_ALERT_TTL_SEC


def _level_key(level) -> str:
    try:
        v = float(level)
    except (TypeError, ValueError):
        return "0"
    if abs(v) >= 100:
        return f"{v:.2f}"
    if abs(v) >= 1:
        return f"{v:.4f}"
    if abs(v) >= 0.01:
        return f"{v:.5f}"
    return f"{v:.6g}"


def signal_fingerprint(sym: str, tf: str, hit: dict) -> str:
    """
    Unique signal id for cooldown — LIVE/CLOSED aur exact candleTime ignore.
    Same coin + TF + pattern + direction + level = ek hi signal.
    """
    pattern = hit.get("pattern") or ""
    direction = hit.get("direction") or ""
    level = hit.get("level") if hit.get("level") is not None else (
        hit.get("entry") if hit.get("entry") is not None else hit.get("close")
    )
    if pattern in CANDLE_PATTERNS:
        ct = int(hit.get("candleTime") or 0)
        day = ct // 86_400_000 if ct else 0
        return f"{sym}|{tf}|{pattern}|{direction}|day{day}"
    return f"{sym}|{tf}|{pattern}|{direction}|{_level_key(level)}"


def cooldown_ttl_for(pattern: str) -> int:
    return int(PATTERN_COOLDOWN_SEC.get(pattern or "", BREAKOUT_ALERT_TTL_SEC))


def prune_cooldown(now: float | None = None):
    now = now or time.time()
    for key, seen_at in list(cooldown.items()):
        # key: sym|tf|pattern|direction|level
        parts = key.split("|")
        pattern = parts[2] if len(parts) >= 3 else ""
        ttl = cooldown_ttl_for(pattern)
        if seen_at < now - ttl:
            del cooldown[key]


def _persist_cooldown():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        COOLDOWN_STORE.write_text(
            json.dumps(cooldown, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[My Signals] cooldown persist failed: {e}")


def _load_persisted_cooldown():
    global cooldown
    try:
        if COOLDOWN_STORE.is_file():
            raw = json.loads(COOLDOWN_STORE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cooldown.clear()
                cooldown.update({str(k): float(v) for k, v in raw.items()})
        # Seed from alert history so restart pe purani signals dubara na aayein
        for a in alert_history:
            sym = a.get("symbol") or ""
            tf = a.get("timeframe") or ""
            if not sym:
                continue
            fp = signal_fingerprint(sym, tf, a)
            at_ms = a.get("alertedAt") or a.get("at") or 0
            at = (at_ms / 1000.0) if at_ms > 1e12 else float(at_ms or 0)
            if at <= 0:
                at = time.time()
            prev = cooldown.get(fp, 0)
            if at > prev:
                cooldown[fp] = at
        prune_cooldown()
        _persist_cooldown()
        print(f"[My Signals] Cooldown loaded: {len(cooldown)} fingerprints")
    except Exception as e:
        print(f"[My Signals] cooldown restore failed: {e}")


def _persist_pending_retests():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        PENDING_RETEST_STORE.write_text(
            json.dumps(pending_retests, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[My Signals] pending retest persist failed: {e}")


def _load_persisted_pending_retests():
    global pending_retests
    try:
        if not PENDING_RETEST_STORE.is_file():
            return
        raw = json.loads(PENDING_RETEST_STORE.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            pending_retests.clear()
            pending_retests.update(raw)
            print(f"[My Signals] Pending retests restored: {len(pending_retests)}")
    except Exception as e:
        print(f"[My Signals] pending retest restore failed: {e}")


def mark_signal_cooldown(sym: str, tf: str, hit: dict) -> str:
    fp = signal_fingerprint(sym, tf, hit)
    cooldown[fp] = time.time()
    _persist_cooldown()
    return fp


def is_signal_cooled(sym: str, tf: str, hit: dict) -> bool:
    fp = signal_fingerprint(sym, tf, hit)
    seen = cooldown.get(fp)
    if not seen:
        return False
    ttl = cooldown_ttl_for(hit.get("pattern") or "")
    if seen < time.time() - ttl:
        del cooldown[fp]
        return False
    return True


def _load_persisted_alerts():
    """Restart ke baad purani alerts wapas lao."""
    global alert_history
    try:
        if not ALERT_STORE.is_file():
            return
        raw = json.loads(ALERT_STORE.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            alert_history[:] = raw[:80]
            prune_alert_history()
            scan_stats["alertsTotal"] = len(alert_history)
            print(f"[My Signals] Restored {len(alert_history)} alerts from disk")
    except Exception as e:
        print(f"[My Signals] alert restore failed: {e}")


def _persist_alerts():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        ALERT_STORE.write_text(
            json.dumps(alert_history[:80], ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[My Signals] alert persist failed: {e}")


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
        _persist_alerts()
    return removed_ids


async def _send_ntfy_strong(alert: dict):
    """App band ho tab bhi score>=90 signals phone par (ntfy)."""
    score = float(alert.get("score") or 0)
    if score < STRONG_SCORE or not NTFY_TOPIC:
        return
    sym = (alert.get("symbol") or "").replace("_USDT", "")
    side = alert.get("side") or alert.get("direction") or ""
    tf = alert.get("timeframe") or ""
    body = (
        f"{sym} {side} · {tf} · score {int(score)}\n"
        f"Entry {alert.get('entry')} | SL {alert.get('sl')} | TP {alert.get('tp')}\n"
        f"{alert.get('pattern') or 'Breakout'} {alert.get('patternDetail') or ''}"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{NTFY_SERVER}/{NTFY_TOPIC}",
                content=body.encode("utf-8"),
                headers={
                    "Title": f"{NTFY_TITLE} {sym} {side}",
                    "Priority": "5",
                    "Tags": "rotating_light,chart_with_upwards_trend",
                },
            )
            if r.status_code >= 300:
                print(f"[My Signals] ntfy fail: {r.status_code}")
            else:
                print(f"[My Signals] ntfy strong alert sent: {sym} score={score}")
    except Exception as e:
        print(f"[My Signals] ntfy error: {e}")


def _broadcast(alert: dict):
    # Stable id — LIVE tag se naya id na bane (duplicate UI/alarm avoid)
    if not alert.get("id"):
        sym = alert.get("symbol") or ""
        tf = alert.get("timeframe") or ""
        alert["id"] = signal_fingerprint(sym, tf, alert).replace("|", "-")
    prune_alert_history()
    alert_history.insert(0, alert)
    del alert_history[80:]
    scan_stats["alertsTotal"] = len(alert_history)
    _persist_alerts()
    _push_sse({"type": "alert", "data": _normalize_alert(alert)})
    _broadcast_stats()
    # Strong signals → background push even if PWA closed
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send_ntfy_strong(alert))
    except RuntimeError:
        pass


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
    i = -1 if hit.get("live") else -2
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
        # Stronger baseline — fake breaks filtered via HTF confluence in scan_loop
        score = 72
        if hit.get("htfConfluence"):
            score = 80
        prior_sl = _prior_breakout_sl(ohlc, direction, level, i, buffer)
        if direction == "UP":
            dist = (close - level) / (avg_rng or 0.0001)
            # Prefer prior-area SL (slightly above last swing zone); fallback candle
            sl = prior_sl if prior_sl is not None else (candle_low - buffer)
            if prior_sl is not None and prior_sl >= entry:
                sl = min(candle_low, level) - buffer
        else:
            dist = (level - close) / (avg_rng or 0.0001)
            sl = prior_sl if prior_sl is not None else (candle_high + buffer)
            if prior_sl is not None and prior_sl <= entry:
                sl = max(candle_high, level) + buffer
        score += min(14, int(dist * 8))
        score += min(10, int(body_str * 7))
        if direction == "UP" and close > level * 1.003:
            score += 6
        if direction == "DOWN" and close < level * 0.997:
            score += 6
        # Reject-style wick penalty (fake break scent)
        rng = max(candle_high - candle_low, 1e-12)
        if direction == "UP":
            upper_wick = candle_high - max(close, float(o[i]))
            if upper_wick / rng > 0.45:
                score -= 10
        else:
            lower_wick = min(close, float(o[i])) - candle_low
            if lower_wick / rng > 0.45:
                score -= 10

    elif pattern in ("Retest Wait", "Retest Complete"):
        # Limit / entry at broken S/R level — wait or confirmed retest
        score = 70 if pattern == "Retest Wait" else 84
        if hit.get("htfConfluence"):
            score += 6
        entry = float(hit.get("entryOverride") or level or close)
        prior_sl = _prior_breakout_sl(ohlc, direction, level or entry, i, buffer)
        if direction == "UP":
            sl = prior_sl if prior_sl is not None else (entry - buffer * 2)
            if sl >= entry:
                sl = entry - max(buffer * 2, abs(entry) * 0.004)
        else:
            sl = prior_sl if prior_sl is not None else (entry + buffer * 2)
            if sl <= entry:
                sl = entry + max(buffer * 2, abs(entry) * 0.004)
        # Slightly tighter RR for wait; stronger for complete
        if pattern == "Retest Complete":
            score += 4

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


def build_retest_wait_hit(ohlc: dict, breakout: dict) -> dict:
    """
    Breakout ke turant baad: retest abhi nahi hua —
    level pe limit lagao, wait karo. SL/TP saath.
    """
    level = float(breakout.get("level") or breakout.get("entry") or 0)
    direction = breakout.get("direction", "UP")
    lvl_txt = _round_price(level)
    if direction == "UP":
        advice = (
            f"Breakout ho chuka hai lekin abi retest nahi hua. "
            f"Level {lvl_txt} pe limit lagao aur retest ka wait karo. "
            f"SL/TP plan saath mein diya hai."
        )
    else:
        advice = (
            f"Support break ho chuka hai lekin abi retest nahi hua. "
            f"Level {lvl_txt} pe limit lagao aur retest ka wait karo. "
            f"SL/TP plan saath mein diya hai."
        )
    hit = {
        "side": breakout.get("side", "BUY" if direction == "UP" else "SELL"),
        "direction": direction,
        "pattern": "Retest Wait",
        "patternDetail": f"Breakout done · retest pending · limit @ {lvl_txt}",
        "level": level,
        "close": breakout.get("close"),
        "candleTime": breakout.get("candleTime"),
        "live": False,
        "htfConfluence": breakout.get("htfConfluence"),
        "entryOverride": level,
        "advice": advice,
        "stage": "wait",
    }
    return enrich_trade_plan(ohlc, hit)


def detect_retest_complete(ohlc: dict, pending: dict) -> dict | None:
    """
    Price ne broken level ko touch kiya aur hold kiya → Retest Complete signal.
    """
    h, l, c, t = ohlc["highs"], ohlc["lows"], ohlc["closes"], ohlc["times"]
    if len(c) < 4:
        return None
    i = -2  # last closed
    direction = pending.get("direction", "UP")
    level = float(pending.get("level") or 0)
    if level <= 0:
        return None
    brk_time = pending.get("candleTime") or 0
    if t[i] <= brk_time:
        return None
    tol = max(abs(level) * RETEST_TOUCH_TOL, _avg_range(ohlc) * 0.15)
    if direction == "UP":
        touched = l[i] <= level + tol
        held = c[i] >= level - tol * 0.5
        if not (touched and held):
            # Fake: closed hard back below level
            if l[i] <= level + tol and c[i] < level - tol:
                pending["failed"] = True
            return None
        advice = (
            f"Retest complete @ {_round_price(level)}. "
            f"Ab long entry / limit fill zone. SL neeche, TP upar plan dekho."
        )
    else:
        touched = h[i] >= level - tol
        held = c[i] <= level + tol * 0.5
        if not (touched and held):
            if h[i] >= level - tol and c[i] > level + tol:
                pending["failed"] = True
            return None
        advice = (
            f"Retest complete @ {_round_price(level)}. "
            f"Ab short entry / limit fill zone. SL upar, TP neeche plan dekho."
        )
    hit = {
        "side": "BUY" if direction == "UP" else "SELL",
        "direction": direction,
        "pattern": "Retest Complete",
        "patternDetail": f"Retest ho chuka · entry zone {_round_price(level)}",
        "level": level,
        "close": c[i],
        "candleTime": t[i],
        "live": False,
        "htfConfluence": pending.get("htfConfluence"),
        "entryOverride": level,
        "advice": advice,
        "stage": "complete",
    }
    return enrich_trade_plan(ohlc, hit)


def register_pending_retest(sym: str, tf_label: str, breakout: dict):
    key = f"{sym}:{tf_label}:{breakout.get('direction')}"
    pending_retests[key] = {
        "symbol": sym,
        "tf": tf_label,
        "direction": breakout.get("direction"),
        "level": float(breakout.get("level") or 0),
        "candleTime": breakout.get("candleTime"),
        "htfConfluence": breakout.get("htfConfluence"),
        "at": time.time(),
        "wait_sent": True,
        "complete_sent": False,
        "failed": False,
    }
    _persist_pending_retests()


def _prior_breakout_sl(
    ohlc: dict, direction: str, level: float, i: int, buffer: float
) -> float | None:
    """
    Resistance break (LONG): pehle dekho last time price kahan tak gaya (swing low
    area), phir us area se zara sa UPAR SL — fake break pe jaldi nikalne ke liye.
    Support break (SHORT): last swing high area se zara sa NEECHE SL.
    """
    h, l, c = ohlc["highs"], ohlc["lows"], ohlc["closes"]
    end = len(c) + i if i < 0 else i  # positive index of signal candle
    if end < 6:
        return None
    start = max(0, end - LOOKBACK * 4)
    hist_l = l[start:end]
    hist_h = h[start:end]
    if len(hist_l) < 5:
        return None

    if direction == "UP":
        swing_lows: list[float] = []
        for j in range(1, len(hist_l) - 1):
            if hist_l[j] <= hist_l[j - 1] and hist_l[j] <= hist_l[j + 1] and hist_l[j] < level:
                swing_lows.append(hist_l[j])
        zone = swing_lows[-1] if swing_lows else min(hist_l[-8:])
        # Last-time area se zara sa upar
        return float(zone) + max(buffer * 0.4, abs(level) * 0.0008)
    swing_highs: list[float] = []
    for j in range(1, len(hist_h) - 1):
        if hist_h[j] >= hist_h[j - 1] and hist_h[j] >= hist_h[j + 1] and hist_h[j] > level:
            swing_highs.append(hist_h[j])
    zone = swing_highs[-1] if swing_highs else max(hist_h[-8:])
    # Last-time area se zara sa neeche
    return float(zone) - max(buffer * 0.4, abs(level) * 0.0008)


def extract_sr_levels(ohlc: dict, lookback: int = LOOKBACK) -> tuple[float | None, float | None]:
    """Closed-candle S/R from candles before the latest closed bar."""
    h, l = ohlc["highs"], ohlc["lows"]
    if len(h) < lookback + 3:
        return None, None
    rh = max(h[-lookback - 2:-2])
    rl = min(l[-lookback - 2:-2])
    return float(rh), float(rl)


def has_sr_confluence(
    level: float,
    direction: str,
    htf_levels: dict[str, tuple[float | None, float | None]],
    price: float,
    *,
    required: tuple[str, ...] = CONFLUENCE_TFS,
) -> bool:
    """
    Breakout level must exist as resistance (UP) or support (DOWN)
    on at least 4H + 1D + 1W.
    """
    if not level or not price or price <= 0:
        return False
    tol = max(abs(price) * SR_CONFLUENCE_TOL, abs(level) * 0.008)
    for tf in required:
        pair = htf_levels.get(tf)
        if not pair or pair[0] is None or pair[1] is None:
            return False
        rh, rl = pair
        ref = rh if direction == "UP" else rl
        if abs(float(ref) - float(level)) > tol:
            return False
    return True


def _body_ok(highs, lows, closes, opens, idx: int, min_frac: float = 0.3) -> bool:
    body = abs(closes[idx] - opens[idx])
    ranges = [highs[j] - lows[j] for j in range(max(0, len(highs) - 12), len(highs) - 1)]
    avg = sum(ranges) / max(len(ranges), 1)
    return body >= avg * min_frac


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


def detect_sr_breakout(
    ohlc: dict, lookback: int = LOOKBACK, *, live: bool = False
) -> dict | None:
    """
    S/R breakout on closed candle (-2) or LIVE forming candle (-1).
    Stricter body + distance filters to cut fake pierces.
    HTF 4H/1D/1W confluence is applied in scan_loop.
    """
    h, l, c, o, t = ohlc["highs"], ohlc["lows"], ohlc["closes"], ohlc["opens"], ohlc["times"]
    i = -1 if live else -2
    need = lookback + (2 if live else 3)
    if len(c) < need:
        return None
    # Reference levels must end before the candle being evaluated.
    if live:
        rh = max(h[-lookback - 1:-1])
        rl = min(l[-lookback - 1:-1])
        body_frac = 0.28  # LIVE bhi strong body — weak wick pierce skip
    else:
        rh = max(h[-lookback - 2:i])
        rl = min(l[-lookback - 2:i])
        body_frac = 0.32
    if not _body_ok(h, l, c, o, i, min_frac=body_frac):
        return None
    avg_rng = _avg_range(ohlc) or abs(c[i]) * 0.01
    min_break = max(avg_rng * 0.12, abs(c[i]) * 0.0015)
    detail_suffix = " (LIVE)" if live else ""
    # Prefer real close break; LIVE still allows strong high/low pierce
    buy_hit = (c[i] > rh + min_break * 0.35 and c[i - 1] <= rh) or (
        live and h[i] > rh + min_break and c[i - 1] <= rh and c[i] >= rh
    )
    sell_hit = (c[i] < rl - min_break * 0.35 and c[i - 1] >= rl) or (
        live and l[i] < rl - min_break and c[i - 1] >= rl and c[i] <= rl
    )
    # Fake-break wick filter on closed candles
    if not live and buy_hit:
        rng = max(h[i] - l[i], 1e-12)
        if (h[i] - max(c[i], o[i])) / rng > 0.5 and c[i] < rh + min_break:
            return None
    if not live and sell_hit:
        rng = max(h[i] - l[i], 1e-12)
        if (min(c[i], o[i]) - l[i]) / rng > 0.5 and c[i] > rl - min_break:
            return None
    if buy_hit:
        return {
            "side": "BUY", "direction": "UP", "pattern": "S/R Breakout",
            "patternDetail": f"Resistance breakout{detail_suffix}",
            "level": rh, "close": c[i], "candleTime": t[i],
            "live": live,
        }
    if sell_hit:
        return {
            "side": "SELL", "direction": "DOWN", "pattern": "S/R Breakout",
            "patternDetail": f"Support breakdown{detail_suffix}",
            "level": rl, "close": c[i], "candleTime": t[i],
            "live": live,
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


def scan_ohlc(
    ohlc: dict,
    *,
    timeframe: str = "",
    include_d1_patterns: bool = False,
    htf_confluence: bool = False,
) -> list[dict]:
    """
    TF-gated strategy:
      Breakout TFs → S/R LIVE-first + Triangle (1h+)
      D1 → also Dragonfly/Hammer/Doji + green close
    htf_confluence=True marks S/R hits that already passed 4H+1D+1W gate.
    """
    hits: list[dict] = []
    tf = timeframe or ""

    run_breakouts = tf in BREAKOUT_TFS or (not tf and not include_d1_patterns)
    run_triangle = tf in TRIANGLE_TFS or (not tf and not include_d1_patterns)
    run_candles = tf in CANDLE_TFS or include_d1_patterns

    if run_breakouts:
        # LIVE first — breakout hoti hi signal (pump wait nahi)
        seen_dirs: set[str] = set()
        for live in (True, False):
            sr = detect_sr_breakout(ohlc, live=live)
            if not sr:
                continue
            if sr["direction"] in seen_dirs:
                continue
            seen_dirs.add(sr["direction"])
            if htf_confluence:
                sr["htfConfluence"] = True
                sr["patternDetail"] = (
                    f"{sr.get('patternDetail', 'S/R')} · HTF 4H+1D+1W"
                )
            hits.append(enrich_trade_plan(ohlc, sr))
        if run_triangle:
            tri = detect_triangle_breakout(ohlc)
            if tri and tri["direction"] not in seen_dirs:
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
    print(f"[My Signals] MEXC Futures USDT contracts loaded: {len(api_syms)}")
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
        f"[My Signals] Futures USDT pairs: {len(rows)} "
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
        "Min5": 5 * 60,
        "Min15": 15 * 60,
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
    print("[My Signals] Strategy: HTF 4H+1D+1W S/R confluence · prior-area SL · strong>=90 ntfy")
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            started = time.time()
            morning = in_morning_window()
            scan_stats["morningWindow"] = morning
            scan_stats["d1PatternsEnabled"] = True
            scan_stats["enabledTfs"] = dict(enabled_tfs)
            scan_stats["confluenceTfs"] = list(CONFLUENCE_TFS)
            wait_sec = MORNING_SCAN_SEC if morning else SCAN_SEC
            # Only scan TFs that are both capable and enabled
            active_tfs = [
                row for row in TIMEFRAMES
                if row[1] in SIGNAL_CAPABLE_TFS and enabled_tfs.get(row[1], True)
            ]
            if not active_tfs:
                active_tfs = list(TIMEFRAMES)
            # Subah: D1/1W pehle
            tf_order = (
                list(reversed(active_tfs)) if morning else list(active_tfs)
            )
            # Cooldown prune — fingerprint based (pattern TTL)
            prune_cooldown(started)
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
                mode = "MORNING HTF first" if morning else "4H+1D+1W confluence"
                print(
                    f"[My Signals] Scanning {len(symbols)} futures × {len(tf_order)} TFs "
                    f"({mode}, wait={wait_sec}s)..."
                )
                new_alerts = 0
                for i, (sym, vol) in enumerate(symbols):
                    scan_stats["currentCoin"] = sym
                    scan_stats["scanned"] = i
                    coin_hits = 0
                    coin_err = False
                    ohlc_cache: dict[str, dict] = {}
                    # Always load 4H + 1D + 1W for S/R confluence gate
                    htf_levels: dict[str, tuple[float | None, float | None]] = {}
                    for interval, tf_label, limit in CONFLUENCE_FETCH:
                        ohlc_htf = await fetch_klines(client, sym, interval, limit)
                        if ohlc_htf:
                            ohlc_cache[tf_label] = ohlc_htf
                            htf_levels[tf_label] = extract_sr_levels(ohlc_htf)
                        else:
                            htf_levels[tf_label] = (None, None)
                        await asyncio.sleep(0.02)

                    for interval, tf_label, limit in tf_order:
                        scan_stats["currentTimeframe"] = tf_label
                        if i % 3 == 0:
                            _broadcast_stats()
                        ohlc = ohlc_cache.get(tf_label)
                        if ohlc is None:
                            ohlc = await fetch_klines(client, sym, interval, limit)
                            if ohlc:
                                ohlc_cache[tf_label] = ohlc
                        if not ohlc:
                            coin_err = True
                            scan_stats["errors"] += 1
                            await asyncio.sleep(0.04)
                            continue
                        raw_hits = scan_ohlc(ohlc, timeframe=tf_label)
                        filtered: list[dict] = []
                        for hit in raw_hits:
                            if hit.get("pattern") == "S/R Breakout":
                                if not has_sr_confluence(
                                    float(hit.get("level") or 0),
                                    hit.get("direction", "UP"),
                                    htf_levels,
                                    float(hit.get("close") or hit.get("entry") or 0),
                                ):
                                    continue
                                # Re-enrich with confluence flag for better score/SL context
                                hit["htfConfluence"] = True
                                detail = hit.get("patternDetail") or "S/R Breakout"
                                if "HTF 4H+1D+1W" not in detail:
                                    hit["patternDetail"] = f"{detail} · HTF 4H+1D+1W"
                                hit = enrich_trade_plan(ohlc, hit)
                                lvl = hit.get("level")
                                hit["advice"] = (
                                    f"Breakout confirm. Level {lvl}. "
                                    f"Abhi retest ka wait — limit plan alag alert mein."
                                )
                                hit["stage"] = "breakout"
                            filtered.append(hit)
                        # Pending retest complete check for this TF
                        for rk, pending in list(pending_retests.items()):
                            if pending.get("symbol") != sym or pending.get("tf") != tf_label:
                                continue
                            if time.time() - pending.get("at", 0) > RETEST_TTL_SEC:
                                del pending_retests[rk]
                                continue
                            if pending.get("complete_sent") or pending.get("failed"):
                                if pending.get("failed"):
                                    del pending_retests[rk]
                                    _persist_pending_retests()
                                continue
                            done = detect_retest_complete(ohlc, pending)
                            if done:
                                filtered.append(done)
                                pending["complete_sent"] = True
                                _persist_pending_retests()
                        # Prefer CLOSED over LIVE for same fingerprint in this batch
                        filtered.sort(key=lambda h: 1 if h.get("live") else 0)
                        emitted_fps: set[str] = set()
                        for hit in filtered:
                            fp = signal_fingerprint(sym, tf_label, hit)
                            if fp in emitted_fps or is_signal_cooled(sym, tf_label, hit):
                                continue
                            emitted_fps.add(fp)
                            mark_signal_cooldown(sym, tf_label, hit)
                            live_tag = "LIVE" if hit.get("live") else "CLOSED"
                            alert = {
                                "symbol": sym,
                                "timeframe": tf_label,
                                "volume": vol,
                                "alertedAt": int(time.time() * 1000),
                                **hit,
                            }
                            coin_hits += 1
                            new_alerts += 1
                            print(
                                f"[My Signals] {sym} {tf_label} "
                                f"{hit['pattern']} {hit['direction']} "
                                f"{live_tag} score={hit.get('score')} "
                                f"E={hit.get('entry')} SL={hit.get('sl')} TP={hit.get('tp')}"
                                f"{' · HTF' if hit.get('htfConfluence') else ''}"
                            )
                            _broadcast(alert)
                            # Breakout ke baad turant Retest Wait — sirf ek dafa
                            if hit.get("pattern") == "S/R Breakout":
                                wait_hit = build_retest_wait_hit(ohlc, hit)
                                wait_fp = signal_fingerprint(sym, tf_label, wait_hit)
                                if wait_fp not in emitted_fps and not is_signal_cooled(
                                    sym, tf_label, wait_hit
                                ):
                                    emitted_fps.add(wait_fp)
                                    mark_signal_cooldown(sym, tf_label, wait_hit)
                                    wait_alert = {
                                        "symbol": sym,
                                        "timeframe": tf_label,
                                        "volume": vol,
                                        "alertedAt": int(time.time() * 1000),
                                        **wait_hit,
                                    }
                                    coin_hits += 1
                                    new_alerts += 1
                                    print(
                                        f"[My Signals] {sym} {tf_label} Retest Wait "
                                        f"{hit['direction']} limit={wait_hit.get('entry')}"
                                    )
                                    _broadcast(wait_alert)
                                    register_pending_retest(sym, tf_label, hit)
                        await asyncio.sleep(0.04)
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
                print(f"[My Signals] Scan done — {new_alerts} new alert(s)")
                _broadcast_stats()
            except Exception as e:
                scan_stats["phase"] = "error"
                print(f"[My Signals] scan error: {e}")
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


@legacy_router.get("")
@legacy_router.get("/")
@legacy_router.get("/{path:path}")
async def legacy_device_care_redirect(path: str = ""):
    """Old /device-care links → /my-signals"""
    target = f"{APP_PREFIX}/" if not path else f"{APP_PREFIX}/{path}"
    return RedirectResponse(url=target, status_code=307)


def start_device_care_scanner():
    global _scan_task
    if _scan_task is not None:
        return
    _load_persisted_alerts()
    _load_persisted_pending_retests()
    _load_persisted_cooldown()
    loop = asyncio.get_running_loop()
    _scan_task = loop.create_task(scan_loop())
    print("[My Signals] PWA → /my-signals (HTF breakouts + retest, deduped cooldown)")
