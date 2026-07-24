"""Mini OHLC chart PNG (base64) for clean breakout alerts."""
from __future__ import annotations

import base64
import io
from typing import Any


def render_breakout_chart_b64(
    ohlc: dict,
    hit: dict,
    *,
    width: int = 360,
    height: int = 200,
    candles: int = 40,
) -> str | None:
    """
    Draw last N candles + trendlines. Returns raw base64 PNG (no data: prefix).
    """
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

    pad_l, pad_r, pad_t, pad_b = 8, 8, 22, 8
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    ymin = min(ls)
    ymax = max(hs)
    if ymax <= ymin:
        ymax = ymin + 1e-9
    # Extra headroom
    span = ymax - ymin
    ymin -= span * 0.06
    ymax += span * 0.06

    def yx(price: float) -> float:
        return pad_t + (ymax - price) / (ymax - ymin) * plot_h

    def xx(i_local: int) -> float:
        return pad_l + (i_local + 0.5) / m * plot_w

    bg = (18, 18, 28)
    up_c = (52, 211, 153)
    dn_c = (248, 113, 113)
    grid = (42, 42, 58)
    line_u = (251, 146, 60)
    line_l = (96, 165, 250)
    txt = (226, 232, 240)

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    # Title
    stage = hit.get("stage") or ""
    direction = hit.get("direction") or ""
    side = "LONG" if direction == "UP" else "SHORT"
    if stage == "about_to_break":
        title = f"{side} · about to break (~70%)"
    else:
        title = f"{side} · clean break just happened"
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((pad_l, 4), title, fill=txt, font=font)

    # Grid
    for g in range(1, 4):
        gy = pad_t + plot_h * g / 4
        draw.line([(pad_l, gy), (width - pad_r, gy)], fill=grid, width=1)

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

    # Trendlines from hit.chartLines (absolute indices)
    lines = hit.get("chartLines") or {}
    for key, color in (("upper", line_u), ("lower", line_l)):
        ln = lines.get(key)
        if not ln:
            continue
        i1, p1 = int(ln["i1"]), float(ln["p1"])
        i2, p2 = int(ln["i2"]), float(ln["p2"])
        # Extend to last candle
        if i2 == i1:
            continue
        slope = (p2 - p1) / (i2 - i1)
        # Draw across visible window
        abs_start = start
        abs_end = n - 1
        p_start = p1 + slope * (abs_start - i1)
        p_end = p1 + slope * (abs_end - i1)
        draw.line(
            [(xx(0), yx(p_start)), (xx(m - 1), yx(p_end))],
            fill=color,
            width=2,
        )

    # Break level marker
    level = hit.get("level")
    if level is not None:
        yl = yx(float(level))
        draw.line([(pad_l, yl), (width - pad_r, yl)], fill=(250, 204, 21), width=1)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def attach_chart(ohlc: dict, hit: dict) -> dict:
    """Mutate hit with chartImage if rendering succeeds."""
    b64 = render_breakout_chart_b64(ohlc, hit)
    if b64:
        hit["chartImage"] = b64
    return hit
