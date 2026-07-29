"""
Clean wick-tip trendlines — MEXC / ENA style.

- Line tip-to-tip on exact wick chotiyan (100% tip fit)
- Use only the LAST 3 chronological tip touches
- Single ascending support OR descending resistance is enough
  (triangles still OK when both sides are clean)
- Signal when 3rd touch is live / about to happen, or just broke
"""
from __future__ import annotations

import os

TRENDLINE_WINDOW = int(os.environ.get("DC_TRENDLINE_WINDOW", "48"))
PIVOT_LEFT = int(os.environ.get("DC_PIVOT_LEFT", "2"))
PIVOT_RIGHT = int(os.environ.get("DC_PIVOT_RIGHT", "2"))
MIN_PIVOT_SEP = int(os.environ.get("DC_MIN_PIVOT_SEP", "3"))
# Wick tip precision — exact tips (user: 100% chotiyan)
TOUCH_TOL_ATR = float(os.environ.get("DC_TOUCH_TOL_ATR", "0.07"))
APPROACH_ATR = float(os.environ.get("DC_APPROACH_ATR", "0.35"))
MAX_BREAK_EXT_ATR = float(os.environ.get("DC_TREND_MAX_EXT_ATR", "0.55"))
MIN_BODY_FRAC_LIVE = float(os.environ.get("DC_TREND_BODY_LIVE", "0.14"))
MIN_BODY_FRAC_CLOSED = float(os.environ.get("DC_TREND_BODY_CLOSED", "0.20"))
MIN_TOUCHES = int(os.environ.get("DC_MIN_TOUCHES", "2"))
PREFER_TOUCHES = int(os.environ.get("DC_PREFER_TOUCHES", "3"))
# Max body pierces allowed between tip anchors (0 = tip-only clean like MEXC)
MAX_BODY_PIERCES = int(os.environ.get("DC_MAX_BODY_PIERCES", "0"))
# ENA-style single ascending/descending line allowed (not only triangles)
REQUIRE_BOTH_SIDES = os.environ.get("DC_REQUIRE_BOTH_SIDES", "0") == "1"


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

            # User rule: only LAST 3 tip touches (ignore older history)
            touches = sorted(touches, key=lambda x: x[0])
            if touch_n > PREFER_TOUCHES:
                touches = touches[-PREFER_TOUCHES:]
                touch_n = len(touches)

            # Re-anchor 100% tip-to-tip on first→last of those last-N tips
            ai1, ap1 = touches[0]
            ai2, ap2 = touches[-1]
            if ai2 <= ai1:
                continue
            slope = (ap2 - ap1) / float(ai2 - ai1)
            if kind == "upper" and slope >= 0:
                continue
            if kind == "lower" and slope <= 0:
                continue

            # Every kept tip must still sit on the re-anchored line
            refined: list[tuple[int, float]] = []
            for ix, px in touches:
                if _on_line(ix, px, ai1, ap1, ai2, ap2, tol):
                    refined.append((ix, px))
            if len(refined) < MIN_TOUCHES:
                continue
            touches = refined
            touch_n = len(touches)
            # Force exact tip prices on endpoints (draw = wick tip)
            touches[0] = (touches[0][0], float(touches[0][1]))
            touches[-1] = (touches[-1][0], float(touches[-1][1]))
            ai1, ap1 = touches[0]
            ai2, ap2 = touches[-1]
            slope = (ap2 - ap1) / float(ai2 - ai1)

            # First touch must be the extreme among selected (rank rule)
            prices = [p for _, p in touches]
            if kind == "upper" and max(prices) != touches[0][1]:
                if touches[0][1] < max(prices) - tol:
                    continue
            if kind == "lower" and min(prices) != touches[0][1]:
                if touches[0][1] > min(prices) + tol:
                    continue

            # Score: prefer 3 touches, recent last tip, tight tip fit
            span = touches[-1][0] - touches[0][0]
            fit_err = 0.0
            for ix, px in touches:
                fit_err += abs(px - _line_at(ai1, ap1, ai2, ap2, ix))
            fit_err /= touch_n
            last_idx = pivots[-1][0] if pivots else touches[-1][0]
            last_touch_age = max(0, last_idx - touches[-1][0])
            recency = max(0, 20 - last_touch_age)
            key = (
                1 if touch_n >= PREFER_TOUCHES else 0,
                touch_n,
                recency,
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
                        # Anchor for projection / draw = first→last tip
                        "ai1": ai1,
                        "ap1": ap1,
                        "ai2": ai2,
                        "ap2": ap2,
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


def _body_pierce_count(
    ohlc: dict,
    line: dict,
    *,
    kind: str,
    end: int,
    tol: float,
) -> int:
    """
    Count candles whose BODY cuts through the tip-to-tip line.
    Tip touch bars are exempt. Dirty lines (HANA bot chawal) fail this.
    kind='upper' resistance / 'lower' support.
    """
    opens = ohlc["opens"]
    closes = ohlc["closes"]
    tip_idxs = {int(p["i"]) for p in (line.get("points") or [])}
    ai1 = int(line.get("ai1", line["i1"]))
    pierces = 0
    # From first tip through current bar — line must stay tip-clean
    for j in range(ai1, end + 1):
        if j in tip_idxs:
            continue
        if j < 0 or j >= len(closes):
            continue
        lp = _project(line, j)
        o = float(opens[j])
        c = float(closes[j])
        body_hi = max(o, c)
        body_lo = min(o, c)
        # Full body cross through the line
        crossed = body_lo < lp - tol * 0.15 and body_hi > lp + tol * 0.15
        if kind == "upper":
            # Closed / body above resistance = line cut through price
            if c > lp + tol * 0.25 or crossed:
                pierces += 1
        else:
            if c < lp - tol * 0.25 or crossed:
                pierces += 1
    return pierces


def _line_tip_clean(ohlc: dict, line: dict | None, *, kind: str, end: int, tol: float) -> bool:
    if not line:
        return False
    return _body_pierce_count(ohlc, line, kind=kind, end=end, tol=tol) <= MAX_BODY_PIERCES


def chart_last3_wick_lines(
    ohlc: dict,
    *,
    direction: str = "UP",
    window: int = TRENDLINE_WINDOW,
) -> dict:
    """
    For mini-charts: last-3 wick tip lines from ABOVE and BELOW when available.

    - Upper = last 2–3 top wick tips (descending resistance preferred)
    - Lower = last 2–3 bottom wick tips (ascending support preferred)
    - `break` marks which side the signal prefers (for title / highlight)
    No body-pierce gate — chart should still show the tip lines.
    """
    h = ohlc["highs"]
    l = ohlc["lows"]
    c = ohlc["closes"]
    n = len(c)
    if n < 10:
        return {"upper": None, "lower": None, "break": None}

    end = n - 1
    start = max(0, end - window)
    avg_rng = _avg_range(ohlc, end) or abs(c[end]) * 0.01
    # Slightly looser tol for chart drawing so last-3 tips usually appear
    tol = max(avg_rng * max(TOUCH_TOL_ATR, 0.12), abs(c[end]) * 0.0012)

    high_pivots = _swing_pivots(h, kind="high", start=start, end=end)
    low_pivots = _swing_pivots(l, kind="low", start=start, end=end)
    upper = _fit_ranked_wick_line(high_pivots, kind="upper", tol=tol)
    lower = _fit_ranked_wick_line(low_pivots, kind="lower", tol=tol)

    # Fallback: raw last-3 swing tips tip-to-tip (even if rank soft)
    if not upper and len(high_pivots) >= 2:
        tips = sorted(high_pivots, key=lambda p: p[0])[-3:]
        if tips[-1][0] > tips[0][0]:
            upper = {
                "i1": tips[0][0],
                "p1": tips[0][1],
                "i2": tips[-1][0],
                "p2": tips[-1][1],
                "touches": len(tips),
                "slope": (tips[-1][1] - tips[0][1]) / (tips[-1][0] - tips[0][0]),
                "points": [{"i": i, "p": p} for i, p in tips],
                "ai1": tips[0][0],
                "ap1": tips[0][1],
                "ai2": tips[-1][0],
                "ap2": tips[-1][1],
            }
    if not lower and len(low_pivots) >= 2:
        tips = sorted(low_pivots, key=lambda p: p[0])[-3:]
        if tips[-1][0] > tips[0][0]:
            lower = {
                "i1": tips[0][0],
                "p1": tips[0][1],
                "i2": tips[-1][0],
                "p2": tips[-1][1],
                "touches": len(tips),
                "slope": (tips[-1][1] - tips[0][1]) / (tips[-1][0] - tips[0][0]),
                "points": [{"i": i, "p": p} for i, p in tips],
                "ai1": tips[0][0],
                "ap1": tips[0][1],
                "ai2": tips[-1][0],
                "ap2": tips[-1][1],
            }

    prefer_upper = direction in ("DOWN", "SELL", "BEARISH")
    if prefer_upper:
        brk = "resistance" if upper else ("support" if lower else None)
    else:
        brk = "support" if lower else ("resistance" if upper else None)

    return {
        "upper": _line_payload(upper) if upper else None,
        "lower": _line_payload(lower) if lower else None,
        "break": brk,
    }


def detect_clean_trendline_breakout(
    ohlc: dict,
    window: int = TRENDLINE_WINDOW,
    *,
    live: bool = False,
    approaching: bool = False,
) -> dict | None:
    """
    Clean wick-tip line(s): last-3 tip touches, single-line OK (ENA) or triangle.
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

    # Drop dirty lines that cut candle bodies (must be tip-to-tip only).
    # Exclude current signal bar — break candle is allowed to pierce.
    hist_end = max(0, i - 1)
    if upper and not _line_tip_clean(ohlc, upper, kind="upper", end=hist_end, tol=tol):
        upper = None
    if lower and not _line_tip_clean(ohlc, lower, kind="lower", end=hist_end, tol=tol):
        lower = None

    if REQUIRE_BOTH_SIDES:
        if not upper or not lower:
            return None
    elif not upper and not lower:
        return None

    u_n = int(upper["touches"]) if upper else 0
    l_n = int(lower["touches"]) if lower else 0
    if REQUIRE_BOTH_SIDES:
        if u_n < MIN_TOUCHES or l_n < MIN_TOUCHES:
            return None
    else:
        if max(u_n, l_n) < MIN_TOUCHES:
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
    elif lower is not None:
        shape = "Ascending support"
    elif upper is not None:
        shape = "Descending resistance"

    body_frac = MIN_BODY_FRAC_LIVE if live else MIN_BODY_FRAC_CLOSED
    min_break = max(avg_rng * (0.05 if live else 0.08), abs(c[i]) * 0.0008)
    detail_live = " (LIVE)" if live else ""

    def _hit(direction: str, level: float, line_kind: str, line: dict, stage: str) -> dict:
        side = "BUY" if direction == "UP" else "SELL"
        tn = int(line.get("touches") or 0)
        # Chart: both last-3 tip lines (upar + neeche) when clean; break marks signal side
        chart_upper = _line_payload(upper) if upper else None
        chart_lower = _line_payload(lower) if lower else None
        both_txt = " · up+down tips" if (chart_upper and chart_lower) else ""
        if stage == "about_to_break":
            pattern = "Break Setup"
            advice = (
                f"Last-3 wick tip setup · {shape} · {line_kind} ({tn} tips){both_txt}. "
                f"{'LONG' if direction == 'UP' else 'SHORT'} — teesra touch / break abi hony wala. "
                f"Entry plan + SL/TP alert pe; chase mat karo."
            )
            detail = f"{shape} · 3rd touch / about to break{detail_live}"
            chance = 72
        else:
            pattern = "Clean Breakout"
            advice = (
                f"Clean wick-tip break abi abi · {shape} · {line_kind} "
                f"({tn} wick tips){both_txt}. "
                f"{'LONG' if direction == 'UP' else 'SHORT'} — entry abhi near level, "
                f"SL plan follow karo, late chase mat karo."
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
                "upper": chart_upper,
                "lower": chart_lower,
                "break": line_kind,
            },
        }

    # --- Just broke (strict — no false LONG on dirty / early resistance) ---
    if not approaching:
        if not _body_ok(ohlc, i, body_frac):
            return None

        if upper and upper_now is not None and upper_prev is not None:
            # LONG only on clear close ABOVE clean descending resistance
            # Prefer 3 tip touches; 2-touch needs stronger close
            need_clear = min_break if u_n >= PREFER_TOUCHES else min_break * 1.4
            broke = (
                c[i] > upper_now + need_clear
                and c[i - 1] <= upper_prev + tol * 0.5
                and c[i] > o[i]  # bullish close confirmation
            )
            if broke:
                ext = (c[i] - upper_now) / (avg_rng or 1e-12)
                if ext <= MAX_BREAK_EXT_ATR:
                    return _hit("UP", upper_now, "resistance", upper, "just_broke")

        if lower and lower_now is not None and lower_prev is not None:
            need_clear = min_break if l_n >= PREFER_TOUCHES else min_break * 1.4
            broke = (
                c[i] < lower_now - need_clear
                and c[i - 1] >= lower_prev - tol * 0.5
                and c[i] < o[i]
            )
            if broke:
                ext = (lower_now - c[i]) / (avg_rng or 1e-12)
                if ext <= MAX_BREAK_EXT_ATR:
                    return _hit("DOWN", lower_now, "support", lower, "just_broke")
        return None

    # --- About to break / 3rd touch (HANA: resistance touch = SHORT) ---
    approach = avg_rng * APPROACH_ATR

    def _ready_for_third(tn: int) -> bool:
        return tn >= MIN_TOUCHES

    # Descending resistance: price still BELOW line at 3rd touch → SHORT (not LONG)
    if upper and upper_now is not None and c[i] < upper_now and _ready_for_third(u_n):
        dist = upper_now - c[i]
        wick_tag = h[i] >= upper_now - tol and c[i] <= upper_now
        near = 0 < dist <= approach
        if wick_tag or near:
            return _hit("DOWN", upper_now, "resistance", upper, "about_to_break")

    # Ascending support: hugging / about to break down → SHORT watch
    if lower and lower_now is not None and c[i] > lower_now and _ready_for_third(l_n):
        dist = c[i] - lower_now
        wick_tag = l[i] <= lower_now + tol and c[i] >= lower_now
        near = 0 < dist <= approach
        if wick_tag or near:
            return _hit("DOWN", lower_now, "support", lower, "about_to_break")

    # Apex squeeze — nearer side wins; resistance side = SHORT, support = SHORT break watch
    if both and upper_now is not None and lower_now is not None:
        width = upper_now - lower_now
        if 0 < width < avg_rng * 1.6 and lower_now < c[i] < upper_now:
            if (upper_now - c[i]) <= approach or (c[i] - lower_now) <= approach:
                if (upper_now - c[i]) <= (c[i] - lower_now):
                    return _hit("DOWN", upper_now, "resistance", upper, "about_to_break")
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
