"""Daily 25% unlock gate — unit tests (no MT5)."""

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock


class DailyUnlockTests(unittest.TestCase):
    def test_pkt_today_format(self):
        import main
        d = main.pkt_today()
        self.assertRegex(d, r"^\d{4}-\d{2}-\d{2}$")

    def test_follower_can_copy_requires_today_unlock(self):
        import main
        today = main.pkt_today()
        user = SimpleNamespace(
            username="trader1",
            bot_active=True,
            mt5_login=123,
            daily_profit_owed=0.0,
            payment_status="clear",
            daily_unlock_date=today,
        )
        with mock.patch.object(main, "is_master_user", return_value=False):
            self.assertTrue(main.follower_can_copy(user))
            user.daily_unlock_date = "2000-01-01"
            self.assertFalse(main.follower_can_copy(user))
            user.daily_unlock_date = today
            user.daily_profit_owed = 12.5
            self.assertFalse(main.follower_can_copy(user))
            user.daily_profit_owed = 0
            user.payment_status = "pending"
            self.assertFalse(main.follower_can_copy(user))

    def test_master_always_can_copy(self):
        import main
        user = SimpleNamespace(username="Admin99", bot_active=False, mt5_login=None)
        with mock.patch.object(main, "is_master_user", return_value=True):
            self.assertTrue(main.follower_can_copy(user))

    def test_grant_and_revoke(self):
        import main
        user = SimpleNamespace(
            id=9,
            daily_unlock_date=None,
            payment_status="pending",
            daily_profit_owed=5.0,
            referral_owed=1.0,
            bot_active=True,
        )
        main.active_bots[9] = True
        main.grant_daily_unlock(user)
        self.assertEqual(user.daily_unlock_date, main.pkt_today())
        self.assertEqual(user.daily_profit_owed, 0.0)
        self.assertEqual(user.payment_status, "clear")
        main.revoke_daily_unlock(user, reason="pending")
        self.assertIsNone(user.daily_unlock_date)
        self.assertFalse(user.bot_active)
        self.assertEqual(user.payment_status, "pending")


if __name__ == "__main__":
    unittest.main()
