"""
PumpingBot Windows VPS Supervisor

- Polls Railway API for users who logged in from mobile
- Provisions a portable MT5 terminal per account
- Starts local_agent for each user (master + followers)
- Users never run anything on their PC

Env:
  SERVER_URL=https://your-app.up.railway.app
  VPS_SECRET=same-as-railway
  MT5_TEMPLATE_DIR=C:\\PumpingBot\\MT5_Template
  MT5_INSTANCES_DIR=C:\\PumpingBot\\MT5_Instances
  PYTHON_EXE=python
  REPO_DIR=C:\\PumpingBot\\PumpingBot   (git clone path)
  POLL_SEC=10
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests

from provision import ensure_portable_instance, start_terminal, terminal_exe

POLL_SEC = float(os.environ.get("POLL_SEC", "10"))
SERVER_URL = (os.environ.get("SERVER_URL") or "").rstrip("/")
VPS_SECRET = os.environ.get("VPS_SECRET") or ""
PYTHON_EXE = os.environ.get("PYTHON_EXE") or sys.executable
REPO_DIR = Path(os.environ.get("REPO_DIR") or Path(__file__).resolve().parents[1])
HOST_NAME = os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "vps"


class ManagedAgent:
    def __init__(self, user: dict):
        self.user_id = int(user["user_id"])
        self.username = user["username"]
        self.role = user.get("role") or "follower"
        self.login = int(user["mt5_login"])
        self.password = user["mt5_password"]
        self.server = user["mt5_server"]
        self.bot_active = bool(user.get("bot_active"))
        self.proc: Optional[subprocess.Popen] = None
        self.term_proc: Optional[subprocess.Popen] = None
        self.last_error: Optional[str] = None
        self.ready = False
        self.balance = 0.0
        self.equity = 0.0
        self.status = "starting"
        self.restart_after = 0.0  # cooldown before next restart

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None


class Supervisor:
    def __init__(self):
        if not SERVER_URL:
            raise SystemExit("SERVER_URL required")
        if not VPS_SECRET:
            raise SystemExit("VPS_SECRET required (must match Railway env)")
        self.agents: dict[int, ManagedAgent] = {}
        self._stop = False
        self.session = requests.Session()
        self.session.headers["X-VPS-Secret"] = VPS_SECRET

    def _url(self, path: str) -> str:
        return f"{SERVER_URL}{path}"

    def fetch_roster(self) -> list[dict]:
        r = self.session.get(self._url("/admin/vps/roster"), timeout=30)
        r.raise_for_status()
        return r.json().get("users") or []

    def fetch_token(self, user_id: int) -> str:
        r = self.session.post(
            self._url(f"/admin/vps/agent-token/{user_id}"),
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["access_token"]

    def report(self):
        payload = {
            "host": HOST_NAME,
            "agents": [
                {
                    "user_id": a.user_id,
                    "status": a.status if a.alive() else ("error" if a.last_error else "stopped"),
                    "ready": bool(a.ready and a.alive()),
                    "balance": a.balance,
                    "equity": a.equity,
                    "error": a.last_error,
                    "pid": a.proc.pid if a.alive() else None,
                }
                for a in self.agents.values()
            ],
        }
        try:
            self.session.post(self._url("/admin/vps/report"), json=payload, timeout=30)
        except Exception as e:
            print(f"[VPS] report failed: {e}")

    def start_agent(self, user: dict) -> ManagedAgent:
        agent = ManagedAgent(user)
        print(f"[VPS] Starting {agent.username} login={agent.login} role={agent.role}")
        try:
            ensure_portable_instance(agent.login)
            agent.term_proc = start_terminal(agent.login)
            token = self.fetch_token(agent.user_id)
            mt5_path = str(terminal_exe(agent.login))
            env = os.environ.copy()
            env.update({
                "SERVER_URL": SERVER_URL,
                "ACCESS_TOKEN": token,
                "MT5_LOGIN": str(agent.login),
                "MT5_PASSWORD": agent.password,
                "MT5_SERVER": agent.server,
                "MT5_PATH": mt5_path,
                "AGENT_ROLE": agent.role,
                "BOT_ACTIVE": "1" if user.get("bot_active") else "0",
                "ACCOUNT_TYPE": os.environ.get("ACCOUNT_TYPE", "standard"),
                "PYTHONUNBUFFERED": "1",
            })
            if os.environ.get("SYMBOLS"):
                env["SYMBOLS"] = os.environ["SYMBOLS"]
            agent.bot_active = bool(user.get("bot_active"))
            agent_py = REPO_DIR / "local_agent" / "agent.py"
            if not agent_py.is_file():
                raise FileNotFoundError(f"Missing {agent_py}")

            log_dir = Path(os.environ.get("AGENT_LOG_DIR", r"C:\PumpingBot\logs"))
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"agent_{agent.user_id}_{agent.login}.log"
            log_f = open(log_path, "a", encoding="utf-8")

            # Let portable MT5 finish login UI / IPC before python attaches
            boot_wait = float(os.environ.get("MT5_BOOT_WAIT_SEC", "20"))
            time.sleep(max(0.0, boot_wait - 20.0))  # start_terminal already waited ~20s
            agent.proc = subprocess.Popen(
                [PYTHON_EXE, str(agent_py)],
                cwd=str(REPO_DIR),
                env=env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            agent.status = "running"
            agent.ready = False  # becomes ready after WS hello + MT5 connect
            agent.last_error = None
            agent.log_path = str(log_path)
            print(f"[VPS] Agent pid={agent.proc.pid} log={log_path}")
            # Quick death check — surface MT5 login errors immediately
            time.sleep(3)
            if agent.proc.poll() is not None:
                agent.status = "error"
                agent.last_error = f"agent exited code={agent.proc.returncode}"
                print(f"[VPS] Agent died immediately: {agent.last_error}")
                try:
                    tail = Path(log_path).read_text(encoding="utf-8", errors="ignore").splitlines()[-15:]
                    for line in tail:
                        print(f"[AGENT LOG] {line}")
                except Exception:
                    pass
        except Exception as e:
            agent.status = "error"
            agent.last_error = str(e)
            print(f"[VPS] Start failed {agent.username}: {e}")
        return agent

    def stop_agent(self, agent: ManagedAgent):
        print(f"[VPS] Stopping user={agent.user_id} {agent.username}")
        if agent.proc and agent.proc.poll() is None:
            try:
                if os.name == "nt":
                    agent.proc.terminate()
                else:
                    agent.proc.send_signal(signal.SIGTERM)
                try:
                    agent.proc.wait(timeout=8)
                except Exception:
                    agent.proc.kill()
            except Exception as e:
                print(f"[VPS] stop error: {e}")
        agent.proc = None
        # Also stop portable MT5 terminal so logins don't pile up
        if agent.term_proc and agent.term_proc.poll() is None:
            try:
                agent.term_proc.terminate()
                try:
                    agent.term_proc.wait(timeout=5)
                except Exception:
                    agent.term_proc.kill()
            except Exception as e:
                print(f"[VPS] terminal stop error: {e}")
        agent.term_proc = None
        agent.status = "stopped"
        agent.ready = False

    def sync(self):
        roster = self.fetch_roster()
        wanted = {int(u["user_id"]): u for u in roster}

        # Stop agents no longer desired
        for uid in list(self.agents.keys()):
            if uid not in wanted:
                self.stop_agent(self.agents[uid])
                del self.agents[uid]

        # Start / restart wanted agents
        for uid, user in wanted.items():
            existing = self.agents.get(uid)
            if existing is None:
                self.agents[uid] = self.start_agent(user)
                continue

            # Credentials / role changed → restart.
            # bot_active is toggled live over WebSocket (set_bot_active) — no restart.
            bot_active = bool(user.get("bot_active"))
            need_restart = (
                int(user["mt5_login"]) != existing.login
                or user["mt5_password"] != existing.password
                or user["mt5_server"] != existing.server
                or (user.get("role") or "follower") != existing.role
            )
            if need_restart:
                self.stop_agent(existing)
                self.agents[uid] = self.start_agent(user)
                continue

            if not existing.alive():
                # Avoid restart spam (MT5 IPC timeout needs breathing room)
                now = time.time()
                if now < getattr(existing, "restart_after", 0):
                    existing.status = "waiting_restart"
                    continue
                exit_code = None
                try:
                    if existing.proc is not None:
                        exit_code = existing.proc.poll()
                except Exception:
                    pass
                print(
                    f"[VPS] Restart dead agent {existing.username} "
                    f"exit={exit_code} — check log agent_{existing.user_id}_{existing.login}.log"
                )
                # IMPORTANT: never taskkill python.exe / all terminal64 —
                # that kills THIS supervisor process too.
                self.stop_agent(existing)
                time.sleep(5)
                fresh = self.start_agent(user)
                fresh.restart_after = time.time() + 30
                self.agents[uid] = fresh
                continue

            # Refresh fields — do NOT mark ready just because process is alive
            existing.password = user["mt5_password"]
            if bot_active != existing.bot_active:
                print(
                    f"[VPS] {existing.username} bot_active {existing.bot_active}→{bot_active} "
                    f"(live WS; no restart)"
                )
            existing.bot_active = bot_active
            existing.status = "running"
            # ready stays False here; agent WS heartbeat on Railway sets vps_ready

    def run(self):
        print("=" * 60)
        print("PumpingBot VPS Supervisor")
        print(f"  SERVER_URL = {SERVER_URL}")
        print(f"  REPO_DIR   = {REPO_DIR}")
        print(f"  POLL_SEC   = {POLL_SEC}")
        print("  Users mobile pe login karenge — yahan agents auto chalenge")
        print("=" * 60)
        while not self._stop:
            try:
                self.sync()
                self.report()
            except Exception as e:
                print(f"[VPS] loop error: {e}")
            time.sleep(POLL_SEC)


def main():
    Supervisor().run()


if __name__ == "__main__":
    main()
