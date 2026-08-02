"""
Project Module (Stage 5)

Stage 4 tak auto render ho jata tha.
Stage 5 mein hum cut plan ko project JSON ki tarah save/load karte hain,
editor se timings fix karte hain, phir bina dubara match kiye render karte hain.

Project JSON roughly aisa dikhta hai:
{
  "version": 1,
  "name": "my_cut",
  "paths": { "video": "...", "movie_srt": "...", "narration_srt": "...", "narration_audio": "..." },
  "settings": { "sync_to_narration": true, "burn_subs": true },
  "cut_plan": [ ... Stage 2/4 items ... ]
}
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from final_render import (
    create_sample_narration_audio,
    render_final,
    render_from_cut_plan,
    sync_cut_plan_to_narration,
)
from scene_matcher import match_scenes, summarize_cut_plan
from srt_parser import parse_narration_srt, parse_srt
from video_cutter import create_sample_video

PROJECT_VERSION = 1


def build_project(
    name: str,
    video_path: str | Path,
    movie_srt_path: str | Path,
    narration_srt_path: str | Path,
    cut_plan: list[dict],
    narration_audio_path: str | Path | None = None,
    sync_to_narration: bool = True,
    burn_subs: bool = True,
) -> dict[str, Any]:
    """Create an in-memory project dictionary."""
    return {
        "version": PROJECT_VERSION,
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "paths": {
            "video": str(Path(video_path).resolve()),
            "movie_srt": str(Path(movie_srt_path).resolve()),
            "narration_srt": str(Path(narration_srt_path).resolve()),
            "narration_audio": (
                str(Path(narration_audio_path).resolve())
                if narration_audio_path
                else None
            ),
        },
        "settings": {
            "sync_to_narration": bool(sync_to_narration),
            "burn_subs": bool(burn_subs),
        },
        "cut_plan": cut_plan,
        "stats": summarize_cut_plan(cut_plan),
    }


def save_project(project: dict[str, Any], project_path: str | Path) -> Path:
    """Save project dict as pretty JSON."""
    project_path = Path(project_path)
    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text(
        json.dumps(project, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return project_path


def load_project(project_path: str | Path) -> dict[str, Any]:
    """Load and lightly validate a project JSON file."""
    project_path = Path(project_path)
    if not project_path.exists():
        raise FileNotFoundError(f"Project file nahi mili: {project_path}")

    try:
        data = json.loads(project_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Project JSON invalid hai: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Project JSON object hona chahiye.")
    if "cut_plan" not in data or not isinstance(data["cut_plan"], list):
        raise ValueError("Project mein 'cut_plan' list zaroori hai.")
    if "paths" not in data or not isinstance(data["paths"], dict):
        raise ValueError("Project mein 'paths' object zaroori hai.")
    if not data["paths"].get("video"):
        raise ValueError("Project paths.video missing hai.")

    data.setdefault("version", PROJECT_VERSION)
    data.setdefault("name", project_path.stem)
    data.setdefault("settings", {"sync_to_narration": True, "burn_subs": True})
    data["stats"] = summarize_cut_plan(data["cut_plan"])
    return data


def apply_cut_plan_edits(
    cut_plan: list[dict],
    edits: list[dict],
) -> list[dict]:
    """
    Editor se aayi hui values cut plan pe apply karo.

    Har edit item roughly:
      {
        "narration_index": 1,
        "matched": true/false,
        "movie_start": 1.2,
        "movie_end": 3.5,
      }
    """
    by_index = {int(item["narration_index"]): dict(item) for item in cut_plan}

    for edit in edits:
        idx = int(edit["narration_index"])
        if idx not in by_index:
            continue

        row = by_index[idx]
        matched = bool(edit.get("matched", row.get("matched", False)))
        row["matched"] = matched

        if matched:
            start = float(edit["movie_start"])
            end = float(edit["movie_end"])
            if end <= start:
                raise ValueError(
                    f"Narration [{idx}] invalid timing: end ({end}) start ({start}) se bara hona chahiye."
                )
            row["movie_start"] = round(start, 3)
            row["movie_end"] = round(end, 3)
            row["target_duration"] = round(end - start, 3)
            # Keep text fields if present; editor may not send them
            if edit.get("movie_text"):
                row["movie_text"] = edit["movie_text"]
            if edit.get("movie_index") is not None:
                row["movie_index"] = edit["movie_index"]
        else:
            row["movie_index"] = None
            row["movie_text"] = None
            row["movie_start"] = None
            row["movie_end"] = None
            row["score"] = 0.0
            row["target_duration"] = None
            row["synced_to_narration"] = False

        by_index[idx] = row

    # Preserve original order
    return [by_index[int(item["narration_index"])] for item in cut_plan]


def create_project_from_sources(
    name: str,
    video_path: str | Path,
    movie_srt_path: str | Path,
    narration_srt_path: str | Path,
    narration_audio_path: str | Path | None = None,
    sync_to_narration: bool = True,
    burn_subs: bool = True,
) -> dict[str, Any]:
    """
    Stage 1+2 (+ optional sync) chala ke naya project banao.
    Video abhi cut nahi hoti — sirf plan save hota hai.
    """
    movie_entries = parse_srt(str(movie_srt_path))
    narration_entries = parse_narration_srt(str(narration_srt_path))
    cut_plan = match_scenes(movie_entries, narration_entries)
    if sync_to_narration:
        cut_plan = sync_cut_plan_to_narration(cut_plan)

    return build_project(
        name=name,
        video_path=video_path,
        movie_srt_path=movie_srt_path,
        narration_srt_path=narration_srt_path,
        cut_plan=cut_plan,
        narration_audio_path=narration_audio_path,
        sync_to_narration=sync_to_narration,
        burn_subs=burn_subs,
    )


def render_project(
    project: dict[str, Any],
    output_path: str | Path,
) -> tuple[Path, dict]:
    """
    Saved/edited cut plan se final video banao (no re-match).
    """
    paths = project["paths"]
    settings = project.get("settings", {})
    video = paths.get("video")
    audio = paths.get("narration_audio")

    if not video or not Path(video).exists():
        raise FileNotFoundError(f"Project video missing/not found: {video}")

    if audio and not Path(audio).exists():
        # Audio optional — missing ho to skip, crash nahi
        audio = None

    result, info = render_from_cut_plan(
        video_path=video,
        cut_plan=project["cut_plan"],
        output_path=output_path,
        narration_audio_path=audio,
        burn_subs=bool(settings.get("burn_subs", True)),
    )
    info["project_name"] = project.get("name")
    info["sync_to_narration"] = bool(settings.get("sync_to_narration", True))
    return result, info


def main() -> None:
    """
    CLI helper.

    Usage:
      python project.py --sample
      python project.py create <video> <movie.srt> <narration.srt> <project.json> [--audio file]
      python project.py render <project.json> [output.mp4]
    """
    args = sys.argv[1:]
    base = Path(__file__).resolve().parent

    try:
        if not args:
            print(
                "Usage:\n"
                "  python project.py --sample\n"
                "  python project.py create <video> <movie.srt> <narration.srt> <project.json> [--audio file]\n"
                "  python project.py render <project.json> [output.mp4]"
            )
            sys.exit(1)

        if args[0] == "--sample":
            video = base / "sample_movie.mp4"
            audio = base / "sample_narration.m4a"
            movie_srt = base / "sample_movie.srt"
            narration_srt = base / "sample_narration.srt"
            project_path = base / "output" / "sample_project.json"
            output_video = base / "output" / "sample_project_final.mp4"

            print("Sample media bana raha hoon...")
            create_sample_video(video, duration_seconds=20.0)
            narration_entries = parse_narration_srt(str(narration_srt))
            create_sample_narration_audio(narration_entries, audio)

            print("Project create + save...")
            project = create_project_from_sources(
                name="sample_project",
                video_path=video,
                movie_srt_path=movie_srt,
                narration_srt_path=narration_srt,
                narration_audio_path=audio,
                sync_to_narration=True,
                burn_subs=True,
            )
            save_project(project, project_path)
            print(f"Project saved: {project_path}")

            # Demo edit: pehli clip ko thoda short kar do
            edits = [
                {
                    "narration_index": project["cut_plan"][0]["narration_index"],
                    "matched": True,
                    "movie_start": project["cut_plan"][0]["movie_start"],
                    "movie_end": round(
                        float(project["cut_plan"][0]["movie_start"]) + 1.5,
                        3,
                    ),
                }
            ]
            project["cut_plan"] = apply_cut_plan_edits(project["cut_plan"], edits)
            project["stats"] = summarize_cut_plan(project["cut_plan"])
            save_project(project, project_path)
            print("Demo edit apply ho gaya (first clip -> 1.5s).")

            print("Edited project se render...")
            result, info = render_project(project, output_video)
            print(f"Info: {info}")
            print(f"Output: {result}")
            return

        if args[0] == "create":
            if len(args) < 5:
                print(
                    "Usage: python project.py create <video> <movie.srt> "
                    "<narration.srt> <project.json> [--audio file]"
                )
                sys.exit(1)
            video, movie_srt, narration_srt, project_path = args[1:5]
            audio = None
            if len(args) >= 7 and args[5] == "--audio":
                audio = args[6]

            project = create_project_from_sources(
                name=Path(project_path).stem,
                video_path=video,
                movie_srt_path=movie_srt,
                narration_srt_path=narration_srt,
                narration_audio_path=audio,
            )
            save_project(project, project_path)
            print(f"Project saved: {project_path}")
            print(f"Stats: {project['stats']}")
            return

        if args[0] == "render":
            if len(args) < 2:
                print("Usage: python project.py render <project.json> [output.mp4]")
                sys.exit(1)
            project_path = args[1]
            output = args[2] if len(args) >= 3 else "output_from_project.mp4"
            project = load_project(project_path)
            result, info = render_project(project, output)
            print(f"Info: {info}")
            print(f"Output: {result}")
            return

        print(f"Unknown command: {args[0]}")
        sys.exit(1)

    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
