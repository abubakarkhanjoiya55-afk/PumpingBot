"""
PumpingBot Trading Engine - M1 candle-pattern strategy (no indicators).

Entry: 1-minute closed candle patterns + direction confirmation.
Sizing: score-based risk multiplier (higher score -> more margin/lot).
"""

# ─── Engine constants ─────────────────────────────────────────────────────────
DAILY_MAX_LOSS_PCT    = 0.015
DAILY_PROFIT_TARGET   = 0.05
DAILY_TRAIL_START     = 0.03
DAILY_TRAIL_GAP       = 0.01
RISK_PER_TRADE_PCT    = 0.004   # demo USD accuracy test sizing
MAX_OPEN_TRADES       = 1       # one bot trade at a time
MAX_TRADES_PER_SYMBOL = 1
MIN_PATTERN_SCORE     = 60      # demo: clear setups (still needs H1+M15 agree)
STRONG_SCORE          = 72      # strong trend -> FAST_SCALP
MIN_BREAKOUT_SCORE    = MIN_PATTERN_SCORE  # legacy alias used by main.py
MIN_SCORE             = MIN_PATTERN_SCORE
MIN_TREND_STRUCTURE   = 20      # H1 structure floor
MIN_EFFECTIVE_SCORE   = MIN_PATTERN_SCORE
MIN_CONFLUENCE        = 0
SCAN_INTERVAL_SEC     = 4
MARGIN_PROFIT_TRIGGER = 0.45    # strong scalp: take ~45% of margin as TP
MARGIN_SL_LOCK_PCT    = 0.70
MAX_SPREAD_POINTS     = 2000
MIN_COOLDOWN_SEC      = 90      # demo accuracy: slightly faster cycle
STRONG_COOLDOWN_SEC   = 40      # fast re-entry after strong scalp win
LOSS_COOLDOWN_SEC     = 600
TRADE_MAX_LOSS_PCT    = 0.004
EARLY_LOSS_CUT_PCT    = 0.0025
MASTER_AUTO_LOSS_CUT  = False   # never bot-close in loss
MASTER_AUTO_CLOSE     = True    # profit-only scalp exits (demo accuracy)
MASTER_PROFIT_ONLY    = True    # closes only when profit > 0
SESSION_MAX_DD_PCT    = 0.08    # stop new entries if equity -8% from session start
STALE_LOSS_MINUTES    = 6
BREAKEVEN_PROFIT_USD  = 3.0
SCALP_ATR_MULT        = 0.7     # tight scalp target on strong trend
HOLD_MIN_PROFIT       = 5.0
HOLD_TRAIL_PCT        = 0.55    # trail giveback for fast scalp
SL_BUFFER_ATR_MULT    = 0.35
SL_HALF_POINT         = 0.5
TP_HALF_POINT         = 0.5
MIN_H1_STRENGTH       = MIN_TREND_STRUCTURE
STRONG_TREND_STRENGTH = 30      # H1+M15 combined -> fast scalp

SYMBOL_MAX_SPREAD = {
    "XAUUSDm":  30000,
    "XAGUSDm":  5000,
    "BTCUSDm":  2000000,
    "ETHUSDm":  200000,
    "SOLUSDm":  200000,
    "EURUSDm":  2000,
    "GBPUSDm":  2000,
    "USDJPYm":  2000,
    "AUDUSDm":  2000,
    "USDCADm":  2000,
    "GBPJPYm":  8000,
    "NZDUSDm":  2000,
    # Exness CENT (*c) - same point budgets as standard
    "XAUUSDc":  30000,
    "XAGUSDc":  5000,
    "BTCUSDc":  2000000,
    "ETHUSDc":  200000,
    "EURUSDc":  2000,
    "GBPUSDc":  2000,
    "USDJPYc":  2000,
    "AUDUSDc":  2000,
}


def symbol_spread_limit(symbol: str) -> float:
    if symbol in SYMBOL_MAX_SPREAD:
        return SYMBOL_MAX_SPREAD[symbol]
    stem = symbol.rstrip("cmzrCMZR")
    for suf in ("m", "c", "", "z", "r"):
        key = f"{stem}{suf}"
        if key in SYMBOL_MAX_SPREAD:
            return SYMBOL_MAX_SPREAD[key]
    return MAX_SPREAD_POINTS

TRAILING_LEVELS = [
    (2.0,  1.0), (5.0,  3.0), (8.0,  5.0), (10.0, 7.0),
    (12.0, 9.0), (15.0, 12.0), (18.0, 14.0), (20.0, 16.0),
    (25.0, 20.0), (30.0, 25.0), (40.0, 33.0), (50.0, 42.0),
]

# Kept for older imports / helpers
BREAKOUT_LOOKBACK = {"M15": 10, "H1": 20, "H4": 24}


# ─── Price utilities ──────────────────────────────────────────────────────────

def calc_atr(highs, lows, closes, period=14):
    try:
        if len(closes) < period + 1:
            return 0
        tr_list = [
            max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            for i in range(1, len(closes))
        ]
        return sum(tr_list[-period:]) / period
    except Exception:
        return 0


def half_point_offset(symbol, mt5_manager):
    info = mt5_manager.symbol_info(symbol)
    if info is None:
        return SL_HALF_POINT
    sym = symbol.upper()
    if "XAU" in sym or "XAG" in sym:
        return 0.5
    if "BTC" in sym or "ETH" in sym or "SOL" in sym:
        return 0.5
    if "JPY" in sym:
        return 0.05
    return max(info.point * 10, 0.0001)


def fetch_ohlc(symbol, timeframe, count, mt5_manager):
    rates = mt5_manager.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) < 3:
        return None
    rates = sorted(rates, key=lambda r: r.get("time", 0))
    return {
        "opens":  [r["open"] for r in rates],
        "highs":  [r["high"] for r in rates],
        "lows":   [r["low"] for r in rates],
        "closes": [r["close"] for r in rates],
        "times":  [r.get("time", 0) for r in rates],
    }


# ─── Candle patterns (OHLC only - no indicators) ──────────────────────────────

def detect_candle_pattern(opens, highs, lows, closes):
    """
    Detect pattern on the LAST candle in the arrays (expected: last CLOSED M1).
    Returns (name, direction, base_score 10-28).
    """
    if len(closes) < 3:
        return None, None, 0

    o1, h1, l1, c1 = opens[-1], highs[-1], lows[-1], closes[-1]
    o2, h2, l2, c2 = opens[-2], highs[-2], lows[-2], closes[-2]
    o3, h3, l3, c3 = opens[-3], highs[-3], lows[-3], closes[-3]

    body1 = abs(c1 - o1)
    body2 = abs(c2 - o2)
    range1 = h1 - l1 if h1 != l1 else 0.0001
    range2 = h2 - l2 if h2 != l2 else 0.0001
    uw1 = h1 - max(o1, c1)
    lw1 = min(o1, c1) - l1

    # Bullish
    if lw1 >= body1 * 2 and uw1 <= body1 * 0.3 and c1 > o1:
        return "Hammer", "BUY", 18
    if c2 < o2 and c1 > o1 and c1 >= o2 and o1 <= c2 and body1 > body2 * 0.8:
        return "Bullish Engulfing", "BUY", 28
    if c3 < o3 and body2 < range2 * 0.3 and c1 > o1 and c1 > (o3 + c3) / 2:
        return "Morning Star", "BUY", 26
    if c1 > o1 and body1 >= range1 * 0.85:
        return "Bullish Marubozu", "BUY", 16
    if c2 < o2 and c1 > o1 and o1 < l2 and c1 > (o2 + c2) / 2:
        return "Piercing Line", "BUY", 20
    if body1 < range1 * 0.1 and lw1 > uw1 and c2 < o2:
        return "Bullish Doji Reversal", "BUY", 14
    if c1 > o1 and c2 > o2 and c3 > o3 and body1 > body2 > 0:
        return "Three White Soldiers", "BUY", 24
    if c2 > o2 and c1 < o1 and c1 > o2 and body1 < body2 * 0.5:
        return "Bullish Harami", "BUY", 12
    if abs(l1 - l2) / range1 < 0.05 and c1 > o1 and c2 < o2:
        return "Tweezer Bottom", "BUY", 16

    # Bearish
    if uw1 >= body1 * 2 and lw1 <= body1 * 0.3 and c1 < o1:
        return "Shooting Star", "SELL", 18
    if c2 > o2 and c1 < o1 and c1 <= o2 and o1 >= c2 and body1 > body2 * 0.8:
        return "Bearish Engulfing", "SELL", 28
    if c3 > o3 and body2 < range2 * 0.3 and c1 < o1 and c1 < (o3 + c3) / 2:
        return "Evening Star", "SELL", 26
    if c1 < o1 and body1 >= range1 * 0.85:
        return "Bearish Marubozu", "SELL", 16
    if c2 > o2 and c1 < o1 and o1 > h2 and c1 < (o2 + c2) / 2:
        return "Dark Cloud Cover", "SELL", 20
    if body1 < range1 * 0.1 and uw1 > lw1 and c2 > o2:
        return "Bearish Doji Reversal", "SELL", 14
    if c1 < o1 and c2 < o2 and c3 < o3 and body1 > body2 > 0:
        return "Three Black Crows", "SELL", 24
    if c2 < o2 and c1 > o1 and c1 < o2 and body1 < body2 * 0.5:
        return "Bearish Harami", "SELL", 12
    if abs(h1 - h2) / range1 < 0.05 and c1 < o1 and c2 > o2:
        return "Tweezer Top", "SELL", 16

    return None, None, 0


def confirm_m1_direction(opens, highs, lows, closes, direction):
    """
    Direction confirmation on 1m - no indicators.
    Uses closed-candle structure after the pattern candle.
    Returns (confirmed: bool, bonus_score: int, reason: str)
    """
    if len(closes) < 4 or not direction:
        return False, 0, "short_history"

    # Pattern candle = -2 (last fully closed before current forming),
    # confirm candle = -1 if we pass closed-only arrays, else use -1 as latest closed.
    # Caller passes closed-only OHLC so [-1] is latest closed.
    c0, o0 = closes[-1], opens[-1]
    c1, o1 = closes[-2], opens[-2]
    h0, l0 = highs[-1], lows[-1]
    body0 = abs(c0 - o0)
    range0 = h0 - l0 if h0 != l0 else 0.0001

    bonus = 0
    reasons = []

    if direction == "BUY":
        if c0 > o0:
            bonus += 12
            reasons.append("green_close")
        if c0 > c1:
            bonus += 10
            reasons.append("higher_close")
        if c0 > max(o1, c1):
            bonus += 8
            reasons.append("broke_prior_body")
        if body0 >= range0 * 0.45:
            bonus += 6
            reasons.append("strong_body")
        # Micro structure: last 3 closes rising
        if closes[-1] > closes[-2] >= closes[-3]:
            bonus += 8
            reasons.append("rising_3")
    else:
        if c0 < o0:
            bonus += 12
            reasons.append("red_close")
        if c0 < c1:
            bonus += 10
            reasons.append("lower_close")
        if c0 < min(o1, c1):
            bonus += 8
            reasons.append("broke_prior_body")
        if body0 >= range0 * 0.45:
            bonus += 6
            reasons.append("strong_body")
        if closes[-1] < closes[-2] <= closes[-3]:
            bonus += 8
            reasons.append("falling_3")

    # Need at least one solid confirm signal
    confirmed = bonus >= 12
    return confirmed, bonus, "+".join(reasons) if reasons else "weak"


def score_m1_setup(pattern_score, confirm_bonus, atr, body, range_):
    """Combine pattern + confirmation into 0-100 score for lot sizing."""
    raw = pattern_score * 2.2 + confirm_bonus
    # Momentum quality: larger body vs range boosts score
    if range_ and range_ > 0:
        raw += min(10, (body / range_) * 12)
    # Mild ATR context - not an indicator entry, just size realism
    if atr and atr > 0 and body > atr * 0.35:
        raw += 6
    return int(max(0, min(100, round(raw))))


def detect_m1_signal(symbol, mt5_manager):
    """
    Primary signal: M1 candle patterns only.
    Uses last CLOSED candle for pattern; requires direction confirmation.
    """
    tf = getattr(mt5_manager, "TIMEFRAME_M1", "1m")
    ohlc = fetch_ohlc(symbol, tf, 80, mt5_manager)
    if ohlc is None or len(ohlc["closes"]) < 6:
        return None

    # Drop forming candle if MetaApi includes current incomplete bar
    # Heuristic: if last candle time is "now-ish" we still use it as closed-enough
    # for cloud RPC; pattern uses last 3 closed bars from the series.
    opens, highs, lows, closes = (
        ohlc["opens"], ohlc["highs"], ohlc["lows"], ohlc["closes"]
    )

    # Pattern on bars[:-1] (exclude potentially forming), confirm with bars[-2:]
    # Safer: pattern at -2, confirm at -1 (both treated as closed in history)
    if len(closes) < 5:
        return None

    p_opens, p_highs, p_lows, p_closes = opens[:-1], highs[:-1], lows[:-1], closes[:-1]
    pname, pdir, pbase = detect_candle_pattern(p_opens, p_highs, p_lows, p_closes)
    if not pdir:
        return {
            "skip": True,
            "reason": "no_pattern",
            "symbol": symbol,
            "ohlc": ohlc,
        }

    # Confirmation window = last closed candle after pattern
    c_opens, c_highs, c_lows, c_closes = opens[-4:], highs[-4:], lows[-4:], closes[-4:]
    confirmed, cbonus, creason = confirm_m1_direction(
        c_opens, c_highs, c_lows, c_closes, pdir
    )
    if not confirmed:
        return {
            "skip": True,
            "reason": "no_confirm",
            "symbol": symbol,
            "pattern_name": pname,
            "pattern_dir": pdir,
            "confirm": creason,
            "ohlc": ohlc,
        }

    atr = calc_atr(highs, lows, closes) or 0
    body = abs(closes[-1] - opens[-1])
    rng = highs[-1] - lows[-1] if highs[-1] != lows[-1] else 0.0001
    score = score_m1_setup(pbase, cbonus, atr, body, rng)

    levels = {
        "recent_high": max(highs[-8:-1]),
        "recent_low": min(lows[-8:-1]),
        "range_height": max(highs[-8:-1]) - min(lows[-8:-1]),
        "breakout_level": closes[-1],
    }

    return {
        "symbol": symbol,
        "trend": pdir,
        "score": score,
        "pattern_name": f"M1:{pname}",
        "pattern_base": pbase,
        "confirm_bonus": cbonus,
        "confirm_reason": creason,
        "atr": atr,
        "breakout_levels": levels,
        "ohlc": ohlc,
        "m1_pattern": pname,
    }


# ─── Legacy HTF helpers (kept for position management / trend fail) ───────────

def detect_htf_candle_patterns(symbol, mt5_manager):
    patterns = {}
    tf_map = {
        "H1": (mt5_manager.TIMEFRAME_H1, 60),
        "H4": (mt5_manager.TIMEFRAME_H4, 80),
        "D1": (mt5_manager.TIMEFRAME_D1, 60),
    }
    for label, (tf, count) in tf_map.items():
        ohlc = fetch_ohlc(symbol, tf, count, mt5_manager)
        if ohlc is None:
            patterns[label] = (None, None, 0)
            continue
        patterns[label] = detect_candle_pattern(
            ohlc["opens"], ohlc["highs"], ohlc["lows"], ohlc["closes"]
        )
    return patterns


def detect_breakout(highs, lows, closes, lookback=20, min_body_ratio=0.30):
    empty_levels = {"recent_high": 0, "recent_low": 0, "range_height": 0, "breakout_level": 0}
    if len(closes) < lookback + 2:
        return None, None, 0, empty_levels
    recent_high = max(highs[-lookback - 1:-1])
    recent_low = min(lows[-lookback - 1:-1])
    prev_close = closes[-2]
    price = closes[-1]
    body = abs(price - prev_close)
    avg_range = sum(h - l for h, l in zip(highs[-10:], lows[-10:])) / max(len(highs[-10:]), 1)
    strong_move = body >= avg_range * min_body_ratio
    range_height = recent_high - recent_low
    levels = {
        "recent_high": recent_high,
        "recent_low": recent_low,
        "range_height": range_height,
        "breakout_level": recent_high,
    }
    if price > recent_high and prev_close <= recent_high and strong_move:
        levels["breakout_level"] = recent_high
        strength = 20 + min(15, int((body / max(avg_range, 0.0001)) * 5))
        return "Bullish Breakout", "BUY", strength, levels
    levels["breakout_level"] = recent_low
    if price < recent_low and prev_close >= recent_low and strong_move:
        strength = 20 + min(15, int((body / max(avg_range, 0.0001)) * 5))
        return "Bearish Breakout", "SELL", strength, levels
    return None, None, 0, levels


def get_htf_atr(symbol, mt5_manager, period=14):
    # Prefer M1 ATR for M1 strategy; fall back to H1
    for tf_attr, tf_fallback in (
        ("TIMEFRAME_M1", "1m"),
        ("TIMEFRAME_M15", "15m"),
        ("TIMEFRAME_H1", "1h"),
    ):
        tf = getattr(mt5_manager, tf_attr, tf_fallback)
        rates = mt5_manager.copy_rates_from_pos(symbol, tf, 0, period + 20)
        if rates is None or len(rates) < period + 1:
            continue
        highs = [r["high"] for r in rates]
        lows = [r["low"] for r in rates]
        closes = [r["close"] for r in rates]
        atr = calc_atr(highs, lows, closes, period)
        if atr and atr > 0:
            return atr
    return None


def calc_pattern_sl(symbol, trade_type, entry_price, levels, mt5_manager):
    atr = get_htf_atr(symbol, mt5_manager) or 0
    half = half_point_offset(symbol, mt5_manager)
    recent_high = (levels or {}).get("recent_high") or entry_price
    recent_low = (levels or {}).get("recent_low") or entry_price
    buffer = (atr * SL_BUFFER_ATR_MULT) if atr else abs(recent_high - recent_low) * 0.25

    if trade_type == "BUY":
        sl = recent_low - buffer - half
        if sl >= entry_price:
            sl = entry_price - max(atr, buffer) - half
    else:
        sl = recent_high + buffer + half
        if sl <= entry_price:
            sl = entry_price + max(atr, buffer) + half
    return sl


# Aliases used by main.py
def calc_breakout_sl(symbol, trade_type, entry_price, levels, mt5_manager):
    return calc_pattern_sl(symbol, trade_type, entry_price, levels, mt5_manager)


def calc_h1_sl(symbol, trade_type, entry_price, mt5_manager, levels=None):
    return calc_pattern_sl(symbol, trade_type, entry_price, levels or {}, mt5_manager)


def calc_breakout_tp_price(trade_type, entry_price, levels, symbol, mt5_manager):
    half = half_point_offset(symbol, mt5_manager)
    range_h = levels.get("range_height", 0) if levels else 0
    if range_h <= 0:
        atr = get_htf_atr(symbol, mt5_manager)
        range_h = atr * 1.6 if atr else entry_price * 0.0015
    if trade_type == "BUY":
        return entry_price + range_h - half
    return entry_price - range_h + half


def price_distance_to_usd(price_distance, lot, symbol, mt5_manager):
    try:
        info = mt5_manager.symbol_info(symbol)
        if info is None or lot <= 0:
            return None
        tick_value = info.trade_tick_value
        tick_size = info.trade_tick_size
        if tick_value == 0 or tick_size == 0:
            return None
        return abs(price_distance) * (lot * tick_value) / tick_size
    except Exception:
        return None


def get_breakout_profit_target(entry_price, trade_type, levels, lot, symbol, mt5_manager, score=50):
    tp_price = calc_breakout_tp_price(trade_type, entry_price, levels, symbol, mt5_manager)
    distance = abs(tp_price - entry_price)
    usd = price_distance_to_usd(distance, lot, symbol, mt5_manager)
    if usd is None:
        atr = get_htf_atr(symbol, mt5_manager) or 1.0
        usd = price_distance_to_usd(atr * 1.5, lot, symbol, mt5_manager) or 5.0
    mult = 1.35 if score >= STRONG_SCORE else SCALP_ATR_MULT
    return round(max(2.0, min(150.0, usd * mult)), 2)


def get_profit_target(score, atr, symbol, mt5_manager, entry_price=None,
                      trade_type=None, levels=None, lot=0.01):
    if entry_price and trade_type and levels:
        return get_breakout_profit_target(
            entry_price, trade_type, levels, lot, symbol, mt5_manager, score)
    info = mt5_manager.symbol_info(symbol)
    if info is None or not atr:
        return 5.0
    tick_value = info.trade_tick_value
    tick_size = info.trade_tick_size
    if tick_value == 0 or tick_size == 0:
        return 5.0
    atr_dollar = (atr / tick_size) * tick_value * 0.01
    mult = 1.35 if score >= STRONG_SCORE else SCALP_ATR_MULT
    target = atr_dollar * mult - half_point_offset(symbol, mt5_manager)
    return round(max(2.0, min(150.0, target)), 2)


def calc_margin_used(lot, symbol, price, mt5_manager):
    try:
        sym_info = mt5_manager.symbol_info(symbol)
        acc_info = mt5_manager.account_info()
        if sym_info is None or acc_info is None:
            return None
        leverage = getattr(acc_info, "leverage", 0) or 100
        contract_size = getattr(sym_info, "contract_size", 0) or 100000
        if leverage <= 0 or lot <= 0 or price <= 0:
            return None
        return (lot * contract_size * price) / leverage
    except Exception:
        return None


def profit_to_price(entry_price, trade_type, target_profit, lot, symbol, mt5_manager):
    try:
        info = mt5_manager.symbol_info(symbol)
        if info is None or lot <= 0:
            return None
        tick_value = info.trade_tick_value
        tick_size = info.trade_tick_size
        if tick_value == 0 or tick_size == 0:
            return None
        profit_per_price_unit = (lot * tick_value) / tick_size
        if profit_per_price_unit == 0:
            return None
        distance = target_profit / profit_per_price_unit
        return entry_price + distance if trade_type == "BUY" else entry_price - distance
    except Exception:
        return None


def get_trend(symbol, mt5_manager):
    """M1 micro-structure bias for position fail checks - no indicators."""
    tf = getattr(mt5_manager, "TIMEFRAME_M1", "1m")
    ohlc = fetch_ohlc(symbol, tf, 30, mt5_manager)
    if ohlc is None:
        return "BUY", 0, 0, False
    closes = ohlc["closes"]
    if len(closes) < 8:
        return "BUY", 0, 0, False
    mid = sum(closes[-8:]) / 8
    trend = "BUY" if closes[-1] > mid else "SELL"
    aligned = (closes[-1] > closes[-3] > closes[-5]) if trend == "BUY" else (
        closes[-1] < closes[-3] < closes[-5]
    )
    return trend, 0, 0, aligned


def get_risk_multiplier(score):
    """Higher pattern score -> more margin/lot on that trade."""
    if score >= 90:
        return 3.5
    if score >= STRONG_SCORE:
        return 2.8
    if score >= 55:
        return 2.0
    if score >= MIN_PATTERN_SCORE:
        return 1.4
    return 1.0


def get_locked_profit(current_profit):
    locked = None
    for trigger, lock in TRAILING_LEVELS:
        if current_profit >= trigger:
            locked = lock
    return locked


def is_scalp_trade(score):
    return score < STRONG_SCORE


def calculate_lot(balance, atr, symbol, score, mt5_manager, sl_distance=None):
    try:
        mult = get_risk_multiplier(score)
        risk_amount = balance * RISK_PER_TRADE_PCT * mult
        info = mt5_manager.symbol_info(symbol)
        if info is None:
            return None
        tick_value = info.trade_tick_value
        tick_size = info.trade_tick_size
        if tick_value == 0 or tick_size == 0:
            return info.volume_min
        if sl_distance and sl_distance > 0:
            sl_ticks = sl_distance / tick_size
        elif atr and atr > 0:
            sl_ticks = atr / tick_size
        else:
            return info.volume_min
        lot = risk_amount / (sl_ticks * tick_value)
        lot = max(info.volume_min, min(info.volume_max,
              round(lot / info.volume_step) * info.volume_step))
        return round(lot, 2)
    except Exception:
        return None


# ─── HTF bias + M5 S/R breakout/retest ───────────────────────────────────────

def _structure_bias(opens, highs, lows, closes, tag: str):
    """
    Strict swing structure on closed bars.
    Needs clear directional push - not a soft mid-cross.
    Returns ("BUY"|"SELL"|None, strength 0-30, detail).
    """
    c, h, l, o = closes[:-1], highs[:-1], lows[:-1], opens[:-1]
    if len(c) < 8:
        return None, 0, f"{tag}_short"

    last4 = c[-4:]
    prior = c[-8:-4]
    mid_prior = sum(prior) / len(prior)
    up = last4[-1] > mid_prior and last4[-1] > last4[0] and c[-1] > c[-2]
    down = last4[-1] < mid_prior and last4[-1] < last4[0] and c[-1] < c[-2]
    higher_lows = l[-1] > l[-2] > l[-3]
    higher_highs = h[-1] > h[-2] > h[-3]
    lower_highs = h[-1] < h[-2] < h[-3]
    lower_lows = l[-1] < l[-2] < l[-3]
    bull_body = sum(1 for i in range(-4, 0) if c[i] > o[i])
    bear_body = sum(1 for i in range(-4, 0) if c[i] < o[i])

    # Strict: need structure (HH/HL or LH/LL) - body count alone is not enough
    if up and higher_lows and (higher_highs or bull_body >= 3):
        strength = 20 + (6 if higher_highs else 0) + (4 if bull_body >= 3 else 0)
        return "BUY", min(30, strength), f"{tag}_bull_struct"
    if down and lower_highs and (lower_lows or bear_body >= 3):
        strength = 20 + (6 if lower_lows else 0) + (4 if bear_body >= 3 else 0)
        return "SELL", min(30, strength), f"{tag}_bear_struct"
    return None, 0, f"{tag}_chop"


def get_h1_bias(symbol, mt5_manager):
    """1H swing structure - only trade this side when clear."""
    tf = getattr(mt5_manager, "TIMEFRAME_H1", "1h")
    ohlc = fetch_ohlc(symbol, tf, 40, mt5_manager)
    if ohlc is None or len(ohlc["closes"]) < 10:
        return None, 0, "no_h1"
    return _structure_bias(
        ohlc["opens"], ohlc["highs"], ohlc["lows"], ohlc["closes"], "h1"
    )


def get_m15_bias(symbol, mt5_manager):
    """M15 must agree with H1 - blocks chop entries."""
    tf = getattr(mt5_manager, "TIMEFRAME_M15", "15m")
    ohlc = fetch_ohlc(symbol, tf, 40, mt5_manager)
    if ohlc is None or len(ohlc["closes"]) < 10:
        return None, 0, "no_m15"
    return _structure_bias(
        ohlc["opens"], ohlc["highs"], ohlc["lows"], ohlc["closes"], "m15"
    )


def get_strict_trend(symbol, mt5_manager):
    """
    Sakhti se trend: H1 structure + M15 same direction.
    Returns (dir, strength, detail_dict) or (None, 0, reason).
    """
    h1_dir, h1_str, h1_d = get_h1_bias(symbol, mt5_manager)
    if not h1_dir or h1_str < MIN_H1_STRENGTH:
        return None, 0, {"reason": "weak_h1", "h1": h1_d, "h1_str": h1_str}

    m15_dir, m15_str, m15_d = get_m15_bias(symbol, mt5_manager)
    if not m15_dir:
        return None, 0, {"reason": "no_m15", "h1": h1_d, "m15": m15_d}
    if m15_dir != h1_dir:
        return None, 0, {
            "reason": "m15_disagree",
            "h1": h1_d, "m15": m15_d,
            "h1_dir": h1_dir, "m15_dir": m15_dir,
        }

    strength = int(h1_str + min(15, m15_str // 2 + 6))
    strong = strength >= STRONG_TREND_STRENGTH and h1_str >= 24
    return h1_dir, strength, {
        "reason": "ok",
        "h1": h1_d,
        "m15": m15_d,
        "h1_str": h1_str,
        "m15_str": m15_str,
        "strong": strong,
    }


def is_gold_symbol(symbol: str) -> bool:
    u = (symbol or "").upper()
    return "XAU" in u or u.startswith("GOLD")


def detect_m5_sr_signal(symbol, mt5_manager, bias_dir=None):
    """
    M5 support/resistance: clear break -> retest hold -> continue.
    Also accepts strong M5 engulfs after level break.
    """
    tf = getattr(mt5_manager, "TIMEFRAME_M5", None) or getattr(
        mt5_manager, "TIMEFRAME_M1", "1m"
    )
    # Prefer real M5 if bridge exposes it
    if hasattr(mt5_manager, "TIMEFRAME_M5"):
        tf = mt5_manager.TIMEFRAME_M5
    ohlc = fetch_ohlc(symbol, tf, 80, mt5_manager)
    if ohlc is None or len(ohlc["closes"]) < 20:
        return None

    opens, highs, lows, closes = (
        ohlc["opens"], ohlc["highs"], ohlc["lows"], ohlc["closes"]
    )
    # Closed bars
    o, h, l, c = opens[:-1], highs[:-1], lows[:-1], closes[:-1]
    if len(c) < 18:
        return None

    look = 12
    # Level from bars before the last 3 (break + retest window)
    window = slice(-(look + 4), -4)
    res = max(h[window])
    sup = min(l[window])
    rng = res - sup
    if rng <= 0:
        return None

    atr = calc_atr(h, l, c) or rng * 0.2
    buf = max(atr * 0.15, rng * 0.05)
    b0, b1, b2 = -3, -2, -1  # break, retest, confirm (closed)

    # Resistance break -> retest -> hold above
    broke_up = c[b0] > res + buf and o[b0] < res
    retest_hold_up = (
        l[b1] <= res + buf and l[b1] >= res - buf * 2 and c[b1] >= res - buf
    )
    confirm_up = c[b2] > res and c[b2] >= o[b2]

    # Support break -> retest -> hold below
    broke_dn = c[b0] < sup - buf and o[b0] > sup
    retest_hold_dn = (
        h[b1] >= sup - buf and h[b1] <= sup + buf * 2 and c[b1] <= sup + buf
    )
    confirm_dn = c[b2] < sup and c[b2] <= o[b2]

    pname, pdir, pbase = detect_candle_pattern(o, h, l, c)

    direction = None
    score = 0
    name = None
    levels = {
        "recent_high": res,
        "recent_low": sup,
        "range_height": rng,
        "breakout_level": res,
    }

    if broke_up and retest_hold_up and confirm_up:
        direction = "BUY"
        score = 62 + min(20, int((c[b2] - res) / max(buf, 1e-9) * 4))
        name = "M5:break_retest_res"
        levels["breakout_level"] = res
    elif broke_dn and retest_hold_dn and confirm_dn:
        direction = "SELL"
        score = 62 + min(20, int((sup - c[b2]) / max(buf, 1e-9) * 4))
        name = "M5:break_retest_sup"
        levels["breakout_level"] = sup
    elif pdir and pbase >= 18:
        # Strong candle after sitting near S/R
        near_res = abs(c[-1] - res) <= buf * 2
        near_sup = abs(c[-1] - sup) <= buf * 2
        if pdir == "BUY" and (near_sup or c[-1] > res):
            direction, score, name = "BUY", 50 + pbase, f"M5:pattern_{pname}"
        elif pdir == "SELL" and (near_res or c[-1] < sup):
            direction, score, name = "SELL", 50 + pbase, f"M5:pattern_{pname}"

    if not direction:
        return {"skip": True, "reason": "no_m5_setup", "symbol": symbol}

    if bias_dir and direction != bias_dir:
        return {
            "skip": True,
            "reason": "against_h1",
            "symbol": symbol,
            "m5_dir": direction,
            "h1_bias": bias_dir,
        }

    score = int(max(40, min(100, score)))
    return {
        "symbol": symbol,
        "trend": direction,
        "score": score,
        "pattern_name": name,
        "atr": atr,
        "breakout_levels": levels,
        "m5_setup": name,
        "m1_pattern": name,  # eligibility reuse
        "confirm_reason": "m5_retest_confirm",
        "ohlc": ohlc,
    }


def analyze_symbol(symbol, mt5_manager):
    """
    Strict trend -> then entry:
      1) H1 + M15 same-direction structure (mandatory)
      2) Gold: only M5 S/R break+retest (no weak M1 spam)
      3) Strong trend -> FAST_SCALP mode (higher score / quicker exits)
    """
    tick = mt5_manager.symbol_info_tick(symbol)
    sym_info = mt5_manager.symbol_info(symbol)
    if tick is None or sym_info is None:
        return None

    spread = (tick.ask - tick.bid) / sym_info.point
    max_spread = symbol_spread_limit(symbol)
    if spread > max_spread:
        return {"skip": True, "reason": "spread", "symbol": symbol, "spread": spread}

    trend_dir, trend_str, trend_detail = get_strict_trend(symbol, mt5_manager)
    if not trend_dir:
        return {
            "skip": True,
            "reason": (trend_detail or {}).get("reason", "no_strict_trend"),
            "symbol": symbol,
            "trend_detail": trend_detail,
            "tick": tick,
        }

    gold = is_gold_symbol(symbol)
    signal = detect_m5_sr_signal(symbol, mt5_manager, bias_dir=trend_dir)
    source = "m5"

    # Gold: sakhti - M5 break/retest only. Crypto may use M1 if M5 quiet.
    if signal is None or signal.get("skip"):
        if gold:
            return {
                "skip": True,
                "reason": (signal or {}).get("reason", "no_m5_setup"),
                "symbol": symbol,
                "h1_bias": trend_dir,
                "trend_detail": trend_detail,
                "tick": tick,
            }
        signal = detect_m1_signal(symbol, mt5_manager)
        source = "m1"
        if signal is None:
            return {"skip": True, "reason": "no_candles", "symbol": symbol, "tick": tick}
        if signal.get("skip"):
            signal["tick"] = tick
            signal["h1_bias"] = trend_dir
            return signal
        if signal.get("trend") != trend_dir:
            return {
                "skip": True,
                "reason": "m1_against_trend",
                "symbol": symbol,
                "m1_dir": signal.get("trend"),
                "h1_bias": trend_dir,
                "tick": tick,
            }

    if signal.get("skip"):
        signal["tick"] = tick
        return signal

    trend = signal["trend"]
    strong_trend = bool((trend_detail or {}).get("strong"))
    score = int(signal["score"]) + int(min(20, trend_str // 2))
    if source == "m5":
        score += 10
    if strong_trend:
        score += 8  # unlock fast scalp sizing / exits
    score = int(max(0, min(100, score)))

    # Strong clear trend -> fast scalp; otherwise wait for elite score
    if strong_trend and score >= STRONG_SCORE:
        trade_mode = "FAST_SCALP"
    elif score >= STRONG_SCORE:
        trade_mode = "ELITE"
    else:
        trade_mode = "SCALP"

    levels = signal.get("breakout_levels") or {}
    atr = signal.get("atr") or 0
    entry_est = tick.ask if trend == "BUY" else tick.bid
    sl_est = calc_pattern_sl(symbol, trend, entry_est, levels, mt5_manager)
    sl_distance = abs(entry_est - sl_est) if sl_est else (atr or 1.0)

    return {
        "symbol": symbol,
        "trend": trend,
        "score": score,
        "trade_mode": trade_mode,
        "strong_trend": strong_trend,
        "trend_strength": trend_str,
        "atr": atr,
        "breakout_levels": levels,
        "sl_distance": sl_distance,
        "htf_aligned": True,
        "pattern_name": signal.get("pattern_name"),
        "pattern_conflict": False,
        "htf_patterns": {
            "H1": (trend_detail or {}).get("h1"),
            "M15": (trend_detail or {}).get("m15"),
        },
        "breakouts": {"M5": signal.get("m5_setup")},
        "breakout_name": signal.get("pattern_name"),
        "breakout_dir": trend,
        "breakout_bonus": score,
        "m15_breakout": signal.get("m5_setup") or signal.get("m1_pattern"),
        "m1_pattern": signal.get("m1_pattern") or signal.get("m5_setup"),
        "m1_confirm": signal.get("confirm_reason"),
        "h1_breakout": (trend_detail or {}).get("h1"),
        "h1_bias": trend_dir,
        "entry_source": source,
        "h4_breakout": None,
        "tick": tick,
        "closes15": signal.get("ohlc", {}).get("closes", []),
    }


def trade_eligible(analysis):
    """
    Must have H1+M15 agreement + M5 setup + min score.
    Strong trend -> FAST_SCALP (handled in analyze_symbol trade_mode).
    Demo: clear trend is enough; strong is preferred not mandatory.
    """
    if analysis.get("skip"):
        return False, analysis.get("reason", "skip")

    if not analysis.get("htf_aligned") and not analysis.get("h1_bias"):
        return False, "no_strict_trend"

    if not analysis.get("m1_pattern") and not analysis.get("m15_breakout"):
        return False, "no_setup"

    score = analysis.get("score", 0)
    if score < MIN_PATTERN_SCORE:
        return False, f"pattern_score_{score}_need_{MIN_PATTERN_SCORE}"

    # Gold still requires HTF bias (set by analyze_symbol); no extra strong lock
    return True, "ok"


def should_take_trade(analysis):
    return trade_eligible(analysis)
