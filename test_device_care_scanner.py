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
    def test_dragonfly_doji_on_closed_candle(self):
        size = 5
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        # Closed candle (-2): open≈close near high, long lower wick
        highs[-2], lows[-2], opens[-2], closes[-2] = 100.0, 80.0, 99.5, 99.0

        hit = detect_dragonfly_doji(_ohlc(highs, lows, opens, closes))

        self.assertIsNotNone(hit)
        self.assertEqual("Dragonfly Doji", hit["pattern"])
        self.assertEqual("UP", hit["direction"])
        self.assertEqual(80.0, hit["level"])

    def test_dragonfly_rejects_long_upper_wick(self):
        size = 5
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        highs[-2], lows[-2], opens[-2], closes[-2] = 110.0, 80.0, 95.0, 95.5

        hit = detect_dragonfly_doji(_ohlc(highs, lows, opens, closes))

        self.assertIsNone(hit)

    def test_hammer_on_closed_candle(self):
        size = 5
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        # Green hammer: body in upper third, long lower wick, tiny upper wick
        highs[-2], lows[-2], opens[-2], closes[-2] = 101.2, 90.0, 98.0, 101.0

        hit = detect_hammer(_ohlc(highs, lows, opens, closes))

        self.assertIsNotNone(hit)
        self.assertEqual("Hammer", hit["pattern"])
        self.assertEqual("UP", hit["direction"])

    def test_hammer_rejects_doji_body(self):
        """Tiny body is dragonfly territory, not hammer."""
        size = 5
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        highs[-2], lows[-2], opens[-2], closes[-2] = 100.0, 80.0, 99.5, 99.2

        hit = detect_hammer(_ohlc(highs, lows, opens, closes))

        self.assertIsNone(hit)

    def test_doji_then_green_sequence(self):
        size = 6
        highs = [100.0] * size
        lows = [90.0] * size
        opens = [95.0] * size
        closes = [95.0] * size
        # Doji at -3
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
        highs[-2], lows[-2], opens[-2], closes[-2] = 100.0, 80.0, 99.5, 99.0

        without = scan_ohlc(_ohlc(highs, lows, opens, closes), include_d1_patterns=False)
        with_d1 = scan_ohlc(_ohlc(highs, lows, opens, closes), include_d1_patterns=True)

        self.assertFalse(any(h["pattern"] == "Dragonfly Doji" for h in without))
        self.assertTrue(any(h["pattern"] == "Dragonfly Doji" for h in with_d1))


class MorningWindowTests(unittest.TestCase):
    def test_morning_window_5_to_9_pkt(self):
        self.assertTrue(in_morning_window(datetime(2026, 7, 10, 5, 0)))
        self.assertTrue(in_morning_window(datetime(2026, 7, 10, 8, 59)))
        self.assertFalse(in_morning_window(datetime(2026, 7, 10, 4, 59)))
        self.assertFalse(in_morning_window(datetime(2026, 7, 10, 9, 0)))
        self.assertFalse(in_morning_window(datetime(2026, 7, 10, 14, 0)))


if __name__ == "__main__":
    unittest.main()
