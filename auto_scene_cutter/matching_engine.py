"""
Matching Engine (Stage 3)

Pipeline so far:
  Stage 1 — parse movie SRT + narration SRT
  Stage 2 — cluster movie subtitles into scenes
  Stage 3 — match each narration line to the best movie scene,
             then trim that scene to a short clip (default max 5s)

Output is a "match plan" that Stage 4 (cutting) can feed into ffmpeg.

Note: This is intentionally a simple keyword/text matcher (no heavy AI model).
It is good enough to wire the engine end-to-end and tune later.
"""

from __future__ import annotations

import sys

from scene_clustering import cluster_movie_scenes, merge_short_scenes
from scene_matcher import similarity_score
from srt_parser import parse_narration_srt, parse_srt


def narration_duration(narration_entry: dict) -> float:
    """How long this narration line lasts (seconds)."""
    return max(0.0, float(narration_entry["end"]) - float(narration_entry["start"]))


def scene_duration(scene: dict) -> float:
    """Full clustered scene length (seconds)."""
    return max(0.0, float(scene["end"]) - float(scene["start"]))


def trim_scene_to_clip(
    scene: dict,
    target_duration: float,
    max_clip_duration: float = 5.0,
) -> dict:
    """
    Cut a short usable window out of a longer clustered scene.

    Rules (simple + predictable):
      1) clip length = min(target_duration, max_clip_duration, full scene length)
      2) window starts at the scene start (dialogue usually begins there)

    Example:
      scene = 20.0 -> 36.0 (16s long)
      target_duration = 3.0
      max_clip_duration = 5.0
      => clip 20.0 -> 23.0
    """
    full = scene_duration(scene)
    if full <= 0:
        raise ValueError(f"Scene {scene.get('scene_id')} has invalid duration.")

    # Never exceed max clip length (UI: "Cutting Scenes Max 5s")
    clip_len = min(float(target_duration), float(max_clip_duration), full)
    # Keep a tiny minimum so ffmpeg later doesn't get 0-length cuts
    clip_len = max(0.2, clip_len)

    clip_start = float(scene["start"])
    clip_end = clip_start + clip_len

    # Safety: don't pass the real scene end due to float noise
    clip_end = min(clip_end, float(scene["end"]))

    return {
        "scene_id": scene["scene_id"],
        "scene_start": float(scene["start"]),
        "scene_end": float(scene["end"]),
        "clip_start": round(clip_start, 3),
        "clip_end": round(clip_end, 3),
        "clip_duration": round(clip_end - clip_start, 3),
        "original_scene_duration": round(full, 3),
        "trimmed": clip_len < full,
        "scene_text": scene.get("combined_text", ""),
    }


def find_best_scene_for_narration(
    narration_entry: dict,
    scenes: list[dict],
    used_scene_ids: set[int] | None = None,
    min_score: float = 0.12,
    prefer_unused: bool = True,
) -> tuple[dict | None, float, bool]:
    """
    Find the best clustered scene for one narration line.

    Returns:
      (scene_dict_or_None, score, reused_flag)
    """
    used_scene_ids = used_scene_ids or set()
    narr_text = narration_entry.get("text", "")

    best_unused = None
    best_unused_score = -1.0
    best_any = None
    best_any_score = -1.0

    for scene in scenes:
        score = similarity_score(narr_text, scene.get("combined_text", ""))
        sid = int(scene["scene_id"])

        if score > best_any_score:
            best_any_score = score
            best_any = scene

        if sid not in used_scene_ids and score > best_unused_score:
            best_unused_score = score
            best_unused = scene

    if prefer_unused and best_unused is not None and best_unused_score >= min_score:
        return best_unused, round(best_unused_score, 3), False

    if best_any is not None and best_any_score >= min_score:
        reused = int(best_any["scene_id"]) in used_scene_ids
        return best_any, round(best_any_score, 3), reused

    return None, 0.0, False


def match_narration_to_scenes(
    scenes: list[dict],
    narration_entries: list[dict],
    max_clip_duration: float = 5.0,
    min_score: float = 0.12,
    prefer_unused: bool = True,
) -> list[dict]:
    """
    Match every narration line to a movie scene and build clip windows.

    Returns a list of match items:
    {
      "narration_index": 1,
      "narration_text": "...",
      "narration_start": 0.5,
      "narration_end": 3.0,
      "narration_duration": 2.5,
      "matched": True,
      "score": 0.55,
      "reused_scene": False,
      "scene_id": 2,
      "clip_start": 20.0,   # where to cut in the movie
      "clip_end": 23.0,
      "clip_duration": 3.0,
      "original_scene_duration": 16.0,
      "trimmed": True,
      "scene_text": "...",
    }
    """
    if not scenes:
        raise ValueError("Scenes list empty hai — pehle Stage 2 clustering chalao.")
    if not narration_entries:
        raise ValueError("Narration entries empty hain — matching nahi ho sakti.")

    used_scene_ids: set[int] = set()
    plan: list[dict] = []

    for narr in narration_entries:
        narr_dur = narration_duration(narr)
        scene, score, reused = find_best_scene_for_narration(
            narr,
            scenes,
            used_scene_ids=used_scene_ids,
            min_score=min_score,
            prefer_unused=prefer_unused,
        )

        if scene is None:
            plan.append(
                {
                    "narration_index": narr["index"],
                    "narration_text": narr["text"],
                    "narration_start": narr["start"],
                    "narration_end": narr["end"],
                    "narration_duration": round(narr_dur, 3),
                    "matched": False,
                    "score": 0.0,
                    "reused_scene": False,
                    "scene_id": None,
                    "clip_start": None,
                    "clip_end": None,
                    "clip_duration": None,
                    "original_scene_duration": None,
                    "trimmed": False,
                    "scene_text": None,
                }
            )
            continue

        # Target clip length follows narration timing, but never above max_clip_duration
        target = narr_dur if narr_dur > 0 else max_clip_duration
        clip = trim_scene_to_clip(
            scene,
            target_duration=target,
            max_clip_duration=max_clip_duration,
        )

        used_scene_ids.add(int(scene["scene_id"]))

        plan.append(
            {
                "narration_index": narr["index"],
                "narration_text": narr["text"],
                "narration_start": narr["start"],
                "narration_end": narr["end"],
                "narration_duration": round(narr_dur, 3),
                "matched": True,
                "score": score,
                "reused_scene": reused,
                **clip,
            }
        )

    return plan


def summarize_match_plan(match_plan: list[dict]) -> dict:
    """Simple stats for CLI / later UI."""
    matched = [m for m in match_plan if m.get("matched")]
    return {
        "total_narration_lines": len(match_plan),
        "matched": len(matched),
        "unmatched": len(match_plan) - len(matched),
        "reused_scenes": sum(1 for m in matched if m.get("reused_scene")),
        "avg_clip_duration": (
            round(
                sum(float(m["clip_duration"]) for m in matched) / len(matched),
                3,
            )
            if matched
            else 0.0
        ),
    }


def run_stage1_to_stage3(
    movie_srt_path: str,
    narration_srt_path: str,
    gap_threshold: float = 6.0,
    min_scene_duration: float = 2.0,
    max_clip_duration: float = 5.0,
    min_score: float = 0.12,
) -> dict:
    """
    Full backend chain for now:
      parse → cluster → merge short → match + trim
    """
    movie_entries = parse_srt(movie_srt_path)
    narration_entries = parse_narration_srt(narration_srt_path)

    scenes = cluster_movie_scenes(movie_entries, gap_threshold=gap_threshold)
    scenes = merge_short_scenes(scenes, min_duration=min_scene_duration)

    match_plan = match_narration_to_scenes(
        scenes,
        narration_entries,
        max_clip_duration=max_clip_duration,
        min_score=min_score,
    )

    return {
        "movie_subtitle_count": len(movie_entries),
        "narration_count": len(narration_entries),
        "scenes": scenes,
        "match_plan": match_plan,
        "stats": summarize_match_plan(match_plan),
        "settings": {
            "gap_threshold": gap_threshold,
            "min_scene_duration": min_scene_duration,
            "max_clip_duration": max_clip_duration,
            "min_score": min_score,
        },
    }


def _print_match_plan(match_plan: list[dict], limit: int = 10) -> None:
    stats = summarize_match_plan(match_plan)
    print("\n=== Stage 3 Match Plan ===")
    print(
        f"Matched: {stats['matched']}/{stats['total_narration_lines']} | "
        f"Unmatched: {stats['unmatched']} | "
        f"Reused scenes: {stats['reused_scenes']} | "
        f"Avg clip: {stats['avg_clip_duration']:.2f}s"
    )

    for item in match_plan[:limit]:
        print(
            f"\n  Narration [{item['narration_index']}] "
            f"({item['narration_duration']:.2f}s) | {item['narration_text']}"
        )
        if not item["matched"]:
            print("    -> NO MATCH")
            continue
        trim_note = "trimmed" if item["trimmed"] else "full scene"
        reuse_note = "reuse" if item["reused_scene"] else "fresh"
        print(
            f"    -> Scene {int(item['scene_id']):03d} | "
            f"clip {item['clip_start']:.2f}s -> {item['clip_end']:.2f}s "
            f"({item['clip_duration']:.2f}s, max-check ok, {trim_note}, {reuse_note}) "
            f"| score={item['score']:.3f}"
        )
        scene_text = item.get("scene_text") or ""
        if len(scene_text) > 80:
            scene_text = scene_text[:80] + "..."
        print(f"       Scene text: {scene_text}")


def main() -> None:
    """
    CLI test:

      python matching_engine.py <movie.srt> <narration.srt>
      python matching_engine.py <movie.srt> <narration.srt> [max_clip_duration]

    Example:
      python matching_engine.py sample_movie_cluster.srt sample_narration.srt 5.0
    """
    if len(sys.argv) < 3:
        print(
            "Usage: python matching_engine.py <movie_srt> <narration_srt> "
            "[max_clip_duration=5.0]"
        )
        sys.exit(1)

    movie_srt = sys.argv[1]
    narration_srt = sys.argv[2]
    max_clip = float(sys.argv[3]) if len(sys.argv) >= 4 else 5.0

    try:
        result = run_stage1_to_stage3(
            movie_srt,
            narration_srt,
            max_clip_duration=max_clip,
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    print(f"Movie subtitles: {result['movie_subtitle_count']}")
    print(f"Narration lines: {result['narration_count']}")
    print(f"Clustered scenes: {len(result['scenes'])}")
    print(f"max_clip_duration: {max_clip}s")
    _print_match_plan(result["match_plan"])


if __name__ == "__main__":
    main()
