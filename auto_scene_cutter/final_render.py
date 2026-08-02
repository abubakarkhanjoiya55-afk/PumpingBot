"""
Final Render Module (Stage 4)

Stage 3 ne scenes cut/join kar diye.
Stage 4 final polish karta hai:
  1) har clip ki length narration duration ke barabar sync
  2) optional narration/voiceover audio mix
  3) optional narration subtitles burn-in (on-screen text)

ffmpeg system pe installed hona chahiye.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from scene_matcher import match_scenes, summarize_cut_plan
from srt_parser import parse_narration_srt, parse_srt
from video_cutter import (
    create_sample_video,
    cut_video_from_plan,
    ensure_ffmpeg,
)


def _run_ffmpeg(cmd: list[str], error_label: str) -> None:
    """Run ffmpeg and convert failures into clear errors."""
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"{error_label}\n{details}") from exc


def sync_cut_plan_to_narration(cut_plan: list[dict]) -> list[dict]:
    """
    Har matched scene ki movie clip length ko narration length jaisa banao.

    Example:
      narration = 2.5 seconds
      movie match start = 4.0
      => movie_end becomes 6.5

    Is se final video narration timing ke sath better feel karti hai.
    """
    synced: list[dict] = []

    for item in cut_plan:
        updated = dict(item)
        if not item.get("matched"):
            synced.append(updated)
            continue

        narr_dur = float(item["narration_end"]) - float(item["narration_start"])
        if narr_dur <= 0:
            # Bad timing — original movie window hi rehne do
            synced.append(updated)
            continue

        movie_start = float(item["movie_start"])
        updated["movie_end"] = round(movie_start + narr_dur, 3)
        updated["target_duration"] = round(narr_dur, 3)
        updated["synced_to_narration"] = True
        synced.append(updated)

    return synced


def create_sample_narration_audio(
    narration_entries: list[dict],
    output_path: str | Path,
) -> Path:
    """
    Testing ke liye fake narration audio banao.

    Real voiceover nahi — har narration line pe alag beep/tone.
    Timing narration SRT jaisi hi hoti hai.
    """
    ffmpeg = ensure_ffmpeg()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not narration_entries:
        raise ValueError("Narration entries empty hain — audio nahi ban sakti.")

    total = max(float(e["end"]) for e in narration_entries)
    if total <= 0:
        raise ValueError("Narration duration invalid hai.")

    # Build an ffmpeg filter that places short tones on each narration window
    # Start with silence for full length, then overlay beeps.
    filter_parts = [f"anullsrc=r=44100:cl=stereo,atrim=0:{total:.3f}[base]"]
    mix_labels = ["[base]"]

    for i, entry in enumerate(narration_entries, start=1):
        start = float(entry["start"])
        dur = max(0.2, float(entry["end"]) - float(entry["start"]))
        # Different beep frequency per line so you can hear changes
        freq = 330 + (i * 40)
        label = f"b{i}"
        filter_parts.append(
            f"sine=frequency={freq}:duration={dur:.3f},"
            f"aformat=sample_rates=44100:channel_layouts=stereo,"
            f"adelay={int(start * 1000)}|{int(start * 1000)}"
            f"[{label}]"
        )
        mix_labels.append(f"[{label}]")

    n = len(mix_labels)
    filter_parts.append(
        "".join(mix_labels)
        + f"amix=inputs={n}:duration=longest:dropout_transition=0,"
        + f"atrim=0:{total:.3f},alimiter=limit=0.9[out]"
    )
    filter_complex = ";".join(filter_parts)

    cmd = [
        ffmpeg,
        "-y",
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        "-c:a",
        "aac",
        str(output_path),
    ]
    _run_ffmpeg(cmd, error_label="Sample narration audio banate waqt fail.")
    return output_path


def mix_narration_audio(
    video_path: str | Path,
    narration_audio_path: str | Path,
    output_path: str | Path,
    original_volume: float = 0.12,
    narration_volume: float = 1.0,
) -> Path:
    """
    Final video pe narration/voiceover audio mix karo.

    Original movie audio soft (duck) ho jati hai, narration clear rehti hai.
    """
    ffmpeg = ensure_ffmpeg()
    video_path = Path(video_path)
    narration_audio_path = Path(narration_audio_path)
    output_path = Path(output_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Video nahi mili: {video_path}")
    if not narration_audio_path.exists():
        raise FileNotFoundError(f"Narration audio nahi mili: {narration_audio_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # duration=first => video length follow karo
    filter_complex = (
        f"[0:a]volume={original_volume}[a0];"
        f"[1:a]volume={narration_volume}[a1];"
        f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]"
    )

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(narration_audio_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ]

    try:
        _run_ffmpeg(cmd, error_label="Narration audio mix fail.")
    except RuntimeError:
        # Some videos have no audio track — narration alone use karo
        fallback = [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(narration_audio_path),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
        ]
        _run_ffmpeg(
            fallback,
            error_label="Narration audio mix fail (fallback bhi fail).",
        )

    return output_path


def burn_subtitles(
    video_path: str | Path,
    srt_path: str | Path,
    output_path: str | Path,
) -> Path:
    """
    Narration SRT text ko video pe burn (hardcode) kar do.

    Note: iske liye ffmpeg mein subtitles/ass support hona chahiye.
    """
    ffmpeg = ensure_ffmpeg()
    video_path = Path(video_path)
    srt_path = Path(srt_path)
    output_path = Path(output_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Video nahi mili: {video_path}")
    if not srt_path.exists():
        raise FileNotFoundError(f"SRT nahi mili: {srt_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ffmpeg subtitles filter: escape special chars in path
    # Windows-style drive letters rarely apply here; still escape ':' and '\'
    subs = str(srt_path.resolve())
    subs = subs.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"subtitles='{subs}'",
        "-c:a",
        "copy",
        str(output_path),
    ]
    _run_ffmpeg(cmd, error_label="Subtitle burn-in fail.")
    return output_path


def _rewrite_narration_srt_for_synced_video(
    cut_plan: list[dict],
    output_srt_path: str | Path,
) -> Path:
    """
    Synced final video ke liye naya SRT banao.

    Original narration times movie timeline pe hoti hain,
    lekin final cut video 0 se start hoti hai — is liye timings
    ko dubara 0-based sequence mein likhte hain.
    """
    output_srt_path = Path(output_srt_path)
    lines: list[str] = []
    cursor = 0.0
    index = 1

    def fmt(seconds: float) -> str:
        ms = int(round(seconds * 1000))
        h, rem = divmod(ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, milli = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"

    for item in cut_plan:
        if not item.get("matched"):
            continue
        dur = float(item.get("target_duration") or (item["movie_end"] - item["movie_start"]))
        start = cursor
        end = cursor + max(0.2, dur)
        lines.append(str(index))
        lines.append(f"{fmt(start)} --> {fmt(end)}")
        lines.append(item["narration_text"])
        lines.append("")
        cursor = end
        index += 1

    if not lines:
        raise ValueError("Synced SRT ke liye koi matched narration nahi mili.")

    output_srt_path.write_text("\n".join(lines), encoding="utf-8")
    return output_srt_path


def render_from_cut_plan(
    video_path: str | Path,
    cut_plan: list[dict],
    output_path: str | Path,
    narration_audio_path: str | Path | None = None,
    burn_subs: bool = True,
) -> tuple[Path, dict]:
    """
    Stage 3+4 render using an already-built/edited cut plan.

    Matching dubara nahi hota — project editor isi liye use karta hai.
    """
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="asc_final_") as tmp:
        tmp_dir = Path(tmp)
        cut_path = tmp_dir / "cut.mp4"
        cut_video_from_plan(video_path, cut_plan, cut_path, work_dir=tmp_dir / "clips")

        current = cut_path

        if narration_audio_path:
            mixed = tmp_dir / "mixed.mp4"
            mix_narration_audio(current, narration_audio_path, mixed)
            current = mixed

        if burn_subs:
            synced_srt = tmp_dir / "burn.srt"
            _rewrite_narration_srt_for_synced_video(cut_plan, synced_srt)
            burned = tmp_dir / "burned.mp4"
            burn_subtitles(current, synced_srt, burned)
            current = burned

        output_path.write_bytes(current.read_bytes())

    info = {
        "burn_subs": burn_subs,
        "narration_audio": bool(narration_audio_path),
        **summarize_cut_plan(cut_plan),
    }
    return output_path, info


def render_final(
    video_path: str | Path,
    movie_srt_path: str | Path,
    narration_srt_path: str | Path,
    output_path: str | Path,
    narration_audio_path: str | Path | None = None,
    sync_to_narration: bool = True,
    burn_subs: bool = True,
) -> tuple[Path, list[dict], dict]:
    """
    Full Stage 1→4 pipeline.

    Returns:
      (final_video_path, cut_plan, info_dict)
    """
    movie_entries = parse_srt(str(movie_srt_path))
    narration_entries = parse_narration_srt(str(narration_srt_path))
    cut_plan = match_scenes(movie_entries, narration_entries)

    if sync_to_narration:
        cut_plan = sync_cut_plan_to_narration(cut_plan)

    result, info = render_from_cut_plan(
        video_path=video_path,
        cut_plan=cut_plan,
        output_path=output_path,
        narration_audio_path=narration_audio_path,
        burn_subs=burn_subs,
    )
    info["sync_to_narration"] = sync_to_narration
    return result, cut_plan, info


def main() -> None:
    """
    CLI helper.

    Usage:
      python final_render.py --sample
      python final_render.py <movie.mp4> <movie.srt> <narration.srt> [output.mp4]
                          [--audio narration.m4a] [--no-sync] [--no-subs]
    """
    args = sys.argv[1:]
    base = Path(__file__).resolve().parent

    try:
        if len(args) >= 1 and args[0] == "--sample":
            sample_video = base / "sample_movie.mp4"
            sample_audio = base / "sample_narration.m4a"
            output = base / "output" / "sample_final.mp4"

            print("Sample movie bana raha hoon...")
            create_sample_video(sample_video, duration_seconds=20.0)

            narration_entries = parse_narration_srt(str(base / "sample_narration.srt"))
            print("Sample narration audio bana raha hoon...")
            create_sample_narration_audio(narration_entries, sample_audio)

            print("Stage 4 final render chal raha hai...")
            result, cut_plan, info = render_final(
                sample_video,
                base / "sample_movie.srt",
                base / "sample_narration.srt",
                output,
                narration_audio_path=sample_audio,
                sync_to_narration=True,
                burn_subs=True,
            )
            print(f"Info: {info}")
            print(f"Output: {result}")
            return

        if len(args) < 3:
            print(
                "Usage:\n"
                "  python final_render.py --sample\n"
                "  python final_render.py <movie.mp4> <movie.srt> <narration.srt> "
                "[output.mp4] [--audio file] [--no-sync] [--no-subs]"
            )
            sys.exit(1)

        video = args[0]
        movie_srt = args[1]
        narration_srt = args[2]
        rest = args[3:]

        output = "output_final.mp4"
        audio = None
        sync = True
        subs = True

        # Optional positional output as first non-flag arg
        if rest and not rest[0].startswith("--"):
            output = rest[0]
            rest = rest[1:]

        i = 0
        while i < len(rest):
            if rest[i] == "--audio" and i + 1 < len(rest):
                audio = rest[i + 1]
                i += 2
            elif rest[i] == "--no-sync":
                sync = False
                i += 1
            elif rest[i] == "--no-subs":
                subs = False
                i += 1
            else:
                print(f"Unknown arg: {rest[i]}")
                sys.exit(1)

        result, cut_plan, info = render_final(
            video,
            movie_srt,
            narration_srt,
            output,
            narration_audio_path=audio,
            sync_to_narration=sync,
            burn_subs=subs,
        )
        print(f"Info: {info}")
        print(f"Output: {result}")

    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
