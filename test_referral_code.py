"""Referral code ensure + invite URL helpers."""
import os
import unittest
from unittest.mock import MagicMock


class ReferralHelperTests(unittest.TestCase):
    def test_build_invite_url_from_request(self):
        # Import after path setup — avoid full main app deps when possible
        os.environ.setdefault("DATABASE_URL", "sqlite:///./test_referral_tmp.db")
        from main import build_invite_url

        req = MagicMock()
        req.base_url = "https://web-production-26ef9.up.railway.app/"
        self.assertEqual(
            build_invite_url(req, "ABC12345"),
            "https://web-production-26ef9.up.railway.app/my-signals/?ref=ABC12345",
        )

    def test_build_invite_url_empty_code(self):
        from main import build_invite_url
        self.assertEqual(build_invite_url(None, ""), "")

    def test_ensure_referral_code_creates_when_missing(self):
        from main import User, ensure_referral_code, SessionLocal, Base, engine

        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            u = User(
                username="refmiss1",
                email="refmiss1@ex.com",
                hashed_password="x",
                referral_code=None,
            )
            db.add(u)
            db.commit()
            db.refresh(u)
            self.assertIsNone(u.referral_code)
            code = ensure_referral_code(u, db)
            self.assertTrue(code)
            self.assertEqual(8, len(code))
            self.assertEqual(code, u.referral_code)
            # second call keeps same
            self.assertEqual(code, ensure_referral_code(u, db))
        finally:
            db.query(User).filter(User.username == "refmiss1").delete()
            db.commit()
            db.close()


if __name__ == "__main__":
    unittest.main()
