"""
Export Engine (Stage 5)

Stage 4 ne cut/join video bana di.
Stage 5 final export karta hai:
  1) output-timeline narration SRT (0 se start)
  2) narration/voiceover audio mix (movie audio duck)
  3) optional burned-in narration subtitles

Yeh Spec pipeline ka last backend step hai (UI alag).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from cutting_engine import run_stage1_to_stage4, save_match_plan_json
from final_render import (
    burn_subtitles,
    create_sample_narration_audio,
    mix_narration_audio,
)
from matching_engine import summarize_match_plan
from progress import ProgressLogger
from video_cutter import create_sample_video, ensure_ffmpeg


def _run_ffmpeg(cmd: list[str], error_label: str) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"{error_label}\n{details}") from exc


def _fmt_srt_time(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def matched_items(match_plan: list[dict]) -> list[dict]:
    """Only items that have a valid cut window."""
    items = []
    for item in match_plan:
        if not item.get("matched"):
            continue
        if item.get("clip_start") is None or item.get("clip_end") is None:
            continue
        if float(item["clip_end"]) <= float(item["clip_start"]):
            continue
        items.append(item)
    return items


def build_timeline_srt(
    match_plan: list[dict],
    output_srt_path: str | Path,
) -> Path:
    """
    Final cut video ke liye 0-based SRT banao.

    Har matched clip ke baad cursor aage badhta hai (clip_duration).
    """
    output_srt_path = Path(output_srt_path)
    output_srt_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    cursor = 0.0
    index = 1

    for item in matched_items(match_plan):
        dur = float(item.get("clip_duration") or (item["clip_end"] - item["clip_start"]))
        dur = max(0.2, dur)
        start = cursor
        end = cursor + dur
        text = str(item.get("narration_text") or "").strip() or f"Clip {index}"

        lines.append(str(index))
        lines.append(f"{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}")
        lines.append(text)
        lines.append("")

        cursor = end
        index += 1

    if not lines:
        raise ValueError("Timeline SRT ke liye koi matched clip nahi mili.")

    output_srt_path.write_text("\n".join(lines), encoding="utf-8")
    return output_srt_path


def build_timeline_narration_audio(
    match_plan: list[dict],
    output_audio_path: str | Path,
    source_narration_audio: str | Path | None = None,
) -> Path:
    """
    Final video timeline ke mutabiq narration audio banao.

    - Agar source VO audio di hai: har narration line extract + concat
    - Warna: testing tones generate (create_sample_narration_audio)
    """
    ensure_ffmpeg()
    output_audio_path = Path(output_audio_path)
    output_audio_path.parent.mkdir(parents=True, exist_ok=True)
    items = matched_items(match_plan)
    if not items:
        raise ValueError("Narration audio ke liye koi matched clip nahi.")

    # No source audio → synthetic bed aligned to output timeline
    if not source_narration_audio or not Path(source_narration_audio).exists():
        fake_entries = []
        cursor = 0.0
        for i, item in enumerate(items, start=1):
            dur = float(item.get("clip_duration") or 0.2)
            dur = max(0.2, dur)
            fake_entries.append(
                {
                    "index": i,
                    "start": cursor,
                    "end": cursor + dur,
                    "text": item.get("narration_text") or "",
                }
            )
            cursor += dur
        return create_sample_narration_audio(fake_entries, output_audio_path)

    # Source audio exists → cut each narration window, then concat
    ffmpeg = ensure_ffmpeg()
    source = Path(source_narration_audio)

    with tempfile.TemporaryDirectory(prefix="asc_vo_") as tmp:
        tmp_dir = Path(tmp)
        segment_paths: list[Path] = []

        for i, item in enumerate(items, start=1):
            # Prefer original narration timing for audio extract
            start = float(item.get("narration_start") or 0.0)
            # Length should follow the video clip duration for sync
            dur = float(item.get("clip_duration") or 0.2)
            dur = max(0.2, dur)
            seg = tmp_dir / f"vo_{i:03d}.m4a"
            segment_paths.append(seg)

            cmd = [
                ffmpeg,
                "-y",
                "-ss",
                f"{start:.3f}",
                "-i",
                str(source),
                "-t",
                f"{dur:.3f}",
                "-c:a",
                "aac",
                str(seg),
            ]
            _run_ffmpeg(cmd, error_label=f"Narration audio segment {i} cut fail.")

        list_file = tmp_dir / "vo_concat.txt"
        list_file.write_text(
            "\n".join(
                f"file '{p.resolve().as_posix().replace(chr(39), r"'\\''")}'"
                for p in segment_paths
            )
            + "\n",
            encoding="utf-8",
        )
        concat_cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:a",
            "aac",
            str(output_audio_path),
        ]
        _run_ffmpeg(concat_cmd, error_label="Narration audio concat fail.")

    return output_audio_path


def export_final_video(
    cut_video_path: str | Path,
    match_plan: list[dict],
    output_path: str | Path,
    source_narration_audio: str | Path | None = None,
    burn_subs: bool = True,
    original_volume: float = 0.12,
    narration_volume: float = 1.0,
) -> dict:
    """
    Stage 4 cut video → Stage 5 final export (VO mix + optional subs).
    """
    cut_video_path = Path(cut_video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not cut_video_path.exists():
        raise FileNotFoundError(f"Cut video nahi mili: {cut_video_path}")

    steps = 2 + (1 if burn_subs else 0)  # timeline audio + mix (+ burn)
    logger = ProgressLogger(total=steps, label="Stage5")

    with tempfile.TemporaryDirectory(prefix="asc_export_") as tmp:
        tmp_dir = Path(tmp)

        logger.step("Timeline narration audio bana raha hoon")
        vo_path = tmp_dir / "timeline_vo.m4a"
        build_timeline_narration_audio(
            match_plan,
            vo_path,
            source_narration_audio=source_narration_audio,
        )

        logger.step("Narration audio mix")
        mixed_path = tmp_dir / "mixed.mp4"
        mix_narration_audio(
            cut_video_path,
            vo_path,
            mixed_path,
            original_volume=original_volume,
            narration_volume=narration_volume,
        )
        current = mixed_path

        timeline_srt = output_path.with_name(output_path.stem + "_timeline.srt")
        build_timeline_srt(match_plan, timeline_srt)

        if burn_subs:
            logger.step("Subtitle burn-in")
            burned = tmp_dir / "burned.mp4"
            burn_subtitles(current, timeline_srt, burned)
            current = burned

        output_path.write_bytes(current.read_bytes())

    return {
        "output_video": str(output_path),
        "timeline_srt": str(timeline_srt),
        "burn_subs": burn_subs,
        "stats": summarize_match_plan(match_plan),
    }


def run_stage1_to_stage5(
    video_path: str | Path,
    movie_srt_path: str,
    narration_srt_path: str,
    output_path: str | Path,
    narration_audio_path: str | Path | None = None,
    gap_threshold: float = 6.0,
    min_scene_duration: float = 2.0,
    max_clip_duration: float = 5.0,
    quality: str = "fast",
    transition: str = "none",
    burn_subs: bool = True,
) -> dict:
    """
    Full Spec backend:
      parse → cluster → match → cut → export (VO + subs)
    """
    cut_output = Path(output_path).with_name(Path(output_path).stem + "_cut_only.mp4")

    stage4 = run_stage1_to_stage4(
        video_path=video_path,
        movie_srt_path=movie_srt_path,
        narration_srt_path=narration_srt_path,
        output_path=cut_output,
        gap_threshold=gap_threshold,
        min_scene_duration=min_scene_duration,
        max_clip_duration=max_clip_duration,
        quality=quality,
        transition=transition,
    )

    export_info = export_final_video(
        cut_video_path=stage4["output_video"],
        match_plan=stage4["match_plan"],
        output_path=output_path,
        source_narration_audio=narration_audio_path,
        burn_subs=burn_subs,
    )

    return {
        **stage4,
        **export_info,
        "cut_only_video": str(cut_output),
    }


def main() -> None:
    """
    CLI:

      python export_engine.py --sample
      python export_engine.py <movie.mp4> <movie.srt> <narration.srt> [output.mp4]
                             [--audio narration.m4a] [--max-clip 5] [--no-subs]
    """
    args = sys.argv[1:]
    base = Path(__file__).resolve().parent

    try:
        if args and args[0] == "--sample":
            video = base / "sample_movie.mp4"
            movie_srt = base / "sample_movie_cluster.srt"
            narration_srt = base / "sample_narration.srt"
            output = base / "output" / "stage5_final.mp4"
            plan_json = base / "output" / "stage5_match_plan.json"

            print("Sample movie (60s)...")
            create_sample_video(video, duration_seconds=60.0)

            # Build a disposable source VO from narration SRT timings
            from srt_parser import parse_narration_srt

            vo_source = base / "sample_narration.m4a"
            print("Sample narration audio...")
            create_sample_narration_audio(parse_narration_srt(str(narration_srt)), vo_source)

            print("Stage 1→5 chal raha hai...")
            result = run_stage1_to_stage5(
                video_path=video,
                movie_srt_path=str(movie_srt),
                narration_srt_path=str(narration_srt),
                output_path=output,
                narration_audio_path=vo_source,
                max_clip_duration=5.0,
                quality="fast",
                burn_subs=True,
            )
            save_match_plan_json(result["match_plan"], plan_json)

            stats = result["stats"]
            print("\n=== Stage 5 Done ===")
            print(f"Scenes: {len(result['scenes'])}")
            print(
                f"Matched: {stats['matched']}/{stats['total_narration_lines']} "
                f"(avg clip {stats['avg_clip_duration']:.2f}s)"
            )
            print(f"Cut-only: {result['cut_only_video']}")
            print(f"Final:    {result['output_video']}")
            print(f"Timeline SRT: {result['timeline_srt']}")
            return

        if len(args) < 3:
            print(
                "Usage:\n"
                "  python export_engine.py --sample\n"
                "  python export_engine.py <movie.mp4> <movie.srt> <narration.srt> "
                "[output.mp4] [--audio file] [--max-clip 5] [--no-subs]"
            )
            sys.exit(1)

        video, movie_srt, narration_srt = args[:3]
        rest = args[3:]
        output = "output_stage5_final.mp4"
        audio = None
        max_clip = 5.0
        burn_subs = True

        i = 0
        if rest and not rest[0].startswith("--"):
            output = rest[0]
            i = 1
        while i < len(rest):
            if rest[i] == "--audio" and i + 1 < len(rest):
                audio = rest[i + 1]
                i += 2
            elif rest[i] == "--max-clip" and i + 1 < len(rest):
                max_clip = float(rest[i + 1])
                i += 2
            elif rest[i] == "--no-subs":
                burn_subs = False
                i += 1
            else:
                print(f"Unknown arg: {rest[i]}")
                sys.exit(1)

        result = run_stage1_to_stage5(
            video_path=video,
            movie_srt_path=movie_srt,
            narration_srt_path=narration_srt,
            output_path=output,
            narration_audio_path=audio,
            max_clip_duration=max_clip,
            burn_subs=burn_subs,
        )
        print(f"Final: {result['output_video']}")
        print(f"Timeline SRT: {result['timeline_srt']}")

    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
