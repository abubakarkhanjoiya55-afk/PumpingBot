"""
Progress helpers (Stage 8)

Lamba ffmpeg kaam chal raha ho to terminal/UI ko
simple step messages dikhate hain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable


ProgressCallback = Callable[[str, int, int], None]


@dataclass
class ProgressLogger:
    """
    Simple step counter.

    Example:
      p = ProgressLogger(total=5)
      p.step("Cutting segment 1")
    """

    total: int
    label: str = "Progress"
    callback: ProgressCallback | None = None
    current: int = 0
    history: list[str] = field(default_factory=list)

    def step(self, message: str) -> str:
        self.current += 1
        if self.total > 0:
            line = f"[{self.label} {self.current}/{self.total}] {message}"
        else:
            line = f"[{self.label}] {message}"
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        full = f"{stamp} {line}"
        self.history.append(full)
        print(full)
        if self.callback:
            self.callback(message, self.current, self.total)
        return full


def make_print_callback(prefix: str = "") -> ProgressCallback:
    """Optional extra callback (mostly for tests / UI hooks)."""

    def _cb(message: str, current: int, total: int) -> None:
        if prefix:
            print(f"{prefix}{current}/{total}: {message}")

    return _cb
