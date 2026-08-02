"""
Render quality presets (Stage 6).

ffmpeg x264 settings — simple names so beginners easily choose:
  - fast: jaldi banega, file thodi badi / quality ordinary
  - balanced: daily use (default)
  - high: slow encode, better quality
"""

from __future__ import annotations

QUALITY_PRESETS: dict[str, dict[str, str]] = {
    "fast": {
        "label": "Fast",
        "preset": "ultrafast",
        "crf": "28",
        "description": "Jaldi test ke liye",
    },
    "balanced": {
        "label": "Balanced",
        "preset": "veryfast",
        "crf": "23",
        "description": "Normal daily use (default)",
    },
    "high": {
        "label": "High",
        "preset": "medium",
        "crf": "18",
        "description": "Behtar quality, slow encode",
    },
}

DEFAULT_QUALITY = "balanced"


def get_quality_settings(quality: str | None) -> dict[str, str]:
    """
    Return ffmpeg settings for a quality name.
    Unknown names fall back to balanced.
    """
    key = (quality or DEFAULT_QUALITY).strip().lower()
    if key not in QUALITY_PRESETS:
        key = DEFAULT_QUALITY
    return dict(QUALITY_PRESETS[key])


def list_qualities() -> list[str]:
    """Available quality keys."""
    return list(QUALITY_PRESETS.keys())
