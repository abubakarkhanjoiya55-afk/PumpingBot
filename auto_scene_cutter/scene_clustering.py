"""
Scene Clustering Module (Stage 2)

Stage 1 ne movie SRT ko subtitle entries mein tod diya.
Stage 2 un consecutive subtitles ko "scenes" mein group karta hai.

Idea simple hai:
  - Agar do subtitles ke darmiyan chhota gap hai → same scene
  - Agar gap bada hai (dialogue break / silence) → naya scene start

Baad mein SceneCut Pro in scenes ko narration se match karke timeline pe rakhega.
"""

from __future__ import annotations

import sys

from srt_parser import parse_srt


def cluster_movie_scenes(
    subtitle_entries: list[dict],
    gap_threshold: float = 6.0,
) -> list[dict]:
    """
    Group consecutive movie subtitles into scenes using a time gap.

    Logic:
      Look at subtitle A then subtitle B.
      gap = B.start - A.end

      - if gap < gap_threshold  → same scene (dialogue still flowing)
      - if gap >= gap_threshold → start a new scene (pause / cut / new beat)

    Args:
        subtitle_entries: list from parse_srt(), each with text/start/end
        gap_threshold: max silence (seconds) allowed inside one scene.
                       Smaller value = more scenes.
                       Larger value = fewer, longer scenes.

    Returns:
        List of scene dicts:
        {
            "scene_id": 1,
            "start": 1.0,
            "end": 9.8,
            "combined_text": "Hello... oak tree.",
            "subtitle_count": 3,
        }
    """
    if not subtitle_entries:
        return []

    scenes: list[dict] = []

    # Start the first scene with the first subtitle
    current_subs: list[dict] = [subtitle_entries[0]]

    for entry in subtitle_entries[1:]:
        previous = current_subs[-1]
        gap = float(entry["start"]) - float(previous["end"])

        if gap < gap_threshold:
            # Still the same scene — keep collecting lines
            current_subs.append(entry)
        else:
            # Big enough pause → close current scene, open a new one
            scenes.append(_build_scene(len(scenes) + 1, current_subs))
            current_subs = [entry]

    # Don't forget the last open scene
    scenes.append(_build_scene(len(scenes) + 1, current_subs))
    return scenes


def _build_scene(scene_id: int, subtitle_entries: list[dict]) -> dict:
    """Turn a list of subtitle lines into one scene dictionary."""
    texts = [str(item.get("text", "")).strip() for item in subtitle_entries]
    texts = [t for t in texts if t]  # drop empties

    return {
        "scene_id": scene_id,
        "start": float(subtitle_entries[0]["start"]),
        "end": float(subtitle_entries[-1]["end"]),
        "combined_text": " ".join(texts),
        "subtitle_count": len(subtitle_entries),
    }


def merge_short_scenes(
    scenes: list[dict],
    min_duration: float = 2.0,
) -> list[dict]:
    """
    Merge scenes that are too short into the NEXT scene.

    Why?
      Sometimes a single short subtitle sits alone (1-2 words).
      Those tiny "scenes" are hard to use for cutting / matching.
      So we glue them forward into the following scene.

    Args:
        scenes: output of cluster_movie_scenes()
        min_duration: scenes shorter than this (seconds) get merged forward.
                      Smaller value = keep more tiny scenes.
                      Larger value = more aggressive merging.

    Returns:
        Cleaned scene list with fresh scene_id numbers (1, 2, 3, ...).
    """
    if not scenes:
        return []

    merged: list[dict] = []
    i = 0

    while i < len(scenes):
        current = dict(scenes[i])
        duration = float(current["end"]) - float(current["start"])

        # Keep merging forward while current blob is still too short
        # and there is a next scene available.
        while duration < min_duration and (i + 1) < len(scenes):
            nxt = scenes[i + 1]
            current["end"] = float(nxt["end"])
            current["combined_text"] = (
                f"{current['combined_text']} {nxt['combined_text']}"
            ).strip()
            current["subtitle_count"] = int(current["subtitle_count"]) + int(
                nxt["subtitle_count"]
            )
            i += 1
            duration = float(current["end"]) - float(current["start"])

        merged.append(current)
        i += 1

    # Re-number scene_id so IDs stay clean after merges
    for new_id, scene in enumerate(merged, start=1):
        scene["scene_id"] = new_id

    return merged


def _print_scenes(scenes: list[dict], limit: int = 10) -> None:
    """Print a readable preview of clustered scenes."""
    print(f"\nTotal scenes: {len(scenes)}")
    print(f"First {min(limit, len(scenes))} scenes:\n")

    for scene in scenes[:limit]:
        duration = float(scene["end"]) - float(scene["start"])
        text = scene["combined_text"]
        if len(text) > 80:
            text = text[:80] + "..."

        print(
            f"  Scene {scene['scene_id']:03d} | "
            f"{scene['start']:.2f}s -> {scene['end']:.2f}s "
            f"(dur {duration:.2f}s, lines={scene['subtitle_count']})"
        )
        print(f"    {text}\n")


def main() -> None:
    """
    Command-line test helper.

    Usage:
        python scene_clustering.py <movie.srt>
        python scene_clustering.py <movie.srt> [gap_threshold] [min_duration]
    """
    if len(sys.argv) < 2:
        print(
            "Usage: python scene_clustering.py <movie_srt_path> "
            "[gap_threshold=6.0] [min_duration=2.0]"
        )
        sys.exit(1)

    movie_srt_path = sys.argv[1]
    gap_threshold = float(sys.argv[2]) if len(sys.argv) >= 3 else 6.0
    min_duration = float(sys.argv[3]) if len(sys.argv) >= 4 else 2.0

    try:
        entries = parse_srt(movie_srt_path)
        scenes = cluster_movie_scenes(entries, gap_threshold=gap_threshold)
        scenes = merge_short_scenes(scenes, min_duration=min_duration)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    print(f"Parsed subtitles: {len(entries)}")
    print(f"gap_threshold: {gap_threshold}s | min_duration: {min_duration}s")
    _print_scenes(scenes, limit=10)


if __name__ == "__main__":
    main()
