"""
In-memory command queue for MT5 Expert Advisors (followers).

Master trade → enqueue copy_open/copy_close → EA polls /ea/poll every ~1s.
No Python agent on user PC — only Exness MT5 + this EA.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Optional


class EaQueue:
    def __init__(self):
        self._lock = threading.Lock()
        # user_id -> list[dict]
        self._q: dict[int, list[dict]] = {}
        # user_id -> last hello/poll timestamp
        self._seen: dict[int, float] = {}
        # user_id -> last account snapshot from EA
        self._snap: dict[int, dict] = {}

    def touch(self, user_id: int, snap: Optional[dict] = None):
        with self._lock:
            self._seen[user_id] = time.time()
            if snap:
                self._snap[user_id] = snap

    def is_online(self, user_id: int, max_age: float = 45.0) -> bool:
        with self._lock:
            t = self._seen.get(user_id)
            if not t:
                return False
            return (time.time() - t) <= max_age

    def online_user_ids(self, max_age: float = 45.0) -> set[int]:
        now = time.time()
        with self._lock:
            return {uid for uid, t in self._seen.items() if (now - t) <= max_age}

    def snapshot(self, user_id: int) -> dict:
        with self._lock:
            return dict(self._snap.get(user_id) or {})

    def enqueue(self, user_ids: set[int] | list[int], cmd: dict) -> int:
        """Fan-out one command to many users. Returns how many queued."""
        body = dict(cmd)
        body.setdefault("id", str(uuid.uuid4()))
        body.setdefault("ts", time.time())
        n = 0
        with self._lock:
            for uid in user_ids:
                q = self._q.setdefault(int(uid), [])
                # de-dupe copy_open by master_ticket
                if body.get("type") == "copy_open":
                    mt = body.get("master_ticket")
                    if mt and any(
                        x.get("type") == "copy_open" and x.get("master_ticket") == mt
                        for x in q
                    ):
                        continue
                q.append(dict(body))
                # cap queue
                if len(q) > 40:
                    del q[:-40]
                n += 1
        return n

    def poll(self, user_id: int, limit: int = 5) -> list[dict]:
        with self._lock:
            q = self._q.get(int(user_id), [])
            if not q:
                return []
            out = q[:limit]
            self._q[int(user_id)] = q[limit:]
            return out

    def peek_count(self, user_id: int) -> int:
        with self._lock:
            return len(self._q.get(int(user_id), []))


ea_queue = EaQueue()
