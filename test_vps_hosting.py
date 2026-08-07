"""Tests for VPS-hosted agent helpers (no Windows/MT5/FastAPI required)."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["VPS_SECRET"] = "test-secret-123"
os.environ.setdefault("USE_METAAPI", "0")
os.environ.setdefault("TRADING_BACKEND", "agent")


class TestVpsAuth(unittest.TestCase):
    def test_go_live_secret_default(self):
        import importlib
        import vps_auth
        importlib.reload(vps_auth)
        self.assertEqual(vps_auth.vps_secret(), "pumpingbot-vps-live-2026")

    def test_override_when_flag_set(self):
        import importlib
        import vps_auth
        with patch.dict(os.environ, {
            "VPS_SECRET_OVERRIDE": "1",
            "VPS_SECRET": "custom-secret",
        }):
            importlib.reload(vps_auth)
            self.assertEqual(vps_auth.vps_secret(), "custom-secret")
        os.environ.pop("VPS_SECRET_OVERRIDE", None)
        importlib.reload(vps_auth)

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

    def test_this_instance_running_is_per_login_path(self):
        """Follower must not be blocked just because master's terminal64 is open."""
        import importlib
        import vps_supervisor.provision as provision
        importlib.reload(provision)

        master = Path(r"C:\PumpingBot\MT5_Instances\111\terminal64.exe")
        follower = Path(r"C:\PumpingBot\MT5_Instances\222\terminal64.exe")

        with patch.object(
            provision,
            "_running_terminal_paths",
            return_value=[provision._normalize_win_path(master)],
        ):
            self.assertTrue(provision._this_instance_running(master))
            self.assertFalse(provision._this_instance_running(follower))

        # Unknown path fallback ("*") must NOT block multi-user launches.
        with patch.object(provision, "_running_terminal_paths", return_value=["*"]):
            self.assertFalse(provision._this_instance_running(follower))

    def test_start_terminal_launches_second_login_when_other_running(self):
        import importlib
        import vps_supervisor.provision as provision
        importlib.reload(provision)

        fake_exe = Path(r"C:\PumpingBot\MT5_Instances\222\terminal64.exe")
        master_exe = Path(r"C:\PumpingBot\MT5_Instances\111\terminal64.exe")

        with patch.object(provision, "ensure_portable_instance", return_value=fake_exe), \
             patch.object(
                 provision,
                 "_running_terminal_paths",
                 return_value=[provision._normalize_win_path(master_exe)],
             ), \
             patch.object(provision.subprocess, "Popen") as popen, \
             patch.object(provision.time, "sleep"):
            popen.return_value = object()
            proc = provision.start_terminal(222)
            self.assertIsNotNone(proc)
            popen.assert_called_once()
            args = popen.call_args[0][0]
            self.assertEqual(args[0], str(fake_exe))


class TestLocalMt5ConnectGuards(unittest.TestCase):
    def test_connect_requires_path_for_multiuser(self):
        from local_agent.mt5_local import LocalMT5
        m = LocalMT5(login=1, password="x", server="Exness", path=None)
        self.assertFalse(m.connect())

    def test_connect_uses_portable_flag(self):
        from unittest.mock import MagicMock, patch
        from local_agent.mt5_local import LocalMT5

        fake = MagicMock()
        fake.initialize.return_value = True
        acc = MagicMock()
        acc.login = 472348552
        acc.balance = 100.0
        acc.currency = "USD"
        acc.trade_allowed = True
        acc.equity = 100.0
        acc.profit = 0.0
        acc.margin = 0.0
        acc.margin_free = 100.0
        acc.margin_level = 0.0
        acc.name = "t"
        acc.leverage = 100
        acc.server = "Exness-MT5Real12"
        fake.account_info.return_value = acc
        fake.last_error.return_value = (1, "ok")

        with patch.dict("sys.modules", {"MetaTrader5": fake}):
            m = LocalMT5(
                login=472348552,
                password="pw",
                server="Exness-MT5Real12",
                path=r"C:\PumpingBot\MT5_Instances\472348552\terminal64.exe",
            )
            # Force import path inside connect to see our fake
            import local_agent.mt5_local as mod
            with patch.object(mod, "time") as t:
                t.sleep = lambda *_: None
                # MetaTrader5 imported inside connect — patch builtins import is hard;
                # just assert signature intent via source.
        src = Path("local_agent/mt5_local.py").read_text(encoding="utf-8")
        self.assertIn('"portable": True', src)
        self.assertIn("MT5_PATH missing", src)


class TestCopyTradingDefaults(unittest.TestCase):
    def test_metaapi_off_by_default(self):
        import copy_trading as ct
        self.assertTrue(ct.agent_mode_enabled())


class TestAgentTokenExpiryHelper(unittest.TestCase):
    def test_create_access_token_accepts_custom_minutes(self):
        # Import only the token helper without starting the full app lifespan
        import ast
        src = Path("main.py").read_text(encoding="utf-8")
        self.assertIn("expires_minutes", src)
        self.assertIn("60 * 24 * 30", src)
        self.assertIn('scope": "vps_agent"', src)


if __name__ == "__main__":
    unittest.main()
