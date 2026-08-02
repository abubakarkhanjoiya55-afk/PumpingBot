"""
Local test page for Stage 1 → Stage 8.

Open in browser:
    http://localhost:5000
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, render_template_string, request, send_file

from batch_render import batch_render
from config import TRANSITION_OPTIONS, load_config, save_config
from final_render import create_sample_narration_audio
from presets import DEFAULT_QUALITY, QUALITY_PRESETS
from project import (
    apply_cut_plan_edits,
    create_project_from_sources,
    load_project,
    render_project,
    save_project,
)
from report import generate_html_report
from scene_matcher import summarize_cut_plan
from srt_parser import parse_narration_srt, parse_srt
from video_cutter import create_sample_video

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR = BASE_DIR / "_uploads"
LAST_PROJECT = OUTPUT_DIR / "last_project.json"
BATCH_DIR = OUTPUT_DIR / "batch_projects"

PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Auto Scene Cutter — Stage 8</title>
  <style>
    :root {
      --bg: #0f1419; --panel: #1a222c; --text: #e8eef4; --muted: #9aa8b5;
      --accent: #3d9cf0; --line: #2a3542; --ok: #3ecf8e; --err: #ff6b6b;
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
    .wrap { max-width: 1200px; margin: 0 auto; }
    h1 { margin: 0 0 8px; font-size: 1.6rem; }
    h2 { margin: 0 0 8px; font-size: 1.05rem; }
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
    input[type="file"], input[type="number"], select {
      color: var(--text); background: #121820; border: 1px solid var(--line);
      border-radius: 8px; padding: 10px; width: 100%;
    }
    input[type="number"] { max-width: 110px; padding: 6px 8px; }
    select.small { min-width: 180px; padding: 6px 8px; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; }
    button, .btn {
      border: 0; border-radius: 8px; padding: 10px 16px; cursor: pointer;
      font-weight: 600; background: var(--accent); color: #041018;
      text-decoration: none; display: inline-block;
    }
    button.secondary, .btn.secondary {
      background: transparent; color: var(--text); border: 1px solid var(--line);
    }
    .error, .success {
      margin-bottom: 16px; padding: 12px 14px; border-radius: 8px;
    }
    .error {
      background: rgba(255,107,107,.12); border: 1px solid rgba(255,107,107,.4); color: #ffc9c9;
    }
    .success {
      background: rgba(62,207,142,.12); border: 1px solid rgba(62,207,142,.4); color: #b8f5d5;
      display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
    }
    .count { color: var(--ok); font-size: 0.9rem; margin-bottom: 12px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.84rem; }
    th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); vertical-align: top; }
    th { color: var(--muted); }
    .tiny { color: var(--muted); font-size: 0.78rem; }
    video {
      width: 100%; max-width: 720px; margin-top: 12px; border-radius: 10px;
      background: #000; border: 1px solid var(--line);
    }
    ul.batch { margin: 8px 0 0; padding-left: 18px; color: var(--muted); }
    ul.batch li { margin: 4px 0; }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Auto Scene Cutter</h1>
    <p class="sub">Stage 8 — fade transitions, config.json defaults, render progress.</p>

    {% if error %}<div class="error">{{ error }}</div>{% endif %}

    {% if output_name %}
      <div class="success">
        <span>
          Output ready: {{ output_name }}
          {% if info %}
            | matched={{ info.matched }}/{{ info.total_narration_lines }}
            | quality={{ info.quality }}
            | transition={{ info.transition }}
          {% endif %}
        </span>
        <a class="btn" href="{{ url_for('download_output', filename=output_name) }}">Download video</a>
        {% if project %}
          <a class="btn secondary" href="{{ url_for('download_project') }}">Download project JSON</a>
        {% endif %}
        {% if report_name %}
          <a class="btn secondary" href="{{ url_for('view_report', subpath=report_name) }}" target="_blank">
            Open HTML report
          </a>
        {% endif %}
      </div>
      <section>
        <h2>Preview</h2>
        <video controls src="{{ url_for('download_output', filename=output_name) }}"></video>
      </section>
    {% endif %}

    {% if batch_results %}
      <section>
        <h2>Batch results</h2>
        <ul class="batch">
          {% for r in batch_results %}
            <li>
              {% if r.ok %}OK{% else %}FAIL{% endif %} —
              {{ r.project }}
              {% if r.ok %}→ {{ r.output }}{% else %}→ {{ r.error }}{% endif %}
            </li>
          {% endfor %}
        </ul>
      </section>
    {% endif %}

    <form class="panel" method="post" enctype="multipart/form-data">
      <h2>New run / sample</h2>
      <label>Movie video<input type="file" name="movie_video" accept="video/*" /></label>
      <label>Movie SRT<input type="file" name="movie_srt" accept=".srt" /></label>
      <label>Narration SRT<input type="file" name="narration_srt" accept=".srt" /></label>
      <label>Narration audio (optional)
        <input type="file" name="narration_audio" accept="audio/*,.m4a,.mp3,.wav,.aac" />
      </label>
      <label>Quality
        <select name="quality">
          {% for key, meta in qualities.items() %}
            <option value="{{ key }}" {% if key == cfg.quality %}selected{% endif %}>
              {{ meta.label }} — {{ meta.description }}
            </option>
          {% endfor %}
        </select>
      </label>
      <label>Transition
        <select name="transition">
          {% for t in transitions %}
            <option value="{{ t }}" {% if t == cfg.transition %}selected{% endif %}>{{ t }}</option>
          {% endfor %}
        </select>
      </label>
      <label>Transition duration (seconds)
        <input type="number" step="0.05" min="0.05" max="1.5" name="transition_duration"
          value="{{ cfg.transition_duration }}" />
      </label>
      <div class="checks">
        <label class="check"><input type="checkbox" name="sync_to_narration" value="1" {% if cfg.sync_to_narration %}checked{% endif %} />Sync to narration</label>
        <label class="check"><input type="checkbox" name="burn_subs" value="1" {% if cfg.burn_subs %}checked{% endif %} />Burn subtitles</label>
        <label class="check"><input type="checkbox" name="render_now" value="1" checked />Render now</label>
        <label class="check"><input type="checkbox" name="save_as_defaults" value="1" />In settings ko config.json default bana do</label>
      </div>
      <div class="actions">
        <button type="submit" name="action" value="create">Create project + run</button>
        <button class="secondary" type="submit" name="action" value="sample">Sample Stage 8 test</button>
      </div>
    </form>

    <form class="panel" method="post" enctype="multipart/form-data">
      <h2>Load project JSON</h2>
      <label>Project file<input type="file" name="project_file" accept=".json,application/json" /></label>
      <div class="checks">
        <label class="check"><input type="checkbox" name="render_now" value="1" />Load + render</label>
      </div>
      <div class="actions">
        <button type="submit" name="action" value="load_project">Load project</button>
      </div>
    </form>

    <form class="panel" method="post">
      <h2>Batch render (output/batch_projects/*.json)</h2>
      <p class="tiny">
        Sample/create ke baad project copy ho jata hai batch folder mein.
        Yahan se sab projects ek saath render ho sakte hain.
      </p>
      <label>Quality override (optional)
        <select name="quality">
          <option value="">Use each project setting</option>
          {% for key, meta in qualities.items() %}
            <option value="{{ key }}">{{ meta.label }}</option>
          {% endfor %}
        </select>
      </label>
      <div class="actions">
        <button type="submit" name="action" value="batch_render">Run batch render</button>
        <button class="secondary" type="submit" name="action" value="copy_to_batch">
          Current project ko batch folder mein copy karo
        </button>
      </div>
    </form>

    {% if project %}
    <form class="panel" method="post">
      <h2>Editor — {{ project.name }}</h2>
      <div class="count">
        Matched: {{ project.stats.matched }} /
        {{ project.stats.total_narration_lines }}
        | quality={{ project.settings.quality }}
        | transition={{ project.settings.transition }}
      </div>
      <p class="tiny">
        Rematch dropdown se movie dialogue manually choose karo.
        Ya start/end seconds edit karo. Uncheck = skip.
      </p>
      <label>Quality
        <select name="quality">
          {% for key, meta in qualities.items() %}
            <option value="{{ key }}" {% if key == project.settings.quality %}selected{% endif %}>
              {{ meta.label }}
            </option>
          {% endfor %}
        </select>
      </label>
      <label>Transition
        <select name="transition">
          {% for t in transitions %}
            <option value="{{ t }}" {% if t == project.settings.transition %}selected{% endif %}>{{ t }}</option>
          {% endfor %}
        </select>
      </label>
      <label>Transition duration
        <input type="number" step="0.05" min="0.05" max="1.5" name="transition_duration"
          value="{{ project.settings.transition_duration }}" />
      </label>
      <table>
        <thead>
          <tr>
            <th>Use</th>
            <th>Narration</th>
            <th>Rematch</th>
            <th>Start</th>
            <th>End</th>
          </tr>
        </thead>
        <tbody>
          {% for item in project.cut_plan %}
          <tr>
            <td>
              <input type="checkbox" name="matched_{{ item.narration_index }}" value="1"
                {% if item.matched %}checked{% endif %} />
            </td>
            <td>
              <strong>[{{ item.narration_index }}]</strong> {{ item.narration_text }}
              <div class="tiny">
                {% if item.movie_text %}current: [{{ item.movie_index }}] {{ item.movie_text }}{% else %}no match{% endif %}
              </div>
            </td>
            <td>
              <select class="small" name="assign_movie_{{ item.narration_index }}">
                <option value="" selected>(keep current / only edit times)</option>
                {% for m in movie_entries %}
                  <option value="{{ m.index }}">
                    [{{ m.index }}] {{ m.text[:42] }}{% if m.text|length > 42 %}…{% endif %}
                  </option>
                {% endfor %}
              </select>
            </td>
            <td>
              <input type="number" step="0.001" min="0"
                name="movie_start_{{ item.narration_index }}"
                value="{{ '%.3f'|format(item.movie_start) if item.movie_start is not none else '0.000' }}" />
            </td>
            <td>
              <input type="number" step="0.001" min="0"
                name="movie_end_{{ item.narration_index }}"
                value="{{ '%.3f'|format(item.movie_end) if item.movie_end is not none else '0.000' }}" />
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      <div class="checks">
        <label class="check">
          <input type="checkbox" name="burn_subs" value="1"
            {% if project.settings.burn_subs %}checked{% endif %} />
          Burn subtitles
        </label>
      </div>
      <div class="actions">
        <button type="submit" name="action" value="save_edits">Save edits</button>
        <button type="submit" name="action" value="render_edits">Save + render</button>
        <button class="secondary" type="submit" name="action" value="make_report">
          Thumbnails + HTML report
        </button>
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


def _make_report(project: dict, final_video_path: Path | None = None) -> str:
    """Generate HTML report + thumbs; return report filename."""
    name = project.get("name", "project")
    report_path = OUTPUT_DIR / f"{name}_report.html"
    thumbs_dir = OUTPUT_DIR / f"{name}_report_thumbs"
    generate_html_report(
        project,
        output_html=report_path,
        thumbs_dir=thumbs_dir,
        final_video_path=final_video_path,
    )
    return report_path.name


def _movie_entries_for_project(project: dict | None) -> list[dict]:
    if not project:
        return []
    movie_srt = project.get("paths", {}).get("movie_srt")
    if not movie_srt or not Path(movie_srt).exists():
        return []
    try:
        return parse_srt(movie_srt)
    except (FileNotFoundError, ValueError, OSError):
        return []


def _edits_from_form(form, cut_plan: list[dict]) -> list[dict]:
    edits = []
    for item in cut_plan:
        idx = int(item["narration_index"])
        edits.append(
            {
                "narration_index": idx,
                "matched": form.get(f"matched_{idx}") == "1",
                "movie_start": float(form.get(f"movie_start_{idx}") or 0),
                "movie_end": float(form.get(f"movie_end_{idx}") or 0),
                "assign_movie_index": form.get(f"assign_movie_{idx}") or "",
            }
        )
    return edits


@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    output_name = None
    info = None
    project = None
    batch_results = None
    report_name = None

    if LAST_PROJECT.exists():
        try:
            project = load_project(LAST_PROJECT)
        except (ValueError, FileNotFoundError, OSError):
            project = None

    if request.method == "POST":
        action = request.form.get("action", "create")
        try:
            OUTPUT_DIR.mkdir(exist_ok=True)
            BATCH_DIR.mkdir(exist_ok=True)

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
                    quality="fast",
                    transition="fade",
                    transition_duration=0.35,
                )
                _persist_project(project)
                save_project(project, BATCH_DIR / "sample_project.json")
                result, info = render_project(
                    project, OUTPUT_DIR / "sample_project_final.mp4"
                )
                output_name = result.name
                report_name = _make_report(project, final_video_path=result)

            elif action == "create":
                sync = request.form.get("sync_to_narration") == "1"
                burn = request.form.get("burn_subs") == "1"
                do_render = request.form.get("render_now") == "1"
                quality = request.form.get("quality") or DEFAULT_QUALITY
                transition = request.form.get("transition") or "fade"
                transition_duration = float(
                    request.form.get("transition_duration") or 0.35
                )

                if request.form.get("save_as_defaults") == "1":
                    save_config(
                        {
                            "quality": quality,
                            "transition": transition,
                            "transition_duration": transition_duration,
                            "sync_to_narration": sync,
                            "burn_subs": burn,
                        }
                    )

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
                    quality=quality,
                    transition=transition,
                    transition_duration=transition_duration,
                )
                _persist_project(project)
                save_project(project, BATCH_DIR / "upload_project.json")

                if do_render:
                    result, info = render_project(
                        project, OUTPUT_DIR / "upload_project_final.mp4"
                    )
                    output_name = result.name
                    report_name = _make_report(project, final_video_path=result)

            elif action == "load_project":
                project_file = request.files.get("project_file")
                if not project_file or not project_file.filename:
                    raise ValueError("Project JSON file select karo.")
                saved = _save_upload(project_file, "uploaded_project.json")
                project = load_project(saved)
                _persist_project(project)
                if request.form.get("render_now") == "1":
                    result, info = render_project(
                        project, OUTPUT_DIR / "loaded_project_final.mp4"
                    )
                    output_name = result.name
                    report_name = _make_report(project, final_video_path=result)

            elif action == "copy_to_batch":
                if not LAST_PROJECT.exists():
                    raise ValueError("Pehle project create/load karo.")
                project = load_project(LAST_PROJECT)
                dest = BATCH_DIR / f"{project.get('name', 'project')}.json"
                save_project(project, dest)
                info = {"copied_to": str(dest), **project.get("stats", {}), "quality": project.get("settings", {}).get("quality"), "matched": project["stats"]["matched"], "total_narration_lines": project["stats"]["total_narration_lines"]}

            elif action == "batch_render":
                quality = request.form.get("quality") or None
                batch_results = batch_render(
                    BATCH_DIR,
                    output_dir=OUTPUT_DIR / "batch_output",
                    quality_override=quality or None,
                )
                if LAST_PROJECT.exists():
                    project = load_project(LAST_PROJECT)

            elif action in ("save_edits", "render_edits"):
                if not LAST_PROJECT.exists():
                    raise ValueError("Pehle project create/load karo.")
                project = load_project(LAST_PROJECT)
                movie_entries = _movie_entries_for_project(project)
                edits = _edits_from_form(request.form, project["cut_plan"])
                sync = bool(project.get("settings", {}).get("sync_to_narration", True))
                project["cut_plan"] = apply_cut_plan_edits(
                    project["cut_plan"],
                    edits,
                    movie_entries=movie_entries,
                    sync_to_narration=sync,
                )
                project["stats"] = summarize_cut_plan(project["cut_plan"])
                project.setdefault("settings", {})
                project["settings"]["burn_subs"] = request.form.get("burn_subs") == "1"
                project["settings"]["quality"] = (
                    request.form.get("quality") or DEFAULT_QUALITY
                )
                project["settings"]["transition"] = (
                    request.form.get("transition") or "fade"
                )
                project["settings"]["transition_duration"] = float(
                    request.form.get("transition_duration") or 0.35
                )
                _persist_project(project)
                save_project(
                    project, BATCH_DIR / f"{project.get('name', 'project')}.json"
                )

                if action == "render_edits":
                    result, info = render_project(
                        project, OUTPUT_DIR / "edited_project_final.mp4"
                    )
                    output_name = result.name
                    report_name = _make_report(project, final_video_path=result)

            elif action == "make_report":
                if not LAST_PROJECT.exists():
                    raise ValueError("Pehle project create/load karo.")
                project = load_project(LAST_PROJECT)
                report_name = _make_report(project)

            else:
                raise ValueError(f"Unknown action: {action}")

        except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
            error = str(exc)
            if LAST_PROJECT.exists() and project is None:
                try:
                    project = load_project(LAST_PROJECT)
                except (ValueError, FileNotFoundError, OSError):
                    project = None

    movie_entries = _movie_entries_for_project(project)

    return render_template_string(
        PAGE,
        error=error,
        output_name=output_name,
        info=info,
        project=project,
        movie_entries=movie_entries,
        batch_results=batch_results,
        report_name=report_name,
        qualities=QUALITY_PRESETS,
        default_quality=DEFAULT_QUALITY,
        transitions=TRANSITION_OPTIONS,
        cfg=load_config(),
    )


@app.route("/download/<path:filename>")
def download_output(filename: str):
    safe_name = Path(filename).name
    path = OUTPUT_DIR / safe_name
    if not path.exists():
        # also allow batch_output files
        batch_path = OUTPUT_DIR / "batch_output" / safe_name
        path = batch_path if batch_path.exists() else path
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


@app.route("/report/<path:subpath>")
def view_report(subpath: str):
    """
    Serve report HTML and its thumbnail folder.

    Example:
      /report/sample_project_report.html
      /report/sample_project_report_thumbs/narration_001.jpg
    """
    root = OUTPUT_DIR.resolve()
    path = (OUTPUT_DIR / subpath).resolve()
    if root not in path.parents and path != root:
        return "Invalid path.", 400
    if not path.exists() or not path.is_file():
        return "File nahi mili.", 404
    return send_file(path)


if __name__ == "__main__":
    print("Test page: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
