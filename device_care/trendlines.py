"""
2-touch wick trendline / clean breakout detection.

Rules (user screenshots):
  - Upper + lower lines must each touch ≥2 wicks (pivots)
  - Symmetrical / ascending / descending triangle OR single diagonal
  - Signal at break moment (LIVE) — LONG and SHORT
  - Optional "about to break" when price is hugging the line
"""
from __future__ import annotations

import os

TRENDLINE_WINDOW = int(os.environ.get("DC_TRENDLINE_WINDOW", "36"))
PIVOT_LEFT = int(os.environ.get("DC_PIVOT_LEFT", "2"))
PIVOT_RIGHT = int(os.environ.get("DC_PIVOT_RIGHT", "2"))
MIN_PIVOT_SEP = int(os.environ.get("DC_MIN_PIVOT_SEP", "3"))
TOUCH_TOL_ATR = float(os.environ.get("DC_TOUCH_TOL_ATR", "0.22"))
APPROACH_ATR = float(os.environ.get("DC_APPROACH_ATR", "0.35"))
MAX_BREAK_EXT_ATR = float(os.environ.get("DC_TREND_MAX_EXT_ATR", "0.85"))
MIN_BODY_FRAC_LIVE = float(os.environ.get("DC_TREND_BODY_LIVE", "0.16"))
MIN_BODY_FRAC_CLOSED = float(os.environ.get("DC_TREND_BODY_CLOSED", "0.24"))


def _avg_range(ohlc: dict, end: int, look: int = 12) -> float:
    h, l = ohlc["highs"], ohlc["lows"]
    start = max(0, end - look)
    ranges = [h[j] - l[j] for j in range(start, end)]
    return sum(ranges) / max(len(ranges), 1) if ranges else 0.0


def _body_ok(ohlc: dict, idx: int, min_frac: float) -> bool:
    h, l, c, o = ohlc["highs"], ohlc["lows"], ohlc["closes"], ohlc["opens"]
    body = abs(c[idx] - o[idx])
    avg = _avg_range(ohlc, idx) or abs(c[idx]) * 0.01
    return body >= avg * min_frac


def _swing_pivots(
    values: list[float],
    *,
    kind: str,
    start: int,
    end: int,
    left: int = PIVOT_LEFT,
    right: int = PIVOT_RIGHT,
) -> list[tuple[int, float]]:
    """Swing high/low pivots in [start, end) — wick tips (strict local extrema)."""
    pivots: list[tuple[int, float]] = []
    lo = max(start + left, left)
    hi = min(end - right, len(values) - right)
    for i in range(lo, hi):
        left_vals = values[i - left: i]
        right_vals = values[i + 1: i + right + 1]
        if not left_vals or not right_vals:
            continue
        if kind == "high":
            if values[i] > max(left_vals) and values[i] >= max(right_vals):
                pivots.append((i, float(values[i])))
        else:
            if values[i] < min(left_vals) and values[i] <= min(right_vals):
                pivots.append((i, float(values[i])))
    return pivots


def _line_at(i1: int, p1: float, i2: int, p2: float, x: int) -> float:
    if i2 == i1:
        return p1
    return p1 + (p2 - p1) * (x - i1) / (i2 - i1)


def _count_touches(
    pivots: list[tuple[int, float]],
    i1: int,
    p1: float,
    i2: int,
    p2: float,
    tol: float,
) -> int:
    n = 0
    for idx, price in pivots:
        if abs(price - _line_at(i1, p1, i2, p2, idx)) <= tol:
            n += 1
    return n


def _best_two_touch_line(
    pivots: list[tuple[int, float]],
    *,
    prefer: str,
    tol: float,
    min_sep: int = MIN_PIVOT_SEP,
) -> dict | None:
    """
    prefer: 'down' | 'up' | 'flat' | 'any'
    Returns line dict with ≥2 wick touches.
    """
    if len(pivots) < 2:
        return None
    best: tuple | None = None
    for a in range(len(pivots)):
        for b in range(a + 1, len(pivots)):
            i1, p1 = pivots[a]
            i2, p2 = pivots[b]
            if i2 - i1 < min_sep:
                continue
            slope = (p2 - p1) / (i2 - i1)
            # Soft slope gates (tol scales with ATR)
            flat_lim = max(tol * 0.08, 1e-12)
            if prefer == "down" and slope > flat_lim:
                continue
            if prefer == "up" and slope < -flat_lim:
                continue
            if prefer == "flat" and abs(slope) > flat_lim * 2.5:
                continue
            touches = _count_touches(pivots, i1, p1, i2, p2, tol)
            if touches < 2:
                continue
            # Prefer more touches, longer span, cleaner slope match
            slope_score = 0.0
            if prefer == "down":
                slope_score = -slope
            elif prefer == "up":
                slope_score = slope
            elif prefer == "flat":
                slope_score = -abs(slope)
            key = (touches, i2 - i1, slope_score)
            if best is None or key > best[0]:
                best = (key, i1, p1, i2, p2, touches, slope)
    if not best:
        return None
    _, i1, p1, i2, p2, touches, slope = best
    return {
        "i1": i1,
        "p1": p1,
        "i2": i2,
        "p2": p2,
        "touches": touches,
        "slope": slope,
    }


def _line_payload(line: dict) -> dict:
    return {
        "i1": line["i1"],
        "p1": line["p1"],
        "i2": line["i2"],
        "p2": line["p2"],
        "touches": line["touches"],
    }


def detect_clean_trendline_breakout(
    ohlc: dict,
    window: int = TRENDLINE_WINDOW,
    *,
    live: bool = False,
    approaching: bool = False,
) -> dict | None:
    """
    Clean 2-touch trendline / triangle break (or about-to-break).

    Returns hit with pattern 'Clean Breakout' or 'Break Setup'.
    """
    h = ohlc["highs"]
    l = ohlc["lows"]
    c = ohlc["closes"]
    o = ohlc["opens"]
    t = ohlc["times"]
    n = len(c)
    need = window + (4 if live else 5)
    if n < need:
        return None

    i = n - 1 if live else n - 2
    form_end = i  # pivots strictly before candidate candle
    form_start = max(0, form_end - window)
    avg_rng = _avg_range(ohlc, i) or abs(c[i]) * 0.01
    tol = max(avg_rng * TOUCH_TOL_ATR, abs(c[i]) * 0.001)

    high_pivots = _swing_pivots(h, kind="high", start=form_start, end=form_end)
    low_pivots = _swing_pivots(l, kind="low", start=form_start, end=form_end)

    upper = (
        _best_two_touch_line(high_pivots, prefer="down", tol=tol)
        or _best_two_touch_line(high_pivots, prefer="flat", tol=tol)
        or _best_two_touch_line(high_pivots, prefer="any", tol=tol)
    )
    lower = (
        _best_two_touch_line(low_pivots, prefer="up", tol=tol)
        or _best_two_touch_line(low_pivots, prefer="flat", tol=tol)
        or _best_two_touch_line(low_pivots, prefer="any", tol=tol)
    )

    # Need at least one valid 2-touch line; prefer both (triangle)
    if not upper and not lower:
        return None

    upper_now = _line_at(upper["i1"], upper["p1"], upper["i2"], upper["p2"], i) if upper else None
    lower_now = _line_at(lower["i1"], lower["p1"], lower["i2"], lower["p2"], i) if lower else None
    upper_prev = (
        _line_at(upper["i1"], upper["p1"], upper["i2"], upper["p2"], i - 1) if upper else None
    )
    lower_prev = (
        _line_at(lower["i1"], lower["p1"], lower["i2"], lower["p2"], i - 1) if lower else None
    )

    # Classify geometry for messaging
    both = upper is not None and lower is not None
    shape = "Trendline"
    if both:
        us, ls = upper["slope"], lower["slope"]
        flat_u = abs(us) <= tol * 0.08
        flat_l = abs(ls) <= tol * 0.08
        if flat_u and ls > 0:
            shape = "Ascending triangle"
        elif flat_l and us < 0:
            shape = "Descending triangle"
        elif us < 0 and ls > 0:
            shape = "Symmetrical triangle"
        else:
            shape = "2-touch channel"

    body_frac = MIN_BODY_FRAC_LIVE if live else MIN_BODY_FRAC_CLOSED
    min_break = max(avg_rng * (0.04 if live else 0.06), abs(c[i]) * 0.0006)
    detail_live = " (LIVE)" if live else ""

    def _hit(direction: str, level: float, line_kind: str, line: dict, stage: str) -> dict:
        side = "BUY" if direction == "UP" else "SELL"
        if stage == "about_to_break":
            pattern = "Break Setup"
            advice = (
                f"Clean break ~70% setup · {shape} · {line_kind} 2-touch. "
                f"{'LONG' if direction == 'UP' else 'SHORT'} — abi hony wala (price line ke qareeb)."
            )
            detail = f"{shape} · about to break{detail_live}"
        else:
            pattern = "Clean Breakout"
            advice = (
                f"Clean break abi abi hua · {shape} · {line_kind} "
                f"({line['touches']} wick touches). "
                f"{'LONG' if direction == 'UP' else 'SHORT'} — entry abhi, chase mat karo."
            )
            detail = f"{shape} · just broke{detail_live}"
        return {
            "side": side,
            "direction": direction,
            "pattern": pattern,
            "patternDetail": detail,
            "level": float(level),
            "close": float(c[i]),
            "candleTime": t[i],
            "live": live,
            "stage": stage,
            "advice": advice,
            "breakChance": 70 if stage == "about_to_break" else 88,
            "chartLines": {
                "upper": _line_payload(upper) if upper else None,
                "lower": _line_payload(lower) if lower else None,
                "break": line_kind,
            },
        }

    # --- Actual break (just broke) ---
    if not approaching:
        if not _body_ok(ohlc, i, body_frac):
            return None

        # LONG: break above upper 2-touch line
        if upper and upper_now is not None and upper_prev is not None:
            broke = (c[i] > upper_now + min_break * 0.25 and c[i - 1] <= upper_prev + min_break * 0.1) or (
                live
                and h[i] > upper_now + min_break
                and c[i - 1] <= upper_prev
                and c[i] >= upper_now
            )
            if broke:
                ext = (c[i] - upper_now) / (avg_rng or 1e-12)
                if ext <= MAX_BREAK_EXT_ATR:
                    # prev must have been inside / below
                    if c[i - 1] <= upper_prev + tol:
                        return _hit("UP", upper_now, "resistance", upper, "just_broke")

        # SHORT: break below lower 2-touch line
        if lower and lower_now is not None and lower_prev is not None:
            broke = (c[i] < lower_now - min_break * 0.25 and c[i - 1] >= lower_prev - min_break * 0.1) or (
                live
                and l[i] < lower_now - min_break
                and c[i - 1] >= lower_prev
                and c[i] <= lower_now
            )
            if broke:
                ext = (lower_now - c[i]) / (avg_rng or 1e-12)
                if ext <= MAX_BREAK_EXT_ATR:
                    if c[i - 1] >= lower_prev - tol:
                        return _hit("DOWN", lower_now, "support", lower, "just_broke")
        return None

    # --- About to break (squeeze near line) ---
    approach = avg_rng * APPROACH_ATR
    # Prefer triangle apex squeeze when both lines exist
    if both and upper_now is not None and lower_now is not None:
        width = upper_now - lower_now
        if width > 0 and width < avg_rng * 1.8:
            mid = (upper_now + lower_now) / 2
            if abs(c[i] - mid) <= approach * 1.2 and lower_now < c[i] < upper_now:
                # Bias by which side is closer
                if (upper_now - c[i]) <= (c[i] - lower_now):
                    return _hit("UP", upper_now, "resistance", upper, "about_to_break")
                return _hit("DOWN", lower_now, "support", lower, "about_to_break")

    if upper and upper_now is not None and c[i] < upper_now:
        if 0 < (upper_now - c[i]) <= approach and c[i] >= (lower_now if lower_now else c[i] - approach):
            # Rising into resistance
            if c[i] >= c[i - 1]:
                return _hit("UP", upper_now, "resistance", upper, "about_to_break")

    if lower and lower_now is not None and c[i] > lower_now:
        if 0 < (c[i] - lower_now) <= approach:
            if c[i] <= c[i - 1]:
                return _hit("DOWN", lower_now, "support", lower, "about_to_break")

    return None


# Back-compat name used by older tests — wraps clean detector (closed candle)
def detect_triangle_breakout(ohlc: dict, window: int = TRENDLINE_WINDOW) -> dict | None:
    hit = detect_clean_trendline_breakout(ohlc, window=window, live=False, approaching=False)
    if not hit:
        return None
    # Map to legacy pattern name for older callers/tests that expect Triangle
    detail = hit.get("patternDetail") or ""
    if "Ascending" in detail:
        hit["pattern"] = "Triangle Breakout"
        hit["patternDetail"] = "Ascending triangle"
    elif "Descending" in detail:
        hit["pattern"] = "Triangle Breakout"
        hit["patternDetail"] = "Descending triangle"
    elif "Symmetrical" in detail:
        hit["pattern"] = "Triangle Breakout"
        hit["patternDetail"] = (
            "Symmetrical triangle UP" if hit["direction"] == "UP" else "Symmetrical triangle DOWN"
        )
    else:
        hit["pattern"] = "Triangle Breakout"
    return hit
