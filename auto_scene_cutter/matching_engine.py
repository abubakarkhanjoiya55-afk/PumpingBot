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


def score_narration_against_scene(narration_entry: dict, scene: dict) -> float:
    """Similarity of one narration line vs one clustered scene text."""
    return similarity_score(
        narration_entry.get("text", ""),
        scene.get("combined_text", ""),
    )


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

    best_unused = None
    best_unused_score = -1.0
    best_any = None
    best_any_score = -1.0

    for scene in scenes:
        score = score_narration_against_scene(narration_entry, scene)
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


def _empty_match_item(narr: dict, narr_dur: float) -> dict:
    return {
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


def build_match_item(
    narr: dict,
    scene: dict,
    score: float,
    reused: bool,
    max_clip_duration: float = 5.0,
) -> dict:
    """Build one match-plan row for a narration + chosen scene."""
    narr_dur = narration_duration(narr)
    target = narr_dur if narr_dur > 0 else max_clip_duration
    clip = trim_scene_to_clip(
        scene,
        target_duration=target,
        max_clip_duration=max_clip_duration,
    )
    return {
        "narration_index": narr["index"],
        "narration_text": narr["text"],
        "narration_start": narr["start"],
        "narration_end": narr["end"],
        "narration_duration": round(narr_dur, 3),
        "matched": True,
        "score": round(float(score), 3),
        "reused_scene": bool(reused),
        **clip,
    }


def match_narration_to_scenes(
    scenes: list[dict],
    narration_entries: list[dict],
    max_clip_duration: float = 5.0,
    min_score: float = 0.12,
    prefer_unused: bool = True,
) -> list[dict]:
    """
    Match every narration line to a movie scene and build clip windows.

    Assignment strategy (better than pure sequential greedy):
      1) Score all narration×scene pairs
      2) Assign highest scores first (global best-first)
      3) Prefer unused scenes; only reuse after unused options are gone

    Returns a list of match items (see build_match_item / _empty_match_item).
    """
    if not scenes:
        raise ValueError("Scenes list empty hai — pehle Stage 2 clustering chalao.")
    if not narration_entries:
        raise ValueError("Narration entries empty hain — matching nahi ho sakti.")

    # Precompute all pair scores
    pairs: list[tuple[float, int, int]] = []  # (score, narr_pos, scene_pos)
    for ni, narr in enumerate(narration_entries):
        for si, scene in enumerate(scenes):
            score = score_narration_against_scene(narr, scene)
            if score >= min_score:
                pairs.append((score, ni, si))

    pairs.sort(key=lambda row: row[0], reverse=True)

    assigned: dict[int, tuple[dict, float, bool]] = {}
    used_scene_ids: set[int] = set()

    # Pass 1: unique scenes only (best pairs first)
    for score, ni, si in pairs:
        if ni in assigned:
            continue
        scene = scenes[si]
        sid = int(scene["scene_id"])
        if sid in used_scene_ids:
            continue
        assigned[ni] = (scene, score, False)
        used_scene_ids.add(sid)

    # Pass 2 (optional reuse): leftover narrations get best remaining scene
    if not prefer_unused or len(assigned) < len(narration_entries):
        for score, ni, si in pairs:
            if ni in assigned:
                continue
            scene = scenes[si]
            sid = int(scene["scene_id"])
            reused = sid in used_scene_ids
            # If prefer_unused, only allow reuse once unique pass is done
            assigned[ni] = (scene, score, reused)
            used_scene_ids.add(sid)

    plan: list[dict] = []
    for ni, narr in enumerate(narration_entries):
        narr_dur = narration_duration(narr)
        if ni not in assigned:
            plan.append(_empty_match_item(narr, narr_dur))
            continue
        scene, score, reused = assigned[ni]
        plan.append(
            build_match_item(
                narr,
                scene,
                score=score,
                reused=reused,
                max_clip_duration=max_clip_duration,
            )
        )

    return plan


def scene_by_id(scenes: list[dict], scene_id: int) -> dict | None:
    """Lookup clustered scene by id."""
    for scene in scenes:
        if int(scene["scene_id"]) == int(scene_id):
            return scene
    return None


def rematch_plan_item(
    match_plan: list[dict],
    scenes: list[dict],
    narration_index: int,
    scene_id: int | None,
    max_clip_duration: float = 5.0,
) -> list[dict]:
    """
    Manual editor action:
      - scene_id=None → skip / unmatch that narration line
      - scene_id=N → force that scene onto the narration line

    Returns a new match_plan list (does not mutate the input list items in-place
    beyond replacing the target row).
    """
    scenes_map = {int(s["scene_id"]): s for s in scenes}
    used = {
        int(m["scene_id"])
        for m in match_plan
        if m.get("matched") and m.get("scene_id") is not None
        and int(m["narration_index"]) != int(narration_index)
    }

    new_plan: list[dict] = []
    found = False
    for item in match_plan:
        if int(item["narration_index"]) != int(narration_index):
            new_plan.append(dict(item))
            continue

        found = True
        narr = {
            "index": item["narration_index"],
            "text": item["narration_text"],
            "start": item["narration_start"],
            "end": item["narration_end"],
        }
        narr_dur = narration_duration(narr)

        if scene_id is None:
            new_plan.append(_empty_match_item(narr, narr_dur))
            continue

        scene = scenes_map.get(int(scene_id))
        if scene is None:
            raise ValueError(f"Scene id {scene_id} nahi mili.")

        score = score_narration_against_scene(narr, scene)
        reused = int(scene_id) in used
        new_plan.append(
            build_match_item(
                narr,
                scene,
                score=score,
                reused=reused,
                max_clip_duration=max_clip_duration,
            )
        )

    if not found:
        raise ValueError(f"Narration index {narration_index} match plan mein nahi hai.")

    # Refresh reused flags after edit
    seen: set[int] = set()
    for item in new_plan:
        if not item.get("matched") or item.get("scene_id") is None:
            item["reused_scene"] = False
            continue
        sid = int(item["scene_id"])
        item["reused_scene"] = sid in seen
        seen.add(sid)

    return new_plan


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
