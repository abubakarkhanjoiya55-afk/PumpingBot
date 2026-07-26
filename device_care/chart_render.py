"""Mini OHLC chart — clean white MEXC style, orange wick-tip / S/R lines."""
from __future__ import annotations

import base64
import io


def render_breakout_chart_b64(
    ohlc: dict,
    hit: dict,
    *,
    width: int = 420,
    height: int = 250,
    candles: int = 48,
) -> str | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    highs = ohlc.get("highs") or []
    lows = ohlc.get("lows") or []
    opens = ohlc.get("opens") or []
    closes = ohlc.get("closes") or []
    n = len(closes)
    if n < 8:
        return None

    start = max(0, n - candles)
    hs = highs[start:]
    ls = lows[start:]
    os_ = opens[start:]
    cs = closes[start:]
    m = len(cs)
    if m < 5:
        return None

    pad_l, pad_r, pad_t, pad_b = 12, 12, 26, 14
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    tip_prices: list[float] = []
    lines = hit.get("chartLines") or {}
    primary = (lines.get("break") or hit.get("chartPrimary") or "").lower()
    for key in ("upper", "lower"):
        ln = lines.get(key) or {}
        for pt in (ln.get("points") or [])[-3:]:
            tip_prices.append(float(pt["p"]))
        if ln.get("p1") is not None:
            tip_prices.append(float(ln["p1"]))
        if ln.get("p2") is not None:
            tip_prices.append(float(ln["p2"]))

    level = hit.get("level")
    if level is not None:
        try:
            tip_prices.append(float(level))
        except (TypeError, ValueError):
            level = None

    ymin = min(min(ls), min(tip_prices) if tip_prices else min(ls))
    ymax = max(max(hs), max(tip_prices) if tip_prices else max(hs))
    if ymax <= ymin:
        ymax = ymin + 1e-9
    span = ymax - ymin
    ymin -= span * 0.08
    ymax += span * 0.08

    def yx(price: float) -> float:
        return pad_t + (ymax - price) / (ymax - ymin) * plot_h

    def xx(i_local: float) -> float:
        return pad_l + (i_local + 0.5) / m * plot_w

    # Clean white MEXC-like palette
    bg = (255, 255, 255)
    up_c = (14, 203, 129)
    dn_c = (246, 70, 93)
    grid = (235, 238, 242)
    axis = (210, 214, 220)
    line_orange = (255, 140, 0)
    line_soft = (255, 180, 80)
    level_blue = (37, 99, 235)
    dot_fill = (255, 140, 0)
    title_c = (30, 34, 42)

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    stage = hit.get("stage") or ""
    direction = hit.get("direction") or ""
    pattern = hit.get("pattern") or ""
    side = "LONG" if direction == "UP" else "SHORT"
    has_trend = bool(lines.get("upper") or lines.get("lower"))
    if has_trend and stage == "about_to_break":
        title = f"{side} · last-3 wick tips · 3rd touch"
    elif has_trend:
        title = f"{side} · last-3 wick tips · clean break"
    elif pattern == "S/R Breakout":
        title = f"{side} · S/R level break"
    elif pattern:
        title = f"{side} · {pattern}"
    else:
        title = f"{side} · price chart"
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((pad_l, 6), title, fill=title_c, font=font)

    for g in range(1, 4):
        gy = pad_t + plot_h * g / 4
        draw.line([(pad_l, gy), (width - pad_r, gy)], fill=grid, width=1)
    draw.rectangle(
        [pad_l, pad_t, width - pad_r, height - pad_b],
        outline=axis,
        width=1,
    )

    candle_w = max(2, int(plot_w / m * 0.55))
    for i in range(m):
        x = xx(i)
        o, h, l, c = os_[i], hs[i], ls[i], cs[i]
        color = up_c if c >= o else dn_c
        draw.line([(x, yx(h)), (x, yx(l))], fill=color, width=1)
        y1, y2 = yx(max(o, c)), yx(min(o, c))
        if abs(y2 - y1) < 1:
            y2 = y1 + 1
        draw.rectangle(
            [x - candle_w / 2, y1, x + candle_w / 2, y2],
            fill=color,
            outline=color,
        )

    def _draw_line(ln: dict, *, bold: bool):
        if not ln:
            return
        points = list(ln.get("points") or [])[-3:]
        if "i1" not in ln or "p1" not in ln or "i2" not in ln or "p2" not in ln:
            if len(points) < 2:
                return
        i1 = int(ln.get("i1", points[0]["i"] if points else 0))
        p1 = float(ln.get("p1", points[0]["p"] if points else 0))
        i2 = int(ln.get("i2", points[-1]["i"] if points else 1))
        p2 = float(ln.get("p2", points[-1]["p"] if points else 0))
        if points and len(points) >= 2:
            i1 = int(points[0]["i"])
            p1 = float(points[0]["p"])
            i2 = int(points[-1]["i"])
            p2 = float(points[-1]["p"])
        if i2 == i1:
            return
        slope = (p2 - p1) / (i2 - i1)
        abs_end = n - 1
        abs_start = max(start, min(i1, i2) - 2)
        p_start = p1 + slope * (abs_start - i1)
        p_end = p1 + slope * (abs_end - i1)
        x0 = xx(max(0, abs_start - start))
        x1 = xx(m - 1)
        color = line_orange if bold else line_soft
        width_px = 3 if bold else 1
        draw.line([(x0, yx(p_start)), (x1, yx(p_end))], fill=color, width=width_px)

        tips = points if points else [{"i": i1, "p": p1}, {"i": i2, "p": p2}]
        for pt in tips[-3:]:
            abs_i = int(pt["i"])
            if abs_i < start or abs_i >= n:
                continue
            loc = abs_i - start
            px, py = xx(loc), yx(float(pt["p"]))
            r = 4 if bold else 3
            draw.ellipse(
                [px - r, py - r, px + r, py + r],
                outline=dot_fill,
                width=2,
            )
            draw.ellipse(
                [px - 1, py - 1, px + 1, py + 1],
                fill=dot_fill,
            )

    upper = lines.get("upper") or {}
    lower = lines.get("lower") or {}
    drew_trend = False
    if primary == "resistance" and upper:
        _draw_line(upper, bold=True)
        drew_trend = True
        if lower and lower.get("points"):
            _draw_line(lower, bold=False)
    elif primary == "support" and lower:
        _draw_line(lower, bold=True)
        drew_trend = True
        if upper and upper.get("points"):
            _draw_line(upper, bold=False)
    else:
        if lower:
            _draw_line(lower, bold=True)
            drew_trend = True
        if upper:
            _draw_line(upper, bold=bool(not lower))
            drew_trend = True

    # S/R or pattern alerts: orange/blue horizontal level so chart never empty of setup
    if not drew_trend and level is not None:
        try:
            lv = float(level)
            y = yx(lv)
            draw.line([(pad_l, y), (width - pad_r, y)], fill=line_orange, width=2)
            # end marker
            draw.ellipse([width - pad_r - 5, y - 5, width - pad_r + 1, y + 1], fill=level_blue)
        except (TypeError, ValueError):
            pass

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def attach_chart(ohlc: dict, hit: dict) -> dict:
    """Always try to attach a white mini-chart (trendline or S/R/pattern level)."""
    try:
        b64 = render_breakout_chart_b64(ohlc, hit)
        if b64:
            hit["chartImage"] = b64
    except Exception as e:
        print(f"[My Signals] chart render failed: {e}")
    return hit
