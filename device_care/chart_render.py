"""Mini OHLC chart — simple candles only (no tip/trendline drawing)."""
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

    direction = hit.get("direction") or ""
    side = "LONG" if direction == "UP" else "SHORT"
    pattern = (hit.get("pattern") or "Trade").strip()
    title = f"{side} · {pattern}"

    ymin = min(ls)
    ymax = max(hs)
    if ymax <= ymin:
        ymax = ymin + 1e-9
    span = ymax - ymin
    ymin -= span * 0.08
    ymax += span * 0.08

    def yx(price: float) -> float:
        return pad_t + (ymax - price) / (ymax - ymin) * plot_h

    def xx(i_local: float) -> float:
        return pad_l + (i_local + 0.5) / m * plot_w

    bg = (255, 255, 255)
    up_c = (14, 203, 129)
    dn_c = (246, 70, 93)
    grid = (235, 238, 242)
    axis = (210, 214, 220)
    title_c = (30, 34, 42)

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
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

    # Optional entry marker (horizontal dashed feel — short ticks only, no trend draw)
    entry = hit.get("entry") or hit.get("close")
    if entry is not None:
        try:
            ey = yx(float(entry))
            draw.line([(pad_l, ey), (width - pad_r, ey)], fill=(160, 160, 170), width=1)
        except Exception:
            pass

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def attach_chart(ohlc: dict, hit: dict) -> dict:
    """Attach simple candle mini-chart (no tip/trendline drawing)."""
    try:
        hit.pop("chartLines", None)  # never draw tip lines
        b64 = render_breakout_chart_b64(ohlc, hit)
        if b64:
            hit["chartImage"] = b64
    except Exception as e:
        print(f"[My Signals] chart render failed: {e}")
    return hit
