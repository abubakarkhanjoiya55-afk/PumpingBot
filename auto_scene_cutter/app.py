"""
SceneCut Pro — Main Editor server.

Reference-style dark editor UI + Stage 1/2 APIs.
Open: http://localhost:5000
"""

from __future__ import annotations

import shutil
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from scene_clustering import cluster_movie_scenes, merge_short_scenes
from srt_parser import parse_narration_srt, parse_srt
from video_cutter import create_sample_video

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "_uploads"
OUTPUT_DIR = BASE_DIR / "output"

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)

# Remember last uploaded paths for auto-cut
SESSION = {
    "movie": None,
    "movie_srt": None,
    "narration_audio": None,
    "narration_srt": None,
}


def _ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)


def _file_meta(path: Path) -> str:
    if not path.exists():
        return "missing"
    size = path.stat().st_size
    if size >= 1024 * 1024:
        size_txt = f"{size / (1024 * 1024):.1f} MB"
    elif size >= 1024:
        size_txt = f"{size / 1024:.1f} KB"
    else:
        size_txt = f"{size} B"
    return size_txt


def _save_upload(file_storage, filename: str) -> Path:
    _ensure_dirs()
    path = UPLOAD_DIR / filename
    file_storage.save(path)
    return path


@app.get("/")
def index():
    """Main Editor Screen (reference layout)."""
    return render_template("editor.html")


@app.post("/api/upload")
def api_upload():
    """Upload one media/srt file into the working session."""
    kind = (request.form.get("kind") or "").strip()
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "File missing"}), 400

    mapping = {
        "movie": ("movie_upload.mp4", "movie"),
        "movie_srt": ("movie_upload.srt", "movie_srt"),
        "narration_audio": ("narration_upload_audio", "narration_audio"),
        "narration_srt": ("narration_upload.srt", "narration_srt"),
    }
    if kind not in mapping:
        return jsonify({"error": f"Unknown kind: {kind}"}), 400

    filename, session_key = mapping[kind]
    # Keep original extension when useful
    suffix = Path(file.filename).suffix
    if kind == "movie" and suffix:
        filename = f"movie_upload{suffix}"
    if kind == "narration_audio" and suffix:
        filename = f"narration_upload_audio{suffix}"

    path = _save_upload(file, filename)
    SESSION[session_key] = str(path)

    return jsonify(
        {
            "ok": True,
            "filename": file.filename,
            "meta": _file_meta(path),
            "kind": kind,
        }
    )


@app.post("/api/load-sample")
def api_load_sample():
    """Load bundled sample movie + SRTs for quick demo."""
    _ensure_dirs()
    try:
        sample_video = BASE_DIR / "sample_movie.mp4"
        if not sample_video.exists():
            create_sample_video(sample_video, duration_seconds=20.0)

        # Prefer cluster sample (clear scene gaps); fallback to basic sample
        movie_srt = BASE_DIR / "sample_movie_cluster.srt"
        if not movie_srt.exists():
            movie_srt = BASE_DIR / "sample_movie.srt"
        narration_srt = BASE_DIR / "sample_narration.srt"
        narration_audio = BASE_DIR / "sample_narration.m4a"

        SESSION["movie"] = str(sample_video)
        SESSION["movie_srt"] = str(movie_srt)
        SESSION["narration_srt"] = str(narration_srt)
        SESSION["narration_audio"] = (
            str(narration_audio) if narration_audio.exists() else None
        )

        return jsonify(
            {
                "ok": True,
                "files": {
                    "movie": sample_video.name,
                    "movie_meta": _file_meta(sample_video),
                    "movie_srt": movie_srt.name,
                    "movie_srt_meta": _file_meta(movie_srt),
                    "narration_srt": narration_srt.name,
                    "narration_srt_meta": _file_meta(narration_srt),
                    "narration_audio": narration_audio.name if narration_audio.exists() else None,
                    "narration_audio_meta": (
                        _file_meta(narration_audio) if narration_audio.exists() else None
                    ),
                    "movie_url": "/api/media/movie",
                },
            }
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/auto-cut")
def api_auto_cut():
    """
    Stage 1 + Stage 2 pipeline for the editor:
      parse movie SRT → cluster scenes → merge short scenes
    """
    payload = request.get_json(silent=True) or {}
    gap_threshold = float(payload.get("gap_threshold", 6.0))
    min_duration = float(payload.get("min_duration", 2.0))
    use_sample = bool(payload.get("use_sample", False))

    try:
        if use_sample and not SESSION.get("movie_srt"):
            # Auto-load sample paths
            api_load_sample()

        movie_srt = SESSION.get("movie_srt")
        if not movie_srt or not Path(movie_srt).exists():
            return jsonify(
                {"error": "Movie SRT load karo, ya pehle 'Load Sample' dabao."}
            ), 400

        entries = parse_srt(movie_srt)
        scenes = cluster_movie_scenes(entries, gap_threshold=gap_threshold)
        scenes = merge_short_scenes(scenes, min_duration=min_duration)

        narration_lines = None
        narration_srt = SESSION.get("narration_srt")
        if narration_srt and Path(narration_srt).exists():
            narration_lines = len(parse_narration_srt(narration_srt))

        return jsonify(
            {
                "ok": True,
                "subtitle_count": len(entries),
                "narration_lines": narration_lines,
                "scenes": scenes,
                "files": {
                    "movie_srt": Path(movie_srt).name,
                    "movie_srt_meta": _file_meta(Path(movie_srt)),
                    "narration_srt": Path(narration_srt).name if narration_srt else None,
                    "narration_srt_meta": (
                        _file_meta(Path(narration_srt)) if narration_srt else None
                    ),
                    "movie_url": "/api/media/movie" if SESSION.get("movie") else None,
                },
                "settings": {
                    "gap_threshold": gap_threshold,
                    "min_duration": min_duration,
                },
            }
        )
    except (FileNotFoundError, ValueError, OSError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/media/movie")
def api_media_movie():
    """Serve currently loaded movie for the HTML5 player."""
    path = SESSION.get("movie")
    if not path or not Path(path).exists():
        return jsonify({"error": "Movie nahi mili"}), 404
    return send_file(path)


@app.get("/api/media/narration")
def api_media_narration():
    path = SESSION.get("narration_audio")
    if not path or not Path(path).exists():
        return jsonify({"error": "Narration audio nahi mili"}), 404
    return send_file(path)


@app.get("/health")
def health():
    return jsonify({"ok": True, "app": "SceneCut Pro Editor"})


if __name__ == "__main__":
    _ensure_dirs()
    print("SceneCut Pro Editor: http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
