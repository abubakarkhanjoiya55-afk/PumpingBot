"""
Video Cutter Module (Stage 3)

Stage 2 gave us a cut plan (movie_start / movie_end for each narration line).
Stage 3 uses ffmpeg to:
  1) cut those pieces out of the movie
  2) join them into one output video

Note: ffmpeg must be installed on the system (not a Python package).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from presets import DEFAULT_QUALITY, get_quality_settings
from procutil import run_hidden
from progress import ProgressLogger
from scene_matcher import match_scenes
from srt_parser import parse_narration_srt, parse_srt


def ensure_ffmpeg() -> str:
    """
    Check that ffmpeg exists on PATH.
    Returns the ffmpeg executable path, or raises a clear error.
    """
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise RuntimeError(
            "ffmpeg nahi mila. Install karo, phir dubara try karo "
            "(example: sudo apt install ffmpeg)."
        )
    return ffmpeg_path


def create_sample_video(
    output_path: str | Path,
    duration_seconds: float = 20.0,
    width: int = 640,
    height: int = 360,
) -> Path:
    """
    Make a tiny fake 'movie' for testing (no real film needed).

    It shows a color test pattern + a seconds timer, so you can see
    that Stage 3 cuts the right time ranges.
    """
    ffmpeg = ensure_ffmpeg()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # lavfi = ffmpeg's built-in test video generator
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={width}x{height}:rate=25:duration={duration_seconds}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={duration_seconds}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ]

    try:
        run_hidden(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Sample video banate waqt ffmpeg fail ho gaya:\n{exc.stderr}"
        ) from exc

    return output_path


def _run_ffmpeg(cmd: list[str], error_label: str) -> None:
    """Run an ffmpeg command and turn failures into clear Python errors."""
    try:
        # CREATE_NO_WINDOW: no black ffmpeg console (closing it used to kill the app)
        run_hidden(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"{error_label}\n{details}") from exc


def cut_video_from_plan(
    video_path: str | Path,
    cut_plan: list[dict],
    output_path: str | Path,
    work_dir: str | Path | None = None,
    quality: str = DEFAULT_QUALITY,
    transition: str = "none",
    transition_duration: float = 0.35,
    progress: ProgressLogger | None = None,
) -> Path:
    """
    Cut matched scenes from a video and join them into one file.

    Args:
        video_path: path to the original movie / source video
        cut_plan: list from Stage 2 match_scenes()
        output_path: where the final joined video should be saved
        work_dir: optional temp folder for middle clips
                  (if None, a temporary folder is created and cleaned up)
        quality: Stage 6 preset name — fast / balanced / high
        transition: Stage 8 — "none" (hard cut) or "fade" (in/out)
        transition_duration: fade length in seconds
        progress: optional ProgressLogger for step messages

    Returns:
        Path to the finished output video.
    """
    ffmpeg = ensure_ffmpeg()
    quality_settings = get_quality_settings(quality)
    transition = (transition or "none").strip().lower()
    video_path = Path(video_path)
    output_path = Path(output_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Video file nahi mili: {video_path}")

    # Only keep narration lines that found a movie match
    matched = [
        item
        for item in cut_plan
        if item.get("matched")
        and item.get("movie_start") is not None
        and item.get("movie_end") is not None
        and float(item["movie_end"]) > float(item["movie_start"])
    ]

    if not matched:
        raise ValueError(
            "Cut plan mein koi matched scene nahi hai — video cut nahi ho sakti."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # If caller gave no work_dir, use a temp folder and delete it at the end
    cleanup = work_dir is None
    base_work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="asc_cuts_"))
    base_work.mkdir(parents=True, exist_ok=True)

    segment_paths: list[Path] = []
    concat_list_path = base_work / "concat_list.txt"
    total_steps = len(matched) + 1
    logger = progress or ProgressLogger(total=total_steps, label="Cut")
    # If caller gave a logger with different total, keep using it as-is.

    try:
        for i, item in enumerate(matched, start=1):
            start = float(item["movie_start"])
            end = float(item["movie_end"])
            duration = end - start
            segment_path = base_work / f"segment_{i:03d}.mp4"
            segment_paths.append(segment_path)

            logger.step(
                f"Segment {i}/{len(matched)} cut "
                f"({start:.2f}s -> {end:.2f}s, transition={transition})"
            )

            # Accurate cut: seek after opening input, then re-encode
            cmd = [
                ffmpeg,
                "-y",
                "-ss",
                f"{start:.3f}",
                "-i",
                str(video_path),
                "-t",
                f"{duration:.3f}",
            ]

            # Stage 8 fade: soft in/out so joins softer lagte hain
            if transition == "fade" and duration > 0.2:
                fade_d = min(float(transition_duration), duration / 3.0)
                fade_out_start = max(0.0, duration - fade_d)
                cmd += [
                    "-vf",
                    (
                        f"fade=t=in:st=0:d={fade_d:.3f},"
                        f"fade=t=out:st={fade_out_start:.3f}:d={fade_d:.3f}"
                    ),
                    "-af",
                    (
                        f"afade=t=in:st=0:d={fade_d:.3f},"
                        f"afade=t=out:st={fade_out_start:.3f}:d={fade_d:.3f}"
                    ),
                ]

            cmd += [
                "-c:v",
                "libx264",
                "-preset",
                quality_settings["preset"],
                "-crf",
                quality_settings["crf"],
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(segment_path),
            ]
            _run_ffmpeg(
                cmd,
                error_label=(
                    f"Segment {i} cut fail "
                    f"({start:.2f}s -> {end:.2f}s)."
                ),
            )

        logger.step("Segments join (concat)")

        # ffmpeg concat demuxer needs a text file listing the clips
        concat_lines = []
        for seg in segment_paths:
            # Single quotes inside path can break the list format
            safe = str(seg.resolve()).replace("'", r"'\''")
            concat_lines.append(f"file '{safe}'")
        concat_list_path.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

        concat_cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_path),
            "-c",
            "copy",
            str(output_path),
        ]
        _run_ffmpeg(concat_cmd, error_label="Segments join (concat) fail ho gaya.")

    finally:
        if cleanup:
            # Best-effort cleanup of temp clips
            for seg in segment_paths:
                try:
                    seg.unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                concat_list_path.unlink(missing_ok=True)
            except OSError:
                pass
            try:
                base_work.rmdir()
            except OSError:
                pass

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Output video banayi nahi gayi (empty / missing file).")

    return output_path


def build_and_cut(
    video_path: str | Path,
    movie_srt_path: str | Path,
    narration_srt_path: str | Path,
    output_path: str | Path,
) -> tuple[Path, list[dict]]:
    """
    Full Stage 1 → 2 → 3 helper:
    parse SRTs, match scenes, then cut the video.
    """
    movie_entries = parse_srt(str(movie_srt_path))
    narration_entries = parse_narration_srt(str(narration_srt_path))
    cut_plan = match_scenes(movie_entries, narration_entries)
    result = cut_video_from_plan(video_path, cut_plan, output_path)
    return result, cut_plan


def main() -> None:
    """
    Command-line test helper.

    Usage:
        python video_cutter.py <movie.mp4> <movie.srt> <narration.srt> [output.mp4]

    Or make + cut a sample video:
        python video_cutter.py --sample
    """
    args = sys.argv[1:]

    try:
        if len(args) == 1 and args[0] == "--sample":
            base = Path(__file__).resolve().parent
            sample_video = base / "sample_movie.mp4"
            output = base / "output" / "sample_cut.mp4"

            print("Sample video bana raha hoon...")
            create_sample_video(sample_video, duration_seconds=20.0)

            print("SRT parse + match + cut chal raha hai...")
            result, cut_plan = build_and_cut(
                sample_video,
                base / "sample_movie.srt",
                base / "sample_narration.srt",
                output,
            )
            matched = sum(1 for item in cut_plan if item["matched"])
            print(f"Matched scenes: {matched}/{len(cut_plan)}")
            print(f"Output video: {result}")
            return

        if len(args) not in (3, 4):
            print(
                "Usage:\n"
                "  python video_cutter.py <movie.mp4> <movie.srt> <narration.srt> [output.mp4]\n"
                "  python video_cutter.py --sample"
            )
            sys.exit(1)

        video_path = args[0]
        movie_srt = args[1]
        narration_srt = args[2]
        output = args[3] if len(args) == 4 else "output_cut.mp4"

        result, cut_plan = build_and_cut(video_path, movie_srt, narration_srt, output)
        matched = sum(1 for item in cut_plan if item["matched"])
        print(f"Matched scenes: {matched}/{len(cut_plan)}")
        print(f"Output video: {result}")

    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
