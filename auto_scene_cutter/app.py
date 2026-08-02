"""
Local test page for Stage 1 → Stage 5.

Open in browser:
    http://localhost:5000
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, render_template_string, request, send_file

from final_render import create_sample_narration_audio
from project import (
    apply_cut_plan_edits,
    create_project_from_sources,
    load_project,
    render_project,
    save_project,
)
from scene_matcher import summarize_cut_plan
from srt_parser import parse_narration_srt
from video_cutter import create_sample_video

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR = BASE_DIR / "_uploads"
LAST_PROJECT = OUTPUT_DIR / "last_project.json"

PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Auto Scene Cutter — Stage 5</title>
  <style>
    :root {
      --bg: #0f1419;
      --panel: #1a222c;
      --text: #e8eef4;
      --muted: #9aa8b5;
      --accent: #3d9cf0;
      --line: #2a3542;
      --ok: #3ecf8e;
      --err: #ff6b6b;
      --warn: #f0c35d;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      background:
        radial-gradient(1200px 600px at 10% -10%, #1d3348 0%, transparent 55%),
        radial-gradient(900px 500px at 100% 0%, #2a3a4a 0%, transparent 50%),
        var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 32px 16px 48px;
    }
    .wrap { max-width: 1180px; margin: 0 auto; }
    h1 { margin: 0 0 8px; font-size: 1.6rem; }
    .sub { color: var(--muted); margin-bottom: 24px; }
    form.panel, section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 16px;
    }
    label { display: grid; gap: 6px; font-size: 0.92rem; color: var(--muted); margin-bottom: 10px; }
    label.check { display: flex; align-items: center; gap: 8px; color: var(--text); }
    .checks { display: flex; flex-wrap: wrap; gap: 14px; margin: 8px 0 4px; }
    input[type="file"], input[type="number"], input[type="text"] {
      color: var(--text);
      background: #121820;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      width: 100%;
    }
    input[type="number"] { max-width: 120px; padding: 6px 8px; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; }
    button, .btn {
      border: 0;
      border-radius: 8px;
      padding: 10px 16px;
      cursor: pointer;
      font-weight: 600;
      background: var(--accent);
      color: #041018;
      text-decoration: none;
      display: inline-block;
    }
    button.secondary, .btn.secondary {
      background: transparent;
      color: var(--text);
      border: 1px solid var(--line);
    }
    .error {
      margin-bottom: 16px;
      padding: 12px 14px;
      border-radius: 8px;
      background: rgba(255, 107, 107, 0.12);
      border: 1px solid rgba(255, 107, 107, 0.4);
      color: #ffc9c9;
    }
    .success {
      margin-bottom: 16px;
      padding: 12px 14px;
      border-radius: 8px;
      background: rgba(62, 207, 142, 0.12);
      border: 1px solid rgba(62, 207, 142, 0.4);
      color: #b8f5d5;
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }
    .count { color: var(--ok); font-size: 0.9rem; margin-bottom: 12px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.86rem; }
    th, td {
      text-align: left;
      padding: 8px 6px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }
    th { color: var(--muted); }
    td.time { white-space: nowrap; color: #b8d4ef; }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 700;
    }
    .badge.ok { background: rgba(62, 207, 142, 0.18); color: var(--ok); }
    .badge.no { background: rgba(255, 107, 107, 0.18); color: var(--err); }
    video {
      width: 100%;
      max-width: 720px;
      margin-top: 12px;
      border-radius: 10px;
      background: #000;
      border: 1px solid var(--line);
    }
    .tiny { color: var(--muted); font-size: 0.8rem; }
    h2 { margin: 0 0 8px; font-size: 1.05rem; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Auto Scene Cutter</h1>
    <p class="sub">
      Stage 5 — project JSON save/load + cut plan editor + re-render.
    </p>

    {% if error %}
      <div class="error">{{ error }}</div>
    {% endif %}

    {% if output_name %}
      <div class="success">
        <span>
          Output ready: {{ output_name }}
          {% if info %}
            | matched={{ info.matched }}/{{ info.total_narration_lines }}
          {% endif %}
        </span>
        <a class="btn" href="{{ url_for('download_output', filename=output_name) }}">Download video</a>
        {% if project_name %}
          <a class="btn secondary" href="{{ url_for('download_project') }}">Download project JSON</a>
        {% endif %}
      </div>
      <section>
        <h2>Preview</h2>
        <video controls src="{{ url_for('download_output', filename=output_name) }}"></video>
      </section>
    {% endif %}

    <form class="panel" method="post" enctype="multipart/form-data">
      <h2>New run / sample</h2>
      <label>
        Movie video
        <input type="file" name="movie_video" accept="video/*" />
      </label>
      <label>
        Movie SRT
        <input type="file" name="movie_srt" accept=".srt" />
      </label>
      <label>
        Narration SRT
        <input type="file" name="narration_srt" accept=".srt" />
      </label>
      <label>
        Narration audio (optional)
        <input type="file" name="narration_audio" accept="audio/*,.m4a,.mp3,.wav,.aac" />
      </label>
      <div class="checks">
        <label class="check">
          <input type="checkbox" name="sync_to_narration" value="1" checked />
          Sync clip length to narration
        </label>
        <label class="check">
          <input type="checkbox" name="burn_subs" value="1" checked />
          Burn narration subtitles
        </label>
        <label class="check">
          <input type="checkbox" name="render_now" value="1" checked />
          Render video now
        </label>
      </div>
      <div class="actions">
        <button type="submit" name="action" value="create">Create project + run</button>
        <button class="secondary" type="submit" name="action" value="sample">Sample Stage 5 test</button>
      </div>
    </form>

    <form class="panel" method="post" enctype="multipart/form-data">
      <h2>Load existing project JSON</h2>
      <label>
        Project file
        <input type="file" name="project_file" accept=".json,application/json" />
      </label>
      <div class="checks">
        <label class="check">
          <input type="checkbox" name="render_now" value="1" />
          Load ke sath render bhi karo
        </label>
      </div>
      <div class="actions">
        <button type="submit" name="action" value="load_project">Load project</button>
      </div>
    </form>

    {% if project %}
    <form class="panel" method="post">
      <h2>Stage 5 — Cut plan editor ({{ project.name }})</h2>
      <div class="count">
        Matched: {{ project.stats.matched }} /
        {{ project.stats.total_narration_lines }}
        (unmatched: {{ project.stats.unmatched }})
      </div>
      <p class="tiny">
        movie_start / movie_end seconds mein edit karo. Uncheck = scene skip.
      </p>
      <table>
        <thead>
          <tr>
            <th>Use</th>
            <th>Narration</th>
            <th>Start</th>
            <th>End</th>
            <th>Dialogue</th>
          </tr>
        </thead>
        <tbody>
          {% for item in project.cut_plan %}
          <tr>
            <td>
              <input type="hidden" name="narration_index" value="{{ item.narration_index }}" />
              <input
                type="checkbox"
                name="matched_{{ item.narration_index }}"
                value="1"
                {% if item.matched %}checked{% endif %}
              />
            </td>
            <td>
              <strong>[{{ item.narration_index }}]</strong>
              {{ item.narration_text }}
            </td>
            <td>
              <input
                type="number"
                step="0.001"
                min="0"
                name="movie_start_{{ item.narration_index }}"
                value="{{ '%.3f'|format(item.movie_start) if item.movie_start is not none else '0.000' }}"
              />
            </td>
            <td>
              <input
                type="number"
                step="0.001"
                min="0"
                name="movie_end_{{ item.narration_index }}"
                value="{{ '%.3f'|format(item.movie_end) if item.movie_end is not none else '0.000' }}"
              />
            </td>
            <td class="tiny">
              {% if item.movie_text %}[{{ item.movie_index }}] {{ item.movie_text }}{% else %}—{% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      <div class="checks">
        <label class="check">
          <input type="checkbox" name="burn_subs" value="1"
            {% if project.settings.burn_subs %}checked{% endif %} />
          Burn subtitles on re-render
        </label>
      </div>
      <div class="actions">
        <button type="submit" name="action" value="save_edits">Save edits</button>
        <button type="submit" name="action" value="render_edits">Save + render</button>
        <a class="btn secondary" href="{{ url_for('download_project') }}">Download JSON</a>
      </div>
    </form>
    {% endif %}
  </div>
</body>
</html>
"""


def _save_upload(file_storage, filename: str) -> Path:
    UPLOAD_DIR.mkdir(exist_ok=True)
    path = UPLOAD_DIR / filename
    file_storage.save(path)
    return path


def _persist_project(project: dict) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    return save_project(project, LAST_PROJECT)


def _edits_from_form(form, cut_plan: list[dict]) -> list[dict]:
    edits = []
    for item in cut_plan:
        idx = int(item["narration_index"])
        matched = form.get(f"matched_{idx}") == "1"
        start_raw = form.get(f"movie_start_{idx}", "0")
        end_raw = form.get(f"movie_end_{idx}", "0")
        edits.append(
            {
                "narration_index": idx,
                "matched": matched,
                "movie_start": float(start_raw or 0),
                "movie_end": float(end_raw or 0),
            }
        )
    return edits


@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    output_name = None
    info = None
    project = None

    if LAST_PROJECT.exists():
        try:
            project = load_project(LAST_PROJECT)
        except (ValueError, FileNotFoundError, OSError):
            project = None

    if request.method == "POST":
        action = request.form.get("action", "create")
        try:
            OUTPUT_DIR.mkdir(exist_ok=True)

            if action == "sample":
                video_path = BASE_DIR / "sample_movie.mp4"
                audio_path = BASE_DIR / "sample_narration.m4a"
                movie_srt_path = BASE_DIR / "sample_movie.srt"
                narration_srt_path = BASE_DIR / "sample_narration.srt"
                create_sample_video(video_path, duration_seconds=20.0)
                create_sample_narration_audio(
                    parse_narration_srt(str(narration_srt_path)),
                    audio_path,
                )
                project = create_project_from_sources(
                    name="sample_project",
                    video_path=video_path,
                    movie_srt_path=movie_srt_path,
                    narration_srt_path=narration_srt_path,
                    narration_audio_path=audio_path,
                    sync_to_narration=True,
                    burn_subs=True,
                )
                _persist_project(project)
                result, info = render_project(project, OUTPUT_DIR / "sample_project_final.mp4")
                output_name = result.name

            elif action == "create":
                sync = request.form.get("sync_to_narration") == "1"
                burn = request.form.get("burn_subs") == "1"
                do_render = request.form.get("render_now") == "1"

                movie_file = request.files.get("movie_srt")
                narration_file = request.files.get("narration_srt")
                video_file = request.files.get("movie_video")
                audio_file = request.files.get("narration_audio")

                if not movie_file or not movie_file.filename:
                    raise ValueError("Movie SRT select karo.")
                if not narration_file or not narration_file.filename:
                    raise ValueError("Narration SRT select karo.")
                if not video_file or not video_file.filename:
                    raise ValueError("Movie video select karo (ya sample use karo).")

                movie_srt_path = _save_upload(movie_file, "movie_upload.srt")
                narration_srt_path = _save_upload(narration_file, "narration_upload.srt")
                video_path = _save_upload(video_file, "movie_upload.mp4")
                audio_path = None
                if audio_file and audio_file.filename:
                    audio_path = _save_upload(audio_file, "narration_upload_audio")

                project = create_project_from_sources(
                    name="upload_project",
                    video_path=video_path,
                    movie_srt_path=movie_srt_path,
                    narration_srt_path=narration_srt_path,
                    narration_audio_path=audio_path,
                    sync_to_narration=sync,
                    burn_subs=burn,
                )
                _persist_project(project)

                if do_render:
                    result, info = render_project(project, OUTPUT_DIR / "upload_project_final.mp4")
                    output_name = result.name

            elif action == "load_project":
                project_file = request.files.get("project_file")
                if not project_file or not project_file.filename:
                    raise ValueError("Project JSON file select karo.")
                saved = _save_upload(project_file, "uploaded_project.json")
                project = load_project(saved)
                _persist_project(project)
                if request.form.get("render_now") == "1":
                    result, info = render_project(project, OUTPUT_DIR / "loaded_project_final.mp4")
                    output_name = result.name

            elif action in ("save_edits", "render_edits"):
                if not LAST_PROJECT.exists():
                    raise ValueError("Pehle project create/load karo.")
                project = load_project(LAST_PROJECT)
                edits = _edits_from_form(request.form, project["cut_plan"])
                project["cut_plan"] = apply_cut_plan_edits(project["cut_plan"], edits)
                project["stats"] = summarize_cut_plan(project["cut_plan"])
                project.setdefault("settings", {})
                project["settings"]["burn_subs"] = request.form.get("burn_subs") == "1"
                _persist_project(project)

                if action == "render_edits":
                    result, info = render_project(project, OUTPUT_DIR / "edited_project_final.mp4")
                    output_name = result.name

            else:
                raise ValueError(f"Unknown action: {action}")

        except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
            error = str(exc)
            if LAST_PROJECT.exists() and project is None:
                try:
                    project = load_project(LAST_PROJECT)
                except (ValueError, FileNotFoundError, OSError):
                    project = None

    return render_template_string(
        PAGE,
        error=error,
        output_name=output_name,
        info=info,
        project=project,
        project_name=project.get("name") if project else None,
    )


@app.route("/download/<path:filename>")
def download_output(filename: str):
    safe_name = Path(filename).name
    path = OUTPUT_DIR / safe_name
    if not path.exists():
        return "File nahi mili.", 404
    return send_file(path, as_attachment=False, download_name=safe_name)


@app.route("/download-project")
def download_project():
    if not LAST_PROJECT.exists():
        return "Project nahi mila. Pehle create/load karo.", 404
    return send_file(
        LAST_PROJECT,
        as_attachment=True,
        download_name="auto_scene_cutter_project.json",
    )


if __name__ == "__main__":
    print("Test page: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
