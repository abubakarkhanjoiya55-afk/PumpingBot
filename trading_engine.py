"""
PumpingBot Trading Engine — indicators, candle patterns, scoring, risk.
Tuned for high win-rate scalping with strong-score position sizing.
"""

# ─── Engine constants ─────────────────────────────────────────────────────────
DAILY_MAX_LOSS_PCT    = 0.015   # 1.5% max daily loss
DAILY_PROFIT_TARGET   = 0.05    # 5% daily target — hit hone par bot ruk jata hai
DAILY_TRAIL_START     = 0.03    # 3% ke baad profit lock
DAILY_TRAIL_GAP       = 0.01    # 1% trail gap
RISK_PER_TRADE_PCT    = 0.003   # 0.3% base risk per trade
MAX_OPEN_TRADES       = 2       # kam trades = zyada focus, zyada accuracy
MAX_TRADES_PER_SYMBOL = 1       # ek symbol = ek trade (accuracy)
MIN_SCORE             = 85      # technical score minimum
MIN_TREND_STRUCTURE   = 80      # trend structure minimum
MIN_EFFECTIVE_SCORE   = 85      # min(score, struct) — dono strong hon
MIN_ADX_4H            = 22      # trend confirm
MIN_ADX_1H            = 20
STRONG_SCORE          = 88      # elite mode + higher lot
MARGIN_PROFIT_TRIGGER = 1.0     # margin ka 100% profit → SL lock start
MARGIN_SL_LOCK_PCT    = 0.70     # locked profit = 70% of peak
MAX_SPREAD_POINTS     = 2000
MIN_COOLDOWN_SEC      = 900     # 15 min
TRADE_MAX_LOSS_PCT    = 0.006   # ek trade par max 0.6% account loss
SCALP_ATR_MULT       = 0.45
HOLD_MIN_PROFIT      = 8.0
HOLD_TRAIL_PCT       = 0.72    # lock 72% of peak profit

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


# ─── Indicators ───────────────────────────────────────────────────────────────

def ema(prices, period):
    if len(prices) < period:
        return [prices[-1]] * len(prices)
    k = 2.0 / (period + 1)
    result = [prices[0]]
    for p in prices[1:]:
        result.append(p * k + result[-1] * (1 - k))
    return result


def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    return 100 - (100 / (1 + avg_gain / avg_loss))


def calc_stoch_rsi(closes, period=14, smooth=3):
    if len(closes) < period * 2:
        return 50, 50
    rsi_vals = []
    for i in range(period, len(closes)):
        rsi_vals.append(calc_rsi(closes[max(0, i - period):i + 1], period))
    if len(rsi_vals) < period:
        return 50, 50
    recent = rsi_vals[-period:]
    min_r, max_r = min(recent), max(recent)
    if max_r == min_r:
        return 50, 50
    k = (rsi_vals[-1] - min_r) / (max_r - min_r) * 100
    d = sum([(r - min_r) / (max_r - min_r) * 100 for r in rsi_vals[-smooth:]]) / smooth
    return k, d


def calc_adx(highs, lows, closes, period=14):
    try:
        if len(closes) < period + 1:
            return 0
        tr_list, pdm_list, ndm_list = [], [], []
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            pdm = max(highs[i] - highs[i - 1], 0) if highs[i] - highs[i - 1] > lows[i - 1] - lows[i] else 0
            ndm = max(lows[i - 1] - lows[i], 0) if lows[i - 1] - lows[i] > highs[i] - highs[i - 1] else 0
            tr_list.append(tr)
            pdm_list.append(pdm)
            ndm_list.append(ndm)
        atr = sum(tr_list[-period:]) / period
        if atr == 0:
            return 0
        pdi = (sum(pdm_list[-period:]) / period) / atr * 100
        ndi = (sum(ndm_list[-period:]) / period) / atr * 100
        return abs(pdi - ndi) / (pdi + ndi) * 100 if (pdi + ndi) > 0 else 0
    except Exception:
        return 0


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


def calc_macd(closes):
    if len(closes) < 26:
        return 0, 0
    e12 = ema(closes, 12)
    e26 = ema(closes, 26)
    macd_line = [a - b for a, b in zip(e12, e26)]
    signal_line = ema(macd_line, 9)
    hist = [m - s for m, s in zip(macd_line, signal_line)]
    return hist[-1], hist[-2] if len(hist) > 1 else hist[-1]


def calc_bollinger(closes, period=20, std_dev=2):
    if len(closes) < period:
        return closes[-1], closes[-1], closes[-1]
    recent = closes[-period:]
    mid = sum(recent) / period
    std = (sum((x - mid) ** 2 for x in recent) / period) ** 0.5
    return mid + std_dev * std, mid, mid - std_dev * std


def calc_supertrend(highs, lows, closes, period=10, multiplier=3.0):
    """Returns (direction, value): direction 1=BUY, -1=SELL."""
    if len(closes) < period + 2:
        return 0, closes[-1]
    atr_vals = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        atr_vals.append(tr)
    atr = sum(atr_vals[-period:]) / period
    hl2 = (highs[-1] + lows[-1]) / 2
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr
    if closes[-1] > upper:
        return 1, lower
    if closes[-1] < lower:
        return -1, upper
    return (1 if closes[-1] > ema(closes, period)[-1] else -1), (upper + lower) / 2


def calc_ichimoku(highs, lows, closes):
    """Tenkan, Kijun, Senkou A, Senkou B, cloud bias."""
    if len(closes) < 52:
        return None
    tenkan = (max(highs[-9:]) + min(lows[-9:])) / 2
    kijun = (max(highs[-26:]) + min(lows[-26:])) / 2
    senkou_a = (tenkan + kijun) / 2
    senkou_b = (max(highs[-52:]) + min(lows[-52:])) / 2
    price = closes[-1]
    above_cloud = price > max(senkou_a, senkou_b)
    below_cloud = price < min(senkou_a, senkou_b)
    tk_bull = tenkan > kijun
    return {
        "tenkan": tenkan, "kijun": kijun,
        "senkou_a": senkou_a, "senkou_b": senkou_b,
        "above_cloud": above_cloud, "below_cloud": below_cloud,
        "tk_bull": tk_bull, "tk_bear": not tk_bull,
    }


def detect_rsi_divergence(closes, lookback=20):
    """Bullish/bearish RSI divergence — extra confirmation."""
    if len(closes) < lookback + 5:
        return None, 0
    rsi_now = calc_rsi(closes)
    rsi_prev = calc_rsi(closes[:-5])
    price_higher = closes[-1] > closes[-6]
    price_lower = closes[-1] < closes[-6]
    if price_lower and rsi_now > rsi_prev + 3:
        return "BUY", 12
    if price_higher and rsi_now < rsi_prev - 3:
        return "SELL", 12
    return None, 0


# ─── Candle patterns (15+) ────────────────────────────────────────────────────

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

    # Bullish
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

    # Bearish
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


def find_swing_lows(lows, left=3, right=3):
    """Local swing lows — SL placement ke liye."""
    swings = []
    for i in range(left, len(lows) - right):
        window = lows[i - left:i + right + 1]
        if lows[i] == min(window):
            swings.append((i, lows[i]))
    return swings


def find_swing_highs(highs, left=3, right=3):
    """Local swing highs — SL placement ke liye."""
    swings = []
    for i in range(left, len(highs) - right):
        window = highs[i - left:i + right + 1]
        if highs[i] == max(window):
            swings.append((i, highs[i]))
    return swings


def detect_breakout(highs, lows, closes, trend, lookback=20):
    """
    M15 range / level breakout — sirf trend direction mein confirm.
    Returns (name, direction, strength).
    """
    if len(closes) < lookback + 2:
        return None, None, 0

    recent_high = max(highs[-lookback - 1:-1])
    recent_low = min(lows[-lookback - 1:-1])
    prev_close = closes[-2]
    price = closes[-1]
    body = abs(price - prev_close)
    avg_range = sum(h - l for h, l in zip(highs[-10:], lows[-10:])) / 10
    strong_move = body >= avg_range * 0.6

    if trend == "BUY" and price > recent_high and prev_close <= recent_high and strong_move:
        return "Bullish Breakout", "BUY", 25
    if trend == "SELL" and price < recent_low and prev_close >= recent_low and strong_move:
        return "Bearish Breakout", "SELL", 25
    return None, None, 0


def detect_chart_pattern(opens, highs, lows, closes):
    """
    M15 chart patterns — double top/bottom, H&S simplified, triangle breakout.
    Returns (name, direction, strength).
    """
    if len(closes) < 30:
        return None, None, 0

    swing_lows = find_swing_lows(lows)
    swing_highs = find_swing_highs(highs)

    # Double Bottom (W pattern)
    if len(swing_lows) >= 2:
        _, l1 = swing_lows[-2]
        _, l2 = swing_lows[-1]
        mid_high = max(highs[swing_lows[-2][0]:swing_lows[-1][0] + 1]) if swing_lows[-2][0] < swing_lows[-1][0] else 0
        tol = (mid_high - min(l1, l2)) * 0.02 if mid_high else abs(l1 - l2) * 0.05
        if abs(l1 - l2) <= max(tol, 0.0001) and closes[-1] > mid_high and mid_high > 0:
            return "Double Bottom", "BUY", 28

    # Double Top (M pattern)
    if len(swing_highs) >= 2:
        _, h1 = swing_highs[-2]
        _, h2 = swing_highs[-1]
        mid_low = min(lows[swing_highs[-2][0]:swing_highs[-1][0] + 1]) if swing_highs[-2][0] < swing_highs[-1][0] else 0
        tol = (max(h1, h2) - mid_low) * 0.02 if mid_low else abs(h1 - h2) * 0.05
        if abs(h1 - h2) <= max(tol, 0.0001) and closes[-1] < mid_low and mid_low > 0:
            return "Double Top", "SELL", 28

    # Head & Shoulders (simplified — 3 swing highs)
    if len(swing_highs) >= 3:
        _, ls = swing_highs[-3]
        _, head = swing_highs[-2]
        _, rs = swing_highs[-1]
        shoulder_tol = head * 0.003
        if head > ls and head > rs and abs(ls - rs) <= shoulder_tol and closes[-1] < min(ls, rs):
            return "Head & Shoulders", "SELL", 30

    # Inverse H&S (3 swing lows)
    if len(swing_lows) >= 3:
        _, ls = swing_lows[-3]
        _, head = swing_lows[-2]
        _, rs = swing_lows[-1]
        shoulder_tol = head * 0.003
        if head < ls and head < rs and abs(ls - rs) <= shoulder_tol and closes[-1] > max(ls, rs):
            return "Inverse H&S", "BUY", 30

    # Ascending triangle breakout
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        flat_top = abs(swing_highs[-1][1] - swing_highs[-2][1]) / swing_highs[-1][1] < 0.004
        rising_lows = swing_lows[-1][1] > swing_lows[-2][1]
        if flat_top and rising_lows and closes[-1] > swing_highs[-1][1]:
            return "Ascending Triangle", "BUY", 26

    # Descending triangle breakout
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        flat_bottom = abs(swing_lows[-1][1] - swing_lows[-2][1]) / swing_lows[-1][1] < 0.004
        falling_highs = swing_highs[-1][1] < swing_highs[-2][1]
        if flat_bottom and falling_highs and closes[-1] < swing_lows[-1][1]:
            return "Descending Triangle", "SELL", 26

    return None, None, 0


def calc_trend_structure_score(trend, adx_4h, adx_1h, closes, e8, e21, e50, e200,
                                supertrend_dir, ichimoku, htf_aligned):
    """
    Mazboot trend structures ka combined score (0–100).
    90+ = high-probability trend continuation setup.
    """
    score = 0

    if htf_aligned:
        score += 22
    if adx_4h >= 35:
        score += 18
    elif adx_4h >= 28:
        score += 14
    elif adx_4h >= 22:
        score += 8
    if adx_1h >= 28:
        score += 10
    elif adx_1h >= 22:
        score += 6

    # EMA ribbon — full stack
    if trend == "BUY" and e8 > e21 > e50 > e200:
        score += 20
    elif trend == "SELL" and e8 < e21 < e50 < e200:
        score += 20
    elif trend == "BUY" and e8 > e21 > e50:
        score += 12
    elif trend == "SELL" and e8 < e21 < e50:
        score += 12

    # Higher highs / higher lows structure (last 10 bars)
    if len(closes) >= 12:
        mid = len(closes) // 2
        first_half = closes[:mid]
        second_half = closes[mid:]
        if trend == "BUY" and max(second_half) > max(first_half) and min(second_half) > min(first_half):
            score += 12
        elif trend == "SELL" and max(second_half) < max(first_half) and min(second_half) < min(first_half):
            score += 12

    if trend == "BUY" and supertrend_dir == 1:
        score += 8
    elif trend == "SELL" and supertrend_dir == -1:
        score += 8

    if ichimoku:
        if trend == "BUY" and ichimoku["above_cloud"] and ichimoku["tk_bull"]:
            score += 10
        elif trend == "SELL" and ichimoku["below_cloud"] and ichimoku["tk_bear"]:
            score += 10

    return min(score, 100)


def calc_h1_sl(symbol, trade_type, entry_price, mt5_manager):
    """
    1H candle patterns + swing structure se sahi SL.
    Pattern wick / swing low-high ke neeche/upar buffer ke sath.
    """
    rates = mt5_manager.copy_rates_from_pos(symbol, mt5_manager.TIMEFRAME_H1, 0, 60)
    if rates is None or len(rates) < 12:
        atr = get_htf_atr(symbol, mt5_manager)
        if not atr:
            return None
        return entry_price - atr * 1.2 if trade_type == "BUY" else entry_price + atr * 1.2

    opens = [r["open"] for r in rates]
    highs = [r["high"] for r in rates]
    lows = [r["low"] for r in rates]
    closes = [r["close"] for r in rates]
    atr = calc_atr(highs, lows, closes) or (highs[-1] - lows[-1])

    _, pdir, _ = detect_candle_pattern(opens, highs, lows, closes)
    swing_lows = find_swing_lows(lows)
    swing_highs = find_swing_highs(highs)
    buffer = atr * 0.15

    if trade_type == "BUY":
        candidates = [lows[-2], lows[-3]]
        if swing_lows:
            candidates.append(swing_lows[-1][1])
        if pdir == "BUY":
            candidates.append(lows[-1])
        sl = min(candidates) - buffer
        if sl >= entry_price:
            sl = entry_price - atr * 1.2
    else:
        candidates = [highs[-2], highs[-3]]
        if swing_highs:
            candidates.append(swing_highs[-1][1])
        if pdir == "SELL":
            candidates.append(highs[-1])
        sl = max(candidates) + buffer
        if sl <= entry_price:
            sl = entry_price + atr * 1.2

    return sl


def get_htf_atr(symbol, mt5_manager, period=14):
    """
    SL/TP ka basis 1H volatility par — entry analysis M15 candles se hoti hai.
    isse SL trade lagte hi tight hit nahi hota, market ke real breathing room ke
    hisab se set hota hai.
    """
    rates = mt5_manager.copy_rates_from_pos(symbol, mt5_manager.TIMEFRAME_H1, 0, period + 20)
    if rates is None or len(rates) < period + 1:
        return None
    highs = [r["high"] for r in rates]
    lows = [r["low"] for r in rates]
    closes = [r["close"] for r in rates]
    atr = calc_atr(highs, lows, closes, period)
    return atr if atr and atr > 0 else None


def calc_margin_used(lot, symbol, price, mt5_manager):
    """Approximate broker margin used for this position (lot * contract_size * price / leverage)."""
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
    """Convert a target dollar profit into the equivalent price level (for broker-side SL lock)."""
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
    r1h = mt5_manager.copy_rates_from_pos(symbol, mt5_manager.TIMEFRAME_H1, 0, 200)
    r4h = mt5_manager.copy_rates_from_pos(symbol, mt5_manager.TIMEFRAME_H4, 0, 100)
    if r1h is None or len(r1h) < 50:
        return "BUY", 15, 15, False

    closes1h = [r["close"] for r in r1h]
    highs1h = [r["high"] for r in r1h]
    lows1h = [r["low"] for r in r1h]
    e100 = ema(closes1h, min(100, len(closes1h) - 1))
    e20 = ema(closes1h, 20)
    e50 = ema(closes1h, 50)
    adx_1h = calc_adx(highs1h, lows1h, closes1h)
    price = closes1h[-1]

    trend_1h = "BUY" if price > e50[-1] and e20[-1] > e50[-1] else (
        "SELL" if price < e50[-1] and e20[-1] < e50[-1] else
        ("BUY" if e20[-1] > e20[-5] else "SELL")
    )

    adx_4h = adx_1h
    trend_4h = trend_1h
    if r4h is not None and len(r4h) >= 30:
        closes4h = [r["close"] for r in r4h]
        highs4h = [r["high"] for r in r4h]
        lows4h = [r["low"] for r in r4h]
        adx_4h = calc_adx(highs4h, lows4h, closes4h)
        e20_4h = ema(closes4h, 20)
        e50_4h = ema(closes4h, 50)
        trend_4h = "BUY" if e20_4h[-1] > e50_4h[-1] and closes4h[-1] > e50_4h[-1] else (
            "SELL" if e20_4h[-1] < e50_4h[-1] and closes4h[-1] < e50_4h[-1] else trend_1h
        )

    htf_aligned = trend_1h == trend_4h
    trend = trend_4h if htf_aligned else trend_1h
    return trend, adx_4h, adx_1h, htf_aligned


def calc_score(trend, adx_4h, adx_1h, rsi, stoch_k, stoch_d,
               macd_h, macd_h_prev, closes, e8, e21, e50, e200,
               bb_upper, bb_lower, bb_mid, pattern_dir, pattern_bonus,
               supertrend_dir, ichimoku, htf_aligned, div_dir, div_bonus):
    score = 0
    price = closes[-1]

    # HTF alignment — mandatory base
    if htf_aligned:
        score += 15
    else:
        score += 5

    # ADX trend strength
    if adx_4h >= 30:
        score += 15
    elif adx_4h >= 22:
        score += 10
    elif adx_4h >= 18:
        score += 5

    if adx_1h >= 25:
        score += 8
    elif adx_1h >= 18:
        score += 4

    # EMA ribbon stack
    if trend == "BUY" and e8 > e21 > e50 > e200:
        score += 15
    elif trend == "SELL" and e8 < e21 < e50 < e200:
        score += 15
    elif trend == "BUY" and e8 > e21 > e50:
        score += 10
    elif trend == "SELL" and e8 < e21 < e50:
        score += 10
    elif trend == "BUY" and e8 > e21:
        score += 5
    elif trend == "SELL" and e8 < e21:
        score += 5

    # Stoch RSI
    if trend == "BUY" and stoch_k < 25 and stoch_k > stoch_d:
        score += 10
    elif trend == "SELL" and stoch_k > 75 and stoch_k < stoch_d:
        score += 10
    elif trend == "BUY" and stoch_k < 35:
        score += 5
    elif trend == "SELL" and stoch_k > 65:
        score += 5

    # MACD momentum
    if trend == "BUY" and macd_h > 0 and macd_h > macd_h_prev:
        score += 10
    elif trend == "SELL" and macd_h < 0 and macd_h < macd_h_prev:
        score += 10
    elif trend == "BUY" and macd_h_prev < 0 < macd_h:
        score += 8
    elif trend == "SELL" and macd_h_prev > 0 > macd_h:
        score += 8

    # Bollinger squeeze / bounce
    if trend == "BUY" and price <= bb_lower:
        score += 6
    elif trend == "SELL" and price >= bb_upper:
        score += 6

    # Supertrend
    if trend == "BUY" and supertrend_dir == 1:
        score += 8
    elif trend == "SELL" and supertrend_dir == -1:
        score += 8

    # Ichimoku cloud
    if ichimoku:
        if trend == "BUY" and ichimoku["above_cloud"] and ichimoku["tk_bull"]:
            score += 10
        elif trend == "SELL" and ichimoku["below_cloud"] and ichimoku["tk_bear"]:
            score += 10
        elif trend == "BUY" and ichimoku["tk_bull"]:
            score += 5
        elif trend == "SELL" and ichimoku["tk_bear"]:
            score += 5

    # Candle pattern confirmation
    if pattern_dir == trend and pattern_bonus > 0:
        score += pattern_bonus

    # RSI divergence
    if div_dir == trend and div_bonus > 0:
        score += div_bonus

    # RSI filter — avoid overbought buys / oversold sells
    if trend == "BUY" and rsi > 72:
        score -= 10
    elif trend == "SELL" and rsi < 28:
        score -= 10
    elif trend == "BUY" and 40 <= rsi <= 65:
        score += 5
    elif trend == "SELL" and 35 <= rsi <= 60:
        score += 5

    return max(0, min(score, 100))


def get_risk_multiplier(score):
    """Strong score = higher margin allocation (scaled lot)."""
    if score >= 92:
        return 4.0
    if score >= 85:
        return 3.2
    if score >= 78:
        return 2.5
    if score >= 72:
        return 1.8
    return 1.0


def get_profit_target(score, atr, symbol, mt5_manager):
    info = mt5_manager.symbol_info(symbol)
    if info is None or atr == 0:
        return 5.0
    tick_value = info.trade_tick_value
    tick_size = info.trade_tick_size
    if tick_value == 0 or tick_size == 0:
        return 5.0
    atr_dollar = (atr / tick_size) * tick_value * 0.01
    if score >= STRONG_SCORE:
        mult = 2.2 if score >= 90 else 1.8
    else:
        mult = SCALP_ATR_MULT
    return round(max(2.0, min(120.0, atr_dollar * mult)), 2)


def get_locked_profit(current_profit):
    locked = None
    for trigger, lock in TRAILING_LEVELS:
        if current_profit >= trigger:
            locked = lock
    return locked


def is_scalp_trade(score):
    return score < STRONG_SCORE


def calculate_lot(balance, atr, symbol, score, mt5_manager):
    try:
        mult = get_risk_multiplier(score)
        risk_amount = balance * RISK_PER_TRADE_PCT * mult
        info = mt5_manager.symbol_info(symbol)
        if info is None:
            return None
        tick_value = info.trade_tick_value
        tick_size = info.trade_tick_size
        if atr == 0 or tick_value == 0 or tick_size == 0:
            return info.volume_min
        sl_ticks = atr / tick_size
        lot = risk_amount / (sl_ticks * tick_value)
        lot = max(info.volume_min, min(info.volume_max,
              round(lot / info.volume_step) * info.volume_step))
        return round(lot, 2)
    except Exception:
        return None


def analyze_symbol(symbol, mt5_manager):
    """Full analysis for one symbol — returns dict or None if skip."""
    tick = mt5_manager.symbol_info_tick(symbol)
    sym_info = mt5_manager.symbol_info(symbol)
    if tick is None or sym_info is None:
        return None

    spread = (tick.ask - tick.bid) / sym_info.point
    max_spread = SYMBOL_MAX_SPREAD.get(symbol, MAX_SPREAD_POINTS)
    if spread > max_spread:
        return {"skip": True, "reason": "spread", "symbol": symbol, "spread": spread}

    trend, adx_4h, adx_1h, htf_aligned = get_trend(symbol, mt5_manager)

    # Entry signals sirf M15 candles se — M5/M1 scalping band
    rates15 = mt5_manager.copy_rates_from_pos(symbol, mt5_manager.TIMEFRAME_M15, 0, 250)
    if rates15 is None or len(rates15) < 55:
        return {"skip": True, "reason": "no_data", "symbol": symbol}

    opens15 = [r["open"] for r in rates15]
    highs15 = [r["high"] for r in rates15]
    lows15 = [r["low"] for r in rates15]
    closes15 = [r["close"] for r in rates15]

    e8_l = ema(closes15, 8)
    e21_l = ema(closes15, 21)
    e50_l = ema(closes15, 50)
    e200_l = ema(closes15, min(200, len(closes15) - 1))
    rsi = calc_rsi(closes15)
    stk, std = calc_stoch_rsi(closes15)
    atr_m15 = calc_atr(highs15, lows15, closes15)
    # SL/TP 1H volatility — M15 ATR sirf backup
    atr = get_htf_atr(symbol, mt5_manager) or atr_m15
    mh, mhp = calc_macd(closes15)
    bbu, bbm, bbl = calc_bollinger(closes15)
    st_dir, _ = calc_supertrend(highs15, lows15, closes15)
    ichimoku = calc_ichimoku(highs15, lows15, closes15)
    pname, pdir, pbonus = detect_candle_pattern(opens15, highs15, lows15, closes15)
    cname, cdir, cbonus = detect_chart_pattern(opens15, highs15, lows15, closes15)
    bname, bdir, bbonus = detect_breakout(highs15, lows15, closes15, trend)
    ddir, dbonus = detect_rsi_divergence(closes15)

    trend_struct = calc_trend_structure_score(
        trend, adx_4h, adx_1h, closes15,
        e8_l[-1], e21_l[-1], e50_l[-1], e200_l[-1],
        st_dir, ichimoku, htf_aligned,
    )

    # Best M15 confirmation signal
    m15_confirm_name = None
    m15_confirm_dir = None
    m15_confirm_bonus = 0
    for name, direction, bonus in [
        (pname, pdir, pbonus), (cname, cdir, cbonus), (bname, bdir, bbonus),
    ]:
        if direction == trend and bonus > m15_confirm_bonus:
            m15_confirm_name = name
            m15_confirm_dir = direction
            m15_confirm_bonus = bonus

    score = calc_score(
        trend, adx_4h, adx_1h, rsi, stk, std,
        mh, mhp, closes15,
        e8_l[-1], e21_l[-1], e50_l[-1], e200_l[-1],
        bbu, bbl, bbm, pdir, pbonus,
        st_dir, ichimoku, htf_aligned, ddir, dbonus,
    )
    # Chart pattern + breakout bonus
    if cdir == trend and cbonus:
        score = min(100, score + cbonus // 2)
    if bdir == trend and bbonus:
        score = min(100, score + bbonus // 2)
    if trend_struct >= MIN_TREND_STRUCTURE:
        score = min(100, score + 5)

    trade_mode = "ELITE" if score >= STRONG_SCORE else "HOLD"
    m15_aligned = (
        (trend == "BUY" and e8_l[-1] > e21_l[-1] and closes15[-1] > closes15[-2]) or
        (trend == "SELL" and e8_l[-1] < e21_l[-1] and closes15[-1] < closes15[-2])
    )
    m15_confirmed = (
        (pdir == trend and pbonus >= 12) or
        (cdir == trend and cbonus >= 20) or
        (bdir == trend and bbonus >= 20) or
        trend_struct >= MIN_TREND_STRUCTURE
    )

    return {
        "symbol": symbol,
        "trend": trend,
        "score": score,
        "trade_mode": trade_mode,
        "atr": atr,
        "atr_m15": atr_m15,
        "adx_4h": adx_4h,
        "adx_1h": adx_1h,
        "rsi": rsi,
        "htf_aligned": htf_aligned,
        "m15_aligned": m15_aligned,
        "m15_confirmed": m15_confirmed,
        "trend_structure": trend_struct,
        "pattern_name": pname,
        "pattern_dir": pdir,
        "pattern_bonus": pbonus,
        "chart_pattern_name": cname,
        "chart_pattern_dir": cdir,
        "chart_pattern_bonus": cbonus,
        "breakout_name": bname,
        "breakout_dir": bdir,
        "breakout_bonus": bbonus,
        "m15_confirm_name": m15_confirm_name,
        "m15_confirm_dir": m15_confirm_dir,
        "tick": tick,
        "closes15": closes15,
        "e8": e8_l[-1],
        "e21": e21_l[-1],
        "macd": mh,
    }


def trade_eligible(analysis):
    """Same checks as should_take_trade — returns (ok, reason) with clear labels."""
    if analysis.get("skip"):
        return False, "skip"

    score = analysis["score"]
    trend_struct = analysis.get("trend_structure", 0)
    effective = min(score, trend_struct)

    if effective < MIN_EFFECTIVE_SCORE:
        return False, f"effective_{effective}_need_{MIN_EFFECTIVE_SCORE}"
    if score < MIN_SCORE:
        return False, f"score_{score}_need_{MIN_SCORE}"
    if trend_struct < MIN_TREND_STRUCTURE:
        return False, f"struct_{trend_struct}_need_{MIN_TREND_STRUCTURE}"

    if not analysis["htf_aligned"]:
        return False, "htf_conflict"

    if analysis["adx_4h"] < MIN_ADX_4H:
        return False, "weak_adx_4h"

    if analysis["adx_1h"] < MIN_ADX_1H:
        return False, "weak_adx_1h"

    if not analysis.get("m15_aligned"):
        return False, "m15_conflict"

    if not analysis.get("m15_confirmed"):
        return False, "no_m15_confirm"

    pdir = analysis.get("pattern_dir")
    cdir = analysis.get("chart_pattern_dir")
    bdir = analysis.get("breakout_dir")
    trend = analysis["trend"]

    if pdir and pdir != trend:
        return False, "pattern_conflict"
    if cdir and cdir != trend:
        return False, "chart_conflict"
    if bdir and bdir != trend:
        return False, "breakout_conflict"

    rsi = analysis.get("rsi", 50)
    if trend == "BUY" and rsi > 68:
        return False, "rsi_overbought"
    if trend == "SELL" and rsi < 32:
        return False, "rsi_oversold"

    return True, "ok"


def should_take_trade(analysis):
    """Final gate — sirf elite setups jahan score AUR structure dono strong hon."""
    return trade_eligible(analysis)
