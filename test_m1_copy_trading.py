"""Unit tests for M1 candle-pattern scoring + fast copy helpers."""
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

from trading_engine import (
    detect_candle_pattern,
    confirm_m1_direction,
    score_m1_setup,
    get_risk_multiplier,
    trade_eligible,
    MIN_PATTERN_SCORE,
    STRONG_SCORE,
)


class TestM1CandlePatterns(unittest.TestCase):
    def test_bullish_engulfing(self):
        # prev red, then green engulfing (o1 <= c2, c1 >= o2)
        opens = [10.0, 10.5, 9.0]
        highs = [10.2, 10.6, 11.0]
        lows = [9.5, 9.2, 8.9]
        closes = [9.8, 9.3, 10.8]
        name, direction, score = detect_candle_pattern(opens, highs, lows, closes)
        self.assertEqual(direction, "BUY")
        self.assertIn("Engulfing", name)
        self.assertGreaterEqual(score, 20)

    def test_bearish_engulfing(self):
        opens = [10.0, 9.5, 11.0]
        highs = [10.2, 10.6, 11.1]
        lows = [9.5, 9.4, 9.0]
        closes = [9.8, 10.4, 9.2]
        name, direction, score = detect_candle_pattern(opens, highs, lows, closes)
        self.assertEqual(direction, "SELL")
        self.assertIn("Engulfing", name)

    def test_hammer(self):
        # long lower wick, tiny upper wick, green close
        opens = [10.0, 10.0, 10.0]
        highs = [10.2, 10.1, 10.12]
        lows = [9.5, 9.8, 9.40]
        closes = [9.8, 9.9, 10.10]
        name, direction, score = detect_candle_pattern(opens, highs, lows, closes)
        self.assertEqual(direction, "BUY")
        self.assertEqual(name, "Hammer")

    def test_confirm_buy_needs_structure(self):
        opens = [10, 10.1, 10.2, 10.3]
        highs = [10.2, 10.3, 10.4, 10.6]
        lows = [9.9, 10.0, 10.1, 10.2]
        closes = [10.05, 10.15, 10.25, 10.5]
        ok, bonus, reason = confirm_m1_direction(opens, highs, lows, closes, "BUY")
        self.assertTrue(ok)
        self.assertGreaterEqual(bonus, 12)
        self.assertIn("green_close", reason)

    def test_confirm_rejects_weak(self):
        # Opposite direction candles — BUY confirm should be weak/fail
        opens = [10.5, 10.4, 10.3, 10.2]
        highs = [10.6, 10.5, 10.4, 10.25]
        lows = [10.3, 10.2, 10.1, 9.9]
        closes = [10.4, 10.3, 10.2, 10.0]
        ok, bonus, reason = confirm_m1_direction(opens, highs, lows, closes, "BUY")
        self.assertFalse(ok)
        self.assertLess(bonus, 12)

    def test_score_scales_with_pattern(self):
        weak = score_m1_setup(12, 12, atr=1.0, body=0.2, range_=1.0)
        strong = score_m1_setup(28, 30, atr=1.0, body=0.9, range_=1.0)
        self.assertGreater(strong, weak)
        self.assertGreaterEqual(strong, MIN_PATTERN_SCORE)
        self.assertLessEqual(strong, 100)

    def test_risk_multiplier_by_score(self):
        self.assertGreater(get_risk_multiplier(95), get_risk_multiplier(50))
        self.assertGreaterEqual(get_risk_multiplier(STRONG_SCORE), 2.0)

    def test_trade_eligible_m1(self):
        ok, reason = trade_eligible({
            "m1_pattern": "Bullish Engulfing",
            "score": 55,
        })
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

        bad, why = trade_eligible({"skip": True, "reason": "no_confirm"})
        self.assertFalse(bad)
        self.assertEqual(why, "no_confirm")


class TestParallelFanoutTiming(unittest.TestCase):
    def test_parallel_faster_than_sequential(self):
        """Ensure ThreadPool fan-out runs work concurrently."""
        def work(_i):
            time.sleep(0.05)
            return True

        n = 6
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=8) as ex:
            list(as_completed([ex.submit(work, i) for i in range(n)]))
        parallel_ms = (time.perf_counter() - t0) * 1000

        t1 = time.perf_counter()
        for i in range(n):
            work(i)
        sequential_ms = (time.perf_counter() - t1) * 1000

        # Parallel should finish much closer to one sleep than n sleeps
        self.assertLess(parallel_ms, sequential_ms * 0.6)
        self.assertLess(parallel_ms, 200)

    def test_schedule_close_nonblocking(self):
        import copy_trading as ct

        started = time.perf_counter()
        with patch.object(ct, "copy_close_to_followers", side_effect=lambda *a, **k: time.sleep(0.2)):
            fut = ct.schedule_close_followers(12345, "XAUUSDm")
            elapsed = (time.perf_counter() - started) * 1000
            self.assertIsNotNone(fut)
            self.assertLess(elapsed, 50)  # must return immediately
            fut.result(timeout=2)


if __name__ == "__main__":
    unittest.main()
