"""Tests for My Signals standalone split (no network / no httpx)."""
import os
import tempfile
import unittest
from pathlib import Path


def _compute_prefix(raw: str | None) -> str:
    # Mirror device_care.scanner APP_PREFIX logic
    if raw is None:
        raw = "/my-signals"
    raw = raw.strip()
    if raw in ("", "/"):
        return ""
    return "/" + raw.strip("/")


class TestPrefixConfig(unittest.TestCase):
    def test_prefix_root(self):
        self.assertEqual(_compute_prefix(""), "")
        self.assertEqual(_compute_prefix("/"), "")

    def test_prefix_path(self):
        self.assertEqual(_compute_prefix("/my-signals"), "/my-signals")
        self.assertEqual(_compute_prefix("my-signals"), "/my-signals")

    def test_scanner_reads_env(self):
        text = Path("device_care/scanner.py").read_text(encoding="utf-8")
        self.assertIn("MY_SIGNALS_PREFIX", text)

    def test_scanner_guards_empty_prefix_home(self):
        text = Path("device_care/scanner.py").read_text(encoding="utf-8")
        self.assertIn("if APP_PREFIX:", text)
        self.assertIn("async def app_home", text)


class TestServiceFiles(unittest.TestCase):
    def test_dockerfile_and_app_exist(self):
        root = Path(__file__).resolve().parent
        self.assertTrue((root / "my_signals_service" / "app.py").is_file())
        self.assertTrue((root / "my_signals_service" / "Dockerfile").is_file())
        self.assertTrue((root / "my_signals_service" / "railway.toml").is_file())
        self.assertTrue((root / ".github" / "workflows" / "my-signals-deploy.yml").is_file())
        self.assertTrue((root / "device_care" / "auth_api.py").is_file())

    def test_dockerfile_copies_device_care(self):
        text = Path("my_signals_service/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY device_care", text)
        self.assertIn("COPY my_signals_service/app.py", text)

    def test_app_includes_auth(self):
        text = Path("my_signals_service/app.py").read_text(encoding="utf-8")
        self.assertIn("auth_router", text)
        self.assertIn("init_auth_db", text)

    def test_main_has_embed_flag(self):
        text = Path("main.py").read_text(encoding="utf-8")
        self.assertIn("EMBED_MY_SIGNALS", text)
        self.assertIn("MY_SIGNALS_URL", text)


class TestAuthApiImport(unittest.TestCase):
    def test_init_creates_admin(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "t.db"
            os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
            import importlib
            import device_care.auth_api as auth_api

            importlib.reload(auth_api)
            auth_api.init_auth_db()
            db = auth_api.SessionLocal()
            try:
                admin = db.query(auth_api.User).filter(
                    auth_api.User.username == "Admin99"
                ).first()
                self.assertIsNotNone(admin)
                self.assertTrue(auth_api.verify_password("Goku.k.g99", admin.hashed_password))
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
