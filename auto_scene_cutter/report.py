"""
Report + Thumbnails Module (Stage 7)

Har matched scene ka ek preview frame (thumbnail) nikalta hai,
aur ek simple HTML report banata hai taake cut plan visually check ho sake.
"""

from __future__ import annotations

import html
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from presets import DEFAULT_QUALITY
from project import load_project
from video_cutter import ensure_ffmpeg


def _run_ffmpeg(cmd: list[str], error_label: str) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"{error_label}\n{details}") from exc


def extract_thumbnail(
    video_path: str | Path,
    at_seconds: float,
    output_path: str | Path,
    width: int = 320,
) -> Path:
    """
    Video ke kisi time pe ek JPEG thumbnail nikaalo.
    """
    ffmpeg = ensure_ffmpeg()
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not video_path.exists():
        raise FileNotFoundError(f"Video nahi mili: {video_path}")

    at_seconds = max(0.0, float(at_seconds))

    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        f"{at_seconds:.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-vf",
        f"scale={width}:-1",
        "-q:v",
        "4",
        str(output_path),
    ]
    _run_ffmpeg(cmd, error_label=f"Thumbnail fail @ {at_seconds:.2f}s")
    return output_path


def build_thumbnails_for_plan(
    video_path: str | Path,
    cut_plan: list[dict],
    thumbs_dir: str | Path,
) -> list[dict]:
    """
    Har matched scene ke liye thumbnail banao.

    Returns list of:
      {
        "narration_index": ...,
        "thumb_path": Path | None,
        "at_seconds": float | None,
        "matched": bool,
      }
    """
    video_path = Path(video_path)
    thumbs_dir = Path(thumbs_dir)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for item in cut_plan:
        idx = int(item["narration_index"])
        if not item.get("matched"):
            results.append(
                {
                    "narration_index": idx,
                    "thumb_path": None,
                    "at_seconds": None,
                    "matched": False,
                }
            )
            continue

        start = float(item["movie_start"])
        end = float(item["movie_end"])
        # Scene ke beech ka frame lo — zyada representative hota hai
        at = start + max(0.0, (end - start) / 2.0)
        thumb_path = thumbs_dir / f"narration_{idx:03d}.jpg"
        extract_thumbnail(video_path, at, thumb_path)
        results.append(
            {
                "narration_index": idx,
                "thumb_path": thumb_path,
                "at_seconds": round(at, 3),
                "matched": True,
            }
        )

    return results


def generate_html_report(
    project: dict,
    output_html: str | Path,
    thumbs_dir: str | Path | None = None,
    final_video_path: str | Path | None = None,
) -> Path:
    """
    Project cut plan ka readable HTML report banao (+ thumbnails).
    """
    output_html = Path(output_html)
    output_html.parent.mkdir(parents=True, exist_ok=True)

    paths = project.get("paths", {})
    settings = project.get("settings", {})
    cut_plan = project.get("cut_plan", [])
    stats = project.get("stats", {})
    video_path = paths.get("video")

    thumb_info: dict[int, dict] = {}
    if video_path and Path(video_path).exists():
        tdir = Path(thumbs_dir) if thumbs_dir else output_html.parent / "thumbs"
        for row in build_thumbnails_for_plan(video_path, cut_plan, tdir):
            thumb_info[int(row["narration_index"])] = row

    def esc(value: object) -> str:
        return html.escape("" if value is None else str(value))

    rows_html = []
    for item in cut_plan:
        idx = int(item["narration_index"])
        t = thumb_info.get(idx, {})
        thumb_path = t.get("thumb_path")
        if thumb_path and Path(thumb_path).exists():
            # Relative path from report HTML location
            try:
                rel = Path(thumb_path).resolve().relative_to(output_html.parent.resolve())
            except ValueError:
                rel = Path(thumb_path).name
            img = f'<img src="{esc(rel.as_posix())}" alt="thumb {idx}" />'
        else:
            img = '<div class="no-thumb">No thumb</div>'

        if item.get("matched"):
            status = '<span class="ok">MATCH</span>'
            timing = f"{float(item['movie_start']):.2f}s → {float(item['movie_end']):.2f}s"
            dialogue = f"[{item.get('movie_index')}] {item.get('movie_text') or ''}"
        else:
            status = '<span class="no">SKIP</span>'
            timing = "—"
            dialogue = "—"

        rows_html.append(
            f"""
            <tr>
              <td>{img}</td>
              <td>{status}</td>
              <td><strong>[{idx}]</strong> {esc(item.get('narration_text'))}</td>
              <td>{esc(timing)}</td>
              <td>{esc(dialogue)}</td>
              <td>{esc(item.get('score', 0))}</td>
            </tr>
            """
        )

    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    final_line = (
        f"<p><strong>Final video:</strong> {esc(final_video_path)}</p>"
        if final_video_path
        else ""
    )

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Report — {esc(project.get('name', 'project'))}</title>
  <style>
    body {{
      margin: 0; padding: 24px; font-family: "Segoe UI", Tahoma, sans-serif;
      background: #10151b; color: #e8eef4;
    }}
    h1 {{ margin: 0 0 8px; }}
    .meta {{ color: #9aa8b5; margin-bottom: 20px; }}
    table {{ width: 100%; border-collapse: collapse; background: #1a222c; }}
    th, td {{ border-bottom: 1px solid #2a3542; padding: 10px 8px; vertical-align: top; text-align: left; }}
    th {{ color: #9aa8b5; }}
    img {{ width: 160px; border-radius: 8px; border: 1px solid #2a3542; display: block; }}
    .no-thumb {{
      width: 160px; height: 90px; display: grid; place-items: center;
      background: #121820; color: #9aa8b5; border-radius: 8px;
    }}
    .ok {{ color: #3ecf8e; font-weight: 700; }}
    .no {{ color: #ff6b6b; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>Auto Scene Cutter Report</h1>
  <div class="meta">
    <div><strong>Project:</strong> {esc(project.get('name'))}</div>
    <div><strong>Generated:</strong> {esc(created)}</div>
    <div><strong>Matched:</strong> {esc(stats.get('matched'))} / {esc(stats.get('total_narration_lines'))}</div>
    <div><strong>Quality:</strong> {esc(settings.get('quality', DEFAULT_QUALITY))}</div>
    <div><strong>Burn subs:</strong> {esc(settings.get('burn_subs'))}</div>
    <div><strong>Source video:</strong> {esc(video_path)}</div>
  </div>
  {final_line}
  <table>
    <thead>
      <tr>
        <th>Thumb</th><th>Status</th><th>Narration</th>
        <th>Movie cut</th><th>Dialogue</th><th>Score</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
</body>
</html>
"""
    output_html.write_text(page, encoding="utf-8")
    return output_html


def generate_project_report(
    project_path: str | Path,
    output_html: str | Path | None = None,
    final_video_path: str | Path | None = None,
) -> Path:
    """Load project JSON and write HTML report beside it (or custom path)."""
    project_path = Path(project_path)
    project = load_project(project_path)
    if output_html is None:
        output_html = project_path.with_name(f"{project_path.stem}_report.html")
    thumbs_dir = Path(output_html).parent / f"{Path(output_html).stem}_thumbs"
    return generate_html_report(
        project,
        output_html=output_html,
        thumbs_dir=thumbs_dir,
        final_video_path=final_video_path,
    )


def main() -> None:
    """
    Usage:
      python report.py <project.json> [report.html]
    """
    args = sys.argv[1:]
    if not args:
        print("Usage: python report.py <project.json> [report.html]")
        sys.exit(1)

    project_path = args[0]
    output_html = args[1] if len(args) > 1 else None

    try:
        result = generate_project_report(project_path, output_html=output_html)
        print(f"Report ready: {result}")
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
