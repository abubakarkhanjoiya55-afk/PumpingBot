"""Tests for agent hub fan-out (no MetaAPI / no MT5 required)."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from agent_hub import AgentHub, AgentSession


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.closed = False

    async def send_text(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True


class TestAgentHub(unittest.TestCase):
    def test_broadcast_parallel_acks(self):
        async def run():
            hub = AgentHub()
            loop = asyncio.get_running_loop()
            hub.bind_loop(loop)

            agents = []
            for i in range(5):
                ws = FakeWebSocket()
                sess = AgentSession(
                    user_id=100 + i,
                    username=f"u{i}",
                    role="follower",
                    websocket=ws,
                    ready=True,
                )
                await hub.register(sess)
                agents.append(sess)

            async def auto_ack():
                # Simulate agents ACKing shortly after send
                await asyncio.sleep(0.01)
                for sess in agents:
                    for req_id in list(sess.pending.keys()):
                        hub.resolve_response(sess.user_id, {
                            "type": "ack",
                            "req_id": req_id,
                            "ok": True,
                            "ticket": 1000 + sess.user_id,
                        })

            asyncio.create_task(auto_ack())
            results = await hub.broadcast(
                {"type": "copy_open", "symbol": "XAUUSDm", "side": "BUY"},
                roles={"follower"},
                timeout=1.0,
            )
            self.assertEqual(len(results), 5)
            self.assertTrue(all(r.get("ok") for r in results))

        asyncio.run(run())

    def test_offline_send(self):
        async def run():
            hub = AgentHub()
            r = await hub.send_to_user(999, {"type": "ping"})
            self.assertFalse(r.get("ok"))
            self.assertEqual(r.get("error"), "offline")

        asyncio.run(run())

    def test_list_and_master(self):
        async def run():
            hub = AgentHub()
            ws = FakeWebSocket()
            await hub.register(AgentSession(
                user_id=1, username="admin", role="master",
                websocket=ws, ready=True, balance=1000,
            ))
            await hub.register(AgentSession(
                user_id=2, username="bob", role="follower",
                websocket=FakeWebSocket(), ready=True,
            ))
            self.assertIsNotNone(hub.master_online())
            self.assertEqual(len(hub.online_followers()), 1)
            self.assertEqual(len(hub.list_agents()), 2)

        asyncio.run(run())


class TestCopyTradingAgentFlag(unittest.TestCase):
    def test_agent_mode_default(self):
        import copy_trading as ct
        self.assertTrue(hasattr(ct, "agent_mode_enabled"))
        self.assertTrue(callable(ct.fanout_open_via_agents))
        self.assertTrue(callable(ct.fanout_close_via_agents))


if __name__ == "__main__":
    unittest.main()
