"""
PumpingBot Trading Engine — breakout-only strategy.
Sirf M15/H1/H4 breakouts par trade; candle patterns sirf H1/H4/D1 par.
"""

# ─── Engine constants ─────────────────────────────────────────────────────────
DAILY_MAX_LOSS_PCT    = 0.015
DAILY_PROFIT_TARGET   = 0.05
DAILY_TRAIL_START     = 0.03
DAILY_TRAIL_GAP       = 0.01
RISK_PER_TRADE_PCT    = 0.004
MAX_OPEN_TRADES       = 3
MAX_TRADES_PER_SYMBOL = 1
MIN_BREAKOUT_SCORE    = 20      # M15 breakout akela kaafi
STRONG_SCORE          = 60      # H1/H4 bhi confirm hon to strong
MIN_SCORE             = MIN_BREAKOUT_SCORE
MIN_TREND_STRUCTURE   = 0       # legacy — indicators removed
MIN_EFFECTIVE_SCORE   = MIN_BREAKOUT_SCORE
MIN_CONFLUENCE        = 0       # legacy — indicators removed
SCAN_INTERVAL_SEC     = 35
MARGIN_PROFIT_TRIGGER = 0.7
MARGIN_SL_LOCK_PCT    = 0.70
MAX_SPREAD_POINTS     = 2000
MIN_COOLDOWN_SEC      = 480
LOSS_COOLDOWN_SEC     = 900
TRADE_MAX_LOSS_PCT    = 0.004
EARLY_LOSS_CUT_PCT    = 0.0025
STALE_LOSS_MINUTES    = 6
BREAKEVEN_PROFIT_USD  = 3.0
SCALP_ATR_MULT        = 1.2
HOLD_MIN_PROFIT       = 5.0
HOLD_TRAIL_PCT        = 0.70
SL_BUFFER_ATR_MULT    = 0.12   # breakout level ke neeche/upar chhota buffer
SL_HALF_POINT         = 0.5    # SL thoda zyada door — adha point
TP_HALF_POINT         = 0.5    # TP thoda kam — adha point

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
}

TRAILING_LEVELS = [
    (2.0,  1.0), (5.0,  3.0), (8.0,  5.0), (10.0, 7.0),
    (12.0, 9.0), (15.0, 12.0), (18.0, 14.0), (20.0, 16.0),
    (25.0, 20.0), (30.0, 25.0), (40.0, 33.0), (50.0, 42.0),
]

BREAKOUT_LOOKBACK = {
    "M15": 15,
    "H1":  24,
    "H4":  30,
}

M15_FRESH_BARS = 4   # is window ke andar breakout fresh maana jayega


# ─── Price utilities (ATR sirf SL buffer ke liye — entry signal nahi) ─────────

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
    """Adha point — symbol ke hisab se price offset."""
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
    if rates is None or len(rates) < 5:
        return None
    return {
        "opens":  [r["open"] for r in rates],
        "highs":  [r["high"] for r in rates],
        "lows":   [r["low"] for r in rates],
        "closes": [r["close"] for r in rates],
    }


# ─── Candle patterns (sirf H1 / H4 / D1 confirmation) ─────────────────────────

def detect_candle_pattern(opens, highs, lows, closes):
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

    if lw1 >= body1 * 2 and uw1 <= body1 * 0.3 and c1 > o1:
        return "Hammer", "BUY", 15
    if c2 < o2 and c1 > o1 and c1 > o2 and o1 < c2:
        return "Bullish Engulfing", "BUY", 22
    if c3 < o3 and body2 < range2 * 0.3 and c1 > o1 and c1 > (o3 + c3) / 2:
        return "Morning Star", "BUY", 20
    if c1 > o1 and body1 >= range1 * 0.85:
        return "Bullish Marubozu", "BUY", 14
    if c2 < o2 and c1 > o1 and o1 < l2 and c1 > (o2 + c2) / 2:
        return "Piercing Line", "BUY", 16
    if body1 < range1 * 0.1 and c1 > o1 and c2 < o2:
        return "Bullish Doji Reversal", "BUY", 10
    if c1 > o1 and c2 > o2 and c3 > o3 and body1 > body2 > 0:
        return "Three White Soldiers", "BUY", 18
    if c2 > o2 and c1 < o1 and c1 > o2 and body1 < body2 * 0.5:
        return "Bullish Harami", "BUY", 12
    if abs(l1 - l2) / range1 < 0.05 and c1 > o1 and c2 < o2:
        return "Tweezer Bottom", "BUY", 14

    if uw1 >= body1 * 2 and lw1 <= body1 * 0.3 and c1 < o1:
        return "Shooting Star", "SELL", 15
    if c2 > o2 and c1 < o1 and c1 < o2 and o1 > c2:
        return "Bearish Engulfing", "SELL", 22
    if c3 > o3 and body2 < range2 * 0.3 and c1 < o1 and c1 < (o3 + c3) / 2:
        return "Evening Star", "SELL", 20
    if c1 < o1 and body1 >= range1 * 0.85:
        return "Bearish Marubozu", "SELL", 14
    if c2 > o2 and c1 < o1 and o1 > h2 and c1 < (o2 + c2) / 2:
        return "Dark Cloud Cover", "SELL", 16
    if body1 < range1 * 0.1 and c1 < o1 and c2 > o2:
        return "Bearish Doji Reversal", "SELL", 10
    if c1 < o1 and c2 < o2 and c3 < o3 and body1 > body2 > 0:
        return "Three Black Crows", "SELL", 18
    if c2 < o2 and c1 > o1 and c1 < o2 and body1 < body2 * 0.5:
        return "Bearish Harami", "SELL", 12
    if abs(h1 - h2) / range1 < 0.05 and c1 < o1 and c2 > o2:
        return "Tweezer Top", "SELL", 14

    return None, None, 0


def detect_htf_candle_patterns(symbol, mt5_manager):
    """Candle patterns sirf H1, H4, D1 par."""
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


# ─── Breakout detection (M15 live + H1/H4 bonus) ────────────────────────────────

def detect_breakout(highs, lows, closes, lookback=20, min_body_ratio=0.30):
    """Closed-candle range breakout — H1/H4 bonus ke liye."""
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


def detect_m15_breakout_live(highs, lows, closes, live_bid, live_ask, lookback=15):
    """
    M15 live breakout — tick price se turant detect.
    Breakout milte hi trade: forming candle cross ya last 4 bars mein fresh cross.
    """
    empty_levels = {"recent_high": 0, "recent_low": 0, "range_height": 0, "breakout_level": 0}
    if len(closes) < lookback + 3:
        return None, None, 0, empty_levels

    # current forming candle ko range se bahar rakho
    recent_high = max(highs[-lookback - 1:-1])
    recent_low = min(lows[-lookback - 1:-1])
    range_height = max(recent_high - recent_low, 0.0001)
    last_closed = closes[-2]

    levels = {
        "recent_high": recent_high,
        "recent_low": recent_low,
        "range_height": range_height,
        "breakout_level": recent_high,
    }

    def _fresh_bull_cross():
        if live_ask <= recent_high and highs[-1] <= recent_high:
            return False
        # abhi live/forming candle break ho rahi hai
        if (live_ask > recent_high or highs[-1] > recent_high) and last_closed <= recent_high:
            return True
        # pichli 1-4 band hui candles mein cross
        for i in range(2, min(M15_FRESH_BARS + 2, len(closes))):
            if closes[-i] > recent_high and closes[-i - 1] <= recent_high:
                return True
        return False

    def _fresh_bear_cross():
        if live_bid >= recent_low and lows[-1] >= recent_low:
            return False
        if (live_bid < recent_low or lows[-1] < recent_low) and last_closed >= recent_low:
            return True
        for i in range(2, min(M15_FRESH_BARS + 2, len(closes))):
            if closes[-i] < recent_low and closes[-i - 1] >= recent_low:
                return True
        return False

    if _fresh_bull_cross():
        pierce = max(live_ask - recent_high, highs[-1] - recent_high, 0)
        strength = 28 + min(22, int(pierce / max(range_height * 0.05, 0.00001)))
        levels["breakout_level"] = recent_high
        return "M15 Bullish Breakout", "BUY", min(strength, 50), levels

    if _fresh_bear_cross():
        pierce = max(recent_low - live_bid, recent_low - lows[-1], 0)
        strength = 28 + min(22, int(pierce / max(range_height * 0.05, 0.00001)))
        levels["breakout_level"] = recent_low
        return "M15 Bearish Breakout", "SELL", min(strength, 50), levels

    return None, None, 0, levels


def detect_tf_breakout(ohlc, lookback):
    if ohlc is None:
        return None, None, 0, {}
    return detect_breakout(ohlc["highs"], ohlc["lows"], ohlc["closes"], lookback=lookback)


def get_multi_tf_breakouts(symbol, mt5_manager, tick=None):
    """M15 live breakout primary; H1/H4 sirf bonus score."""
    results = {}
    tf_config = [
        ("H1",  mt5_manager.TIMEFRAME_H1,  BREAKOUT_LOOKBACK["H1"],  80),
        ("H4",  mt5_manager.TIMEFRAME_H4,  BREAKOUT_LOOKBACK["H4"],  60),
    ]
    m15_ohlc = fetch_ohlc(symbol, mt5_manager.TIMEFRAME_M15, 120, mt5_manager)
    if m15_ohlc is None:
        results["M15"] = {"name": None, "dir": None, "strength": 0, "levels": {}, "ohlc": None}
    elif tick is not None:
        name, direction, strength, levels = detect_m15_breakout_live(
            m15_ohlc["highs"], m15_ohlc["lows"], m15_ohlc["closes"],
            tick.bid, tick.ask, lookback=BREAKOUT_LOOKBACK["M15"],
        )
        results["M15"] = {
            "name": name, "dir": direction, "strength": strength,
            "levels": levels, "ohlc": m15_ohlc,
        }
    else:
        name, direction, strength, levels = detect_tf_breakout(
            m15_ohlc, BREAKOUT_LOOKBACK["M15"])
        results["M15"] = {
            "name": name, "dir": direction, "strength": strength,
            "levels": levels, "ohlc": m15_ohlc,
        }

    for label, tf, lookback, count in tf_config:
        ohlc = fetch_ohlc(symbol, tf, count, mt5_manager)
        name, direction, strength, levels = detect_tf_breakout(ohlc, lookback)
        results[label] = {
            "name": name, "dir": direction, "strength": strength,
            "levels": levels, "ohlc": ohlc,
        }
    return results


def resolve_breakout_direction(breakouts):
    """M15 breakout = trade turant. H1/H4 sirf score bonus."""
    m15 = breakouts.get("M15", {})
    h1 = breakouts.get("H1", {})
    h4 = breakouts.get("H4", {})

    m15_dir = m15.get("dir")
    if not m15_dir:
        return None, 0, {}

    score = m15.get("strength", 0)
    for tf in ("H1", "H4"):
        if breakouts[tf].get("dir") == m15_dir:
            score += breakouts[tf].get("strength", 0) // 2
    if h1.get("dir") == m15_dir and h4.get("dir") == m15_dir:
        score += 15

    primary_levels = m15.get("levels") or h1.get("levels") or h4.get("levels") or {}
    return m15_dir, min(score, 100), primary_levels


# ─── SL / TP — breakout ke hisab se ───────────────────────────────────────────

def calc_breakout_sl(symbol, trade_type, entry_price, levels, mt5_manager):
    """
    Breakout range ke neeche/upar SL — thoda zyada door (adha point extra).
    """
    if not levels or not levels.get("recent_high"):
        atr = get_htf_atr(symbol, mt5_manager)
        if not atr:
            return None
        half = half_point_offset(symbol, mt5_manager)
        if trade_type == "BUY":
            return entry_price - atr - half
        return entry_price + atr + half

    highs = levels.get("recent_high", entry_price)
    lows = levels.get("recent_low", entry_price)
    range_h = levels.get("range_height", highs - lows)
    atr = get_htf_atr(symbol, mt5_manager) or (range_h * 0.15)
    buffer = atr * SL_BUFFER_ATR_MULT
    half = half_point_offset(symbol, mt5_manager)

    if trade_type == "BUY":
        sl = lows - buffer - half
        if sl >= entry_price:
            sl = entry_price - range_h * 0.5 - half
    else:
        sl = highs + buffer + half
        if sl <= entry_price:
            sl = entry_price + range_h * 0.5 + half

    return sl


def calc_breakout_tp_price(trade_type, entry_price, levels, symbol, mt5_manager):
    """Breakout range projection — TP thoda kam (adha point)."""
    half = half_point_offset(symbol, mt5_manager)
    range_h = levels.get("range_height", 0) if levels else 0
    if range_h <= 0:
        atr = get_htf_atr(symbol, mt5_manager)
        range_h = atr * 2 if atr else entry_price * 0.002

    if trade_type == "BUY":
        return entry_price + range_h - half
    return entry_price - range_h + half


def get_htf_atr(symbol, mt5_manager, period=14):
    rates = mt5_manager.copy_rates_from_pos(symbol, mt5_manager.TIMEFRAME_H1, 0, period + 20)
    if rates is None or len(rates) < period + 1:
        return None
    highs = [r["high"] for r in rates]
    lows = [r["low"] for r in rates]
    closes = [r["close"] for r in rates]
    atr = calc_atr(highs, lows, closes, period)
    return atr if atr and atr > 0 else None


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
    """TP dollar target — breakout range se, thoda kam."""
    tp_price = calc_breakout_tp_price(trade_type, entry_price, levels, symbol, mt5_manager)
    distance = abs(tp_price - entry_price)
    usd = price_distance_to_usd(distance, lot, symbol, mt5_manager)
    if usd is None:
        atr = get_htf_atr(symbol, mt5_manager) or 1.0
        info = mt5_manager.symbol_info(symbol)
        if info and info.trade_tick_size:
            usd = price_distance_to_usd(atr * 2, lot, symbol, mt5_manager) or 5.0
        else:
            usd = 5.0
    mult = 1.3 if score >= STRONG_SCORE else SCALP_ATR_MULT
    return round(max(3.0, min(200.0, usd * mult)), 2)


# Legacy alias — main.py position loop
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
    mult = 1.3 if score >= STRONG_SCORE else SCALP_ATR_MULT
    target = atr_dollar * mult - half_point_offset(symbol, mt5_manager)
    return round(max(3.0, min(200.0, target)), 2)


def calc_h1_sl(symbol, trade_type, entry_price, mt5_manager, levels=None):
    """Breakout SL — calc_breakout_sl ka wrapper."""
    return calc_breakout_sl(symbol, trade_type, entry_price, levels or {}, mt5_manager)


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
    """Breakout bias — H1/H4 direction (indicators nahi)."""
    breakouts = get_multi_tf_breakouts(symbol, mt5_manager)
    h1_dir = breakouts.get("H1", {}).get("dir")
    h4_dir = breakouts.get("H4", {}).get("dir")
    htf_aligned = h1_dir is not None and h4_dir is not None and h1_dir == h4_dir
    if htf_aligned:
        return h4_dir, 0, 0, True
    if h4_dir:
        return h4_dir, 0, 0, False
    if h1_dir:
        return h1_dir, 0, 0, False
    ohlc = fetch_ohlc(symbol, mt5_manager.TIMEFRAME_H1, 30, mt5_manager)
    if ohlc is None:
        return "BUY", 0, 0, False
    mid = (max(ohlc["highs"][-20:]) + min(ohlc["lows"][-20:])) / 2
    trend = "BUY" if ohlc["closes"][-1] > mid else "SELL"
    return trend, 0, 0, False


def get_risk_multiplier(score):
    if score >= 90:
        return 3.0
    if score >= STRONG_SCORE:
        return 2.5
    if score >= 60:
        return 2.0
    if score >= MIN_BREAKOUT_SCORE:
        return 1.5
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


def analyze_symbol(symbol, mt5_manager):
    """Breakout-only analysis — indicators nahi."""
    tick = mt5_manager.symbol_info_tick(symbol)
    sym_info = mt5_manager.symbol_info(symbol)
    if tick is None or sym_info is None:
        return None

    spread = (tick.ask - tick.bid) / sym_info.point
    max_spread = SYMBOL_MAX_SPREAD.get(symbol, MAX_SPREAD_POINTS)
    if spread > max_spread:
        return {"skip": True, "reason": "spread", "symbol": symbol, "spread": spread}

    breakouts = get_multi_tf_breakouts(symbol, mt5_manager, tick=tick)
    trend, score, levels = resolve_breakout_direction(breakouts)

    if trend is None:
        m15 = breakouts.get("M15", {})
        lvls = m15.get("levels") or {}
        if not lvls.get("recent_high") and m15.get("ohlc"):
            o = m15["ohlc"]
            lb = BREAKOUT_LOOKBACK["M15"]
            if len(o["closes"]) >= lb + 2:
                lvls = {
                    "recent_high": max(o["highs"][-lb - 1:-1]),
                    "recent_low": min(o["lows"][-lb - 1:-1]),
                }
        return {
            "skip": True, "reason": "no_breakout", "symbol": symbol,
            "m15_high": lvls.get("recent_high"),
            "m15_low": lvls.get("recent_low"),
            "bid": tick.bid, "ask": tick.ask,
        }

    htf_patterns = detect_htf_candle_patterns(symbol, mt5_manager)
    pattern_bonus = 0
    pattern_name = None
    pattern_conflict = False
    for tf_label, (pname, pdir, pbonus) in htf_patterns.items():
        if pdir == trend and pbonus > 0:
            pattern_bonus += pbonus // 3
            if not pattern_name:
                pattern_name = f"{tf_label}:{pname}"
        elif pdir and pdir != trend and pbonus >= 15:
            pattern_conflict = True

    score = min(100, score + pattern_bonus)
    trade_mode = "ELITE" if score >= STRONG_SCORE else "SCALP"

    m15 = breakouts["M15"]
    h1 = breakouts["H1"]
    h4 = breakouts["H4"]
    atr = get_htf_atr(symbol, mt5_manager)
    if atr is None and m15.get("ohlc"):
        o = m15["ohlc"]
        atr = calc_atr(o["highs"], o["lows"], o["closes"])

    entry_est = tick.ask if trend == "BUY" else tick.bid
    sl_est = calc_breakout_sl(symbol, trend, entry_est, levels, mt5_manager)
    sl_distance = abs(entry_est - sl_est) if sl_est else (atr or 1.0)

    breakout_names = []
    for tf in ("M15", "H1", "H4"):
        if breakouts[tf].get("dir") == trend:
            breakout_names.append(f"{tf}:{breakouts[tf].get('name')}")

    return {
        "symbol": symbol,
        "trend": trend,
        "score": score,
        "trade_mode": trade_mode,
        "atr": atr or 0,
        "breakout_levels": levels,
        "sl_distance": sl_distance,
        "htf_aligned": h1.get("dir") == h4.get("dir") == trend,
        "pattern_name": pattern_name,
        "pattern_conflict": pattern_conflict,
        "htf_patterns": htf_patterns,
        "breakouts": breakouts,
        "breakout_name": " + ".join(breakout_names),
        "breakout_dir": trend,
        "breakout_bonus": score,
        "m15_breakout": m15.get("name"),
        "h1_breakout": h1.get("name") if h1.get("dir") == trend else None,
        "h4_breakout": h4.get("name") if h4.get("dir") == trend else None,
        "tick": tick,
        "closes15": m15.get("ohlc", {}).get("closes", []),
    }


def trade_eligible(analysis):
    """M15 breakout milte hi trade — H1/H4 optional bonus."""
    if analysis.get("skip"):
        return False, "skip"

    if not analysis.get("m15_breakout"):
        return False, "no_m15_breakout"

    score = analysis.get("score", 0)
    if score < MIN_BREAKOUT_SCORE:
        return False, f"breakout_score_{score}_need_{MIN_BREAKOUT_SCORE}"

    return True, "ok"


def should_take_trade(analysis):
    return trade_eligible(analysis)
