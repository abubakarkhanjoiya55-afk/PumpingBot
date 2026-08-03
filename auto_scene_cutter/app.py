"""
SceneCut Pro+ — Main Editor server.

Stages 1→5 engine + Pro features:
  settings, live job progress, project save/load,
  trim/reorder, HTML report

Open: http://127.0.0.1:5000
"""

from __future__ import annotations

import copy
import os
import sys
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from cutting_engine import cut_from_match_plan
from export_engine import export_final_video, run_stage1_to_stage5
from final_render import create_sample_narration_audio
from matching_engine import rematch_plan_item, run_stage1_to_stage3, summarize_match_plan
from pro_plus import (
    JobProgress,
    build_editor_project,
    generate_match_plan_report,
    load_editor_project,
    normalize_settings,
    reorder_match_plan,
    save_editor_project,
    settings_options,
    trim_match_clip,
)
from srt_parser import parse_narration_srt
from video_cutter import create_sample_video


def _resource_dir() -> Path:
    """Templates/static/samples — PyInstaller extract dir when frozen."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def _data_dir() -> Path:
    """Writable app data (uploads/output/projects)."""
    if getattr(sys, "frozen", False):
        # Prefer install folder next to the .exe; fallback to LocalAppData
        exe_dir = Path(sys.executable).resolve().parent
        if os.access(exe_dir, os.W_OK):
            return exe_dir
        local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
        return local / "SceneCutProPlus"
    return Path(__file__).resolve().parent


RESOURCE_DIR = _resource_dir()
BASE_DIR = _data_dir()
UPLOAD_DIR = BASE_DIR / "_uploads"
OUTPUT_DIR = BASE_DIR / "output"
PROJECTS_DIR = BASE_DIR / "projects"

app = Flask(
    __name__,
    template_folder=str(RESOURCE_DIR / "templates"),
    static_folder=str(RESOURCE_DIR / "static"),
)
# Full-length movies (2GB+). Override with SCENECUT_MAX_UPLOAD_MB.
# Chunked uploads send small parts; this caps total movie size + single-request body.
_MAX_UPLOAD_MB = int(os.environ.get("SCENECUT_MAX_UPLOAD_MB", "20480"))  # 20 GB default
app.config["MAX_CONTENT_LENGTH"] = _MAX_UPLOAD_MB * 1024 * 1024
app.config["SCENECUT_MAX_UPLOAD_BYTES"] = _MAX_UPLOAD_MB * 1024 * 1024

SESSION = {
    "movie": None,
    "movie_srt": None,
    "narration_audio": None,
    "narration_srt": None,
    "final_video": None,
    "cut_only_video": None,
    "timeline_srt": None,
    "report_html": None,
    "last_match_plan": None,
    "scenes": None,
    "settings": normalize_settings(None),
    "project_name": "scenecut_project",
    "undo_stack": [],
}

JOB = JobProgress()
_JOB_LOCK = threading.Lock()
_JOB_THREAD: threading.Thread | None = None
_UPLOAD_LOCK = threading.Lock()
# In-progress chunked uploads: id -> meta
PENDING_UPLOADS: dict[str, dict] = {}

UPLOAD_KIND_MAP = {
    "movie": "movie",
    "movie_srt": "movie_srt",
    "narration_audio": "narration_audio",
    "narration_srt": "narration_srt",
}
UPLOAD_ALLOWED_EXT = {
    "movie": {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ""},
    "movie_srt": {".srt", ".txt", ""},
    "narration_audio": {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac", ""},
    "narration_srt": {".srt", ".txt", ""},
}
UPLOAD_EXT_HINTS = {
    "movie": "Movie ke liye MP4/MOV/MKV select karo (SRT nahi).",
    "movie_srt": "Movie SRT ke liye .srt file select karo.",
    "narration_audio": "Narration audio ke liye MP3/M4A/WAV select karo.",
    "narration_srt": "Narration timestamps ke liye .srt file select karo.",
}


def _ensure_dirs() -> None:
    UPLOAD_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    PROJECTS_DIR.mkdir(exist_ok=True)


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


def _push_undo() -> None:
    plan = SESSION.get("last_match_plan")
    if not plan:
        return
    stack = SESSION.setdefault("undo_stack", [])
    stack.append(copy.deepcopy(plan))
    if len(stack) > 30:
        del stack[0 : len(stack) - 30]


def _result_payload(extra: dict | None = None) -> dict:
    plan = SESSION.get("last_match_plan") or []
    settings = normalize_settings(SESSION.get("settings"))
    payload = {
        "ok": True,
        "subtitle_count": None,
        "narration_lines": len(plan) if plan else 0,
        "scenes": SESSION.get("scenes") or [],
        "match_plan": plan,
        "stats": summarize_match_plan(plan) if plan else {},
        "final_video_url": (
            "/api/media/final"
            if SESSION.get("final_video") and Path(SESSION["final_video"]).exists()
            else None
        ),
        "cut_only_url": (
            "/api/media/cut"
            if SESSION.get("cut_only_video") and Path(SESSION["cut_only_video"]).exists()
            else None
        ),
        "timeline_srt_url": (
            "/api/media/timeline-srt"
            if SESSION.get("timeline_srt") and Path(SESSION["timeline_srt"]).exists()
            else None
        ),
        "report_url": (
            "/api/media/report"
            if SESSION.get("report_html") and Path(SESSION["report_html"]).exists()
            else None
        ),
        "source_movie_url": "/api/media/movie",
        "settings": settings,
        "project_name": SESSION.get("project_name") or "scenecut_project",
        "can_undo": bool(SESSION.get("undo_stack")),
    }
    if extra:
        payload.update(extra)
    return payload


def _load_sample_into_session() -> dict:
    """Prepare bundled sample media/SRTs in SESSION."""
    _ensure_dirs()
    sample_video = BASE_DIR / "sample_movie.mp4"
    create_sample_video(sample_video, duration_seconds=60.0)

    movie_srt = RESOURCE_DIR / "sample_movie_cluster.srt"
    if not movie_srt.exists():
        movie_srt = RESOURCE_DIR / "sample_movie.srt"
    if not movie_srt.exists():
        movie_srt = BASE_DIR / "sample_movie_cluster.srt"
    narration_srt = RESOURCE_DIR / "sample_narration.srt"
    if not narration_srt.exists():
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
    SESSION["project_name"] = "sample_project"

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


def _merge_settings_from_payload(payload: dict) -> dict:
    current = normalize_settings(SESSION.get("settings"))
    for key in (
        "max_clip_duration",
        "burn_subs",
        "gap_threshold",
        "min_duration",
        "quality",
        "transition",
        "transition_duration",
    ):
        if key in payload:
            current[key] = payload[key]
    settings = normalize_settings(current)
    SESSION["settings"] = settings
    return settings


def _export_from_session_plan(progress_callback=None) -> dict:
    """Re-cut + re-export using SESSION match_plan."""
    movie = SESSION.get("movie")
    plan = SESSION.get("last_match_plan")
    if not movie or not Path(movie).exists():
        raise ValueError("Movie nahi mili — pehle Auto-Cut / Load Sample karo.")
    if not plan:
        raise ValueError("Match plan empty hai — pehle Auto-Cut chalao.")

    settings = normalize_settings(SESSION.get("settings"))
    _ensure_dirs()
    cut_path = OUTPUT_DIR / "editor_final_cut_only.mp4"
    final_path = OUTPUT_DIR / "editor_final.mp4"

    cut_from_match_plan(
        video_path=movie,
        match_plan=plan,
        output_path=cut_path,
        quality=settings["quality"],
        transition=settings["transition"],
        transition_duration=settings["transition_duration"],
        progress=None,
    )
    export_info = export_final_video(
        cut_video_path=cut_path,
        match_plan=plan,
        output_path=final_path,
        source_narration_audio=SESSION.get("narration_audio"),
        burn_subs=settings["burn_subs"],
        progress_callback=progress_callback,
    )

    SESSION["cut_only_video"] = str(cut_path)
    SESSION["final_video"] = export_info["output_video"]
    SESSION["timeline_srt"] = export_info["timeline_srt"]

    # Lightweight report (thumbnails may take a moment)
    try:
        report_path = OUTPUT_DIR / "editor_report.html"
        generate_match_plan_report(
            name=SESSION.get("project_name") or "scenecut_project",
            video_path=movie,
            match_plan=plan,
            output_html=report_path,
            settings=settings,
            final_video_path=export_info["output_video"],
        )
        SESSION["report_html"] = str(report_path)
    except (OSError, RuntimeError, ValueError):
        SESSION["report_html"] = None

    return _result_payload()


def _run_full_pipeline(settings: dict, mode: str = "full") -> dict:
    movie = SESSION.get("movie")
    movie_srt = SESSION.get("movie_srt")
    narration_srt = SESSION.get("narration_srt")
    narration_audio = SESSION.get("narration_audio")

    if not movie_srt or not Path(movie_srt).exists():
        raise ValueError("Movie SRT load karo (ya Load Sample).")
    if not narration_srt or not Path(narration_srt).exists():
        raise ValueError("Narration SRT load karo (ya Load Sample).")

    _ensure_dirs()
    JOB.update(stage="analyze_movie", message="Movie SRT parse + cluster", current=1, total=5)
    JOB.update(stage="analyze_narration", message="Narration parse", current=2, total=5)

    # CapCut-style: match from SRT instantly — movie file not required yet
    if mode == "match_only":
        JOB.update(stage="matching", message="Matching scenes", current=3, total=5)
        result = run_stage1_to_stage3(
            movie_srt_path=movie_srt,
            narration_srt_path=narration_srt,
            gap_threshold=settings["gap_threshold"],
            min_scene_duration=settings["min_duration"],
            max_clip_duration=settings["max_clip_duration"],
        )
        SESSION["last_match_plan"] = result["match_plan"]
        SESSION["scenes"] = result["scenes"]
        SESSION["final_video"] = None
        JOB.update(stage="matching", message="Match only done", current=5, total=5)
        return _result_payload(
            {
                "mode": "match_only",
                "subtitle_count": result["movie_subtitle_count"],
                "narration_lines": result["narration_count"],
                "cut_clip_count": result["stats"]["matched"],
            }
        )

    # Cut+export using an existing match plan (movie sync can finish after match)
    if mode in ("cut_export", "export_only"):
        if not movie or not Path(movie).exists():
            raise ValueError("Movie video abhi server pe nahi — sync complete hone do.")
        if not SESSION.get("last_match_plan"):
            raise ValueError("Pehle match chalao.")
        JOB.update(stage="cutting", message="Cutting clips", current=4, total=5)
        result = _export_from_session_plan(
            progress_callback=lambda msg, cur, tot: JOB.update(
                stage="export" if "Subtitle" in msg or "narration" in msg.lower() else "cutting",
                message=msg,
                current=5 if "Subtitle" in msg else 4,
                total=5,
            )
        )
        JOB.update(stage="export", message="Export done", current=5, total=5)
        return result

    if not movie or not Path(movie).exists():
        raise ValueError("Movie video load karo (ya Load Sample).")

    JOB.update(stage="matching", message="Matching + trim", current=3, total=5)

    def _cb(message: str, current: int, total: int) -> None:
        # Map ffmpeg sub-steps into cutting/export stages
        stage = JOB.snapshot().get("stage") or "cutting"
        if "Stage5" in message or "narration" in message.lower() or "Subtitle" in message:
            stage = "export"
            JOB.update(stage=stage, message=message, current=5, total=5)
        else:
            stage = "cutting"
            JOB.update(stage=stage, message=message, current=4, total=5)

    JOB.update(stage="cutting", message="Cutting clips", current=4, total=5)
    output = OUTPUT_DIR / "editor_final.mp4"
    result = run_stage1_to_stage5(
        video_path=movie,
        movie_srt_path=movie_srt,
        narration_srt_path=narration_srt,
        output_path=output,
        narration_audio_path=narration_audio,
        gap_threshold=settings["gap_threshold"],
        min_scene_duration=settings["min_duration"],
        max_clip_duration=settings["max_clip_duration"],
        quality=settings["quality"],
        transition=settings["transition"],
        transition_duration=settings["transition_duration"],
        burn_subs=settings["burn_subs"],
        progress_callback=_cb,
    )

    SESSION["last_match_plan"] = result["match_plan"]
    SESSION["scenes"] = result["scenes"]
    SESSION["final_video"] = result["output_video"]
    SESSION["cut_only_video"] = result.get("cut_only_video")
    SESSION["timeline_srt"] = result.get("timeline_srt")

    JOB.update(stage="export", message="Building report", current=5, total=5)
    try:
        report_path = OUTPUT_DIR / "editor_report.html"
        generate_match_plan_report(
            name=SESSION.get("project_name") or "scenecut_project",
            video_path=movie,
            match_plan=result["match_plan"],
            output_html=report_path,
            settings=settings,
            final_video_path=result["output_video"],
        )
        SESSION["report_html"] = str(report_path)
    except (OSError, RuntimeError, ValueError):
        SESSION["report_html"] = None

    return _result_payload(
        {
            "mode": "full",
            "subtitle_count": result["movie_subtitle_count"],
            "narration_lines": result["narration_count"],
            "cut_clip_count": result.get("cut_clip_count") or result["stats"]["matched"],
        }
    )


@app.get("/")
def index():
    return render_template("editor.html")


def _max_upload_bytes() -> int:
    return int(app.config.get("SCENECUT_MAX_UPLOAD_BYTES") or (20 * 1024 * 1024 * 1024))


def _disk_free_bytes(path: Path) -> int | None:
    try:
        st = os.statvfs(path)
        return int(st.f_bavail * st.f_frsize)
    except (AttributeError, OSError):
        return None


@app.errorhandler(413)
def _too_large(_err):
    gb = max(1, _max_upload_bytes() // (1024 * 1024 * 1024))
    return jsonify(
        {
            "error": f"File limit ~{gb}GB hai. Agar movie is se bari hai to compress karo, ya /download Student Pack (desktop) use karo.",
        }
    ), 413


def _upload_dest_name(kind: str, suffix: str) -> str:
    return {
        "movie": f"movie_upload{suffix or '.mp4'}",
        "movie_srt": "movie_upload.srt",
        "narration_audio": f"narration_upload_audio{suffix or '.m4a'}",
        "narration_srt": "narration_upload.srt",
    }[kind]


def _upload_tip(kind: str) -> str | None:
    if kind == "movie":
        return "Movie OK. Ab Movie SRT + Narration SRT bhi select karo, phir Export dabao."
    if kind in ("movie_srt", "narration_srt") and SESSION.get("movie"):
        need = []
        if not SESSION.get("movie_srt"):
            need.append("Movie SRT")
        if not SESSION.get("narration_srt"):
            need.append("Narration SRT")
        return "Ab Export dabao." if not need else f"Ab {', '.join(need)} bhi select karo."
    return None


def _validate_upload_kind(kind: str, original_name: str) -> tuple[str | None, str | None]:
    """Return (error, suffix)."""
    if kind not in UPLOAD_KIND_MAP:
        return f"Unknown kind: {kind}", None
    suffix = (Path(original_name).suffix or "").lower()
    if suffix and suffix not in UPLOAD_ALLOWED_EXT[kind]:
        return UPLOAD_EXT_HINTS[kind], None
    return None, suffix


def _finalize_saved_upload(kind: str, path: Path, original_name: str) -> dict:
    SESSION[UPLOAD_KIND_MAP[kind]] = str(path)
    return {
        "ok": True,
        "filename": original_name,
        "meta": _file_meta(path),
        "kind": kind,
        "tip": _upload_tip(kind),
    }


@app.post("/api/upload")
def api_upload():
    kind = (request.form.get("kind") or "").strip()
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "File select nahi hui. Dobara Movie File pe click karke select karo."}), 400

    err, suffix = _validate_upload_kind(kind, file.filename)
    if err:
        return jsonify({"error": err}), 400

    filename = _upload_dest_name(kind, suffix or "")
    try:
        path = _save_upload(file, filename)
        if not path.exists() or path.stat().st_size <= 0:
            return jsonify({"error": "Upload path failed — file save nahi hui. Disk full ya permission issue."}), 500
        return jsonify(_finalize_saved_upload(kind, path, file.filename))
    except OSError as exc:
        return jsonify({"error": f"Upload path failed: {exc}"}), 500
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": f"Upload fail: {exc}"}), 500


@app.post("/api/upload/init")
def api_upload_init():
    """Start a chunked upload (mobile-friendly; survives flaky networks)."""
    payload = request.get_json(silent=True) or {}
    kind = (payload.get("kind") or "").strip()
    original = (payload.get("filename") or "upload.bin").strip() or "upload.bin"
    size = int(payload.get("size") or 0)
    err, suffix = _validate_upload_kind(kind, original)
    if err:
        return jsonify({"error": err}), 400
    if size <= 0:
        return jsonify({"error": "File size invalid."}), 400

    max_bytes = _max_upload_bytes()
    if size > max_bytes:
        gb = max(1, max_bytes // (1024 * 1024 * 1024))
        return jsonify(
            {
                "error": f"Ye movie ~{size / (1024 * 1024):.0f}MB hai — limit ~{gb}GB. Compress karke try karo ya Student Pack desktop use karo.",
            }
        ), 413

    _ensure_dirs()
    free = _disk_free_bytes(UPLOAD_DIR)
    # Need movie + some headroom for ffmpeg outputs
    if free is not None and free < size + (512 * 1024 * 1024):
        free_gb = free / (1024 * 1024 * 1024)
        return jsonify(
            {
                "error": (
                    f"Server disk kam hai (~{free_gb:.1f}GB free) — {size / (1024 * 1024):.0f}MB movie "
                    "yahan fit nahi. /download se Student Pack desktop use karo (wahan bari movie chal jati hai)."
                ),
            }
        ), 507

    upload_id = uuid.uuid4().hex
    dest_name = _upload_dest_name(kind, suffix or "")
    part_path = UPLOAD_DIR / f".part_{upload_id}"
    # Bigger chunks for multi‑GB movies (faster, fewer requests)
    if size >= 2 * 1024 * 1024 * 1024:
        default_chunk = 16 * 1024 * 1024
    elif size >= 1024 * 1024 * 1024:
        default_chunk = 8 * 1024 * 1024
    else:
        default_chunk = 4 * 1024 * 1024
    chunk_size = int(payload.get("chunk_size") or default_chunk)
    chunk_size = max(256 * 1024, min(chunk_size, 32 * 1024 * 1024))
    total_chunks = (size + chunk_size - 1) // chunk_size
    with _UPLOAD_LOCK:
        PENDING_UPLOADS[upload_id] = {
            "kind": kind,
            "original": original,
            "dest_name": dest_name,
            "part_path": str(part_path),
            "size": size,
            "chunk_size": chunk_size,
            "total_chunks": total_chunks,
            "received": set(),
            "lock": threading.Lock(),
        }
    # Sparse pre-size so parallel workers can seek+write safely
    with open(part_path, "wb") as fh:
        if size > 0:
            fh.truncate(size)
    return jsonify(
        {
            "ok": True,
            "upload_id": upload_id,
            "chunk_size": chunk_size,
            "total_chunks": total_chunks,
            "parallel": True,
        }
    )


@app.post("/api/upload/chunk")
def api_upload_chunk():
    upload_id = (request.form.get("upload_id") or "").strip()
    try:
        index = int(request.form.get("index"))
    except (TypeError, ValueError):
        return jsonify({"error": "chunk index missing"}), 400
    chunk = request.files.get("chunk")
    if not upload_id or chunk is None:
        return jsonify({"error": "upload_id/chunk missing"}), 400

    with _UPLOAD_LOCK:
        meta = PENDING_UPLOADS.get(upload_id)
    if not meta:
        return jsonify({"error": "Upload session expire — dobara file select karo."}), 400

    if index < 0 or index >= int(meta["total_chunks"]):
        return jsonify({"error": f"Bad chunk index {index}"}), 400

    data = chunk.read()
    part_path = Path(meta["part_path"])
    offset = index * int(meta["chunk_size"])
    try:
        # Parallel-safe: each chunk writes at its own offset
        with meta["lock"]:
            with open(part_path, "r+b") as fh:
                fh.seek(offset)
                fh.write(data)
            received: set = meta["received"]
            received.add(index)
            done_count = len(received)
    except OSError as exc:
        msg = str(exc)
        if "No space" in msg or getattr(exc, "errno", None) == 28:
            return jsonify(
                {
                    "error": "Disk full — bari movie web pe fit nahi. Student Pack desktop (/download) use karo.",
                }
            ), 507
        return jsonify({"error": f"Upload path failed: {exc}"}), 500

    return jsonify(
        {
            "ok": True,
            "index": index,
            "received": done_count,
            "total_chunks": meta["total_chunks"],
        }
    )


@app.post("/api/upload/complete")
def api_upload_complete():
    payload = request.get_json(silent=True) or {}
    upload_id = (payload.get("upload_id") or "").strip()
    with _UPLOAD_LOCK:
        meta = PENDING_UPLOADS.get(upload_id)
        if meta is None:
            return jsonify({"error": "Upload session expire — dobara file select karo."}), 400
        received = set(meta.get("received") or [])
        total = int(meta["total_chunks"])
        if len(received) != total:
            missing = sorted(set(range(total)) - received)[:8]
            return jsonify(
                {
                    "error": f"Upload incomplete — {len(received)}/{total} chunks. Missing e.g. {missing}",
                }
            ), 400
        PENDING_UPLOADS.pop(upload_id, None)

    part_path = Path(meta["part_path"])
    if not part_path.exists():
        return jsonify({"error": "Upload path failed — partial file missing."}), 500
    if part_path.stat().st_size != meta["size"]:
        part_path.unlink(missing_ok=True)
        return jsonify({"error": "Upload incomplete — size mismatch. Dobara try karo."}), 400

    dest = UPLOAD_DIR / meta["dest_name"]
    try:
        if dest.exists():
            dest.unlink()
        part_path.replace(dest)
    except OSError as exc:
        return jsonify({"error": f"Upload path failed: {exc}"}), 500

    return jsonify(_finalize_saved_upload(meta["kind"], dest, meta["original"]))


@app.post("/api/load-sample")
def api_load_sample():
    try:
        files = _load_sample_into_session()
        return jsonify({"ok": True, "files": files, "settings": SESSION["settings"]})
    except (OSError, RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/settings")
def api_get_settings():
    return jsonify(
        {
            "ok": True,
            "settings": normalize_settings(SESSION.get("settings")),
            "options": settings_options(),
        }
    )


@app.post("/api/settings")
def api_set_settings():
    payload = request.get_json(silent=True) or {}
    settings = _merge_settings_from_payload(payload)
    return jsonify({"ok": True, "settings": settings, "options": settings_options()})


@app.get("/api/progress")
def api_progress():
    return jsonify({"ok": True, **JOB.snapshot()})


@app.post("/api/auto-cut")
def api_auto_cut():
    """
    Full Spec engine for the editor.
    Body:
      async: true → background job + poll /api/progress
      async: false → blocking (tests)
    """
    global _JOB_THREAD
    payload = request.get_json(silent=True) or {}
    mode = (payload.get("mode") or "full").strip().lower()
    use_sample = bool(payload.get("use_sample", False))
    run_async = bool(payload.get("async", False))

    try:
        has_movie = bool(SESSION.get("movie") and Path(SESSION["movie"]).exists())
        has_movie_srt = bool(SESSION.get("movie_srt") and Path(SESSION["movie_srt"]).exists())
        has_narr_srt = bool(
            SESSION.get("narration_srt") and Path(SESSION["narration_srt"]).exists()
        )

        # use_sample=true only from Load Sample flow. Never silently replace a user's movie.
        if use_sample:
            if not (has_movie and has_movie_srt and has_narr_srt):
                _load_sample_into_session()
        elif mode == "match_only":
            if not has_movie_srt or not has_narr_srt:
                return jsonify(
                    {
                        "error": "Movie SRT + Narration SRT select karo (video baad mein sync ho sakti hai).",
                    }
                ), 400
        elif mode in ("cut_export", "export_only"):
            if not has_movie:
                return jsonify(
                    {
                        "error": "Movie abhi sync nahi hui. Thora wait / Export dobara dabao.",
                    }
                ), 400
            if not SESSION.get("last_match_plan"):
                return jsonify({"error": "Pehle match chalao."}), 400
        elif not has_movie or not has_movie_srt:
            return jsonify(
                {
                    "error": "Pehle Movie File + Movie SRT select karo (Project Files pe click). Sample ke liye ⋯ → Load Sample.",
                }
            ), 400
        elif not has_narr_srt:
            return jsonify(
                {
                    "error": "Narration Timestamps (.srt) missing hai. Project Files se Narration SRT select karo.",
                }
            ), 400

        settings = _merge_settings_from_payload(payload)

        if not run_async:
            JOB.start(total_stages=5)
            try:
                result = _run_full_pipeline(settings, mode=mode)
                JOB.finish(result)
                return jsonify(result)
            except Exception as exc:  # noqa: BLE001 — surface to client
                JOB.fail(str(exc))
                raise

        with _JOB_LOCK:
            if _JOB_THREAD and _JOB_THREAD.is_alive():
                return jsonify({"error": "Pehle wala job abhi chal raha hai."}), 409
            job_id = JOB.start(total_stages=5)

            def _worker() -> None:
                try:
                    result = _run_full_pipeline(settings, mode=mode)
                    JOB.finish(result)
                except Exception as exc:  # noqa: BLE001
                    JOB.fail(str(exc))

            _JOB_THREAD = threading.Thread(target=_worker, daemon=True)
            _JOB_THREAD.start()

        return jsonify({"ok": True, "async": True, "job_id": job_id})
    except (FileNotFoundError, ValueError, OSError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/rematch")
def api_rematch():
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
    settings = normalize_settings(SESSION.get("settings"))

    try:
        _push_undo()
        new_plan = rematch_plan_item(
            plan,
            scenes,
            narration_index=narration_index,
            scene_id=scene_id,
            max_clip_duration=settings["max_clip_duration"],
        )
        SESSION["last_match_plan"] = new_plan

        if reexport:
            return jsonify(_export_from_session_plan())

        return jsonify(_result_payload({"final_video_url": None}))
    except (ValueError, OSError, RuntimeError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/clip/trim")
def api_clip_trim():
    """Nudge or set clip in/out points, then optional re-export."""
    payload = request.get_json(silent=True) or {}
    if "narration_index" not in payload:
        return jsonify({"error": "narration_index required"}), 400
    plan = SESSION.get("last_match_plan")
    if not plan:
        return jsonify({"error": "Match plan missing"}), 400

    try:
        _push_undo()
        new_plan = trim_match_clip(
            plan,
            narration_index=int(payload["narration_index"]),
            clip_start=payload.get("clip_start"),
            clip_end=payload.get("clip_end"),
            delta_start=float(payload.get("delta_start", 0.0)),
            delta_end=float(payload.get("delta_end", 0.0)),
        )
        SESSION["last_match_plan"] = new_plan
        if bool(payload.get("reexport", True)):
            return jsonify(_export_from_session_plan())
        return jsonify(_result_payload({"final_video_url": None}))
    except (ValueError, OSError, RuntimeError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/clip/reorder")
def api_clip_reorder():
    payload = request.get_json(silent=True) or {}
    order = payload.get("narration_order")
    if not isinstance(order, list) or not order:
        return jsonify({"error": "narration_order list required"}), 400
    plan = SESSION.get("last_match_plan")
    if not plan:
        return jsonify({"error": "Match plan missing"}), 400
    try:
        _push_undo()
        SESSION["last_match_plan"] = reorder_match_plan(plan, order)
        if bool(payload.get("reexport", True)):
            return jsonify(_export_from_session_plan())
        return jsonify(_result_payload({"final_video_url": None}))
    except (ValueError, OSError, RuntimeError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/undo")
def api_undo():
    stack = SESSION.get("undo_stack") or []
    if not stack:
        return jsonify({"error": "Undo stack empty"}), 400
    SESSION["last_match_plan"] = stack.pop()
    reexport = bool((request.get_json(silent=True) or {}).get("reexport", True))
    try:
        if reexport:
            return jsonify(_export_from_session_plan())
        return jsonify(_result_payload({"final_video_url": None}))
    except (ValueError, OSError, RuntimeError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/reexport")
def api_reexport():
    try:
        return jsonify(_export_from_session_plan())
    except (ValueError, OSError, RuntimeError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/project/save")
def api_project_save():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or SESSION.get("project_name") or "scenecut_project").strip()
    SESSION["project_name"] = name
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name) or "project"
    path = PROJECTS_DIR / f"{safe}.scenecut.json"
    try:
        project = build_editor_project(name, SESSION)
        save_editor_project(project, path)
        return jsonify(
            {
                "ok": True,
                "path": str(path),
                "filename": path.name,
                "project_name": name,
            }
        )
    except (OSError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/project/load")
def api_project_load():
    """
    Load by uploaded file OR by filename inside projects/.
    multipart: file=...
    json: {"filename": "sample_project.scenecut.json"}
    """
    try:
        if request.files.get("file"):
            path = _save_upload(request.files["file"], "loaded_project.scenecut.json")
        else:
            payload = request.get_json(silent=True) or {}
            filename = (payload.get("filename") or "").strip()
            if not filename:
                return jsonify({"error": "filename or file required"}), 400
            path = PROJECTS_DIR / Path(filename).name

        project = load_editor_project(path)
        paths = project.get("paths") or {}
        for key_sess, key_path in (
            ("movie", "video"),
            ("movie_srt", "movie_srt"),
            ("narration_srt", "narration_srt"),
            ("narration_audio", "narration_audio"),
        ):
            val = paths.get(key_path)
            if val and Path(val).exists():
                SESSION[key_sess] = val

        SESSION["last_match_plan"] = project.get("match_plan") or []
        SESSION["scenes"] = project.get("scenes") or []
        SESSION["settings"] = normalize_settings(project.get("settings"))
        SESSION["project_name"] = project.get("name") or path.stem
        SESSION["undo_stack"] = []
        SESSION["final_video"] = paths.get("final_video")
        SESSION["cut_only_video"] = paths.get("cut_only_video")
        SESSION["timeline_srt"] = paths.get("timeline_srt")

        return jsonify(
            _result_payload(
                {
                    "loaded": path.name,
                    "files": {
                        "movie": Path(SESSION["movie"]).name if SESSION.get("movie") else None,
                        "movie_srt": Path(SESSION["movie_srt"]).name
                        if SESSION.get("movie_srt")
                        else None,
                        "narration_srt": Path(SESSION["narration_srt"]).name
                        if SESSION.get("narration_srt")
                        else None,
                    },
                }
            )
        )
    except (OSError, ValueError, FileNotFoundError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/api/project/list")
def api_project_list():
    _ensure_dirs()
    files = sorted(PROJECTS_DIR.glob("*.scenecut.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return jsonify(
        {
            "ok": True,
            "projects": [
                {"filename": p.name, "meta": _file_meta(p), "mtime": p.stat().st_mtime}
                for p in files
            ],
        }
    )


def _session_file_info(key: str) -> dict | None:
    raw = SESSION.get(key)
    if not raw:
        return None
    path = Path(raw)
    if not path.exists():
        SESSION[key] = None
        return None
    return {
        "filename": path.name,
        "meta": _file_meta(path),
        "url": "/api/media/movie" if key == "movie" else None,
    }


@app.get("/api/session")
def api_session():
    plan = SESSION.get("last_match_plan")
    files = {
        "movie": _session_file_info("movie"),
        "movie_srt": _session_file_info("movie_srt"),
        "narration_audio": _session_file_info("narration_audio"),
        "narration_srt": _session_file_info("narration_srt"),
    }
    return jsonify(
        {
            **_result_payload(),
            "has_plan": bool(plan),
            "final_ready": bool(
                SESSION.get("final_video") and Path(SESSION["final_video"]).exists()
            ),
            "options": settings_options(),
            "files": files,
            "ready": bool(files["movie"] and files["movie_srt"] and files["narration_srt"]),
            "project_name": SESSION.get("project_name") or "scenecut_project",
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


@app.get("/api/media/report")
def api_media_report():
    path = SESSION.get("report_html")
    if not path or not Path(path).exists():
        return jsonify({"error": "Report abhi ready nahi"}), 404
    return send_file(path, download_name="scenecut_report.html", as_attachment=True)


@app.get("/api/media/narration")
def api_media_narration():
    path = SESSION.get("narration_audio")
    if not path or not Path(path).exists():
        return jsonify({"error": "Narration audio nahi mili"}), 404
    return send_file(path)


def _student_pack_path() -> Path:
    # Prefer pack next to app source; fallback to writable data dir
    primary = RESOURCE_DIR / "releases" / "SceneCut-Pro-Student.zip"
    if primary.exists():
        return primary
    return BASE_DIR / "releases" / "SceneCut-Pro-Student.zip"


def _fmt_bytes(n: int) -> str:
    mb = n / (1024 * 1024)
    if mb >= 1:
        return f"{mb:.1f} MB"
    return f"{max(1, n // 1024)} KB"


@app.get("/download")
def download_page():
    """Public student download landing page."""
    pack = _student_pack_path()
    ready = pack.exists()
    mtime = ""
    size = ""
    if ready:
        st = pack.stat()
        size = _fmt_bytes(st.st_size)
        from datetime import datetime

        mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
    return render_template(
        "download.html",
        pack_ready=ready,
        pack_name="SceneCut-Pro-Student.zip",
        pack_size=size or "—",
        pack_mtime=mtime or "—",
    )


@app.get("/api/download/student-pack")
def api_download_student_pack():
    pack = _student_pack_path()
    if not pack.exists():
        return (
            jsonify(
                {
                    "error": "Student pack abhi ready nahi. Server pe build_student_pack.sh chalao.",
                }
            ),
            404,
        )
    return send_file(
        pack,
        as_attachment=True,
        download_name="SceneCut-Pro-Student.zip",
        mimetype="application/zip",
    )


@app.get("/health")
def health():
    pack = _student_pack_path()
    return jsonify(
        {
            "ok": True,
            "app": "SceneCut Pro+",
            "engine": "stages-1-to-5",
            "pro_plus": True,
            "desktop": os.environ.get("SCENECUT_DESKTOP") == "1",
            "student_pack": pack.exists(),
            "download_page": "/download",
        }
    )


if __name__ == "__main__":
    _ensure_dirs()
    port = int(os.environ.get("PORT", "5000"))
    host = "0.0.0.0"
    print(f"SceneCut Pro+: http://127.0.0.1:{port}")
    if os.environ.get("SCENECUT_WEB") == "1":
        from waitress import serve

        serve(
            app,
            host=host,
            port=port,
            threads=8,
            channel_timeout=3600,
            recv_bytes=65536,
        )
    else:
        app.run(host=host, port=port, debug=False)
