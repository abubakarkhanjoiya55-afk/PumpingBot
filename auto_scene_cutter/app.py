"""
Local test page for Stage 1 + Stage 2 + Stage 3.

Open in browser:
    http://localhost:5000
"""

from pathlib import Path

from flask import Flask, render_template_string, request, send_file

from scene_matcher import match_scenes, summarize_cut_plan
from srt_parser import parse_narration_srt, parse_srt
from video_cutter import build_and_cut, create_sample_video

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR = BASE_DIR / "_uploads"

PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Auto Scene Cutter — Stage 3 Test</title>
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
    .wrap { max-width: 1100px; margin: 0 auto; }
    h1 { margin: 0 0 8px; font-size: 1.6rem; letter-spacing: 0.02em; }
    .sub { color: var(--muted); margin-bottom: 24px; }
    form {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 20px;
      display: grid;
      gap: 14px;
    }
    label { display: grid; gap: 6px; font-size: 0.92rem; color: var(--muted); }
    input[type="file"] {
      color: var(--text);
      background: #121820;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
    }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; }
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
    button.secondary {
      background: transparent;
      color: var(--text);
      border: 1px solid var(--line);
    }
    .error {
      margin-top: 16px;
      padding: 12px 14px;
      border-radius: 8px;
      background: rgba(255, 107, 107, 0.12);
      border: 1px solid rgba(255, 107, 107, 0.4);
      color: #ffc9c9;
    }
    .success {
      margin-top: 16px;
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
    .grid {
      margin-top: 22px;
      display: grid;
      gap: 16px;
      grid-template-columns: 1fr;
    }
    @media (min-width: 860px) {
      .grid { grid-template-columns: 1fr 1fr; }
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 16px;
    }
    section.full { grid-column: 1 / -1; }
    section h2 {
      margin: 0 0 6px;
      font-size: 1.05rem;
    }
    .count { color: var(--ok); font-size: 0.9rem; margin-bottom: 12px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
    th, td {
      text-align: left;
      padding: 8px 6px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }
    th { color: var(--muted); font-weight: 600; }
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
    .score { color: var(--warn); white-space: nowrap; }
    video {
      width: 100%;
      max-width: 720px;
      margin-top: 12px;
      border-radius: 10px;
      background: #000;
      border: 1px solid var(--line);
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Auto Scene Cutter</h1>
    <p class="sub">
      Stage 1 parse → Stage 2 match → Stage 3 ffmpeg cut/join.
    </p>

    <form method="post" enctype="multipart/form-data">
      <label>
        Movie video (optional for sample test)
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
      <div class="actions">
        <button type="submit" name="action" value="upload">
          Parse + Match + Cut
        </button>
        <button class="secondary" type="submit" name="action" value="sample">
          Sample se full test (video bhi banega)
        </button>
      </div>
    </form>

    {% if error %}
      <div class="error">{{ error }}</div>
    {% endif %}

    {% if output_name %}
      <div class="success">
        <span>Stage 3 output ready: {{ output_name }}</span>
        <a class="btn" href="{{ url_for('download_output', filename=output_name) }}">
          Download cut video
        </a>
      </div>
      <section style="margin-top:16px;">
        <h2>Preview</h2>
        <video controls src="{{ url_for('download_output', filename=output_name) }}"></video>
      </section>
    {% endif %}

    {% if movie_entries is not none and narration_entries is not none %}
      <div class="grid">
        <section>
          <h2>Stage 1 — Movie SRT</h2>
          <div class="count">Total entries: {{ movie_entries|length }}</div>
          <table>
            <thead>
              <tr><th>#</th><th>Start</th><th>End</th><th>Text</th></tr>
            </thead>
            <tbody>
              {% for e in movie_entries[:5] %}
              <tr>
                <td>{{ e.index }}</td>
                <td class="time">{{ '%.3f'|format(e.start) }}s</td>
                <td class="time">{{ '%.3f'|format(e.end) }}s</td>
                <td>{{ e.text }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </section>

        <section>
          <h2>Stage 1 — Narration SRT</h2>
          <div class="count">Total entries: {{ narration_entries|length }}</div>
          <table>
            <thead>
              <tr><th>#</th><th>Start</th><th>End</th><th>Text</th></tr>
            </thead>
            <tbody>
              {% for e in narration_entries[:5] %}
              <tr>
                <td>{{ e.index }}</td>
                <td class="time">{{ '%.3f'|format(e.start) }}s</td>
                <td class="time">{{ '%.3f'|format(e.end) }}s</td>
                <td>{{ e.text }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </section>

        {% if cut_plan is not none %}
        <section class="full">
          <h2>Stage 2 — Cut Plan</h2>
          <div class="count">
            Matched: {{ stats.matched }} /
            {{ stats.total_narration_lines }}
            (unmatched: {{ stats.unmatched }})
          </div>
          <table>
            <thead>
              <tr>
                <th>Status</th>
                <th>Narration</th>
                <th>Movie cut</th>
                <th>Matched dialogue</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {% for item in cut_plan %}
              <tr>
                <td>
                  {% if item.matched %}
                    <span class="badge ok">MATCH</span>
                  {% else %}
                    <span class="badge no">NO MATCH</span>
                  {% endif %}
                </td>
                <td>
                  <strong>[{{ item.narration_index }}]</strong>
                  {{ item.narration_text }}
                </td>
                <td class="time">
                  {% if item.matched %}
                    {{ '%.2f'|format(item.movie_start) }}s
                    → {{ '%.2f'|format(item.movie_end) }}s
                  {% else %}
                    —
                  {% endif %}
                </td>
                <td>
                  {% if item.matched %}
                    [{{ item.movie_index }}] {{ item.movie_text }}
                  {% else %}
                    —
                  {% endif %}
                </td>
                <td class="score">
                  {% if item.matched %}{{ '%.3f'|format(item.score) }}{% else %}0{% endif %}
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </section>
        {% endif %}
      </div>
    {% endif %}
  </div>
</body>
</html>
"""


def _save_upload(file_storage, filename: str) -> Path:
    """Save an uploaded file into a temp folder and return its path."""
    UPLOAD_DIR.mkdir(exist_ok=True)
    path = UPLOAD_DIR / filename
    file_storage.save(path)
    return path


@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    movie_entries = None
    narration_entries = None
    cut_plan = None
    stats = None
    output_name = None

    if request.method == "POST":
        action = request.form.get("action", "upload")
        try:
            OUTPUT_DIR.mkdir(exist_ok=True)

            if action == "sample":
                movie_srt_path = BASE_DIR / "sample_movie.srt"
                narration_srt_path = BASE_DIR / "sample_narration.srt"
                video_path = BASE_DIR / "sample_movie.mp4"
                if not video_path.exists():
                    create_sample_video(video_path, duration_seconds=20.0)
                output_path = OUTPUT_DIR / "sample_cut.mp4"
            else:
                movie_file = request.files.get("movie_srt")
                narration_file = request.files.get("narration_srt")
                video_file = request.files.get("movie_video")

                if not movie_file or not movie_file.filename:
                    raise ValueError("Movie SRT file select karo.")
                if not narration_file or not narration_file.filename:
                    raise ValueError("Narration SRT file select karo.")
                if not video_file or not video_file.filename:
                    raise ValueError(
                        "Movie video select karo, ya sample button use karo."
                    )

                movie_srt_path = _save_upload(movie_file, "movie_upload.srt")
                narration_srt_path = _save_upload(narration_file, "narration_upload.srt")
                video_path = _save_upload(video_file, "movie_upload.mp4")
                output_path = OUTPUT_DIR / "upload_cut.mp4"

            movie_entries = parse_srt(str(movie_srt_path))
            narration_entries = parse_narration_srt(str(narration_srt_path))
            cut_plan = match_scenes(movie_entries, narration_entries)
            stats = summarize_cut_plan(cut_plan)

            # Stage 3: actually cut + join
            build_and_cut(
                video_path,
                movie_srt_path,
                narration_srt_path,
                output_path,
            )
            output_name = output_path.name

        except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
            error = str(exc)

    return render_template_string(
        PAGE,
        error=error,
        movie_entries=movie_entries,
        narration_entries=narration_entries,
        cut_plan=cut_plan,
        stats=stats,
        output_name=output_name,
    )


@app.route("/download/<path:filename>")
def download_output(filename: str):
    """Serve a generated cut video from the output folder."""
    # Keep downloads inside output/ only (simple path safety)
    safe_name = Path(filename).name
    path = OUTPUT_DIR / safe_name
    if not path.exists():
        return "File nahi mili.", 404
    return send_file(path, as_attachment=False, download_name=safe_name)


if __name__ == "__main__":
    print("Test page: http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
