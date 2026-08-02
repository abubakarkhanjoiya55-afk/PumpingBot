"""Tests for VPS-hosted agent helpers (no Windows/MT5/FastAPI required)."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["VPS_SECRET"] = "test-secret-123"
os.environ.setdefault("USE_METAAPI", "0")
os.environ.setdefault("TRADING_BACKEND", "agent")


class TestVpsAuth(unittest.TestCase):
    def test_secret_helper(self):
        from vps_auth import vps_secret
        self.assertEqual(vps_secret(), "test-secret-123")

    def test_migrate_file_lists_vps_columns(self):
        text = Path("db_migrate.py").read_text(encoding="utf-8")
        for col in ("vps_desired", "vps_status", "vps_ready", "vps_balance",
                    "vps_last_error", "vps_last_seen"):
            self.assertIn(f'"{col}"', text)


class TestVpsSupervisorHelpers(unittest.TestCase):
    def test_instance_paths(self):
        with patch.dict(os.environ, {
            "MT5_TEMPLATE_DIR": r"C:\tmpl",
            "MT5_INSTANCES_DIR": r"C:\inst",
        }):
            import importlib
            import vps_supervisor.provision as provision
            importlib.reload(provision)
            self.assertTrue(str(provision.instance_dir(4242)).endswith("4242"))
            self.assertIn("terminal64.exe", str(provision.terminal_exe(4242)))


class TestCopyTradingDefaults(unittest.TestCase):
    def test_metaapi_off_by_default(self):
        import copy_trading as ct
        self.assertTrue(ct.agent_mode_enabled())


if __name__ == "__main__":
    unittest.main()
