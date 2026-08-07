"""Mini OHLC charts — candles + triangle / pattern overlays (milky crystal look)."""
from __future__ import annotations

import base64
import io


def render_breakout_chart_b64(
    ohlc: dict,
    hit: dict,
    *,
    width: int = 440,
    height: int = 268,
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

    pad_l, pad_r, pad_t, pad_b = 14, 14, 30, 16
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
    ymin -= span * 0.10
    ymax += span * 0.10

    def yx(price: float) -> float:
        return pad_t + (ymax - price) / (ymax - ymin) * plot_h

    def xx(i_local: float) -> float:
        return pad_l + (i_local + 0.5) / m * plot_w

    # Milky crystal palette
    bg = (248, 251, 255)
    bg2 = (236, 244, 252)
    up_c = (45, 180, 140)
    dn_c = (232, 96, 120)
    grid = (220, 230, 240)
    axis = (190, 205, 220)
    title_c = (40, 62, 88)
    upper_line = (255, 140, 90)
    lower_line = (70, 150, 230)
    entry_c = (90, 120, 160)
    sl_c = (220, 90, 110)
    tp_c = (40, 170, 130)
    pattern_ring = (120, 90, 210)

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    # Soft crystal wash
    for y in range(height):
        t = y / max(height - 1, 1)
        r = int(bg[0] + (bg2[0] - bg[0]) * t * 0.55)
        g = int(bg[1] + (bg2[1] - bg[1]) * t * 0.55)
        b = int(bg[2] + (bg2[2] - bg[2]) * t * 0.55)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((pad_l, 8), title, fill=title_c, font=font)

    for g_i in range(1, 4):
        gy = pad_t + plot_h * g_i / 4
        draw.line([(pad_l, gy), (width - pad_r, gy)], fill=grid, width=1)
    draw.rectangle(
        [pad_l, pad_t, width - pad_r, height - pad_b],
        outline=axis,
        width=1,
    )

    # Triangle / tip trendlines (absolute bar indices → local)
    lines = hit.get("chartLines") or {}
    for key, color in (("upper", upper_line), ("lower", lower_line)):
        ln = lines.get(key) or {}
        i1 = ln.get("i1")
        i2 = ln.get("i2")
        p1 = ln.get("p1")
        p2 = ln.get("p2")
        if None in (i1, i2, p1, p2):
            continue
        try:
            i1, i2 = int(i1), int(i2)
            p1, p2 = float(p1), float(p2)
        except (TypeError, ValueError):
            continue
        # Extend toward right edge for chart clarity
        x_a = i1 - start
        x_b = i2 - start
        if x_b == x_a:
            continue
        # Project across visible window
        x0, x1 = 0.0, float(m - 1)
        slope = (p2 - p1) / (x_b - x_a)
        y0 = p1 + slope * (x0 - x_a)
        y1 = p1 + slope * (x1 - x_a)
        draw.line(
            [(xx(x0), yx(y0)), (xx(x1), yx(y1))],
            fill=color,
            width=2,
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

    # Highlight pattern / signal candle (last closed unless live)
    sig_local = m - 1 if hit.get("live") else max(0, m - 2)
    sx = xx(sig_local)
    sh, sl = hs[sig_local], ls[sig_local]
    ring = 4
    draw.ellipse(
        [sx - candle_w / 2 - ring, yx(sh) - ring, sx + candle_w / 2 + ring, yx(sl) + ring],
        outline=pattern_ring,
        width=2,
    )

    def _hline(price, color, label: str = ""):
        try:
            py = yx(float(price))
        except Exception:
            return
        draw.line([(pad_l, py), (width - pad_r, py)], fill=color, width=1)
        if label and font:
            draw.text((pad_l + 2, py - 10), label, fill=color, font=font)

    entry = hit.get("entry") or hit.get("close")
    if entry is not None:
        _hline(entry, entry_c, "E")
    if hit.get("sl") is not None:
        _hline(hit["sl"], sl_c, "SL")
    if hit.get("tp") is not None:
        _hline(hit["tp"], tp_c, "TP")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def attach_chart(ohlc: dict, hit: dict) -> dict:
    """Attach candle chart with optional triangle tip lines + Entry/SL/TP."""
    try:
        # Keep chartLines for triangle overlay when present
        b64 = render_breakout_chart_b64(ohlc, hit)
        if b64:
            hit["chartImage"] = b64
    except Exception as e:
        print(f"[My Signals] chart render failed: {e}")
    return hit
