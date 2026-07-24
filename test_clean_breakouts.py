"""Tests for 2-touch clean trendline breakouts + diversify."""
import time
import unittest

from device_care.trendlines import detect_clean_trendline_breakout, _swing_pivots
from device_care.chart_render import render_breakout_chart_b64
import device_care.scanner as sc


def _ohlc(highs, lows, opens, closes):
    return {
        "highs": highs,
        "lows": lows,
        "opens": opens,
        "closes": closes,
        "times": list(range(len(closes))),
    }


def _build_descending_resistance_break(size=50):
    """2-touch descending resistance + ascending support → early UP break."""
    highs = [100.0] * size
    lows = [90.0] * size
    opens = [95.0] * size
    closes = [95.0] * size
    for i in range(size):
        highs[i] = 102.0 - i * 0.02
        lows[i] = 88.0 + i * 0.05
        opens[i] = (highs[i] + lows[i]) / 2
        closes[i] = opens[i]
    for idx, px in ((14, 120.0), (28, 110.0), (38, 102.0)):
        highs[idx] = px
        for j in range(idx - 2, idx + 3):
            if j != idx and 0 <= j < size:
                highs[j] = min(highs[j], px - 8)
    for idx, px in ((16, 82.0), (30, 90.0), (40, 96.0)):
        lows[idx] = px
        for j in range(idx - 2, idx + 3):
            if j != idx and 0 <= j < size:
                lows[j] = max(lows[j], px + 5)
    # Stay under resistance until break candle
    for i in range(41, 48):
        highs[i], lows[i], opens[i], closes[i] = 96.0, 88.0, 92.0, 91.0
    highs[47], lows[47], opens[47], closes[47] = 95.0, 88.0, 92.0, 91.0
    # Early break — just through line (~94.5), not a chase
    highs[48], lows[48], opens[48], closes[48] = 100.0, 89.0, 92.0, 96.5
    highs[49], lows[49], opens[49], closes[49] = 99.0, 94.0, 96.0, 97.0
    return _ohlc(highs, lows, opens, closes)


def _build_ascending_support_break(size=50):
    """2-touch ascending support → early DOWN break."""
    highs = [110.0] * size
    lows = [100.0] * size
    opens = [105.0] * size
    closes = [105.0] * size
    for i in range(size):
        highs[i] = 112.0 - i * 0.02
        lows[i] = 98.0 + i * 0.04
        opens[i] = (highs[i] + lows[i]) / 2
        closes[i] = opens[i]
    for idx, px in ((14, 90.0), (28, 98.0), (38, 104.0)):
        lows[idx] = px
        for j in range(idx - 2, idx + 3):
            if j != idx and 0 <= j < size:
                lows[j] = max(lows[j], px + 5)
    for idx, px in ((16, 120.0), (30, 116.0), (40, 112.0)):
        highs[idx] = px
        for j in range(idx - 2, idx + 3):
            if j != idx and 0 <= j < size:
                highs[j] = min(highs[j], px - 4)
    for i in range(41, 48):
        highs[i], lows[i], opens[i], closes[i] = 112.0, 106.0, 109.0, 110.0
    highs[47], lows[47], opens[47], closes[47] = 112.0, 106.0, 109.0, 110.0
    # Support line 14→38: 90+(104-90)/(24)*(48-14)=109.8 approx — break just under
    highs[48], lows[48], opens[48], closes[48] = 110.0, 100.0, 109.0, 107.0
    highs[49], lows[49], opens[49], closes[49] = 108.0, 102.0, 106.0, 105.0
    return _ohlc(highs, lows, opens, closes)


class CleanTrendlineTests(unittest.TestCase):
    def test_pivots_are_strict(self):
        vals = [1, 2, 5, 2, 1, 2, 6, 2, 1]
        piv = _swing_pivots(vals, kind="high", start=0, end=len(vals), left=1, right=1)
        idxs = [p[0] for p in piv]
        self.assertIn(2, idxs)
        self.assertIn(6, idxs)

    def test_clean_breakout_long_just_broke(self):
        ohlc = _build_descending_resistance_break()
        hit = detect_clean_trendline_breakout(ohlc, live=False, approaching=False)
        self.assertIsNotNone(hit, "expected clean UP break")
        self.assertEqual("UP", hit["direction"])
        self.assertEqual("Clean Breakout", hit["pattern"])
        self.assertEqual("just_broke", hit["stage"])
        self.assertIn("abi abi", hit["advice"])
        upper = (hit.get("chartLines") or {}).get("upper") or {}
        self.assertGreaterEqual(int(upper.get("touches") or 0), 2)

    def test_clean_breakout_short_support_break(self):
        ohlc = _build_ascending_support_break()
        hit = detect_clean_trendline_breakout(ohlc, live=False, approaching=False)
        self.assertIsNotNone(hit, "expected clean DOWN break")
        self.assertEqual("DOWN", hit["direction"])
        self.assertEqual("Clean Breakout", hit["pattern"])

    def test_rejects_late_chase_extension(self):
        ohlc = _build_descending_resistance_break()
        ohlc["highs"][-2] = 160.0
        ohlc["lows"][-2] = 140.0
        ohlc["opens"][-2] = 142.0
        ohlc["closes"][-2] = 155.0
        hit = detect_clean_trendline_breakout(ohlc, live=False, approaching=False)
        self.assertIsNone(hit)

    def test_scan_ohlc_emits_clean_on_1h(self):
        ohlc = _build_descending_resistance_break()
        hits = sc.scan_ohlc(ohlc, timeframe="1h")
        clean = [h for h in hits if h["pattern"] in ("Clean Breakout", "Break Setup")]
        self.assertTrue(clean, f"expected clean hit, got {[h['pattern'] for h in hits]}")

    def test_chart_renders_base64(self):
        ohlc = _build_descending_resistance_break()
        hit = detect_clean_trendline_breakout(ohlc, live=False, approaching=False)
        self.assertIsNotNone(hit)
        b64 = render_breakout_chart_b64(ohlc, hit)
        self.assertIsNotNone(b64)
        self.assertGreater(len(b64), 100)


class DiversifyTests(unittest.TestCase):
    def setUp(self):
        sc.symbol_last_alert_at.clear()
        sc.hourly_symbols.clear()

    def tearDown(self):
        sc.symbol_last_alert_at.clear()
        sc.hourly_symbols.clear()

    def test_hourly_cap_three_distinct(self):
        now = time.time()
        self.assertTrue(sc.can_emit_diversified("A_USDT", now))
        sc.mark_diversified_emit("A_USDT", now)
        self.assertTrue(sc.can_emit_diversified("B_USDT", now))
        sc.mark_diversified_emit("B_USDT", now)
        self.assertTrue(sc.can_emit_diversified("C_USDT", now))
        sc.mark_diversified_emit("C_USDT", now)
        self.assertFalse(sc.can_emit_diversified("D_USDT", now))
        self.assertFalse(sc.can_emit_diversified("A_USDT", now))

    def test_symbol_day_cooldown(self):
        now = time.time()
        sc.mark_diversified_emit("X_USDT", now)
        self.assertTrue(sc.is_symbol_day_cooled("X_USDT", now + 60))
        self.assertFalse(sc.is_symbol_day_cooled("Y_USDT", now + 60))


if __name__ == "__main__":
    unittest.main()
