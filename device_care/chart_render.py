"""Mini OHLC chart PNG — wick-tip trendlines with touch dots (SOL style)."""
from __future__ import annotations

import base64
import io


def render_breakout_chart_b64(
    ohlc: dict,
    hit: dict,
    *,
    width: int = 380,
    height: int = 220,
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

    pad_l, pad_r, pad_t, pad_b = 10, 10, 24, 10
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    # Include trendline tip prices in scale so lines aren't clipped
    tip_prices: list[float] = []
    lines = hit.get("chartLines") or {}
    for key in ("upper", "lower"):
        ln = lines.get(key) or {}
        for pt in ln.get("points") or []:
            tip_prices.append(float(pt["p"]))
        if ln.get("p1") is not None:
            tip_prices.append(float(ln["p1"]))
        if ln.get("p2") is not None:
            tip_prices.append(float(ln["p2"]))

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

    bg = (12, 14, 22)
    up_c = (46, 204, 113)
    dn_c = (231, 76, 60)
    grid = (36, 40, 56)
    line_u = (255, 152, 0)      # orange like user chart
    line_l = (255, 152, 0)
    dot_c = (255, 214, 10)
    txt = (236, 240, 245)

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    stage = hit.get("stage") or ""
    direction = hit.get("direction") or ""
    side = "LONG" if direction == "UP" else "SHORT"
    if stage == "about_to_break":
        title = f"{side} · 3-touch · about to break"
    else:
        title = f"{side} · wick-tip clean break"
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((pad_l, 5), title, fill=txt, font=font)

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

    def _draw_line(ln: dict, color: tuple[int, int, int]):
        if not ln:
            return
        points = ln.get("points") or []
        i1 = int(ln["i1"])
        p1 = float(ln["p1"])
        i2 = int(ln["i2"])
        p2 = float(ln["p2"])
        if i2 == i1:
            return
        slope = (p2 - p1) / (i2 - i1)
        # Extend across visible window
        abs_start = start
        abs_end = n - 1
        p_start = p1 + slope * (abs_start - i1)
        p_end = p1 + slope * (abs_end - i1)
        draw.line(
            [(xx(0), yx(p_start)), (xx(m - 1), yx(p_end))],
            fill=color,
            width=2,
        )
        # Exact wick-tip touch dots
        tips = points if points else [{"i": i1, "p": p1}, {"i": i2, "p": p2}]
        for pt in tips:
            abs_i = int(pt["i"])
            if abs_i < start or abs_i >= n:
                continue
            loc = abs_i - start
            px, py = xx(loc), yx(float(pt["p"]))
            r = 3
            draw.ellipse([px - r, py - r, px + r, py + r], fill=dot_c, outline=color)

    _draw_line(lines.get("upper") or {}, line_u)
    _draw_line(lines.get("lower") or {}, line_l)

    # Soft level dash at break price
    level = hit.get("level")
    if level is not None:
        yl = yx(float(level))
        for x0 in range(pad_l, width - pad_r, 8):
            draw.line([(x0, yl), (min(x0 + 4, width - pad_r), yl)], fill=(250, 204, 21), width=1)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def attach_chart(ohlc: dict, hit: dict) -> dict:
    b64 = render_breakout_chart_b64(ohlc, hit)
    if b64:
        hit["chartImage"] = b64
    return hit
