"""
Smart Money Concepts (SMC) + HTF range breakouts for Joy / My Signals.

Pro-trader toolkit (ICT / SMC style):
  - Break of Structure (BOS) / Change of Character (CHoCH)
  - Order Blocks (bullish / bearish)
  - Fair Value Gaps (FVG / imbalance)
  - Liquidity sweep (stop hunt) + reversal
  - Equal highs / equal lows liquidity grab
  - Range / consolidation breakout (1H · 4H · 1D)

Every hit carries:
  reasons[]  — bullet list of why the trade exists
  advice     — full Urdu/English explanation
  strategy   — strategy family tag
"""
from __future__ import annotations

from typing import Any

# Timeframes where HTF range breakouts fire by default
BREAKOUT_FOCUS_TFS = frozenset({"1h", "4H", "D1"})
SMC_TFS = frozenset({"1h", "4H", "D1", "1W"})

SMC_PATTERNS = frozenset({
    "BOS",
    "CHoCH",
    "Order Block",
    "Fair Value Gap",
    "Liquidity Sweep",
    "Equal Liquidity",
    "Range Breakout",
})


def _avg_range(ohlc: dict, end: int | None = None, look: int = 14) -> float:
    h, l = ohlc["highs"], ohlc["lows"]
    n = len(h)
    e = n if end is None else max(1, min(end, n))
    start = max(0, e - look)
    ranges = [h[j] - l[j] for j in range(start, e)]
    if not ranges:
        return abs(float(ohlc["closes"][-1])) * 0.01 if ohlc["closes"] else 0.01
    return sum(ranges) / len(ranges)


def _round_p(price: float) -> float:
    a = abs(price)
    if a >= 1000:
        return round(price, 2)
    if a >= 100:
        return round(price, 3)
    if a >= 1:
        return round(price, 4)
    if a >= 0.01:
        return round(price, 5)
    return round(price, 6)


def _swing_points(
    values: list[float],
    *,
    kind: str,
    left: int = 2,
    right: int = 2,
    end: int | None = None,
) -> list[tuple[int, float]]:
    """Strict local swing highs/lows up to `end` (exclusive of forming bar)."""
    n = len(values)
    hi = (n - 1) if end is None else min(end, n - 1)
    out: list[tuple[int, float]] = []
    for i in range(left, hi - right + 1):
        window_l = values[i - left:i]
        window_r = values[i + 1:i + right + 1]
        if not window_l or not window_r:
            continue
        if kind == "high":
            if values[i] >= max(window_l) and values[i] >= max(window_r):
                out.append((i, float(values[i])))
        else:
            if values[i] <= min(window_l) and values[i] <= min(window_r):
                out.append((i, float(values[i])))
    return out


def _body_frac(ohlc: dict, i: int) -> float:
    h, l, c, o = ohlc["highs"], ohlc["lows"], ohlc["closes"], ohlc["opens"]
    rng = max(h[i] - l[i], 1e-12)
    return abs(c[i] - o[i]) / rng


def _is_bull(ohlc: dict, i: int) -> bool:
    return float(ohlc["closes"][i]) > float(ohlc["opens"][i])


def _is_bear(ohlc: dict, i: int) -> bool:
    return float(ohlc["closes"][i]) < float(ohlc["opens"][i])


def build_explanation(
    *,
    pattern: str,
    direction: str,
    reasons: list[str],
    level: float | None = None,
    timeframe: str = "",
    extra: str = "",
) -> str:
    """Human-readable trade thesis (Roman Urdu + English cues)."""
    side = "LONG (BUY)" if direction == "UP" else "SHORT (SELL)"
    tf = f" · TF {timeframe}" if timeframe else ""
    lvl = f" @ {_round_p(level)}" if level is not None else ""
    bullets = " | ".join(reasons[:6]) if reasons else "Structure confirm"
    base = (
        f"Trade basis: {pattern}{lvl}{tf} → {side}. "
        f"Kyun: {bullets}."
    )
    if extra:
        return f"{base} {extra}"
    return base


def _pack(
    *,
    pattern: str,
    direction: str,
    level: float,
    close: float,
    candle_time: int,
    reasons: list[str],
    detail: str,
    strategy: str,
    live: bool = False,
    stage: str = "confirmed",
    timeframe: str = "",
    extra_advice: str = "",
) -> dict[str, Any]:
    side = "BUY" if direction == "UP" else "SELL"
    advice = build_explanation(
        pattern=pattern,
        direction=direction,
        reasons=reasons,
        level=level,
        timeframe=timeframe,
        extra=extra_advice,
    )
    return {
        "side": side,
        "direction": direction,
        "pattern": pattern,
        "patternDetail": detail,
        "level": float(level),
        "close": float(close),
        "candleTime": candle_time,
        "live": live,
        "stage": stage,
        "strategy": strategy,
        "reasons": list(reasons),
        "advice": advice,
    }


# ─── Range / Consolidation Breakout (1H 4H 1D) ───────────────────────────

def detect_range_breakout(
    ohlc: dict,
    *,
    lookback: int = 20,
    live: bool = False,
    timeframe: str = "",
    max_ext_atr: float = 0.85,
) -> dict | None:
    """
    Classic HTF range break: last N closed candles define range;
    candidate closes beyond high/low with body confirmation.
    """
    h, l, c, o, t = (
        ohlc["highs"], ohlc["lows"], ohlc["closes"], ohlc["opens"], ohlc["times"]
    )
    n = len(c)
    if n < lookback + 4:
        return None
    i = (n - 1) if live else (n - 2)
    if i < lookback + 1:
        return None
    # Range from candles BEFORE candidate
    seg_h = h[i - lookback:i]
    seg_l = l[i - lookback:i]
    rh, rl = max(seg_h), min(seg_l)
    height = rh - rl
    atr = _avg_range(ohlc, i) or abs(c[i]) * 0.01
    if height < atr * 0.8:
        return None  # not a meaningful range
    # Compression quality: range not exploding already
    if height > atr * 6:
        return None

    close, open_, hi, lo = float(c[i]), float(o[i]), float(h[i]), float(l[i])
    body = abs(close - open_)
    if body < atr * 0.18:
        return None

    reasons: list[str] = [
        f"{timeframe or 'HTF'} range high={_round_p(rh)} / low={_round_p(rl)}",
        f"Last {lookback} candles compressed (height {_round_p(height)})",
    ]

    if close > rh and close > open_:
        ext = (close - rh) / atr
        if ext > max_ext_atr:
            return None
        reasons.append(f"Close {_round_p(close)} ne resistance {_round_p(rh)} tod di")
        reasons.append("Bullish body confirm — range breakout LONG")
        if live:
            reasons.append("LIVE candle — early entry, confirmation wait optional")
        return _pack(
            pattern="Range Breakout",
            direction="UP",
            level=rh,
            close=close,
            candle_time=int(t[i]),
            reasons=reasons,
            detail=f"1H/4H/1D range break UP{' (LIVE)' if live else ''}",
            strategy="HTF Range Breakout",
            live=live,
            timeframe=timeframe,
            extra_advice="Entry near break; SL range mid/low; TP = range height projection.",
        )

    if close < rl and close < open_:
        ext = (rl - close) / atr
        if ext > max_ext_atr:
            return None
        reasons.append(f"Close {_round_p(close)} ne support {_round_p(rl)} tod di")
        reasons.append("Bearish body confirm — range breakdown SHORT")
        if live:
            reasons.append("LIVE candle — early entry, confirmation wait optional")
        return _pack(
            pattern="Range Breakout",
            direction="DOWN",
            level=rl,
            close=close,
            candle_time=int(t[i]),
            reasons=reasons,
            detail=f"1H/4H/1D range break DOWN{' (LIVE)' if live else ''}",
            strategy="HTF Range Breakout",
            live=live,
            timeframe=timeframe,
            extra_advice="Entry near break; SL range mid/high; TP = range height projection.",
        )
    return None


# ─── BOS / CHoCH ─────────────────────────────────────────────────────────

def detect_bos_choch(
    ohlc: dict,
    *,
    live: bool = False,
    timeframe: str = "",
) -> dict | None:
    """
    Break of Structure / Change of Character on swing points.
    BOS = trend continuation (HH→break or LL→break).
    CHoCH = first opposite structure break (trend flip warning).
    """
    h, l, c, t = ohlc["highs"], ohlc["lows"], ohlc["closes"], ohlc["times"]
    n = len(c)
    if n < 30:
        return None
    i = (n - 1) if live else (n - 2)
    swings_h = _swing_points(h, kind="high", end=i)
    swings_l = _swing_points(l, kind="low", end=i)
    if len(swings_h) < 2 or len(swings_l) < 2:
        return None

    sh1, sh0 = swings_h[-2], swings_h[-1]
    sl1, sl0 = swings_l[-2], swings_l[-1]
    close = float(c[i])
    atr = _avg_range(ohlc, i)

    # Prior trend: higher highs + higher lows = bullish structure
    bull_struct = sh0[1] > sh1[1] and sl0[1] > sl1[1]
    bear_struct = sh0[1] < sh1[1] and sl0[1] < sl1[1]

    # Bullish BOS: close breaks last swing high while structure was bullish/neutral
    if close > sh0[1] and (close - sh0[1]) <= atr * 1.2:
        if bull_struct or (not bear_struct and sl0[1] >= sl1[1] * 0.998):
            reasons = [
                f"Swing high {_round_p(sh0[1])} break = BOS bullish",
                f"Prior structure HH/HL (swings {_round_p(sh1[1])}→{_round_p(sh0[1])})",
                "Smart money continuation — trend ke saath LONG",
            ]
            return _pack(
                pattern="BOS",
                direction="UP",
                level=sh0[1],
                close=close,
                candle_time=int(t[i]),
                reasons=reasons,
                detail=f"Break of Structure UP{' (LIVE)' if live else ''}",
                strategy="SMC · BOS",
                live=live,
                timeframe=timeframe,
                extra_advice="Pro tip: pullback to broken level / bullish OB pe entry refine karo.",
            )
        # Was bearish → CHoCH
        if bear_struct:
            reasons = [
                f"Bearish structure tori — CHoCH UP @ {_round_p(sh0[1])}",
                "Pehli opposite BOS = character change (trend flip)",
                "Reversal bias LONG — confirmation + FVG/OB wait best",
            ]
            return _pack(
                pattern="CHoCH",
                direction="UP",
                level=sh0[1],
                close=close,
                candle_time=int(t[i]),
                reasons=reasons,
                detail=f"Change of Character UP{' (LIVE)' if live else ''}",
                strategy="SMC · CHoCH",
                live=live,
                timeframe=timeframe,
                extra_advice="CHoCH pe size chhota; next BOS ke baad add karo.",
            )

    # Bearish BOS
    if close < sl0[1] and (sl0[1] - close) <= atr * 1.2:
        if bear_struct or (not bull_struct and sh0[1] <= sh1[1] * 1.002):
            reasons = [
                f"Swing low {_round_p(sl0[1])} break = BOS bearish",
                f"Prior structure LH/LL (swings {_round_p(sl1[1])}→{_round_p(sl0[1])})",
                "Smart money continuation — trend ke saath SHORT",
            ]
            return _pack(
                pattern="BOS",
                direction="DOWN",
                level=sl0[1],
                close=close,
                candle_time=int(t[i]),
                reasons=reasons,
                detail=f"Break of Structure DOWN{' (LIVE)' if live else ''}",
                strategy="SMC · BOS",
                live=live,
                timeframe=timeframe,
                extra_advice="Pro tip: rally to broken level / bearish OB pe entry refine karo.",
            )
        if bull_struct:
            reasons = [
                f"Bullish structure tori — CHoCH DOWN @ {_round_p(sl0[1])}",
                "Pehli opposite BOS = character change (trend flip)",
                "Reversal bias SHORT — confirmation + FVG/OB wait best",
            ]
            return _pack(
                pattern="CHoCH",
                direction="DOWN",
                level=sl0[1],
                close=close,
                candle_time=int(t[i]),
                reasons=reasons,
                detail=f"Change of Character DOWN{' (LIVE)' if live else ''}",
                strategy="SMC · CHoCH",
                live=live,
                timeframe=timeframe,
                extra_advice="CHoCH pe size chhota; next BOS ke baad add karo.",
            )
    return None


# ─── Order Blocks ────────────────────────────────────────────────────────

def detect_order_block(
    ohlc: dict,
    *,
    live: bool = False,
    timeframe: str = "",
    look: int = 25,
) -> dict | None:
    """
    Last opposing candle before an impulsive move = Order Block.
    Signal when price returns into OB zone and reacts (mitigation).
    """
    h, l, c, o, t = (
        ohlc["highs"], ohlc["lows"], ohlc["closes"], ohlc["opens"], ohlc["times"]
    )
    n = len(c)
    if n < look + 5:
        return None
    i = (n - 1) if live else (n - 2)
    atr = _avg_range(ohlc, i)
    # Find impulsive move in recent history (before candidate)
    for j in range(i - 3, max(4, i - look), -1):
        move = c[j] - c[j - 3]
        # Bullish impulse: find last bearish candle before impulse start
        if move >= atr * 1.8:
            ob_idx = None
            for k in range(j - 1, max(0, j - 6), -1):
                if _is_bear(ohlc, k):
                    ob_idx = k
                    break
            if ob_idx is None:
                continue
            ob_high, ob_low = float(h[ob_idx]), float(l[ob_idx])
            # Mitigation: price revisited zone and held
            touched = l[i] <= ob_high + atr * 0.05 and h[i] >= ob_low - atr * 0.05
            held = c[i] >= ob_low and _is_bull(ohlc, i)
            if not (touched and held):
                continue
            # Must not have fully closed through OB already much earlier
            if min(l[ob_idx + 1:i + 1] or [ob_low]) < ob_low - atr * 0.35:
                continue
            mid = (ob_high + ob_low) / 2
            reasons = [
                f"Bullish Order Block {_round_p(ob_low)}–{_round_p(ob_high)}",
                f"Impulse move +{_round_p(move)} (~{round(move / atr, 1)} ATR) ke pehle last sell candle",
                "Price OB zone pe wapas aayi (mitigation) aur green hold",
                "Institutions ke pending buy orders zone — LONG bias",
            ]
            return _pack(
                pattern="Order Block",
                direction="UP",
                level=mid,
                close=float(c[i]),
                candle_time=int(t[i]),
                reasons=reasons,
                detail=f"Bullish OB mitigation{' (LIVE)' if live else ''}",
                strategy="SMC · Order Block",
                live=live,
                timeframe=timeframe,
                extra_advice="SL OB low ke neeche; TP next liquidity / opposing FVG.",
            )

        # Bearish impulse
        if move <= -atr * 1.8:
            ob_idx = None
            for k in range(j - 1, max(0, j - 6), -1):
                if _is_bull(ohlc, k):
                    ob_idx = k
                    break
            if ob_idx is None:
                continue
            ob_high, ob_low = float(h[ob_idx]), float(l[ob_idx])
            touched = h[i] >= ob_low - atr * 0.05 and l[i] <= ob_high + atr * 0.05
            held = c[i] <= ob_high and _is_bear(ohlc, i)
            if not (touched and held):
                continue
            if max(h[ob_idx + 1:i + 1] or [ob_high]) > ob_high + atr * 0.35:
                continue
            mid = (ob_high + ob_low) / 2
            reasons = [
                f"Bearish Order Block {_round_p(ob_low)}–{_round_p(ob_high)}",
                f"Impulse move {_round_p(move)} (~{round(abs(move) / atr, 1)} ATR) ke pehle last buy candle",
                "Price OB zone pe wapas aayi (mitigation) aur red hold",
                "Institutions ke pending sell orders zone — SHORT bias",
            ]
            return _pack(
                pattern="Order Block",
                direction="DOWN",
                level=mid,
                close=float(c[i]),
                candle_time=int(t[i]),
                reasons=reasons,
                detail=f"Bearish OB mitigation{' (LIVE)' if live else ''}",
                strategy="SMC · Order Block",
                live=live,
                timeframe=timeframe,
                extra_advice="SL OB high ke upar; TP next liquidity / opposing FVG.",
            )
    return None


# ─── Fair Value Gap ──────────────────────────────────────────────────────

def detect_fair_value_gap(
    ohlc: dict,
    *,
    live: bool = False,
    timeframe: str = "",
) -> dict | None:
    """
    3-candle FVG: gap between candle1 high and candle3 low (bullish),
    or candle1 low and candle3 high (bearish). Signal on first fill tap.
    """
    h, l, c, t = ohlc["highs"], ohlc["lows"], ohlc["closes"], ohlc["times"]
    n = len(c)
    if n < 12:
        return None
    i = (n - 1) if live else (n - 2)
    atr = _avg_range(ohlc, i)

    # Search recent unfilled FVGs formed before i
    for g in range(i - 2, max(2, i - 18), -1):
        # candles g-2, g-1, g form the gap; g is the 3rd candle
        c1_h, c1_l = float(h[g - 2]), float(l[g - 2])
        c3_h, c3_l = float(h[g]), float(l[g])
        # Bullish FVG: c1 high < c3 low
        if c3_l > c1_h:
            gap = c3_l - c1_h
            if gap < atr * 0.15:
                continue
            # Already filled completely before i?
            filled_before = any(float(l[k]) <= c1_h for k in range(g + 1, i))
            if filled_before:
                continue
            # Current candle taps into gap from above and holds bullish
            tapped = float(l[i]) <= c3_l and float(l[i]) >= c1_h - atr * 0.05
            held = float(c[i]) >= (c1_h + c3_l) / 2 and _is_bull(ohlc, i)
            if not (tapped and held):
                continue
            mid = (c1_h + c3_l) / 2
            reasons = [
                f"Bullish Fair Value Gap {_round_p(c1_h)}–{_round_p(c3_l)}",
                f"Imbalance gap size {_round_p(gap)} (price inefficiency)",
                "Price pehli baar FVG fill karne aayi aur hold kiya",
                "ICT: gaps magnet → fill + continuation LONG",
            ]
            return _pack(
                pattern="Fair Value Gap",
                direction="UP",
                level=mid,
                close=float(c[i]),
                candle_time=int(t[i]),
                reasons=reasons,
                detail=f"Bullish FVG fill{' (LIVE)' if live else ''}",
                strategy="SMC · Fair Value Gap",
                live=live,
                timeframe=timeframe,
                extra_advice="SL gap low ke neeche; partial TP at CE (consequent encroachment).",
            )

        # Bearish FVG: c1 low > c3 high
        if c3_h < c1_l:
            gap = c1_l - c3_h
            if gap < atr * 0.15:
                continue
            filled_before = any(float(h[k]) >= c1_l for k in range(g + 1, i))
            if filled_before:
                continue
            tapped = float(h[i]) >= c3_h and float(h[i]) <= c1_l + atr * 0.05
            held = float(c[i]) <= (c1_l + c3_h) / 2 and _is_bear(ohlc, i)
            if not (tapped and held):
                continue
            mid = (c1_l + c3_h) / 2
            reasons = [
                f"Bearish Fair Value Gap {_round_p(c3_h)}–{_round_p(c1_l)}",
                f"Imbalance gap size {_round_p(gap)} (price inefficiency)",
                "Price pehli baar FVG fill karne aayi aur hold kiya",
                "ICT: gaps magnet → fill + continuation SHORT",
            ]
            return _pack(
                pattern="Fair Value Gap",
                direction="DOWN",
                level=mid,
                close=float(c[i]),
                candle_time=int(t[i]),
                reasons=reasons,
                detail=f"Bearish FVG fill{' (LIVE)' if live else ''}",
                strategy="SMC · Fair Value Gap",
                live=live,
                timeframe=timeframe,
                extra_advice="SL gap high ke upar; partial TP at CE (consequent encroachment).",
            )
    return None


# ─── Liquidity Sweep ─────────────────────────────────────────────────────

def detect_liquidity_sweep(
    ohlc: dict,
    *,
    live: bool = False,
    timeframe: str = "",
    lookback: int = 20,
) -> dict | None:
    """
    Stop hunt: wick beyond recent swing high/low, close back inside range.
    Classic smart-money reversal after grabbing liquidity.
    """
    h, l, c, o, t = (
        ohlc["highs"], ohlc["lows"], ohlc["closes"], ohlc["opens"], ohlc["times"]
    )
    n = len(c)
    if n < lookback + 4:
        return None
    i = (n - 1) if live else (n - 2)
    if i < lookback:
        return None
    atr = _avg_range(ohlc, i)
    prior_h = max(h[i - lookback:i])
    prior_l = min(l[i - lookback:i])
    hi, lo, close, open_ = float(h[i]), float(l[i]), float(c[i]), float(o[i])
    rng = max(hi - lo, 1e-12)

    # Sweep highs (buy-side liquidity) → bearish reversal
    if hi > prior_h and close < prior_h and close < open_:
        pierce = hi - prior_h
        if pierce < atr * 0.08:
            return None
        upper_wick = hi - max(close, open_)
        if upper_wick / rng < 0.35:
            return None
        reasons = [
            f"Buy-side liquidity sweep above {_round_p(prior_h)}",
            f"Wick pierce {_round_p(pierce)} — stops grab, close wapas andar",
            "Stop-hunt complete → smart money SHORT bias",
            "Rejection wick strong — fake breakout filter",
        ]
        return _pack(
            pattern="Liquidity Sweep",
            direction="DOWN",
            level=prior_h,
            close=close,
            candle_time=int(t[i]),
            reasons=reasons,
            detail=f"Liquidity grab highs → SHORT{' (LIVE)' if live else ''}",
            strategy="SMC · Liquidity Sweep",
            live=live,
            timeframe=timeframe,
            extra_advice="SL sweep high ke upar; TP opposite range / equal lows.",
        )

    # Sweep lows (sell-side liquidity) → bullish reversal
    if lo < prior_l and close > prior_l and close > open_:
        pierce = prior_l - lo
        if pierce < atr * 0.08:
            return None
        lower_wick = min(close, open_) - lo
        if lower_wick / rng < 0.35:
            return None
        reasons = [
            f"Sell-side liquidity sweep below {_round_p(prior_l)}",
            f"Wick pierce {_round_p(pierce)} — stops grab, close wapas andar",
            "Stop-hunt complete → smart money LONG bias",
            "Rejection wick strong — fake breakdown filter",
        ]
        return _pack(
            pattern="Liquidity Sweep",
            direction="UP",
            level=prior_l,
            close=close,
            candle_time=int(t[i]),
            reasons=reasons,
            detail=f"Liquidity grab lows → LONG{' (LIVE)' if live else ''}",
            strategy="SMC · Liquidity Sweep",
            live=live,
            timeframe=timeframe,
            extra_advice="SL sweep low ke neeche; TP opposite range / equal highs.",
        )
    return None


# ─── Equal Highs / Equal Lows ────────────────────────────────────────────

def detect_equal_liquidity(
    ohlc: dict,
    *,
    live: bool = False,
    timeframe: str = "",
    tol_atr: float = 0.12,
) -> dict | None:
    """
    Twin / equal highs or lows = pooled liquidity. Sweep of that pool + close back.
    """
    h, l, c, o, t = (
        ohlc["highs"], ohlc["lows"], ohlc["closes"], ohlc["opens"], ohlc["times"]
    )
    n = len(c)
    if n < 25:
        return None
    i = (n - 1) if live else (n - 2)
    atr = _avg_range(ohlc, i)
    tol = atr * tol_atr
    swings_h = _swing_points(h, kind="high", end=i)
    swings_l = _swing_points(l, kind="low", end=i)

    def _dedupe_swings(swings: list[tuple[int, float]], *, kind: str) -> list[tuple[int, float]]:
        """Keep meaningful pivots — collapse flat plateaus, prefer extremes."""
        if not swings:
            return []
        out: list[tuple[int, float]] = [swings[0]]
        for idx, price in swings[1:]:
            prev_i, prev_p = out[-1]
            if abs(price - prev_p) <= tol and (idx - prev_i) <= 3:
                # Same plateau — keep higher high / lower low
                if kind == "high" and price >= prev_p:
                    out[-1] = (idx, price)
                elif kind == "low" and price <= prev_p:
                    out[-1] = (idx, price)
                continue
            out.append((idx, price))
        return out

    swings_h = _dedupe_swings(swings_h, kind="high")
    swings_l = _dedupe_swings(swings_l, kind="low")

    # Search recent equal-high pairs (not only last two)
    hi, close, open_ = float(h[i]), float(c[i]), float(o[i])
    if len(swings_h) >= 2:
        for a_i in range(len(swings_h) - 1, 0, -1):
            for b_i in range(a_i - 1, max(-1, a_i - 6), -1):
                a, b = swings_h[b_i], swings_h[a_i]
                if abs(a[1] - b[1]) > tol or (b[0] - a[0]) < 3:
                    continue
                # Pair should be recent relative to signal candle
                if i - b[0] > 18:
                    continue
                eq = (a[1] + b[1]) / 2
                if hi > eq + tol * 0.5 and close < eq and close < open_:
                    reasons = [
                        f"Equal highs liquidity pool @ {_round_p(eq)}",
                        f"Twin highs @ {_round_p(a[1])} & {_round_p(b[1])} (stops clustered)",
                        "Pool swept + close below = engineered liquidity grab SHORT",
                    ]
                    return _pack(
                        pattern="Equal Liquidity",
                        direction="DOWN",
                        level=eq,
                        close=close,
                        candle_time=int(t[i]),
                        reasons=reasons,
                        detail=f"Equal highs swept → SHORT{' (LIVE)' if live else ''}",
                        strategy="SMC · Equal Highs/Lows",
                        live=live,
                        timeframe=timeframe,
                        extra_advice="Classic ICT raid on buy-side liquidity.",
                    )

    lo = float(l[i])
    if len(swings_l) >= 2:
        for a_i in range(len(swings_l) - 1, 0, -1):
            for b_i in range(a_i - 1, max(-1, a_i - 6), -1):
                a, b = swings_l[b_i], swings_l[a_i]
                if abs(a[1] - b[1]) > tol or (b[0] - a[0]) < 3:
                    continue
                if i - b[0] > 18:
                    continue
                eq = (a[1] + b[1]) / 2
                if lo < eq - tol * 0.5 and close > eq and close > open_:
                    reasons = [
                        f"Equal lows liquidity pool @ {_round_p(eq)}",
                        f"Twin lows @ {_round_p(a[1])} & {_round_p(b[1])} (stops clustered)",
                        "Pool swept + close above = engineered liquidity grab LONG",
                    ]
                    return _pack(
                        pattern="Equal Liquidity",
                        direction="UP",
                        level=eq,
                        close=close,
                        candle_time=int(t[i]),
                        reasons=reasons,
                        detail=f"Equal lows swept → LONG{' (LIVE)' if live else ''}",
                        strategy="SMC · Equal Highs/Lows",
                        live=live,
                        timeframe=timeframe,
                        extra_advice="Classic ICT raid on sell-side liquidity.",
                    )
    return None


# ─── Orchestrator ────────────────────────────────────────────────────────

def scan_smc(
    ohlc: dict,
    *,
    timeframe: str = "",
    enable_range: bool = True,
    enable_bos: bool = True,
    enable_ob: bool = True,
    enable_fvg: bool = True,
    enable_liq: bool = True,
    enable_eq: bool = True,
) -> list[dict]:
    """
    Run all SMC + range breakout detectors.
    Prefers closed-candle signals; adds LIVE only if no closed hit in that family.
    """
    hits: list[dict] = []
    seen: set[tuple[str, str]] = set()  # (pattern, direction)

    def _add(hit: dict | None):
        if not hit:
            return
        key = (hit["pattern"], hit["direction"])
        if key in seen:
            return
        # Prefer non-live if we already somehow have live — first wins by call order
        seen.add(key)
        if timeframe and not hit.get("timeframe"):
            # rebuild advice with TF
            hit["advice"] = build_explanation(
                pattern=hit["pattern"],
                direction=hit["direction"],
                reasons=hit.get("reasons") or [],
                level=hit.get("level"),
                timeframe=timeframe,
                extra="",
            )
        hits.append(hit)

    # Closed first, then live for early alerts
    for live in (False, True):
        if enable_range and (not timeframe or timeframe in BREAKOUT_FOCUS_TFS or timeframe in SMC_TFS):
            _add(detect_range_breakout(ohlc, live=live, timeframe=timeframe))
        if enable_bos:
            _add(detect_bos_choch(ohlc, live=live, timeframe=timeframe))
        if enable_ob:
            _add(detect_order_block(ohlc, live=live, timeframe=timeframe))
        if enable_fvg:
            _add(detect_fair_value_gap(ohlc, live=live, timeframe=timeframe))
        if enable_liq:
            _add(detect_liquidity_sweep(ohlc, live=live, timeframe=timeframe))
        if enable_eq:
            _add(detect_equal_liquidity(ohlc, live=live, timeframe=timeframe))

    return hits


def enrich_legacy_reasons(hit: dict, timeframe: str = "") -> dict:
    """Attach reasons[] + stronger advice for classic (non-SMC) patterns."""
    if hit.get("reasons"):
        return hit
    pattern = hit.get("pattern") or "Signal"
    direction = hit.get("direction") or "UP"
    level = hit.get("level")
    detail = hit.get("patternDetail") or ""
    reasons: list[str] = []

    if pattern == "Triangle Breakout":
        reasons = [
            "Converging wick-tip trendlines (triangle / wedge compression)",
            f"Price ne triangle {'upar' if direction == 'UP' else 'neeche'} break kiya",
            "Volatility expansion setup — pro breakout continuation",
        ]
        if "LIVE" in detail or hit.get("live"):
            reasons.append("LIVE break — early catch, close confirm better")
    elif pattern in ("Clean Breakout", "Break Setup"):
        reasons = [
            "Clean tip-to-tip trendline structure",
            f"Stage: {hit.get('stage') or 'break'}",
            "Multi-touch line — higher probability break",
        ]
    elif pattern == "S/R Breakout":
        reasons = [
            f"{'Resistance' if direction == 'UP' else 'Support'} level break @ {_round_p(float(level or 0))}",
            "HTF confluence filter (4H+1D+1W) se fake break kam",
            "Trade prefer after retest (Retest Complete)",
        ]
    elif pattern == "Retest Wait":
        reasons = [
            "Breakout already done — retest abhi pending",
            f"Limit plan @ broken level {_round_p(float(level or 0))}",
            "Pro style: break → retest → continue (FOMO chase mat karo)",
        ]
    elif pattern == "Retest Complete":
        reasons = [
            f"Broken level {_round_p(float(level or 0))} pe retest touch + hold",
            "Smart money continuation entry zone",
            "SL beyond retest wick; TP measured move / next liquidity",
        ]
    elif pattern in ("Dragonfly Doji", "Hammer", "Doji + Green"):
        reasons = [
            "1D support pe rejection candle (Doji/Hammer)",
            "Next candle green close = confirmation",
            "Daily bias LONG — swing traders ka classic reversal",
        ]
    else:
        reasons = [detail or f"{pattern} structure confirm"]

    if hit.get("htfConfluence"):
        reasons.append("HTF 4H+1D+1W level align (confluence)")
    if hit.get("score") is not None:
        reasons.append(f"Internal score {hit['score']}/100")

    hit["reasons"] = reasons
    if not hit.get("strategy"):
        hit["strategy"] = {
            "Triangle Breakout": "Classic · Triangle",
            "Clean Breakout": "Classic · Trendline",
            "Break Setup": "Classic · Trendline Setup",
            "S/R Breakout": "Classic · S/R",
            "Retest Wait": "Classic · Retest",
            "Retest Complete": "Classic · Retest",
            "Dragonfly Doji": "Classic · Candle",
            "Hammer": "Classic · Candle",
            "Doji + Green": "Classic · Candle",
        }.get(pattern, "Classic")

    # Always refresh advice to include full basis
    existing = (hit.get("advice") or "").strip()
    thesis = build_explanation(
        pattern=pattern,
        direction=direction,
        reasons=reasons,
        level=float(level) if level is not None else None,
        timeframe=timeframe or hit.get("timeframe") or "",
        extra=existing if existing and "Trade basis:" not in existing else "",
    )
    hit["advice"] = thesis
    return hit
