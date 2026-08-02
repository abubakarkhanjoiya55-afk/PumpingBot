"""
Config Module (Stage 8)

Default settings ek JSON file se aati hain taake har baar
quality / transition dubara type na karna pade.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from presets import DEFAULT_QUALITY, QUALITY_PRESETS

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.json"

TRANSITION_OPTIONS = ("none", "fade")

DEFAULT_CONFIG: dict[str, Any] = {
    "quality": DEFAULT_QUALITY,
    "transition": "fade",
    "transition_duration": 0.35,
    "sync_to_narration": True,
    "burn_subs": True,
}


def _normalize(config: dict[str, Any]) -> dict[str, Any]:
    """Unknown / invalid values ko safe defaults pe lao."""
    merged = dict(DEFAULT_CONFIG)
    merged.update(config or {})

    quality = str(merged.get("quality", DEFAULT_QUALITY)).strip().lower()
    if quality not in QUALITY_PRESETS:
        quality = DEFAULT_QUALITY
    merged["quality"] = quality

    transition = str(merged.get("transition", "fade")).strip().lower()
    if transition not in TRANSITION_OPTIONS:
        transition = "fade"
    merged["transition"] = transition

    try:
        dur = float(merged.get("transition_duration", 0.35))
    except (TypeError, ValueError):
        dur = 0.35
    # Keep fades short so tiny clips na toot jayein
    merged["transition_duration"] = max(0.05, min(dur, 1.5))

    merged["sync_to_narration"] = bool(merged.get("sync_to_narration", True))
    merged["burn_subs"] = bool(merged.get("burn_subs", True))
    return merged


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """
    config.json padho. File na mile to defaults return.
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return dict(DEFAULT_CONFIG)

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)

    if not isinstance(data, dict):
        return dict(DEFAULT_CONFIG)
    return _normalize(data)


def save_config(config: dict[str, Any], path: str | Path | None = None) -> Path:
    """Normalized config ko disk pe save karo."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    normalized = _normalize(config)
    config_path.write_text(
        json.dumps(normalized, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return config_path


def ensure_default_config(path: str | Path | None = None) -> Path:
    """Agar config.json missing hai to defaults likh do."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        save_config(DEFAULT_CONFIG, config_path)
    return config_path
