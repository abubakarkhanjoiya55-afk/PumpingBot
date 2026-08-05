# SceneCut Pro — permanent Railway / Docker image
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      curl \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure sample media + student ZIP exist inside the image
RUN python3 - <<'PY'
from pathlib import Path
from video_cutter import create_sample_video
from final_render import create_sample_narration_audio
from srt_parser import parse_narration_srt

root = Path(".")
movie = root / "sample_movie.mp4"
audio = root / "sample_narration.m4a"
narration_srt = root / "sample_narration.srt"
if not movie.exists() or movie.stat().st_size < 1000:
    create_sample_video(movie, duration_seconds=60.0)
if narration_srt.exists() and (not audio.exists() or audio.stat().st_size < 500):
    create_sample_narration_audio(parse_narration_srt(str(narration_srt)), audio)
print("samples ok", movie.stat().st_size if movie.exists() else 0,
      audio.stat().st_size if audio.exists() else 0)
PY

RUN chmod +x desktop/build_student_pack.sh start_web.sh \
  && ./desktop/build_student_pack.sh

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV SCENECUT_WEB=1
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=8s --start-period=40s --retries=5 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8080}/health" || exit 1

CMD ["./start_web.sh"]
