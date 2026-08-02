"""
Unified CLI for Auto Scene Cutter (Stage 7/8)

Ek hi entry point se common commands chalayein:

  python main.py sample
  python main.py create <video> <movie.srt> <narration.srt> <project.json>
                 [--audio file] [--quality fast] [--transition fade] [--fade-dur 0.35]
  python main.py render <project.json> [output.mp4]
  python main.py report <project.json> [report.html]
  python main.py batch <projects_folder> [output_folder] [--quality fast|balanced|high]
  python main.py serve
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from batch_render import batch_render
from config import TRANSITION_OPTIONS, load_config
from final_render import create_sample_narration_audio
from presets import list_qualities
from project import create_project_from_sources, load_project, render_project, save_project
from report import generate_project_report
from srt_parser import parse_narration_srt
from video_cutter import create_sample_video


def _print_help() -> None:
    print(
        "Auto Scene Cutter — unified CLI\n\n"
        "Commands:\n"
        "  sample\n"
        "  create <video> <movie.srt> <narration.srt> <project.json>\n"
        "         [--audio file] [--quality NAME] [--transition none|fade] [--fade-dur 0.35]\n"
        "  render <project.json> [output.mp4]\n"
        "  report <project.json> [report.html]\n"
        "  batch <projects_folder> [output_folder] [--quality NAME]\n"
        "  serve\n\n"
        f"Quality options: {', '.join(list_qualities())}\n"
        f"Transitions: {', '.join(TRANSITION_OPTIONS)}"
    )


def cmd_sample() -> int:
    base = Path(__file__).resolve().parent
    video = base / "sample_movie.mp4"
    audio = base / "sample_narration.m4a"
    movie_srt = base / "sample_movie.srt"
    narration_srt = base / "sample_narration.srt"
    project_path = base / "output" / "sample_project.json"
    output_video = base / "output" / "sample_project_final.mp4"
    report_html = base / "output" / "sample_project_report.html"

    print("1) Sample media...")
    create_sample_video(video, duration_seconds=20.0)
    create_sample_narration_audio(parse_narration_srt(str(narration_srt)), audio)

    print("2) Project create...")
    cfg = load_config()
    project = create_project_from_sources(
        name="sample_project",
        video_path=video,
        movie_srt_path=movie_srt,
        narration_srt_path=narration_srt,
        narration_audio_path=audio,
        sync_to_narration=True,
        burn_subs=True,
        quality="fast",
        transition=cfg.get("transition", "fade"),
        transition_duration=float(cfg.get("transition_duration", 0.35)),
    )
    save_project(project, project_path)

    print("3) Render...")
    result, info = render_project(project, output_video)
    print(f"   Info: {info}")
    print(f"   Video: {result}")

    print("4) HTML report + thumbnails...")
    report_path = generate_project_report(
        project_path,
        output_html=report_html,
        final_video_path=result,
    )
    print(f"   Report: {report_path}")
    return 0


def cmd_create(args: list[str]) -> int:
    if len(args) < 4:
        print(
            "Usage: python main.py create <video> <movie.srt> <narration.srt> "
            "<project.json> [--audio file] [--quality NAME]"
        )
        return 1

    video, movie_srt, narration_srt, project_path = args[:4]
    audio = None
    quality = None
    transition = None
    fade_dur = None
    rest = args[4:]
    i = 0
    while i < len(rest):
        if rest[i] == "--audio" and i + 1 < len(rest):
            audio = rest[i + 1]
            i += 2
        elif rest[i] == "--quality" and i + 1 < len(rest):
            quality = rest[i + 1]
            i += 2
        elif rest[i] == "--transition" and i + 1 < len(rest):
            transition = rest[i + 1]
            i += 2
        elif rest[i] == "--fade-dur" and i + 1 < len(rest):
            fade_dur = float(rest[i + 1])
            i += 2
        else:
            print(f"Unknown arg: {rest[i]}")
            return 1

    project = create_project_from_sources(
        name=Path(project_path).stem,
        video_path=video,
        movie_srt_path=movie_srt,
        narration_srt_path=narration_srt,
        narration_audio_path=audio,
        quality=quality,
        transition=transition,
        transition_duration=fade_dur,
    )
    save_project(project, project_path)
    print(f"Project saved: {project_path}")
    print(f"Stats: {project['stats']}")
    return 0


def cmd_render(args: list[str]) -> int:
    if not args:
        print("Usage: python main.py render <project.json> [output.mp4]")
        return 1
    project_path = args[0]
    output = args[1] if len(args) > 1 else "output_from_project.mp4"
    project = load_project(project_path)
    result, info = render_project(project, output)
    print(f"Info: {info}")
    print(f"Output: {result}")

    # Auto report next to output
    report_path = Path(output).with_name(Path(output).stem + "_report.html")
    generate_project_report(project_path, output_html=report_path, final_video_path=result)
    print(f"Report: {report_path}")
    return 0


def cmd_report(args: list[str]) -> int:
    if not args:
        print("Usage: python main.py report <project.json> [report.html]")
        return 1
    project_path = args[0]
    output_html = args[1] if len(args) > 1 else None
    result = generate_project_report(project_path, output_html=output_html)
    print(f"Report ready: {result}")
    return 0


def cmd_batch(args: list[str]) -> int:
    if not args:
        print(
            "Usage: python main.py batch <projects_folder> [output_folder] "
            f"[--quality {'|'.join(list_qualities())}]"
        )
        return 1

    folder = args[0]
    output_dir = None
    quality = None
    rest = args[1:]
    i = 0
    while i < len(rest):
        if rest[i] == "--quality" and i + 1 < len(rest):
            quality = rest[i + 1]
            i += 2
        elif not rest[i].startswith("--") and output_dir is None:
            output_dir = rest[i]
            i += 1
        else:
            print(f"Unknown arg: {rest[i]}")
            return 1

    results = batch_render(folder, output_dir=output_dir, quality_override=quality)
    return 0 if all(r["ok"] for r in results) else 2


def cmd_serve(_args: list[str]) -> int:
    app_path = Path(__file__).resolve().parent / "app.py"
    print("Starting UI at http://localhost:5000")
    # Replace current process with flask app for simple UX
    return subprocess.call([sys.executable, str(app_path)])


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help", "help"}:
        _print_help()
        return 0

    cmd = argv[0]
    args = argv[1:]

    try:
        if cmd == "sample":
            return cmd_sample()
        if cmd == "create":
            return cmd_create(args)
        if cmd == "render":
            return cmd_render(args)
        if cmd == "report":
            return cmd_report(args)
        if cmd == "batch":
            return cmd_batch(args)
        if cmd == "serve":
            return cmd_serve(args)
        print(f"Unknown command: {cmd}")
        _print_help()
        return 1
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
