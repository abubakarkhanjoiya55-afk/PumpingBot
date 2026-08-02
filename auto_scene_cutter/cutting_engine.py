"""
Cutting Engine (Stage 4)

Pipeline:
  Stage 1 — parse SRTs
  Stage 2 — cluster movie subtitles into scenes
  Stage 3 — match narration → scenes + trim (max 5s)
  Stage 4 — ffmpeg se matched clips cut karke ek video join

Yeh module Stage 3 ke match_plan (clip_start/clip_end) ko use karta hai.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from matching_engine import run_stage1_to_stage3, summarize_match_plan
from presets import DEFAULT_QUALITY
from progress import ProgressLogger
from video_cutter import create_sample_video, cut_video_from_plan, ensure_ffmpeg


def match_plan_to_cut_plan(match_plan: list[dict]) -> list[dict]:
    """
    Stage 3 match_plan → format that cut_video_from_plan() understands.

    cut_video_from_plan expects:
      matched, movie_start, movie_end
    """
    cut_plan: list[dict] = []
    for item in match_plan:
        if not item.get("matched"):
            continue
        if item.get("clip_start") is None or item.get("clip_end") is None:
            continue
        start = float(item["clip_start"])
        end = float(item["clip_end"])
        if end <= start:
            continue

        cut_plan.append(
            {
                "matched": True,
                "movie_start": start,
                "movie_end": end,
                "narration_index": item.get("narration_index"),
                "narration_text": item.get("narration_text"),
                "scene_id": item.get("scene_id"),
                "score": item.get("score"),
            }
        )
    return cut_plan


def cut_from_match_plan(
    video_path: str | Path,
    match_plan: list[dict],
    output_path: str | Path,
    quality: str = "fast",
    transition: str = "none",
    transition_duration: float = 0.25,
    progress: ProgressLogger | None = None,
) -> Path:
    """
    Stage 3 match_plan se actual video cut + join.
    """
    ensure_ffmpeg()
    cut_plan = match_plan_to_cut_plan(match_plan)
    if not cut_plan:
        raise ValueError(
            "Match plan mein koi valid matched clip nahi — cutting nahi ho sakti."
        )

    return cut_video_from_plan(
        video_path=video_path,
        cut_plan=cut_plan,
        output_path=output_path,
        quality=quality or DEFAULT_QUALITY,
        transition=transition,
        transition_duration=transition_duration,
        progress=progress,
    )


def run_stage1_to_stage4(
    video_path: str | Path,
    movie_srt_path: str,
    narration_srt_path: str,
    output_path: str | Path,
    gap_threshold: float = 6.0,
    min_scene_duration: float = 2.0,
    max_clip_duration: float = 5.0,
    min_score: float = 0.12,
    quality: str = "fast",
    transition: str = "none",
) -> dict:
    """
    Full backend engine (no UI):
      parse → cluster → match → cut/join
    """
    stage3 = run_stage1_to_stage3(
        movie_srt_path=movie_srt_path,
        narration_srt_path=narration_srt_path,
        gap_threshold=gap_threshold,
        min_scene_duration=min_scene_duration,
        max_clip_duration=max_clip_duration,
        min_score=min_score,
    )

    matched_count = stage3["stats"]["matched"]
    # segments + concat
    logger = ProgressLogger(total=matched_count + 1, label="Stage4")

    output = cut_from_match_plan(
        video_path=video_path,
        match_plan=stage3["match_plan"],
        output_path=output_path,
        quality=quality,
        transition=transition,
        progress=logger,
    )

    return {
        **stage3,
        "output_video": str(output),
        "cut_clip_count": matched_count,
        "quality": quality,
        "transition": transition,
    }


def save_match_plan_json(match_plan: list[dict], path: str | Path) -> Path:
    """Debug/inspect ke liye match plan JSON save."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(match_plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main() -> None:
    """
    CLI:

      python cutting_engine.py --sample
      python cutting_engine.py <movie.mp4> <movie.srt> <narration.srt> [output.mp4]
                               [--max-clip 5.0] [--quality fast] [--transition none|fade]
    """
    args = sys.argv[1:]
    base = Path(__file__).resolve().parent

    try:
        if args and args[0] == "--sample":
            video = base / "sample_movie.mp4"
            movie_srt = base / "sample_movie_cluster.srt"
            narration_srt = base / "sample_narration.srt"
            output = base / "output" / "stage4_sample_cut.mp4"
            plan_json = base / "output" / "stage4_match_plan.json"

            # Cluster sample timestamps 50s+ tak jaate hain — video utni lambi chahiye
            print("Sample movie bana raha hoon (60s)...")
            create_sample_video(video, duration_seconds=60.0)

            print("Stage 1→4 chal raha hai...")
            result = run_stage1_to_stage4(
                video_path=video,
                movie_srt_path=str(movie_srt),
                narration_srt_path=str(narration_srt),
                output_path=output,
                max_clip_duration=5.0,
                quality="fast",
                transition="none",
            )
            save_match_plan_json(result["match_plan"], plan_json)

            stats = summarize_match_plan(result["match_plan"])
            print("\n=== Stage 4 Done ===")
            print(f"Scenes clustered: {len(result['scenes'])}")
            print(
                f"Matched clips: {stats['matched']}/{stats['total_narration_lines']} "
                f"(avg {stats['avg_clip_duration']:.2f}s)"
            )
            print(f"Output video: {result['output_video']}")
            print(f"Match plan JSON: {plan_json}")
            return

        if len(args) < 3:
            print(
                "Usage:\n"
                "  python cutting_engine.py --sample\n"
                "  python cutting_engine.py <movie.mp4> <movie.srt> <narration.srt> "
                "[output.mp4] [--max-clip 5] [--quality fast] [--transition none|fade]"
            )
            sys.exit(1)

        video = args[0]
        movie_srt = args[1]
        narration_srt = args[2]
        rest = args[3:]

        output = "output_stage4_cut.mp4"
        max_clip = 5.0
        quality = "fast"
        transition = "none"

        i = 0
        if rest and not rest[0].startswith("--"):
            output = rest[0]
            i = 1
        while i < len(rest):
            if rest[i] == "--max-clip" and i + 1 < len(rest):
                max_clip = float(rest[i + 1])
                i += 2
            elif rest[i] == "--quality" and i + 1 < len(rest):
                quality = rest[i + 1]
                i += 2
            elif rest[i] == "--transition" and i + 1 < len(rest):
                transition = rest[i + 1]
                i += 2
            else:
                print(f"Unknown arg: {rest[i]}")
                sys.exit(1)

        result = run_stage1_to_stage4(
            video_path=video,
            movie_srt_path=movie_srt,
            narration_srt_path=narration_srt,
            output_path=output,
            max_clip_duration=max_clip,
            quality=quality,
            transition=transition,
        )
        stats = summarize_match_plan(result["match_plan"])
        print(
            f"Matched clips: {stats['matched']}/{stats['total_narration_lines']} | "
            f"Output: {result['output_video']}"
        )

    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
