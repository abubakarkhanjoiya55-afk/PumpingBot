"""Admin JWT never-expire + CPS branding smoke tests."""
import unittest
from datetime import datetime, timedelta

from jose import jwt

from main import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    FREE_TRIAL_HOURS,
    is_master_user,
    refresh_subscription_status,
)


class _U:
    def __init__(self, username, status="trial", expires=None):
        self.username = username
        self.email = f"{username}@t.com"
        self.subscription_status = status
        self.subscription_expires_at = expires
        self.bot_active = True
        self.payment_status = "clear"
        self.subscription_fee_owed = 10


class AdminNeverExpireTests(unittest.TestCase):
    def test_admin_token_lives_years(self):
        token = create_access_token({"sub": "Admin99", "role": "admin"}, expires_minutes=0)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        exp = datetime.utcfromtimestamp(payload["exp"])
        self.assertGreater(exp, datetime.utcnow() + timedelta(days=365 * 5))

    def test_user_token_uses_default_window(self):
        token = create_access_token({"sub": "trader1"})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        exp = datetime.utcfromtimestamp(payload["exp"])
        # ~24h default — not multi-year
        self.assertLess(exp, datetime.utcnow() + timedelta(days=3))
        self.assertGreater(exp, datetime.utcnow() + timedelta(hours=12))

    def test_admin_subscription_always_active(self):
        u = _U("Admin99", status="expired", expires=datetime.utcnow() - timedelta(days=1))
        self.assertTrue(is_master_user(u))
        self.assertEqual("active", refresh_subscription_status(u))

    def test_trial_hours_is_24(self):
        self.assertEqual(24, FREE_TRIAL_HOURS)

    def test_user_trial_expires(self):
        u = _U("bob", status="trial", expires=datetime.utcnow() - timedelta(minutes=1))
        self.assertEqual("expired", refresh_subscription_status(u))
        self.assertFalse(u.bot_active)


class BrandingAssetTests(unittest.TestCase):
    def test_icons_and_name(self):
        from pathlib import Path
        root = Path("device_care/static")
        self.assertTrue((root / "icon-192.png").is_file())
        self.assertTrue((root / "icon-512.png").is_file())
        html = (root / "index.html").read_text(encoding="utf-8")
        self.assertIn("Crypto Pumping Signals", html)
        self.assertIn("updateBanner", html)
        self.assertIn("SKIP_WAITING", html)
        sw = (root / "sw.js").read_text(encoding="utf-8")
        self.assertIn("cps-v4.1.0", sw)
        self.assertIn("SKIP_WAITING", sw)
        self.assertNotIn("skipWaiting()", sw.split("message")[0])  # no auto skip on install


if __name__ == "__main__":
    unittest.main()
