"""
Agent Hub — WebSocket fan-out for local MT5 agents (no MetaAPI).

Each user runs a Windows local_agent that connects here. Open/close
commands are broadcast in parallel so many followers execute together.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AgentSession:
    user_id: int
    username: str
    role: str  # master | follower
    websocket: Any
    login: Optional[int] = None
    server: Optional[str] = None
    balance: float = 0.0
    equity: float = 0.0
    currency: str = ""
    is_cent: bool = False
    ready: bool = False
    positions: list = field(default_factory=list)
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    pending: dict = field(default_factory=dict)  # req_id -> Future


class AgentHub:
    def __init__(self):
        self._agents: dict[int, AgentSession] = {}
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def register(self, session: AgentSession):
        async with self._lock:
            old = self._agents.get(session.user_id)
            if old and old.websocket is not session.websocket:
                try:
                    await old.websocket.close()
                except Exception:
                    pass
            self._agents[session.user_id] = session
        print(f"[AGENT HUB] Online user={session.user_id} "
              f"{session.username} role={session.role} "
              f"total={len(self._agents)}")

    async def unregister(self, user_id: int, websocket=None):
        async with self._lock:
            sess = self._agents.get(user_id)
            if sess and (websocket is None or sess.websocket is websocket):
                for fut in sess.pending.values():
                    if not fut.done():
                        fut.set_result({"ok": False, "error": "disconnected"})
                self._agents.pop(user_id, None)
                print(f"[AGENT HUB] Offline user={user_id} total={len(self._agents)}")

    async def touch(self, user_id: int, **fields):
        async with self._lock:
            sess = self._agents.get(user_id)
            if not sess:
                return
            sess.last_seen = time.time()
            for k, v in fields.items():
                if hasattr(sess, k) and v is not None:
                    setattr(sess, k, v)

    def list_agents(self) -> list[dict]:
        now = time.time()
        out = []
        for s in list(self._agents.values()):
            out.append({
                "user_id": s.user_id,
                "username": s.username,
                "role": s.role,
                "login": s.login,
                "server": s.server,
                "balance": s.balance,
                "equity": s.equity,
                "currency": s.currency,
                "is_cent": s.is_cent,
                "ready": s.ready,
                "positions": list(s.positions or []),
                "last_seen_sec": round(now - s.last_seen, 1),
                "online": (now - s.last_seen) < 30,
            })
        return out

    def online_followers(self, require_ready: bool = True) -> list[AgentSession]:
        now = time.time()
        out = []
        for s in list(self._agents.values()):
            if s.role == "master":
                continue
            if (now - s.last_seen) > 30:
                continue
            if require_ready and not s.ready:
                continue
            out.append(s)
        return out

    def get_positions(self, user_id: int) -> list:
        s = self._agents.get(user_id)
        if not s:
            return []
        return list(s.positions or [])

    def master_online(self) -> Optional[AgentSession]:
        now = time.time()
        for s in list(self._agents.values()):
            if s.role == "master" and (now - s.last_seen) < 30 and s.ready:
                return s
        return None

    async def send_to_user(self, user_id: int, payload: dict, timeout: float = 2.5) -> dict:
        sess = self._agents.get(user_id)
        if not sess:
            return {"ok": False, "error": "offline"}

        req_id = payload.get("req_id") or str(uuid.uuid4())
        payload = {**payload, "req_id": req_id}
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        sess.pending[req_id] = fut
        try:
            await sess.websocket.send_text(json.dumps(payload))
            return await asyncio.wait_for(fut, timeout=timeout)
        except Exception as e:
            return {"ok": False, "error": str(e), "user_id": user_id}
        finally:
            sess.pending.pop(req_id, None)

    def send_to_user_sync(self, user_id: int, payload: dict, timeout: float = 2.5) -> dict:
        """Thread-safe notify from sync FastAPI routes (Start/Stop Bot)."""
        loop = self._loop
        if loop is None or not loop.is_running():
            return {"ok": False, "error": "no_loop"}
        try:
            fut = asyncio.run_coroutine_threadsafe(
                self.send_to_user(user_id, payload, timeout=timeout),
                loop,
            )
            return fut.result(timeout=timeout + 1.0)
        except Exception as e:
            return {"ok": False, "error": str(e), "user_id": user_id}

    def notify_bot_active(self, user_id: int, bot_active: bool) -> dict:
        return self.send_to_user_sync(
            user_id,
            {"type": "set_bot_active", "bot_active": bool(bot_active)},
            timeout=2.0,
        )

    def notify_force_smoke(self, user_id: int) -> dict:
        """Ask master agent to open one min-lot test trade immediately."""
        result = self.send_to_user_sync(
            user_id,
            {"type": "force_smoke"},
            timeout=4.0,
        )
        # Old agents ignore unknown types (no ACK) → empty TimeoutError.
        # Message was still delivered if agent is online; new code replies.
        if not result.get("ok"):
            err = str(result.get("error") or "")
            online = user_id in self._agents
            if online and (err == "" or "timeout" in err.lower() or "Timeout" in err):
                return {
                    "ok": True,
                    "queued": True,
                    "warn": "no_ack_old_agent_or_slow",
                    "detail": (
                        "Command bhej diya. Agar trade na aaye to VPS pe "
                        "git pull origin main + supervisor restart (code 3.30.10+)."
                    ),
                }
        return result

    def notify_copy_open(
        self,
        user_id: int,
        *,
        symbol: str,
        side: str,
        lot: float = 0.01,
        master_balance: float = 0,
        score: float = 80,
        master_ticket: int = 0,
    ) -> dict:
        """
        Open a market order on the hosted agent via existing copy_open command.
        Works on OLD agents too (they already handle copy_open + ACK).
        """
        ticket = int(master_ticket) or int(time.time() * 1000) % 2_000_000_000
        return self.send_to_user_sync(
            user_id,
            {
                "type": "copy_open",
                "symbol": symbol,
                "side": side.upper(),
                "master_ticket": ticket,
                "master_lot": float(lot),
                "master_balance": float(master_balance or 0),
                "score": float(score),
                "sl": 0,
                "entry": 0,
            },
            timeout=8.0,
        )

    def resolve_response(self, user_id: int, message: dict):
        sess = self._agents.get(user_id)
        if not sess:
            return
        req_id = message.get("req_id")
        if not req_id:
            return
        fut = sess.pending.get(req_id)
        if fut and not fut.done():
            fut.set_result(message)

    async def broadcast(
        self,
        payload: dict,
        *,
        roles: Optional[set[str]] = None,
        exclude_user: Optional[int] = None,
        only_user_ids: Optional[set[int]] = None,
        timeout: float = 2.5,
        require_ready: bool = True,
    ) -> list[dict]:
        """Send the same command to many agents in parallel; gather ACKs."""
        roles = roles or {"follower", "master"}
        now = time.time()
        targets = []
        for s in list(self._agents.values()):
            if s.user_id == exclude_user:
                continue
            if only_user_ids is not None and s.user_id not in only_user_ids:
                continue
            if s.role not in roles:
                continue
            if (now - s.last_seen) > 30:
                continue
            if require_ready and not s.ready:
                continue
            targets.append(s)

        if not targets:
            return []

        req_base = payload.get("req_id") or str(uuid.uuid4())
        t0 = time.perf_counter()

        async def _one(sess: AgentSession):
            body = {**payload, "req_id": f"{req_base}:{sess.user_id}"}
            result = await self.send_to_user(sess.user_id, body, timeout=timeout)
            result.setdefault("user_id", sess.user_id)
            result.setdefault("username", sess.username)
            return result

        results = await asyncio.gather(
            *[_one(s) for s in targets],
            return_exceptions=True,
        )
        out = []
        for r in results:
            if isinstance(r, Exception):
                out.append({"ok": False, "error": str(r)})
            else:
                out.append(r)

        ok_n = sum(1 for r in out if r.get("ok"))
        print(f"[AGENT HUB] broadcast {payload.get('type')} → "
              f"{ok_n}/{len(targets)} in {(time.perf_counter() - t0) * 1000:.0f}ms")
        return out

    def broadcast_sync(self, payload: dict, **kwargs) -> list[dict]:
        """Thread-safe entry for bot / copy_trading threads."""
        if self._loop is None or not self._loop.is_running():
            print("[AGENT HUB] No event loop — broadcast skipped")
            return []
        fut = asyncio.run_coroutine_threadsafe(
            self.broadcast(payload, **kwargs), self._loop
        )
        try:
            return fut.result(timeout=kwargs.get("timeout", 2.5) + 1.0)
        except Exception as e:
            print(f"[AGENT HUB] broadcast_sync error: {e}")
            return []


# Global singleton
agent_hub = AgentHub()
