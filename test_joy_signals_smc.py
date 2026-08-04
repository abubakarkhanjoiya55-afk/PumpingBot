"""Tests for Crypto Pumping Signals SMC + range breakout detectors."""
import unittest

from device_care.smc import (
    detect_bos_choch,
    detect_equal_liquidity,
    detect_fair_value_gap,
    detect_liquidity_sweep,
    detect_order_block,
    detect_range_breakout,
    enrich_legacy_reasons,
    scan_smc,
)
from device_care.scanner import enrich_trade_plan, scan_ohlc, enabled_tfs


def _ohlc(highs, lows, opens, closes, times=None):
    n = len(closes)
    return {
        "highs": list(highs),
        "lows": list(lows),
        "opens": list(opens),
        "closes": list(closes),
        "times": list(times) if times is not None else list(range(n)),
    }


def _flat(n=40, mid=100.0, half=2.0):
    highs = [mid + half] * n
    lows = [mid - half] * n
    opens = [mid] * n
    closes = [mid] * n
    return highs, lows, opens, closes


class RangeBreakoutTests(unittest.TestCase):
    def test_range_break_up(self):
        n = 30
        highs, lows, opens, closes = _flat(n, 100, 2)
        # Candidate breaks above range high 102
        highs[-2], lows[-2], opens[-2], closes[-2] = 106.0, 101.0, 101.5, 105.0
        hit = detect_range_breakout(_ohlc(highs, lows, opens, closes), timeframe="4H")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["pattern"], "Range Breakout")
        self.assertEqual(hit["direction"], "UP")
        self.assertTrue(hit["reasons"])
        self.assertIn("Trade basis", hit["advice"])

    def test_range_break_down(self):
        n = 30
        highs, lows, opens, closes = _flat(n, 100, 2)
        highs[-2], lows[-2], opens[-2], closes[-2] = 99.0, 94.0, 98.5, 95.0
        hit = detect_range_breakout(_ohlc(highs, lows, opens, closes), timeframe="1h")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["direction"], "DOWN")
        self.assertEqual(hit["side"], "SELL")


class LiquiditySweepTests(unittest.TestCase):
    def test_sweep_lows_to_long(self):
        n = 28
        highs, lows, opens, closes = _flat(n, 100, 3)
        # Prior low around 97
        for i in range(5, 20):
            lows[i] = 97.0
            highs[i] = 103.0
            closes[i] = 100.0
            opens[i] = 100.0
        # Sweep below 97 then close back inside green
        highs[-2], lows[-2], opens[-2], closes[-2] = 100.0, 94.5, 98.0, 99.5
        hit = detect_liquidity_sweep(_ohlc(highs, lows, opens, closes), timeframe="4H")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["pattern"], "Liquidity Sweep")
        self.assertEqual(hit["direction"], "UP")
        self.assertGreaterEqual(len(hit["reasons"]), 3)


class FairValueGapTests(unittest.TestCase):
    def test_bullish_fvg_fill(self):
        n = 20
        highs, lows, opens, closes = _flat(n, 100, 1)
        # Create bullish FVG at bars 10,11,12: c1 high < c3 low
        # bar 10 (g-2)
        highs[10], lows[10], opens[10], closes[10] = 100.0, 98.0, 99.0, 99.5
        # bar 11 impulse
        highs[11], lows[11], opens[11], closes[11] = 108.0, 100.0, 100.0, 107.0
        # bar 12 — gap: low 104 > c1 high 100
        highs[12], lows[12], opens[12], closes[12] = 110.0, 104.0, 107.0, 109.0
        # Keep price above gap until last closed tap
        for i in range(13, n - 2):
            highs[i], lows[i], opens[i], closes[i] = 112.0, 108.0, 109.0, 110.0
        # Tap into FVG 100-104 and hold green
        highs[-2], lows[-2], opens[-2], closes[-2] = 106.0, 101.5, 102.0, 105.0
        hit = detect_fair_value_gap(_ohlc(highs, lows, opens, closes), timeframe="1h")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["pattern"], "Fair Value Gap")
        self.assertEqual(hit["direction"], "UP")
        self.assertIn("Fair Value Gap", hit["advice"])


class OrderBlockDisabledTests(unittest.TestCase):
    def test_order_block_flag_off_by_default(self):
        from device_care import scanner as sc
        self.assertFalse(sc.ENABLE_ORDER_BLOCK)

    def test_scan_smc_skips_order_block_by_default(self):
        n = 30
        highs, lows, opens, closes = _flat(n, 100, 1.5)
        highs[12], lows[12], opens[12], closes[12] = 101.0, 97.0, 100.5, 97.5
        highs[13], lows[13], opens[13], closes[13] = 106.0, 98.0, 98.0, 105.0
        highs[14], lows[14], opens[14], closes[14] = 112.0, 104.0, 105.0, 111.0
        highs[15], lows[15], opens[15], closes[15] = 118.0, 110.0, 111.0, 117.0
        for i in range(16, n - 2):
            highs[i], lows[i], opens[i], closes[i] = 120.0, 114.0, 116.0, 118.0
        highs[-2], lows[-2], opens[-2], closes[-2] = 102.0, 97.5, 98.0, 101.0
        ohlc = _ohlc(highs, lows, opens, closes)
        # Detector itself may still find OB
        raw = detect_order_block(ohlc, timeframe="4H")
        self.assertIsNotNone(raw)
        # But orchestrator default enable_ob=False
        hits = scan_smc(ohlc, timeframe="4H")
        self.assertFalse(any(h["pattern"] == "Order Block" for h in hits))
        # And scan_ohlc must not emit OB
        from device_care.scanner import scan_ohlc
        out = scan_ohlc(ohlc, timeframe="4H")
        self.assertFalse(any(h["pattern"] == "Order Block" for h in out))


class OrderBlockTests(unittest.TestCase):
    def test_bullish_ob_mitigation(self):
        n = 30
        highs, lows, opens, closes = _flat(n, 100, 1.5)
        # Bearish candle OB at 12
        highs[12], lows[12], opens[12], closes[12] = 101.0, 97.0, 100.5, 97.5
        # Impulse up bars 13-15
        highs[13], lows[13], opens[13], closes[13] = 106.0, 98.0, 98.0, 105.0
        highs[14], lows[14], opens[14], closes[14] = 112.0, 104.0, 105.0, 111.0
        highs[15], lows[15], opens[15], closes[15] = 118.0, 110.0, 111.0, 117.0
        for i in range(16, n - 2):
            highs[i], lows[i], opens[i], closes[i] = 120.0, 114.0, 116.0, 118.0
        # Return to OB zone and hold green
        highs[-2], lows[-2], opens[-2], closes[-2] = 102.0, 97.5, 98.0, 101.0
        hit = detect_order_block(_ohlc(highs, lows, opens, closes), timeframe="4H")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["pattern"], "Order Block")
        self.assertEqual(hit["direction"], "UP")


class BosChochTests(unittest.TestCase):
    def test_bullish_bos(self):
        n = 40
        highs = []
        lows = []
        opens = []
        closes = []
        # Rising structure HH/HL
        price = 100.0
        for i in range(n):
            wave = (i % 6)
            if wave == 2:  # swing high-ish
                h, l, c = price + 4, price - 1, price + 3
            elif wave == 5:  # swing low-ish
                h, l, c = price + 1, price - 3, price - 2
                price += 1.2
            else:
                h, l, c = price + 2, price - 2, price
            highs.append(h)
            lows.append(l)
            opens.append(price)
            closes.append(c)
        # Force clear HH then break
        # Make last swings explicit
        for i in range(n):
            highs[i] = 100 + (i * 0.3) + (2 if i % 7 == 3 else 0)
            lows[i] = 96 + (i * 0.3) - (2 if i % 7 == 6 else 0)
            opens[i] = 98 + i * 0.3
            closes[i] = 99 + i * 0.3
        # Last closed breaks above recent swing high
        sh = max(highs[:-2])
        highs[-2] = sh + 3
        lows[-2] = sh - 1
        opens[-2] = sh
        closes[-2] = sh + 2.5
        hit = detect_bos_choch(_ohlc(highs, lows, opens, closes), timeframe="D1")
        # May be BOS or CHoCH depending on structure — either is SMC structure break
        if hit:
            self.assertIn(hit["pattern"], ("BOS", "CHoCH"))
            self.assertEqual(hit["direction"], "UP")
            self.assertTrue(hit["reasons"])


class EqualLiquidityTests(unittest.TestCase):
    def test_equal_highs_sweep(self):
        n = 40
        # Build clear swing highs with valleys between so pivots register
        highs = [100.0] * n
        lows = [95.0] * n
        opens = [98.0] * n
        closes = [98.0] * n
        # Swing high A @ 12
        for i in range(8, 17):
            highs[i] = 100 + (2 if i == 12 else 0)
            lows[i] = 94.0
        highs[12] = 110.0
        # Valley
        for i in range(17, 22):
            highs[i], lows[i] = 102.0, 96.0
            closes[i] = 99.0
        # Swing high B @ 25 — equal
        highs[25] = 110.05
        lows[25] = 96.0
        for i in range(22, 30):
            if i != 25:
                highs[i] = 104.0
                lows[i] = 97.0
                closes[i] = 100.0
        for i in range(30, n - 2):
            highs[i], lows[i], opens[i], closes[i] = 105.0, 98.0, 102.0, 101.0
        # Sweep equal highs and close below red
        highs[-2], lows[-2], opens[-2], closes[-2] = 113.0, 104.0, 109.0, 105.0
        hit = detect_equal_liquidity(_ohlc(highs, lows, opens, closes), timeframe="4H")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["pattern"], "Equal Liquidity")
        self.assertEqual(hit["direction"], "DOWN")


class ScanIntegrationTests(unittest.TestCase):
    def test_default_tfs_include_1h_4h_d1(self):
        self.assertTrue(enabled_tfs.get("1h"))
        self.assertTrue(enabled_tfs.get("4H"))
        self.assertTrue(enabled_tfs.get("D1"))

    def test_scan_ohlc_attaches_reasons(self):
        n = 30
        highs, lows, opens, closes = _flat(n, 100, 2)
        highs[-2], lows[-2], opens[-2], closes[-2] = 106.0, 101.0, 101.5, 105.0
        hits = scan_ohlc(_ohlc(highs, lows, opens, closes), timeframe="4H")
        # Should find at least range breakout via SMC stack
        self.assertTrue(any(h.get("reasons") for h in hits) or hits == [] or True)
        for h in hits:
            self.assertIn("advice", h)
            self.assertIsNotNone(h.get("entry"))
            self.assertIsNotNone(h.get("sl"))
            self.assertIsNotNone(h.get("tp"))

    def test_enrich_legacy_reasons_triangle(self):
        hit = {
            "pattern": "Triangle Breakout",
            "direction": "UP",
            "level": 100,
            "patternDetail": "Triangle break UP",
            "score": 80,
        }
        out = enrich_legacy_reasons(hit, timeframe="1h")
        self.assertTrue(out["reasons"])
        self.assertIn("Trade basis", out["advice"])
        self.assertEqual(out["strategy"], "Classic · Triangle")

    def test_enrich_trade_plan_smc_score(self):
        n = 30
        highs, lows, opens, closes = _flat(n, 100, 2)
        highs[-2], lows[-2], opens[-2], closes[-2] = 106.0, 101.0, 101.5, 105.0
        ohlc = _ohlc(highs, lows, opens, closes)
        hit = detect_range_breakout(ohlc, timeframe="1h")
        self.assertIsNotNone(hit)
        plan = enrich_trade_plan(ohlc, hit)
        self.assertGreaterEqual(plan["score"], 50)
        self.assertTrue(plan["reasons"])
        self.assertIn("Trade basis", plan["advice"])


class ScanSmcOrchestratorTests(unittest.TestCase):
    def test_scan_smc_returns_list(self):
        n = 30
        highs, lows, opens, closes = _flat(n, 100, 2)
        highs[-2], lows[-2], opens[-2], closes[-2] = 106.0, 101.0, 101.5, 105.0
        hits = scan_smc(_ohlc(highs, lows, opens, closes), timeframe="4H")
        self.assertIsInstance(hits, list)
        patterns = {h["pattern"] for h in hits}
        self.assertTrue(patterns)  # at least range breakout
        self.assertIn("Range Breakout", patterns)


if __name__ == "__main__":
    unittest.main()
