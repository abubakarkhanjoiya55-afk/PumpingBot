"""Tests for ranked wick-tip 3-touch trendlines (SOL style)."""
import time
import unittest

from device_care.trendlines import (
    detect_clean_trendline_breakout,
    _swing_pivots,
    _fit_ranked_wick_line,
)
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


def _build_sol_style_triangle(size=60):
    """
    Upper: 3 descending wick peaks (highest → lower → lower).
    Lower: 3 ascending wick troughs (lowest → higher → higher).
    Then early break of lower support (SHORT) — like user SOL chart.
    """
    highs = [100.0] * size
    lows = [90.0] * size
    opens = [95.0] * size
    closes = [95.0] * size

    # Mild mid-channel base
    for i in range(size):
        highs[i] = 100.0
        lows[i] = 92.0
        opens[i] = 96.0
        closes[i] = 96.0

    # Upper peaks: idx 12=130, 28=118, 44=106  (strict descending, sep>=3)
    for idx, px in ((12, 130.0), (28, 118.0), (44, 106.0)):
        highs[idx] = px
        for j in range(idx - 2, idx + 3):
            if 0 <= j < size and j != idx:
                highs[j] = min(highs[j], px - 10)

    # Lower troughs: idx 16=70, 32=82, 48=94
    for idx, px in ((16, 70.0), (32, 82.0), (48, 94.0)):
        lows[idx] = px
        for j in range(idx - 2, idx + 3):
            if 0 <= j < size and j != idx:
                lows[j] = max(lows[j], px + 6)

    # Keep mid candles inside triangle after last trough
    # Lower line 16→48: slope=(94-70)/(48-16)=0.75; at 58: 70+0.75*42=101.5
    # Upper line 12→44: slope=(106-130)/(44-12)=-0.75; at 58: 130-0.75*46=95.5
    # Wait that crosses — need geometry that stays valid at end.
    # Recalc: at i=50 upper: 130 + (106-130)/(32)*(50-12)=130-0.75*38=101.5
    # lower at 50: 70+(94-70)/32*(50-16)=70+0.75*34=95.5  OK upper>lower

    for i in range(49, 58):
        highs[i] = 100.0
        lows[i] = 96.0
        opens[i] = 98.0
        closes[i] = 98.0

    # Prev still above support (~95.5 at i=57? use i=58 as break)
    # n=60, closed i=58
    # lower @58: 70+0.75*(58-16)=70+31.5=101.5 — oops troughs make support too high at end

    # Rebuild lower with gentler rise so break is early near tip
    # peaks stay; troughs: 16=78, 32=84, 46=90
    for i in range(size):
        if i not in (12, 28, 44) and not any(abs(i - x) <= 2 for x in (12, 28, 44)):
            if highs[i] > 110:
                highs[i] = 100.0
    lows = [92.0] * size
    for idx, px in ((16, 78.0), (32, 84.0), (46, 90.0)):
        lows[idx] = px
        for j in range(idx - 2, idx + 3):
            if 0 <= j < size and j != idx:
                lows[j] = max(lows[j], px + 5)

    # Restore upper peaks
    for idx, px in ((12, 130.0), (28, 118.0), (44, 106.0)):
        highs[idx] = px
        for j in range(idx - 2, idx + 3):
            if 0 <= j < size and j != idx:
                highs[j] = min(highs[j], px - 10)

    # Inside channel before break
    # upper@57: 130+(106-130)/(44-12)*(57-12)=130-0.75*45=96.25
    # lower@57: 78+(90-78)/(46-16)*(57-16)=78+0.4*41=94.4
    for i in range(47, 58):
        highs[i] = 97.0
        lows[i] = 94.5
        opens[i] = 95.5
        closes[i] = 95.5

    highs[57], lows[57], opens[57], closes[57] = 96.5, 94.6, 95.8, 95.2
    # Break below support — early (close just under ~94.8)
    # lower@58: 78+0.4*(58-16)=78+16.8=94.8
    highs[58], lows[58], opens[58], closes[58] = 95.5, 92.5, 95.0, 93.5
    highs[59], lows[59], opens[59], closes[59] = 94.0, 92.0, 93.5, 92.8

    return _ohlc(highs, lows, opens, closes)


class WickTipLineTests(unittest.TestCase):
    def test_upper_ranks_highest_then_lower_peaks(self):
        ohlc = _build_sol_style_triangle()
        i = len(ohlc["closes"]) - 2
        hp = _swing_pivots(ohlc["highs"], kind="high", start=max(0, i - 48), end=i)
        avg = 4.0
        tol = avg * 0.12
        upper = _fit_ranked_wick_line(hp, kind="upper", tol=tol)
        self.assertIsNotNone(upper)
        self.assertGreaterEqual(upper["touches"], 2)
        pts = upper["points"]
        # First tip is the highest among points
        self.assertEqual(pts[0]["p"], max(p["p"] for p in pts))
        # Descending prices
        for a, b in zip(pts, pts[1:]):
            self.assertGreaterEqual(a["p"] + 1e-9, b["p"])

    def test_lower_ranks_lowest_then_higher_troughs(self):
        ohlc = _build_sol_style_triangle()
        i = len(ohlc["closes"]) - 2
        lp = _swing_pivots(ohlc["lows"], kind="low", start=max(0, i - 48), end=i)
        tol = 0.5
        lower = _fit_ranked_wick_line(lp, kind="lower", tol=tol)
        self.assertIsNotNone(lower)
        pts = lower["points"]
        self.assertEqual(pts[0]["p"], min(p["p"] for p in pts))
        for a, b in zip(pts, pts[1:]):
            self.assertLessEqual(a["p"] - 1e-9, b["p"])

    def test_short_break_of_3touch_support(self):
        ohlc = _build_sol_style_triangle()
        hit = detect_clean_trendline_breakout(ohlc, live=False, approaching=False)
        self.assertIsNotNone(hit, "expected clean SHORT break like SOL")
        self.assertEqual("DOWN", hit["direction"])
        self.assertEqual("Clean Breakout", hit["pattern"])
        lower = (hit.get("chartLines") or {}).get("lower") or {}
        self.assertGreaterEqual(int(lower.get("touches") or 0), 2)
        # Chart lines include exact tip points
        self.assertTrue(lower.get("points"))

    def test_chart_marks_touch_points(self):
        ohlc = _build_sol_style_triangle()
        hit = detect_clean_trendline_breakout(ohlc, live=False, approaching=False)
        self.assertIsNotNone(hit)
        b64 = render_breakout_chart_b64(ohlc, hit)
        self.assertIsNotNone(b64)
        self.assertGreater(len(b64), 200)

    def test_rejects_chase(self):
        ohlc = _build_sol_style_triangle()
        ohlc["closes"][-2] = 70.0
        ohlc["opens"][-2] = 90.0
        ohlc["highs"][-2] = 91.0
        ohlc["lows"][-2] = 68.0
        self.assertIsNone(
            detect_clean_trendline_breakout(ohlc, live=False, approaching=False)
        )

    def test_chart_shows_both_upper_and_lower_tips(self):
        """User rule: chart last-3 tips upar + neeche (when both fit)."""
        from device_care.trendlines import chart_last3_wick_lines

        ohlc = _build_sol_style_triangle()
        lines = chart_last3_wick_lines(ohlc, direction="DOWN")
        self.assertIsNotNone(lines.get("upper"), "expected upper last-3 tips")
        self.assertIsNotNone(lines.get("lower"), "expected lower last-3 tips")
        self.assertGreaterEqual(len((lines["upper"].get("points") or [])), 2)
        self.assertGreaterEqual(len((lines["lower"].get("points") or [])), 2)
        hit = detect_clean_trendline_breakout(ohlc, live=False, approaching=False)
        self.assertIsNotNone(hit)
        # Signal payload keeps both sides for chart
        cl = hit.get("chartLines") or {}
        self.assertTrue(cl.get("upper") or cl.get("lower"))
        b64 = render_breakout_chart_b64(ohlc, hit)
        self.assertIsNotNone(b64)
        self.assertGreater(len(b64), 200)

    def test_scan_4h_and_d1(self):
        ohlc = _build_sol_style_triangle()
        for tf in ("4H", "D1"):
            hits = sc.scan_ohlc(ohlc, timeframe=tf)
            tri = [h for h in hits if h["pattern"] in ("Triangle Breakout", "Clean Breakout")]
            self.assertTrue(tri, f"expected triangle break on {tf}")
            plan = tri[0]
            self.assertIsNotNone(plan.get("entry"))
            self.assertIsNotNone(plan.get("sl"))
            self.assertIsNotNone(plan.get("tp"))
            self.assertTrue(plan.get("chartImage"))
            # Triangle tip lines kept for milky crystal chart overlay
            self.assertIn("chartLines", plan)
            self.assertTrue(plan["chartLines"].get("upper") or plan["chartLines"].get("lower"))

    def test_default_tfs_focus_4h_d1(self):
        self.assertTrue(sc.enabled_tfs.get("4H"))
        self.assertTrue(sc.enabled_tfs.get("D1"))
        self.assertTrue(sc.enabled_tfs.get("1h"))  # Crypto Pumping Signals: 1H+4H+1D focus
        self.assertFalse(sc.enabled_tfs.get("1W"))
        self.assertTrue(sc.ENABLE_CANDLE_PATTERNS)
        self.assertTrue(sc.ENABLE_SR_BREAKOUTS)
        self.assertTrue(sc.ENABLE_TRIANGLE_BREAK)
        # Indicators / SMC off — candle + triangle focus
        self.assertFalse(sc.ENABLE_SMC)
        self.assertFalse(sc.ENABLE_RANGE_BREAKOUT)

    def test_scan_no_break_setup_noise(self):
        ohlc = _build_sol_style_triangle()
        hits = sc.scan_ohlc(ohlc, timeframe="4H")
        self.assertFalse(any(h["pattern"] == "Break Setup" for h in hits))

    def test_last_three_tips_only(self):
        """Older 4th tip is dropped — line uses last 3 chronological tips."""
        pivots = [
            (5, 70.0),
            (15, 78.0),
            (25, 86.0),
            (35, 94.0),  # 4 ascending tips on one line
        ]
        # Line through first→last of last-3: 15/78 → 35/94
        lower = _fit_ranked_wick_line(pivots, kind="lower", tol=0.5)
        self.assertIsNotNone(lower)
        self.assertLessEqual(int(lower["touches"]), 3)
        pts = lower["points"]
        self.assertEqual(len(pts), int(lower["touches"]))
        # Endpoints are exact tip prices
        self.assertEqual(pts[0]["p"], lower["ap1"] if "ap1" in lower else pts[0]["p"])
        self.assertEqual(pts[-1]["i"], 35)
        self.assertEqual(pts[-1]["p"], 94.0)

    def test_ena_single_ascending_support_about_to_touch(self):
        """ENA single-line only when DC_REQUIRE_BOTH_SIDES=0."""
        import device_care.trendlines as tl
        old = tl.REQUIRE_BOTH_SIDES
        tl.REQUIRE_BOTH_SIDES = False
        try:
            size = 56
            highs = [100.0] * size
            lows = [92.0] * size
            opens = [96.0] * size
            closes = [96.0] * size
            lows = [92.0] * size
            highs = [100.0] * size
            opens = [96.0] * size
            closes = [96.0] * size
            for idx, px in ((12, 86.0), (30, 90.0)):
                lows[idx] = px
                for j in range(idx - 2, idx + 3):
                    if 0 <= j < size and j != idx:
                        lows[j] = max(lows[j], px + 3)
            for i in range(32, 55):
                supp = 86.0 + (90.0 - 86.0) / (30 - 12) * (i - 12)
                highs[i] = supp + 5
                lows[i] = supp + 1.2
                opens[i] = supp + 3
                closes[i] = supp + 2.8
            i = 54
            supp = 86.0 + (4.0 / 18.0) * (i - 12)
            highs[i] = supp + 3
            lows[i] = supp - 0.05
            opens[i] = supp + 1.5
            closes[i] = supp + 0.8
            ohlc = _ohlc(highs, lows, opens, closes)
            hit = detect_clean_trendline_breakout(ohlc, live=True, approaching=True)
            self.assertIsNotNone(hit, "expected ENA-style about-to 3rd touch")
            self.assertEqual("Break Setup", hit["pattern"])
            self.assertIn("Ascending support", hit.get("patternDetail") or "")
        finally:
            tl.REQUIRE_BOTH_SIDES = old

    def test_hana_descending_resistance_third_touch_is_short(self):
        """HANA single resistance — only when both-sides requirement off."""
        import device_care.trendlines as tl
        old = tl.REQUIRE_BOTH_SIDES
        tl.REQUIRE_BOTH_SIDES = False
        try:
            size = 64
            highs = [80.0] * size
            lows = [70.0] * size
            opens = [75.0] * size
            closes = [75.0] * size
            tips = ((14, 120.0), (30, 108.0), (46, 96.0))
            tip_idx = {t[0] for t in tips}
            for idx, px in tips:
                highs[idx] = px
                opens[idx] = px - 8
                closes[idx] = px - 10
                lows[idx] = px - 14
                for j in range(idx - 2, idx + 3):
                    if 0 <= j < size and j not in tip_idx:
                        line = 120.0 - 0.75 * (j - 14)
                        highs[j] = min(line - 4, px - 10)
                        opens[j] = highs[j] - 3
                        closes[j] = highs[j] - 4
                        lows[j] = highs[j] - 6
            for i in range(size):
                if i in tip_idx:
                    continue
                line = 120.0 - 0.75 * (i - 14)
                highs[i] = min(highs[i], line - 2.5)
                opens[i] = line - 6
                closes[i] = line - 5
                lows[i] = line - 9
            i = 58
            line = 120.0 - 0.75 * (i - 14)
            highs[i] = line + 0.2
            opens[i] = line - 2.5
            closes[i] = line - 1.0
            lows[i] = line - 5
            ohlc = _ohlc(highs[: i + 1], lows[: i + 1], opens[: i + 1], closes[: i + 1])

            self.assertIsNone(
                detect_clean_trendline_breakout(ohlc, live=True, approaching=False)
            )
            hit = detect_clean_trendline_breakout(ohlc, live=True, approaching=True)
            self.assertIsNotNone(hit, "expected HANA SHORT at 3rd resistance tip")
            self.assertEqual("DOWN", hit["direction"])
            self.assertEqual("Break Setup", hit["pattern"])
            self.assertEqual("resistance", (hit.get("chartLines") or {}).get("break"))
        finally:
            tl.REQUIRE_BOTH_SIDES = old

    def test_strategy_flags_classic_signals(self):
        """Doji@support + S/R retest + triangle break enabled."""
        self.assertTrue(sc.ENABLE_CANDLE_PATTERNS)
        self.assertTrue(sc.ENABLE_SR_BREAKOUTS)
        self.assertTrue(sc.ENABLE_TRIANGLE_BREAK)

    def test_clean_hit_has_trade_plan(self):
        ohlc = _build_sol_style_triangle()
        hit = detect_clean_trendline_breakout(ohlc, live=False, approaching=False)
        self.assertIsNotNone(hit)
        plan = sc.enrich_trade_plan(ohlc, hit)
        self.assertIsNotNone(plan.get("entry"))
        self.assertIsNotNone(plan.get("sl"))
        self.assertIsNotNone(plan.get("tp"))
        if plan["direction"] == "DOWN":
            self.assertGreater(float(plan["sl"]), float(plan["entry"]))
            self.assertLess(float(plan["tp"]), float(plan["entry"]))

    def test_rejects_body_cutting_resistance_line(self):
        """Line that slices candle bodies is rejected (not tip-clean)."""
        size = 50
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        for idx, px in ((8, 120.0), (24, 110.0)):
            highs[idx] = px
            for j in range(idx - 2, idx + 3):
                if 0 <= j < size and j != idx:
                    highs[j] = min(highs[j], px - 6)
        # Mid candles pierce ABOVE the would-be line
        for i in range(10, 22):
            highs[i] = 118.0
            opens[i] = 112.0
            closes[i] = 115.0
            lows[i] = 108.0
        i = 48
        highs[i], opens[i], closes[i], lows[i] = 105.0, 102.0, 103.0, 100.0
        ohlc = _ohlc(highs, lows, opens, closes)
        self.assertIsNone(
            detect_clean_trendline_breakout(ohlc, live=True, approaching=True)
        )
        self.assertIsNone(
            detect_clean_trendline_breakout(ohlc, live=False, approaching=False)
        )


class DiversifyStillOk(unittest.TestCase):
    def setUp(self):
        sc.symbol_last_alert_at.clear()
        sc.hourly_symbols.clear()
        sc.hourly_alert_count.clear()

    def tearDown(self):
        sc.symbol_last_alert_at.clear()
        sc.hourly_symbols.clear()
        sc.hourly_alert_count.clear()

    def test_same_coin_different_tfs_allowed(self):
        now = time.time()
        self.assertTrue(sc.can_emit_diversified("BTC_USDT", "1h", now))
        sc.mark_diversified_emit("BTC_USDT", "1h", now)
        # Same TF blocked this hour
        self.assertFalse(sc.can_emit_diversified("BTC_USDT", "1h", now))
        # Different TF allowed
        self.assertTrue(sc.can_emit_diversified("BTC_USDT", "4H", now))
        sc.mark_diversified_emit("BTC_USDT", "4H", now)
        self.assertTrue(sc.can_emit_diversified("ETH_USDT", "4H", now))

    def test_no_hard_three_cap(self):
        now = time.time()
        for i in range(5):
            sym = f"C{i}_USDT"
            self.assertTrue(sc.can_emit_diversified(sym, "4H", now), sym)
            sc.mark_diversified_emit(sym, "4H", now)
        self.assertEqual(5, sc.hourly_alerts_used(now))
        self.assertTrue(sc.can_emit_diversified("C5_USDT", "4H", now))


if __name__ == "__main__":
    unittest.main()
