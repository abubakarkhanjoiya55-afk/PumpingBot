import unittest

from device_care.scanner import detect_sr_breakout, detect_triangle_breakout


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


if __name__ == "__main__":
    unittest.main()
