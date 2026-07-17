import unittest
from datetime import datetime

from device_care.scanner import (
    detect_doji_then_green,
    detect_dragonfly_doji,
    detect_hammer,
    detect_sr_breakout,
    detect_triangle_breakout,
    in_morning_window,
    scan_ohlc,
)


def _ohlc(highs, lows, opens, closes):
    return {
        "highs": highs,
        "lows": lows,
        "opens": opens,
        "closes": closes,
        "times": list(range(len(closes))),
    }


class BreakoutDetectorTests(unittest.TestCase):
    def test_sr_breakout_uses_only_candles_before_candidate(self):
        size = 23
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [94.0] * size
        closes = [95.0] * size
        highs[-2], lows[-2], opens[-2], closes[-2] = 106.0, 94.0, 95.0, 105.0

        hit = detect_sr_breakout(_ohlc(highs, lows, opens, closes))

        self.assertEqual("UP", hit["direction"])
        self.assertEqual(100.0, hit["level"])

    def test_sr_breakdown_uses_only_candles_before_candidate(self):
        size = 23
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [96.0] * size
        closes = [95.0] * size
        highs[-2], lows[-2], opens[-2], closes[-2] = 96.0, 84.0, 95.0, 85.0

        hit = detect_sr_breakout(_ohlc(highs, lows, opens, closes))

        self.assertEqual("DOWN", hit["direction"])
        self.assertEqual(90.0, hit["level"])

    def test_triangle_formation_excludes_breakout_candidate(self):
        size = 21
        highs = [100.0] * size
        lows = [89.0] + [90.0 + 0.45 * i for i in range(18)] + [98.0, 98.0]
        opens = [95.0] * size
        closes = [95.0] * size
        highs[-2], lows[-2], opens[-2], closes[-2] = 102.0, 98.0, 99.0, 101.0

        hit = detect_triangle_breakout(_ohlc(highs, lows, opens, closes))

        self.assertEqual("UP", hit["direction"])
        self.assertEqual("Ascending triangle", hit["patternDetail"])
        self.assertEqual(100.0, hit["level"])


class D1CandlePatternTests(unittest.TestCase):
    def test_dragonfly_doji_requires_green_confirmation(self):
        size = 6
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        # Pattern at -3: dragonfly doji
        highs[-3], lows[-3], opens[-3], closes[-3] = 100.0, 80.0, 99.5, 99.0
        # Last closed (-2): green confirmation above pattern close
        highs[-2], lows[-2], opens[-2], closes[-2] = 105.0, 98.0, 99.0, 104.0

        hit = detect_dragonfly_doji(_ohlc(highs, lows, opens, closes))

        self.assertIsNotNone(hit)
        self.assertEqual("Dragonfly Doji", hit["pattern"])
        self.assertEqual("UP", hit["direction"])
        self.assertEqual(104.0, hit["close"])
        self.assertEqual(80.0, hit["level"])  # min(pattern low, green low)

    def test_dragonfly_rejects_without_green_followup(self):
        size = 6
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        highs[-3], lows[-3], opens[-3], closes[-3] = 100.0, 80.0, 99.5, 99.0
        # Red follow-up — no alert
        highs[-2], lows[-2], opens[-2], closes[-2] = 100.0, 90.0, 99.0, 92.0

        hit = detect_dragonfly_doji(_ohlc(highs, lows, opens, closes))

        self.assertIsNone(hit)

    def test_dragonfly_rejects_long_upper_wick(self):
        size = 6
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        highs[-3], lows[-3], opens[-3], closes[-3] = 110.0, 80.0, 95.0, 95.5
        highs[-2], lows[-2], opens[-2], closes[-2] = 105.0, 95.0, 96.0, 104.0

        hit = detect_dragonfly_doji(_ohlc(highs, lows, opens, closes))

        self.assertIsNone(hit)

    def test_hammer_requires_green_confirmation(self):
        size = 6
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        # Pattern at -3: green hammer
        highs[-3], lows[-3], opens[-3], closes[-3] = 101.2, 90.0, 98.0, 101.0
        # Last closed (-2): green confirmation
        highs[-2], lows[-2], opens[-2], closes[-2] = 108.0, 100.0, 101.0, 107.0

        hit = detect_hammer(_ohlc(highs, lows, opens, closes))

        self.assertIsNotNone(hit)
        self.assertEqual("Hammer", hit["pattern"])
        self.assertEqual("UP", hit["direction"])
        self.assertEqual(107.0, hit["close"])

    def test_hammer_rejects_doji_body(self):
        """Tiny body is dragonfly territory, not hammer."""
        size = 6
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        highs[-3], lows[-3], opens[-3], closes[-3] = 100.0, 80.0, 99.5, 99.2
        highs[-2], lows[-2], opens[-2], closes[-2] = 105.0, 98.0, 99.0, 104.0

        hit = detect_hammer(_ohlc(highs, lows, opens, closes))

        self.assertIsNone(hit)

    def test_doji_then_green_sequence(self):
        size = 6
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        # Doji at -3 (not dragonfly — short lower wick relative to full range)
        highs[-3], lows[-3], opens[-3], closes[-3] = 100.0, 90.0, 95.2, 95.0
        # Green confirmation at -2 closing above doji
        highs[-2], lows[-2], opens[-2], closes[-2] = 102.0, 94.0, 95.0, 101.0

        hit = detect_doji_then_green(_ohlc(highs, lows, opens, closes))

        self.assertIsNotNone(hit)
        self.assertEqual("Doji + Green", hit["pattern"])
        self.assertEqual("UP", hit["direction"])
        self.assertEqual(101.0, hit["close"])

    def test_doji_then_green_rejects_red_followup(self):
        size = 6
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        highs[-3], lows[-3], opens[-3], closes[-3] = 100.0, 90.0, 95.2, 95.0
        highs[-2], lows[-2], opens[-2], closes[-2] = 96.0, 88.0, 95.0, 89.0

        hit = detect_doji_then_green(_ohlc(highs, lows, opens, closes))

        self.assertIsNone(hit)

    def test_scan_ohlc_includes_d1_patterns_when_enabled(self):
        size = 25
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        # Dragonfly at -3 + green at -2
        highs[-3], lows[-3], opens[-3], closes[-3] = 100.0, 80.0, 99.5, 99.0
        highs[-2], lows[-2], opens[-2], closes[-2] = 105.0, 98.0, 99.0, 104.0

        without = scan_ohlc(_ohlc(highs, lows, opens, closes), include_d1_patterns=False)
        with_d1 = scan_ohlc(_ohlc(highs, lows, opens, closes), include_d1_patterns=True)

        self.assertFalse(any(h["pattern"] == "Dragonfly Doji" for h in without))
        self.assertTrue(any(h["pattern"] == "Dragonfly Doji" for h in with_d1))
        dragon = next(h for h in with_d1 if h["pattern"] == "Dragonfly Doji")
        self.assertIn("score", dragon)
        self.assertIn("entry", dragon)
        self.assertIn("sl", dragon)
        self.assertIn("tp", dragon)
        self.assertGreaterEqual(dragon["score"], 1)
        self.assertLessEqual(dragon["score"], 100)
        self.assertLess(dragon["sl"], dragon["entry"])
        self.assertGreater(dragon["tp"], dragon["entry"])

    def test_tf_gating_breakouts_and_candles(self):
        size = 25
        # Dragonfly + green — D1 only
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        highs[-3], lows[-3], opens[-3], closes[-3] = 100.0, 80.0, 99.5, 99.0
        highs[-2], lows[-2], opens[-2], closes[-2] = 105.0, 98.0, 99.0, 104.0
        ohlc = _ohlc(highs, lows, opens, closes)

        self.assertFalse(any(
            h["pattern"] == "Dragonfly Doji" for h in scan_ohlc(ohlc, timeframe="1h")
        ))
        self.assertFalse(any(
            h["pattern"] == "Dragonfly Doji" for h in scan_ohlc(ohlc, timeframe="4H")
        ))
        self.assertTrue(any(
            h["pattern"] == "Dragonfly Doji" for h in scan_ohlc(ohlc, timeframe="D1")
        ))

        # Ascending triangle — 1h / 4H / D1 (not 5m)
        size = 21
        highs = [100.0] * size
        lows = [89.0] + [90.0 + 0.45 * i for i in range(18)] + [98.0, 98.0]
        opens = [95.0] * size
        closes = [95.0] * size
        highs[-2], lows[-2], opens[-2], closes[-2] = 102.0, 98.0, 99.0, 101.0
        tri = _ohlc(highs, lows, opens, closes)

        m5 = scan_ohlc(tri, timeframe="5m")
        h1 = scan_ohlc(tri, timeframe="1h")
        h4 = scan_ohlc(tri, timeframe="4H")
        d1 = scan_ohlc(tri, timeframe="D1")
        self.assertFalse(any(h["pattern"] == "Triangle Breakout" for h in m5))
        self.assertTrue(any(h["pattern"] == "Triangle Breakout" for h in h1))
        self.assertTrue(any(h["pattern"] == "Triangle Breakout" for h in h4))
        self.assertTrue(any(h["pattern"] == "Triangle Breakout" for h in d1))

    def test_scan_ohlc_sr_breakout_all_toggle_tfs(self):
        size = 23
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [94.0] * size
        closes = [95.0] * size
        highs[-2], lows[-2], opens[-2], closes[-2] = 106.0, 94.0, 95.0, 105.0
        ohlc = _ohlc(highs, lows, opens, closes)

        for tf in ("5m", "15m", "1h", "4H", "D1"):
            hits = scan_ohlc(ohlc, timeframe=tf)
            self.assertTrue(
                any(h["pattern"] == "S/R Breakout" for h in hits),
                f"expected S/R on {tf}",
            )
        sr = next(h for h in scan_ohlc(ohlc, timeframe="4H") if h["pattern"] == "S/R Breakout")
        self.assertEqual("UP", sr["direction"])
        self.assertEqual(100.0, sr["level"])
        self.assertLess(sr["sl"], sr["entry"])
        self.assertGreater(sr["tp"], sr["entry"])

    def test_live_sr_breakout_on_forming_candle(self):
        size = 23
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [94.0] * size
        closes = [95.0] * size
        # Forming candle (-1) breaks resistance
        highs[-1], lows[-1], opens[-1], closes[-1] = 108.0, 96.0, 97.0, 107.0
        ohlc = _ohlc(highs, lows, opens, closes)

        live = detect_sr_breakout(ohlc, live=True)
        closed = detect_sr_breakout(ohlc, live=False)

        self.assertIsNotNone(live)
        self.assertTrue(live["live"])
        self.assertIn("LIVE", live["patternDetail"])
        self.assertEqual("UP", live["direction"])
        self.assertIsNone(closed)

        for tf in ("5m", "15m", "1h", "4H"):
            hits = scan_ohlc(ohlc, timeframe=tf)
            self.assertTrue(any(h.get("live") for h in hits if h["pattern"] == "S/R Breakout"))

    def test_live_pierce_fires_before_close_above(self):
        """Breakout hoti hi — high pierce even if close still near level."""
        size = 23
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [94.0] * size
        closes = [95.0] * size
        # High pierced resistance but close barely above open (body still ok)
        highs[-1], lows[-1], opens[-1], closes[-1] = 106.0, 94.5, 95.0, 96.5
        ohlc = _ohlc(highs, lows, opens, closes)
        live = detect_sr_breakout(ohlc, live=True)
        self.assertIsNotNone(live)
        self.assertEqual("UP", live["direction"])
        self.assertTrue(live["live"])


class MorningWindowTests(unittest.TestCase):
    def test_morning_window_5_to_9_pkt(self):
        self.assertTrue(in_morning_window(datetime(2026, 7, 10, 5, 0)))
        self.assertTrue(in_morning_window(datetime(2026, 7, 10, 8, 59)))
        self.assertFalse(in_morning_window(datetime(2026, 7, 10, 4, 59)))
        self.assertFalse(in_morning_window(datetime(2026, 7, 10, 9, 0)))
        self.assertFalse(in_morning_window(datetime(2026, 7, 10, 14, 0)))


class AlertTtlTests(unittest.TestCase):
    def setUp(self):
        import device_care.scanner as sc
        self.sc = sc
        sc.alert_history.clear()
        sc.scan_stats["alertsTotal"] = 0

    def tearDown(self):
        self.sc.alert_history.clear()
        self.sc.scan_stats["alertsTotal"] = 0

    def test_breakout_clears_after_1h_d1_after_8h(self):
        now = 1_800_000_000.0  # fixed epoch
        self.sc.alert_history.extend([
            {
                "id": "brk",
                "symbol": "BTC_USDT",
                "pattern": "Triangle Breakout",
                "direction": "UP",
                "alertedAt": int((now - 3601) * 1000),
            },
            {
                "id": "tri",
                "symbol": "ETH_USDT",
                "pattern": "Triangle Breakout",
                "direction": "UP",
                "alertedAt": int((now - 1800) * 1000),
            },
            {
                "id": "d1-old",
                "symbol": "SOL_USDT",
                "pattern": "Dragonfly Doji",
                "direction": "UP",
                "alertedAt": int((now - 8 * 3600 - 1) * 1000),
            },
            {
                "id": "d1-keep",
                "symbol": "DOGE_USDT",
                "pattern": "Hammer",
                "direction": "UP",
                "alertedAt": int((now - 4 * 3600) * 1000),
            },
        ])

        removed = self.sc.prune_alert_history(now)
        removed_ids = {r["id"] for r in removed}

        self.assertEqual({"brk", "d1-old"}, removed_ids)
        kept_ids = {a["id"] for a in self.sc.alert_history}
        self.assertEqual({"tri", "d1-keep"}, kept_ids)
        self.assertEqual(2, self.sc.scan_stats["alertsTotal"])


class FuturesFilterTests(unittest.TestCase):
    def test_accepts_crypto_usdt_perp(self):
        from device_care.scanner import _is_crypto_futures_usdt

        self.assertTrue(_is_crypto_futures_usdt({
            "symbol": "BTC_USDT",
            "baseCoin": "BTC",
            "quoteCoin": "USDT",
            "settleCoin": "USDT",
            "state": 0,
            "apiAllowed": True,
            "isHidden": False,
            "type": 1,
        }))

    def test_rejects_spot_style_and_non_crypto(self):
        from device_care.scanner import _is_crypto_futures_usdt

        self.assertFalse(_is_crypto_futures_usdt({
            "symbol": "BTCUSDT",  # spot-style, no underscore
            "baseCoin": "BTC",
            "quoteCoin": "USDT",
            "settleCoin": "USDT",
            "state": 0,
            "apiAllowed": True,
            "isHidden": False,
            "type": 1,
        }))
        self.assertFalse(_is_crypto_futures_usdt({
            "symbol": "XAU_USDT",
            "baseCoin": "XAU",
            "quoteCoin": "USDT",
            "settleCoin": "USDT",
            "state": 0,
            "apiAllowed": True,
            "isHidden": False,
            "type": 1,
        }))
        self.assertFalse(_is_crypto_futures_usdt({
            "symbol": "NVIDIA_USDT",
            "baseCoin": "NVIDIA",
            "quoteCoin": "USDT",
            "settleCoin": "USDT",
            "state": 0,
            "apiAllowed": True,
            "isHidden": False,
            "type": 2,
        }))


if __name__ == "__main__":
    unittest.main()
