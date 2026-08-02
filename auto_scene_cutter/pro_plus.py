"""
SceneCut Pro+ helpers

Pro features on top of Stages 1–5:
  - normalized editor settings (quality / transition / burn / gaps)
  - editor project save/load (match_plan + scenes)
  - clip trim + reorder
  - match-plan HTML report
  - background job progress state
"""

from __future__ import annotations

import copy
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import TRANSITION_OPTIONS
from cutting_engine import match_plan_to_cut_plan
from matching_engine import summarize_match_plan
from presets import DEFAULT_QUALITY, QUALITY_PRESETS, list_qualities
from report import generate_html_report

EDITOR_PROJECT_VERSION = 2

DEFAULT_PRO_SETTINGS: dict[str, Any] = {
    "max_clip_duration": 5.0,
    "burn_subs": True,
    "gap_threshold": 6.0,
    "min_duration": 2.0,
    "quality": DEFAULT_QUALITY,
    "transition": "fade",
    "transition_duration": 0.35,
}


def normalize_settings(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Clamp / validate Pro settings for the editor + engines."""
    src = dict(DEFAULT_PRO_SETTINGS)
    if raw:
        src.update(raw)

    quality = str(src.get("quality", DEFAULT_QUALITY)).strip().lower()
    if quality not in QUALITY_PRESETS:
        quality = DEFAULT_QUALITY

    transition = str(src.get("transition", "fade")).strip().lower()
    if transition not in TRANSITION_OPTIONS:
        transition = "fade"

    try:
        tdur = float(src.get("transition_duration", 0.35))
    except (TypeError, ValueError):
        tdur = 0.35
    tdur = max(0.05, min(tdur, 1.5))

    def _f(key: str, default: float, lo: float, hi: float) -> float:
        try:
            val = float(src.get(key, default))
        except (TypeError, ValueError):
            val = default
        return max(lo, min(hi, val))

    return {
        "max_clip_duration": _f("max_clip_duration", 5.0, 0.5, 30.0),
        "burn_subs": bool(src.get("burn_subs", True)),
        "gap_threshold": _f("gap_threshold", 6.0, 0.5, 60.0),
        "min_duration": _f("min_duration", 2.0, 0.2, 30.0),
        "quality": quality,
        "transition": transition,
        "transition_duration": tdur,
    }


def settings_options() -> dict[str, Any]:
    """UI dropdown options."""
    return {
        "qualities": [
            {
                "id": key,
                "label": meta["label"],
                "description": meta["description"],
            }
            for key, meta in QUALITY_PRESETS.items()
        ],
        "transitions": list(TRANSITION_OPTIONS),
        "defaults": dict(DEFAULT_PRO_SETTINGS),
        "quality_keys": list_qualities(),
    }


def build_editor_project(
    name: str,
    session: dict[str, Any],
) -> dict[str, Any]:
    """Build Pro+ project JSON (v2) from editor SESSION."""
    settings = normalize_settings(session.get("settings"))
    match_plan = session.get("last_match_plan") or []
    scenes = session.get("scenes") or []
    return {
        "version": EDITOR_PROJECT_VERSION,
        "name": name or "scenecut_project",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kind": "scenecut_pro_plus",
        "paths": {
            "video": session.get("movie"),
            "movie_srt": session.get("movie_srt"),
            "narration_srt": session.get("narration_srt"),
            "narration_audio": session.get("narration_audio"),
            "final_video": session.get("final_video"),
            "cut_only_video": session.get("cut_only_video"),
            "timeline_srt": session.get("timeline_srt"),
        },
        "settings": settings,
        "scenes": scenes,
        "match_plan": match_plan,
        "stats": summarize_match_plan(match_plan) if match_plan else {},
    }


def save_editor_project(project: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(project, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_editor_project(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Project file nahi mili: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid project JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Project object hona chahiye.")
    if data.get("kind") != "scenecut_pro_plus" and "match_plan" not in data:
        raise ValueError("Yeh SceneCut Pro+ project nahi lagti (match_plan missing).")
    if "match_plan" not in data or not isinstance(data["match_plan"], list):
        raise ValueError("Project mein match_plan list zaroori hai.")
    data["settings"] = normalize_settings(data.get("settings"))
    return data


def trim_match_clip(
    match_plan: list[dict],
    narration_index: int,
    clip_start: float | None = None,
    clip_end: float | None = None,
    delta_start: float = 0.0,
    delta_end: float = 0.0,
) -> list[dict]:
    """
    Manually nudge / set clip in-out for one narration line.

    Bounds stay inside the original clustered scene window when available.
    """
    new_plan = [dict(item) for item in match_plan]
    found = False
    for item in new_plan:
        if int(item.get("narration_index", -1)) != int(narration_index):
            continue
        found = True
        if not item.get("matched"):
            raise ValueError("Skipped clip trim nahi ho sakti — pehle scene assign karo.")

        scene_start = float(item.get("scene_start", item["clip_start"]))
        scene_end = float(item.get("scene_end", item["clip_end"]))
        start = float(item["clip_start"] if clip_start is None else clip_start)
        end = float(item["clip_end"] if clip_end is None else clip_end)
        start += float(delta_start)
        end += float(delta_end)

        start = max(scene_start, min(start, scene_end - 0.2))
        end = min(scene_end, max(end, start + 0.2))

        item["clip_start"] = round(start, 3)
        item["clip_end"] = round(end, 3)
        item["clip_duration"] = round(end - start, 3)
        item["trimmed"] = (end - start) < (scene_end - scene_start) - 0.01
        break

    if not found:
        raise ValueError(f"Narration index {narration_index} nahi mili.")
    return new_plan


def reorder_match_plan(
    match_plan: list[dict],
    narration_order: list[int],
) -> list[dict]:
    """
    Reorder match_plan rows by narration_index list.
    Any missing indexes are appended in original order.
    """
    by_idx = {int(m["narration_index"]): dict(m) for m in match_plan}
    ordered: list[dict] = []
    seen: set[int] = set()
    for idx in narration_order:
        key = int(idx)
        if key in by_idx and key not in seen:
            ordered.append(by_idx[key])
            seen.add(key)
    for m in match_plan:
        key = int(m["narration_index"])
        if key not in seen:
            ordered.append(dict(m))
            seen.add(key)
    return ordered


def match_plan_to_report_project(
    name: str,
    video_path: str | Path | None,
    match_plan: list[dict],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Adapt match_plan → report.py's cut_plan-shaped project."""
    cut_plan = []
    for item in match_plan:
        cut_plan.append(
            {
                "narration_index": item.get("narration_index"),
                "narration_text": item.get("narration_text"),
                "matched": bool(item.get("matched")),
                "movie_start": item.get("clip_start"),
                "movie_end": item.get("clip_end"),
                "movie_index": item.get("scene_id"),
                "movie_text": item.get("scene_text"),
                "score": item.get("score", 0),
            }
        )
    return {
        "name": name,
        "paths": {"video": str(video_path) if video_path else None},
        "settings": normalize_settings(settings),
        "cut_plan": cut_plan,
        "stats": summarize_match_plan(match_plan),
    }


def generate_match_plan_report(
    name: str,
    video_path: str | Path | None,
    match_plan: list[dict],
    output_html: str | Path,
    settings: dict[str, Any] | None = None,
    final_video_path: str | Path | None = None,
) -> Path:
    """HTML report with thumbnails for the current match plan."""
    project = match_plan_to_report_project(name, video_path, match_plan, settings)
    return generate_html_report(
        project,
        output_html,
        thumbs_dir=Path(output_html).parent / "thumbs",
        final_video_path=final_video_path,
    )


class JobProgress:
    """Thread-safe job progress for Pro+ live status polling."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "job_id": 0,
            "status": "idle",  # idle|running|done|error
            "stage": None,
            "message": "",
            "current": 0,
            "total": 0,
            "percent": 0,
            "error": None,
            "result": None,
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)

    def start(self, total_stages: int = 5) -> int:
        with self._lock:
            self._state["job_id"] = int(self._state["job_id"]) + 1
            self._state.update(
                {
                    "status": "running",
                    "stage": "starting",
                    "message": "Job start",
                    "current": 0,
                    "total": total_stages,
                    "percent": 0,
                    "error": None,
                    "result": None,
                }
            )
            return int(self._state["job_id"])

    def update(
        self,
        stage: str | None = None,
        message: str = "",
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        with self._lock:
            if stage is not None:
                self._state["stage"] = stage
            if message:
                self._state["message"] = message
            if current is not None:
                self._state["current"] = current
            if total is not None:
                self._state["total"] = total
            tot = int(self._state["total"] or 0)
            cur = int(self._state["current"] or 0)
            self._state["percent"] = int(min(100, (cur / tot) * 100)) if tot else 0

    def callback(self, message: str, current: int, total: int) -> None:
        """ProgressLogger-compatible callback."""
        self.update(message=message, current=current, total=total)

    def finish(self, result: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._state["status"] = "done"
            self._state["percent"] = 100
            self._state["message"] = "Done"
            self._state["result"] = result

    def fail(self, error: str) -> None:
        with self._lock:
            self._state["status"] = "error"
            self._state["error"] = error
            self._state["message"] = error


def cut_plan_count(match_plan: list[dict]) -> int:
    """How many ffmpeg segments a match_plan will produce."""
    return len(match_plan_to_cut_plan(match_plan))
