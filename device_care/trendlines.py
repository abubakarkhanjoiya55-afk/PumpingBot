"""
Clean wick-tip trendlines — SOL-chart style.

Upper line (descending resistance):
  1st touch = sab se oonchi wick
  2nd touch = us se neeche wali next peak wick
  3rd touch = us se aur neeche wali peak
  → tip-to-tip descending line (kam az kam 2, prefer 3)

Lower line (ascending support):
  1st touch = sab se neeche wali wick
  2nd = us se oonchi next trough
  3rd = us se aur oonchi
  → tip-to-tip ascending line

Signal tabhi jab dono sides clean 2/3-touch triangle bani ho,
aur 3rd touch pe reject / break ho raha ho (ya abi abi break).
"""
from __future__ import annotations

import os

TRENDLINE_WINDOW = int(os.environ.get("DC_TRENDLINE_WINDOW", "48"))
PIVOT_LEFT = int(os.environ.get("DC_PIVOT_LEFT", "2"))
PIVOT_RIGHT = int(os.environ.get("DC_PIVOT_RIGHT", "2"))
MIN_PIVOT_SEP = int(os.environ.get("DC_MIN_PIVOT_SEP", "3"))
# Wick tip precision — tight (user: exact tips, not messy)
TOUCH_TOL_ATR = float(os.environ.get("DC_TOUCH_TOL_ATR", "0.10"))
APPROACH_ATR = float(os.environ.get("DC_APPROACH_ATR", "0.28"))
MAX_BREAK_EXT_ATR = float(os.environ.get("DC_TREND_MAX_EXT_ATR", "0.55"))
MIN_BODY_FRAC_LIVE = float(os.environ.get("DC_TREND_BODY_LIVE", "0.14"))
MIN_BODY_FRAC_CLOSED = float(os.environ.get("DC_TREND_BODY_CLOSED", "0.20"))
MIN_TOUCHES = int(os.environ.get("DC_MIN_TOUCHES", "2"))
PREFER_TOUCHES = int(os.environ.get("DC_PREFER_TOUCHES", "3"))
REQUIRE_BOTH_SIDES = os.environ.get("DC_REQUIRE_BOTH_SIDES", "1") != "0"


def _avg_range(ohlc: dict, end: int, look: int = 14) -> float:
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
    """Strict local wick extrema."""
    pivots: list[tuple[int, float]] = []
    lo = max(start + left, left)
    hi = min(end - right, len(values) - right)
    for i in range(lo, hi):
        left_vals = values[i - left: i]
        right_vals = values[i + 1: i + right + 1]
        if not left_vals or not right_vals:
            continue
        if kind == "high":
            if values[i] > max(left_vals) and values[i] > max(right_vals):
                pivots.append((i, float(values[i])))
        else:
            if values[i] < min(left_vals) and values[i] < min(right_vals):
                pivots.append((i, float(values[i])))
    return pivots


def _line_at(i1: int, p1: float, i2: int, p2: float, x: float) -> float:
    if i2 == i1:
        return p1
    return p1 + (p2 - p1) * (x - i1) / (i2 - i1)


def _on_line(idx: int, price: float, i1: int, p1: float, i2: int, p2: float, tol: float) -> bool:
    return abs(price - _line_at(i1, p1, i2, p2, idx)) <= tol


def _fit_ranked_wick_line(
    pivots: list[tuple[int, float]],
    *,
    kind: str,
    tol: float,
    min_sep: int = MIN_PIVOT_SEP,
) -> dict | None:
    """
    kind='upper': chronological pivots with strictly descending prices
      (1st=highest wick, 2nd=next lower peak, 3rd=lower still)
    kind='lower': chronological pivots with strictly ascending prices
      (1st=lowest wick, 2nd=higher low, 3rd=higher still)

    Line is fit through the first two tip pivots; every selected touch must
    sit on that line within wick-tip tolerance. Prefer 3 touches.
    """
    if len(pivots) < MIN_TOUCHES:
        return None

    # Chronological
    pivots = sorted(pivots, key=lambda p: p[0])
    best: tuple | None = None

    n = len(pivots)
    # Try all ordered pairs as anchor (first two touches), then collect
    # later pivots that lie ON the line and follow rank order.
    for a in range(n):
        for b in range(a + 1, n):
            i1, p1 = pivots[a]
            i2, p2 = pivots[b]
            if i2 - i1 < min_sep:
                continue
            slope = (p2 - p1) / (i2 - i1)
            if kind == "upper":
                # Descending resistance: p1 must be highest of the two, slope down
                if p2 >= p1 - tol * 0.05:
                    continue
                if slope >= 0:
                    continue
            else:
                # Ascending support: p2 > p1, slope up
                if p2 <= p1 + tol * 0.05:
                    continue
                if slope <= 0:
                    continue

            touches: list[tuple[int, float]] = [(i1, p1), (i2, p2)]
            # Rank check for anchors
            if kind == "upper" and p1 < p2:
                continue
            if kind == "lower" and p1 > p2:
                continue

            for c in range(b + 1, n):
                i3, p3 = pivots[c]
                if i3 - touches[-1][0] < min_sep:
                    continue
                if not _on_line(i3, p3, i1, p1, i2, p2, tol):
                    continue
                # Continue the height ranking
                if kind == "upper":
                    if p3 > touches[-1][1] + tol * 0.05:
                        continue  # must be lower than previous peak
                else:
                    if p3 < touches[-1][1] - tol * 0.05:
                        continue  # must be higher than previous trough
                touches.append((i3, p3))
                if len(touches) >= 4:
                    break  # 3 is enough; keep first 3-4

            # Also allow a pivot BETWEEN anchors if it sits on line (rare)
            mid_touches: list[tuple[int, float]] = []
            for m in range(a + 1, b):
                im, pm = pivots[m]
                if _on_line(im, pm, i1, p1, i2, p2, tol):
                    if kind == "upper" and p1 >= pm >= p2 - tol:
                        mid_touches.append((im, pm))
                    elif kind == "lower" and p1 <= pm <= p2 + tol:
                        mid_touches.append((im, pm))
            if mid_touches:
                merged = sorted(set(touches + mid_touches), key=lambda x: x[0])
                # Re-validate rank order
                ok = True
                for k in range(1, len(merged)):
                    if kind == "upper" and merged[k][1] > merged[k - 1][1] + tol * 0.05:
                        ok = False
                        break
                    if kind == "lower" and merged[k][1] < merged[k - 1][1] - tol * 0.05:
                        ok = False
                        break
                if ok:
                    touches = merged

            touch_n = len(touches)
            if touch_n < MIN_TOUCHES:
                continue

            # First touch must be the extreme among selected (user rule)
            prices = [p for _, p in touches]
            if kind == "upper" and max(prices) != touches[0][1]:
                # Allow if first is within tol of max (almost highest)
                if touches[0][1] < max(prices) - tol:
                    continue
            if kind == "lower" and min(prices) != touches[0][1]:
                if touches[0][1] > min(prices) + tol:
                    continue

            # Score: prefer 3 touches, longer span, tighter tip fit
            span = touches[-1][0] - touches[0][0]
            fit_err = 0.0
            for ix, px in touches:
                fit_err += abs(px - _line_at(i1, p1, i2, p2, ix))
            fit_err /= touch_n
            # Higher touches better; prefer PREFER_TOUCHES; lower error better
            key = (
                1 if touch_n >= PREFER_TOUCHES else 0,
                touch_n,
                span,
                -fit_err,
            )
            if best is None or key > best[0]:
                best = (
                    key,
                    {
                        "i1": touches[0][0],
                        "p1": touches[0][1],
                        "i2": touches[-1][0] if touch_n == 2 else touches[1][0],
                        "p2": touches[-1][1] if touch_n == 2 else touches[1][1],
                        "touches": touch_n,
                        "slope": slope,
                        "points": [{"i": i, "p": p} for i, p in touches],
                        # Anchor for projection = first→last for clean draw
                        "ai1": touches[0][0],
                        "ap1": touches[0][1],
                        "ai2": touches[-1][0],
                        "ap2": touches[-1][1],
                    },
                )

    if not best:
        return None
    return best[1]


def _line_payload(line: dict) -> dict:
    # Draw/project using first→last tip for visual cleanliness
    i1 = int(line.get("ai1", line["i1"]))
    p1 = float(line.get("ap1", line["p1"]))
    i2 = int(line.get("ai2", line["i2"]))
    p2 = float(line.get("ap2", line["p2"]))
    return {
        "i1": i1,
        "p1": p1,
        "i2": i2,
        "p2": p2,
        "touches": line["touches"],
        "points": line.get("points") or [
            {"i": line["i1"], "p": line["p1"]},
            {"i": line["i2"], "p": line["p2"]},
        ],
    }


def _project(line: dict, x: int) -> float:
    i1 = int(line.get("ai1", line["i1"]))
    p1 = float(line.get("ap1", line["p1"]))
    i2 = int(line.get("ai2", line["i2"]))
    p2 = float(line.get("ap2", line["p2"]))
    return _line_at(i1, p1, i2, p2, x)


def detect_clean_trendline_breakout(
    ohlc: dict,
    window: int = TRENDLINE_WINDOW,
    *,
    live: bool = False,
    approaching: bool = False,
) -> dict | None:
    """
    Clean wick-tip triangle: upper descending + lower ascending (2–3 touches each).
    Signal on just-broke or about-to-break at 3rd touch zone.
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
    form_end = i
    form_start = max(0, form_end - window)
    avg_rng = _avg_range(ohlc, i) or abs(c[i]) * 0.01
    tol = max(avg_rng * TOUCH_TOL_ATR, abs(c[i]) * 0.0008)

    high_pivots = _swing_pivots(h, kind="high", start=form_start, end=form_end)
    low_pivots = _swing_pivots(l, kind="low", start=form_start, end=form_end)

    upper = _fit_ranked_wick_line(high_pivots, kind="upper", tol=tol)
    lower = _fit_ranked_wick_line(low_pivots, kind="lower", tol=tol)

    if REQUIRE_BOTH_SIDES:
        if not upper or not lower:
            return None
    elif not upper and not lower:
        return None

    # Prefer quality: at least one side with 3 touches
    u_n = int(upper["touches"]) if upper else 0
    l_n = int(lower["touches"]) if lower else 0
    if max(u_n, l_n) < PREFER_TOUCHES and (u_n < MIN_TOUCHES or l_n < MIN_TOUCHES):
        return None
    # Both sides must meet min touches when both required
    if REQUIRE_BOTH_SIDES and (u_n < MIN_TOUCHES or l_n < MIN_TOUCHES):
        return None

    upper_now = _project(upper, i) if upper else None
    lower_now = _project(lower, i) if lower else None
    upper_prev = _project(upper, i - 1) if upper else None
    lower_prev = _project(lower, i - 1) if lower else None

    # Valid triangle: upper above lower at now
    if upper_now is not None and lower_now is not None:
        if upper_now <= lower_now:
            return None

    both = upper is not None and lower is not None
    shape = "Trendline"
    if both:
        us = float(upper["slope"])
        ls = float(lower["slope"])
        flat_u = abs(us) <= (avg_rng * 0.002)
        flat_l = abs(ls) <= (avg_rng * 0.002)
        if flat_u and ls > 0:
            shape = "Ascending triangle"
        elif flat_l and us < 0:
            shape = "Descending triangle"
        elif us < 0 and ls > 0:
            shape = "Symmetrical triangle"
        else:
            shape = "3-touch channel"

    body_frac = MIN_BODY_FRAC_LIVE if live else MIN_BODY_FRAC_CLOSED
    min_break = max(avg_rng * (0.035 if live else 0.05), abs(c[i]) * 0.0005)
    detail_live = " (LIVE)" if live else ""

    def _hit(direction: str, level: float, line_kind: str, line: dict, stage: str) -> dict:
        side = "BUY" if direction == "UP" else "SELL"
        tn = int(line.get("touches") or 0)
        if stage == "about_to_break":
            pattern = "Break Setup"
            advice = (
                f"3-touch wick tip setup · {shape} · {line_kind} ({tn} touches). "
                f"{'LONG' if direction == 'UP' else 'SHORT'} — teesra touch / break abi hony wala (~70%)."
            )
            detail = f"{shape} · 3rd touch / about to break{detail_live}"
            chance = 72
        else:
            pattern = "Clean Breakout"
            advice = (
                f"Clean wick-tip break abi abi · {shape} · {line_kind} "
                f"({tn} wick tips). "
                f"{'LONG' if direction == 'UP' else 'SHORT'} — entry abhi, chase mat karo."
            )
            detail = f"{shape} · just broke{detail_live}"
            chance = 90
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
            "breakChance": chance,
            "chartLines": {
                "upper": _line_payload(upper) if upper else None,
                "lower": _line_payload(lower) if lower else None,
                "break": line_kind,
            },
        }

    # --- Just broke ---
    if not approaching:
        if not _body_ok(ohlc, i, body_frac):
            return None

        if upper and upper_now is not None and upper_prev is not None:
            broke = (
                c[i] > upper_now + min_break * 0.2 and c[i - 1] <= upper_prev + min_break * 0.15
            ) or (
                live
                and h[i] > upper_now + min_break
                and c[i - 1] <= upper_prev
                and c[i] >= upper_now
            )
            if broke and c[i - 1] <= upper_prev + tol:
                ext = (c[i] - upper_now) / (avg_rng or 1e-12)
                if ext <= MAX_BREAK_EXT_ATR:
                    return _hit("UP", upper_now, "resistance", upper, "just_broke")

        if lower and lower_now is not None and lower_prev is not None:
            broke = (
                c[i] < lower_now - min_break * 0.2 and c[i - 1] >= lower_prev - min_break * 0.15
            ) or (
                live
                and l[i] < lower_now - min_break
                and c[i - 1] >= lower_prev
                and c[i] <= lower_now
            )
            if broke and c[i - 1] >= lower_prev - tol:
                ext = (lower_now - c[i]) / (avg_rng or 1e-12)
                if ext <= MAX_BREAK_EXT_ATR:
                    return _hit("DOWN", lower_now, "support", lower, "just_broke")
        return None

    # --- About to break / 3rd touch zone ---
    approach = avg_rng * APPROACH_ATR

    # 3rd-touch rejection on upper (price tags resistance tip, still below)
    if upper and upper_now is not None and c[i] < upper_now:
        dist = upper_now - c[i]
        wick_tag = h[i] >= upper_now - tol and c[i] <= upper_now
        near = 0 < dist <= approach
        if (wick_tag or near) and (u_n >= PREFER_TOUCHES or near):
            # Prefer SHORT if also near lower break, else LONG setup on resistance break
            if lower and lower_now is not None and (c[i] - lower_now) <= approach * 0.8:
                # Squeeze at apex — bias by closer side / wick
                if wick_tag or (upper_now - c[i]) <= (c[i] - (lower_now or c[i])):
                    # At upper 3rd touch reject → often short if rejecting; user SOL broke lower
                    # If tagging upper and rejecting (close back down) → about SHORT on fail, else LONG break
                    if c[i] < o[i] and wick_tag:
                        return _hit("DOWN", lower_now or upper_now, "support", lower or upper, "about_to_break")
                    return _hit("UP", upper_now, "resistance", upper, "about_to_break")
            if wick_tag and c[i] < o[i]:
                # Reject at resistance 3rd touch — wait for lower break more often
                if lower and lower_now is not None:
                    return _hit("DOWN", lower_now, "support", lower, "about_to_break")
            if near and c[i] >= c[i - 1]:
                return _hit("UP", upper_now, "resistance", upper, "about_to_break")

    # 3rd-touch / hug on lower support
    if lower and lower_now is not None and c[i] > lower_now:
        dist = c[i] - lower_now
        wick_tag = l[i] <= lower_now + tol and c[i] >= lower_now
        near = 0 < dist <= approach
        if (wick_tag or near) and (l_n >= PREFER_TOUCHES or near):
            # Breaking / about to break support (SOL style)
            if wick_tag and (c[i] < o[i] or live and l[i] < lower_now):
                return _hit("DOWN", lower_now, "support", lower, "about_to_break")
            if near and c[i] <= c[i - 1]:
                return _hit("DOWN", lower_now, "support", lower, "about_to_break")

    # Apex squeeze
    if both and upper_now is not None and lower_now is not None:
        width = upper_now - lower_now
        if 0 < width < avg_rng * 1.6 and lower_now < c[i] < upper_now:
            if (upper_now - c[i]) <= approach or (c[i] - lower_now) <= approach:
                if (upper_now - c[i]) <= (c[i] - lower_now):
                    return _hit("UP", upper_now, "resistance", upper, "about_to_break")
                return _hit("DOWN", lower_now, "support", lower, "about_to_break")

    return None


def detect_triangle_breakout(ohlc: dict, window: int = TRENDLINE_WINDOW) -> dict | None:
    hit = detect_clean_trendline_breakout(ohlc, window=window, live=False, approaching=False)
    if not hit:
        return None
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
