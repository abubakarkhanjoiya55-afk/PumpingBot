"""
SceneCut Pro — Main Editor server.

UI wired to Spec backend Stages 1→5:
  parse → cluster → match → cut → export
Open: http://127.0.0.1:5000
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from cutting_engine import cut_from_match_plan
from export_engine import export_final_video, run_stage1_to_stage5
from final_render import create_sample_narration_audio
from matching_engine import rematch_plan_item, run_stage1_to_stage3, summarize_match_plan
from srt_parser import parse_narration_srt
from video_cutter import create_sample_video

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "_uploads"
OUTPUT_DIR = BASE_DIR / "output"

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)

SESSION = {
    "movie": None,
    "movie_srt": None,
    "narration_audio": None,
    "narration_srt": None,
    "final_video": None,
    "cut_only_video": None,
    "timeline_srt": None,
    "last_match_plan": None,
    "scenes": None,
    "settings": {
        "max_clip_duration": 5.0,
        "burn_subs": True,
        "gap_threshold": 6.0,
        "min_duration": 2.0,
    },
}


def _ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)


def _file_meta(path: Path) -> str:
    if not path.exists():
        return "missing"
    size = path.stat().st_size
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _save_upload(file_storage, filename: str) -> Path:
    _ensure_dirs()
    path = UPLOAD_DIR / filename
    file_storage.save(path)
    return path


def _load_sample_into_session() -> dict:
    """Prepare bundled sample media/SRTs in SESSION."""
    _ensure_dirs()
    sample_video = BASE_DIR / "sample_movie.mp4"
    # Cluster sample goes past 50s — keep video long enough for Stage 4/5
    create_sample_video(sample_video, duration_seconds=60.0)

    movie_srt = BASE_DIR / "sample_movie_cluster.srt"
    if not movie_srt.exists():
        movie_srt = BASE_DIR / "sample_movie.srt"
    narration_srt = BASE_DIR / "sample_narration.srt"
    narration_audio = BASE_DIR / "sample_narration.m4a"

    try:
        create_sample_narration_audio(
            parse_narration_srt(str(narration_srt)),
            narration_audio,
        )
    except (OSError, RuntimeError, ValueError):
        narration_audio = None

    SESSION["movie"] = str(sample_video)
    SESSION["movie_srt"] = str(movie_srt)
    SESSION["narration_srt"] = str(narration_srt)
    SESSION["narration_audio"] = str(narration_audio) if narration_audio else None

    return {
        "movie": sample_video.name,
        "movie_meta": _file_meta(sample_video),
        "movie_srt": movie_srt.name,
        "movie_srt_meta": _file_meta(movie_srt),
        "narration_srt": narration_srt.name,
        "narration_srt_meta": _file_meta(narration_srt),
        "narration_audio": Path(narration_audio).name if narration_audio else None,
        "narration_audio_meta": _file_meta(Path(narration_audio)) if narration_audio else None,
        "movie_url": "/api/media/movie",
    }


@app.get("/")
def index():
    return render_template("editor.html")


@app.post("/api/upload")
def api_upload():
    kind = (request.form.get("kind") or "").strip()
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "File missing"}), 400

    mapping = {
        "movie": "movie",
        "movie_srt": "movie_srt",
        "narration_audio": "narration_audio",
        "narration_srt": "narration_srt",
    }
    if kind not in mapping:
        return jsonify({"error": f"Unknown kind: {kind}"}), 400

    suffix = Path(file.filename).suffix or ""
    filename = {
        "movie": f"movie_upload{suffix or '.mp4'}",
        "movie_srt": "movie_upload.srt",
        "narration_audio": f"narration_upload_audio{suffix or '.m4a'}",
        "narration_srt": "narration_upload.srt",
    }[kind]

    path = _save_upload(file, filename)
    SESSION[mapping[kind]] = str(path)

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
    try:
        files = _load_sample_into_session()
        return jsonify({"ok": True, "files": files})
    except (OSError, RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500


@app.post("/api/auto-cut")
def api_auto_cut():
    """
    Full Spec engine for the editor:
      Stage 1→5 (parse/cluster/match/cut/export)

    Optional body:
      mode: "full" (default) | "match_only"
      max_clip_duration: 5.0
      burn_subs: true
    """
    payload = request.get_json(silent=True) or {}
    mode = (payload.get("mode") or "full").strip().lower()
    max_clip = float(payload.get("max_clip_duration", 5.0))
    burn_subs = bool(payload.get("burn_subs", True))
    use_sample = bool(payload.get("use_sample", False))
    gap_threshold = float(payload.get("gap_threshold", 6.0))
    min_duration = float(payload.get("min_duration", 2.0))

    try:
        if use_sample or not SESSION.get("movie_srt") or not SESSION.get("movie"):
            if use_sample or not SESSION.get("movie_srt"):
                _load_sample_into_session()

        movie = SESSION.get("movie")
        movie_srt = SESSION.get("movie_srt")
        narration_srt = SESSION.get("narration_srt")
        narration_audio = SESSION.get("narration_audio")

        if not movie or not Path(movie).exists():
            return jsonify({"error": "Movie video load karo (ya Load Sample)."}), 400
        if not movie_srt or not Path(movie_srt).exists():
            return jsonify({"error": "Movie SRT load karo (ya Load Sample)."}), 400
        if not narration_srt or not Path(narration_srt).exists():
            return jsonify({"error": "Narration SRT load karo (ya Load Sample)."}), 400

        _ensure_dirs()

        settings = {
            "max_clip_duration": max_clip,
            "burn_subs": burn_subs,
            "gap_threshold": gap_threshold,
            "min_duration": min_duration,
        }
        SESSION["settings"] = settings

        if mode == "match_only":
            result = run_stage1_to_stage3(
                movie_srt_path=movie_srt,
                narration_srt_path=narration_srt,
                gap_threshold=gap_threshold,
                min_scene_duration=min_duration,
                max_clip_duration=max_clip,
            )
            SESSION["last_match_plan"] = result["match_plan"]
            SESSION["scenes"] = result["scenes"]
            SESSION["final_video"] = None
            return jsonify(
                {
                    "ok": True,
                    "mode": "match_only",
                    "subtitle_count": result["movie_subtitle_count"],
                    "narration_lines": result["narration_count"],
                    "scenes": result["scenes"],
                    "match_plan": result["match_plan"],
                    "stats": result["stats"],
                    "final_video_url": None,
                    "source_movie_url": "/api/media/movie",
                    "settings": settings,
                }
            )

        output = OUTPUT_DIR / "editor_final.mp4"
        result = run_stage1_to_stage5(
            video_path=movie,
            movie_srt_path=movie_srt,
            narration_srt_path=narration_srt,
            output_path=output,
            narration_audio_path=narration_audio,
            gap_threshold=gap_threshold,
            min_scene_duration=min_duration,
            max_clip_duration=max_clip,
            quality="fast",
            burn_subs=burn_subs,
        )

        SESSION["last_match_plan"] = result["match_plan"]
        SESSION["scenes"] = result["scenes"]
        SESSION["final_video"] = result["output_video"]
        SESSION["cut_only_video"] = result.get("cut_only_video")
        SESSION["timeline_srt"] = result.get("timeline_srt")

        return jsonify(
            {
                "ok": True,
                "mode": "full",
                "subtitle_count": result["movie_subtitle_count"],
                "narration_lines": result["narration_count"],
                "scenes": result["scenes"],
                "match_plan": result["match_plan"],
                "stats": result["stats"],
                "final_video_url": "/api/media/final",
                "cut_only_url": "/api/media/cut",
                "timeline_srt_url": "/api/media/timeline-srt",
                "source_movie_url": "/api/media/movie",
                "settings": settings,
            }
        )
    except (FileNotFoundError, ValueError, OSError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


def _export_from_session_plan() -> dict:
    """Re-cut + re-export using SESSION match_plan (after manual rematch)."""
    movie = SESSION.get("movie")
    plan = SESSION.get("last_match_plan")
    if not movie or not Path(movie).exists():
        raise ValueError("Movie nahi mili — pehle Auto-Cut / Load Sample karo.")
    if not plan:
        raise ValueError("Match plan empty hai — pehle Auto-Cut chalao.")

    settings = SESSION.get("settings") or {}
    max_clip = float(settings.get("max_clip_duration", 5.0))
    burn_subs = bool(settings.get("burn_subs", True))
    _ = max_clip  # kept on settings for rematch helpers

    _ensure_dirs()
    cut_path = OUTPUT_DIR / "editor_final_cut_only.mp4"
    final_path = OUTPUT_DIR / "editor_final.mp4"

    cut_from_match_plan(
        video_path=movie,
        match_plan=plan,
        output_path=cut_path,
        quality="fast",
    )
    export_info = export_final_video(
        cut_video_path=cut_path,
        match_plan=plan,
        output_path=final_path,
        source_narration_audio=SESSION.get("narration_audio"),
        burn_subs=burn_subs,
    )

    SESSION["cut_only_video"] = str(cut_path)
    SESSION["final_video"] = export_info["output_video"]
    SESSION["timeline_srt"] = export_info["timeline_srt"]

    return {
        "ok": True,
        "match_plan": plan,
        "scenes": SESSION.get("scenes") or [],
        "stats": summarize_match_plan(plan),
        "final_video_url": "/api/media/final",
        "cut_only_url": "/api/media/cut",
        "timeline_srt_url": "/api/media/timeline-srt",
        "settings": settings,
    }


@app.post("/api/rematch")
def api_rematch():
    """
    Manual rematch one narration line to a different scene (or skip).

    Body:
      narration_index: int
      scene_id: int | null   (null = skip / unmatch)
      reexport: bool = true
    """
    payload = request.get_json(silent=True) or {}
    if "narration_index" not in payload:
        return jsonify({"error": "narration_index required"}), 400

    plan = SESSION.get("last_match_plan")
    scenes = SESSION.get("scenes")
    if not plan or not scenes:
        return jsonify({"error": "Pehle Auto-Cut chalao (match plan missing)."}), 400

    narration_index = int(payload["narration_index"])
    scene_raw = payload.get("scene_id", None)
    scene_id = None if scene_raw is None or scene_raw == "" else int(scene_raw)
    reexport = bool(payload.get("reexport", True))
    max_clip = float((SESSION.get("settings") or {}).get("max_clip_duration", 5.0))

    try:
        new_plan = rematch_plan_item(
            plan,
            scenes,
            narration_index=narration_index,
            scene_id=scene_id,
            max_clip_duration=max_clip,
        )
        SESSION["last_match_plan"] = new_plan

        if reexport:
            result = _export_from_session_plan()
            return jsonify(result)

        return jsonify(
            {
                "ok": True,
                "match_plan": new_plan,
                "scenes": scenes,
                "stats": summarize_match_plan(new_plan),
                "final_video_url": None,
                "settings": SESSION.get("settings") or {},
            }
        )
    except (ValueError, OSError, RuntimeError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/reexport")
def api_reexport():
    """Re-run cut+export from the current (possibly edited) match plan."""
    try:
        return jsonify(_export_from_session_plan())
    except (ValueError, OSError, RuntimeError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/session")
def api_session():
    """Current editor session snapshot (for UI refresh)."""
    plan = SESSION.get("last_match_plan")
    scenes = SESSION.get("scenes")
    return jsonify(
        {
            "ok": True,
            "has_plan": bool(plan),
            "match_plan": plan or [],
            "scenes": scenes or [],
            "stats": summarize_match_plan(plan) if plan else None,
            "settings": SESSION.get("settings") or {},
            "final_ready": bool(SESSION.get("final_video") and Path(SESSION["final_video"]).exists()),
            "final_video_url": "/api/media/final" if SESSION.get("final_video") else None,
        }
    )


@app.get("/api/media/movie")
def api_media_movie():
    path = SESSION.get("movie")
    if not path or not Path(path).exists():
        return jsonify({"error": "Movie nahi mili"}), 404
    return send_file(path)


@app.get("/api/media/final")
def api_media_final():
    path = SESSION.get("final_video")
    if not path or not Path(path).exists():
        return jsonify({"error": "Final video abhi ready nahi"}), 404
    return send_file(path, download_name="scenecut_final.mp4")


@app.get("/api/media/cut")
def api_media_cut():
    path = SESSION.get("cut_only_video")
    if not path or not Path(path).exists():
        return jsonify({"error": "Cut video abhi ready nahi"}), 404
    return send_file(path, download_name="scenecut_cut_only.mp4")


@app.get("/api/media/timeline-srt")
def api_media_timeline_srt():
    path = SESSION.get("timeline_srt")
    if not path or not Path(path).exists():
        return jsonify({"error": "Timeline SRT abhi ready nahi"}), 404
    return send_file(path, download_name="scenecut_timeline.srt", as_attachment=True)


@app.get("/api/media/narration")
def api_media_narration():
    path = SESSION.get("narration_audio")
    if not path or not Path(path).exists():
        return jsonify({"error": "Narration audio nahi mili"}), 404
    return send_file(path)


@app.get("/health")
def health():
    return jsonify({"ok": True, "app": "SceneCut Pro Editor", "engine": "stages-1-to-5"})


if __name__ == "__main__":
    _ensure_dirs()
    print("SceneCut Pro Editor: http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
