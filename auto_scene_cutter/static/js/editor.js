/* SceneCut Pro editor — Stage 1 parse + Stage 2 clustering UI */

const state = {
  files: {
    movie: null,
    movie_srt: null,
    narration_audio: null,
    narration_srt: null,
  },
  scenes: [],
  selectedSceneId: null,
  pxPerSec: 24,
  movieUrl: null,
};

function $(id) {
  return document.getElementById(id);
}

function fmtTime(seconds) {
  const s = Math.max(0, Number(seconds) || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const whole = Math.floor(sec);
  const frac = Math.floor((sec - whole) * 100);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(whole).padStart(2, "0")}.${String(frac).padStart(2, "0")}`;
}

function showError(msg) {
  const el = $("errorToast");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 4500);
}

function setStatus(step, done, timeLabel) {
  const li = document.querySelector(`[data-step="${step}"]`);
  if (!li) return;
  li.classList.toggle("done", !!done);
  const time = li.querySelector(".time");
  if (time) time.textContent = timeLabel || (done ? "done" : "—");
}

function resetStatus() {
  ["analyze_movie", "analyze_narration", "cluster_scenes", "place_timeline"].forEach((s) =>
    setStatus(s, false, "—")
  );
}

function updateFileCard(key, name, meta) {
  const card = document.querySelector(`.file-card[data-key="${key}"]`);
  if (!card) return;
  card.classList.remove("empty");
  card.innerHTML = `<strong>${name}</strong><div class="meta">${meta || ""}</div>`;
  state.files[key] = name;
}

function bindFileInput(inputId, key, kind) {
  $(inputId).addEventListener("change", async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;

    const body = new FormData();
    body.append("kind", kind);
    body.append("file", file);

    try {
      const res = await fetch("/api/upload", { method: "POST", body });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Upload fail");

      updateFileCard(key, data.filename, data.meta);

      if (kind === "movie") {
        if (state.movieUrl) URL.revokeObjectURL(state.movieUrl);
        state.movieUrl = URL.createObjectURL(file);
        const video = $("videoPlayer");
        video.src = state.movieUrl;
        $("playerPlaceholder").classList.add("hide");
      }
      if (kind === "narration_audio") {
        $("audioWave").classList.add("active");
      }
    } catch (err) {
      showError(err.message || String(err));
    }
  });
}

function renderTimeline() {
  const track = $("trackScenes");
  track.innerHTML = "";
  const scenes = state.scenes || [];
  if (!scenes.length) {
    track.style.minWidth = "100%";
    return;
  }

  const maxEnd = Math.max(...scenes.map((s) => Number(s.end) || 0), 1);
  const width = Math.max(800, maxEnd * state.pxPerSec + 80);
  $("trackScenes").style.minWidth = `${width}px`;
  $("trackAudio").style.minWidth = `${width}px`;

  scenes.forEach((scene) => {
    const start = Number(scene.start) || 0;
    const end = Number(scene.end) || start;
    const dur = Math.max(0.05, end - start);
    const left = start * state.pxPerSec;
    const w = Math.max(28, dur * state.pxPerSec - 4);

    const block = document.createElement("button");
    block.type = "button";
    block.className = "scene-block" + (state.selectedSceneId === scene.scene_id ? " selected" : "");
    block.style.left = `${left}px`;
    block.style.width = `${w}px`;
    block.innerHTML = `<div class="sid">${String(scene.scene_id).padStart(3, "0")}</div><div class="sdur">${dur.toFixed(1)}s</div>`;
    block.title = scene.combined_text || "";
    block.addEventListener("click", () => selectScene(scene.scene_id));
    track.appendChild(block);
  });

  $("timelineScaleLabel").textContent = `Scale: ${state.pxPerSec}px/s`;
  updateFooterStats();
}

function selectScene(sceneId) {
  state.selectedSceneId = sceneId;
  const scene = state.scenes.find((s) => s.scene_id === sceneId);
  if (!scene) return;

  $("propEmpty").style.display = "none";
  $("propDetails").style.display = "block";
  $("propTitle").textContent = `Scene_${String(scene.scene_id).padStart(3, "0")}`;
  $("propStart").textContent = fmtTime(scene.start);
  $("propEnd").textContent = fmtTime(scene.end);
  const dur = Math.max(0, Number(scene.end) - Number(scene.start));
  $("propDur").textContent = fmtTime(dur);
  $("propLines").textContent = String(scene.subtitle_count ?? "—");
  const text = scene.combined_text || "";
  $("propNote").textContent =
    text.length > 180 ? `${text.slice(0, 180)}…` : text || "No dialogue text";

  const video = $("videoPlayer");
  if (video.src) {
    video.currentTime = Math.max(0, Number(scene.start) || 0);
  }
  renderTimeline();
  updatePlayhead();
}

function updateFooterStats() {
  const scenes = state.scenes || [];
  $("statScenes").textContent = String(scenes.length);
  if (!scenes.length) {
    $("statDuration").textContent = "00:00:00.00";
    $("statAvg").textContent = "00:00:00.00";
    return;
  }
  const total = scenes.reduce((acc, s) => acc + Math.max(0, Number(s.end) - Number(s.start)), 0);
  $("statDuration").textContent = fmtTime(total);
  $("statAvg").textContent = fmtTime(total / scenes.length);
}

function updatePlayhead() {
  const video = $("videoPlayer");
  const x = (video.currentTime || 0) * state.pxPerSec;
  $("playhead").style.left = `${x}px`;
  const dur = video.duration && Number.isFinite(video.duration) ? video.duration : 0;
  $("timecode").textContent = `${fmtTime(video.currentTime || 0)} / ${fmtTime(dur)}`;
}

async function runAutoCut() {
  resetStatus();
  const t0 = performance.now();
  try {
    setStatus("analyze_movie", false, "…");
    const res = await fetch("/api/auto-cut", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        gap_threshold: 6.0,
        min_duration: 2.0,
        use_sample: !state.files.movie_srt,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Auto cut fail");

    const tMovie = ((performance.now() - t0) / 1000).toFixed(2) + "s";
    setStatus("analyze_movie", true, tMovie);

    if (data.narration_lines != null) {
      setStatus("analyze_narration", true, `${data.narration_lines} lines`);
    } else {
      setStatus("analyze_narration", true, "skipped");
    }

    setStatus("cluster_scenes", true, `${data.scenes.length} scenes`);
    state.scenes = data.scenes || [];
    $("statSubs").textContent = String(data.subtitle_count || 0);

    if (data.files) {
      if (data.files.movie_srt) updateFileCard("movie_srt", data.files.movie_srt, data.files.movie_srt_meta || "");
      if (data.files.narration_srt) {
        updateFileCard("narration_srt", data.files.narration_srt, data.files.narration_srt_meta || "");
      }
      if (data.files.movie_url) {
        const video = $("videoPlayer");
        video.src = data.files.movie_url;
        $("playerPlaceholder").classList.add("hide");
      }
    }

    renderTimeline();
    setStatus("place_timeline", true, "done");
    if (state.scenes[0]) selectScene(state.scenes[0].scene_id);
  } catch (err) {
    showError(err.message || String(err));
  }
}

function wireControls() {
  bindFileInput("fileMovie", "movie", "movie");
  bindFileInput("fileMovieSrt", "movie_srt", "movie_srt");
  bindFileInput("fileNarrationAudio", "narration_audio", "narration_audio");
  bindFileInput("fileNarrationSrt", "narration_srt", "narration_srt");

  $("btnAutoCut").addEventListener("click", runAutoCut);
  $("btnAutoCutTop").addEventListener("click", runAutoCut);
  $("btnSample").addEventListener("click", async () => {
    resetStatus();
    try {
      const res = await fetch("/api/load-sample", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Sample load fail");

      updateFileCard("movie", data.files.movie, data.files.movie_meta);
      updateFileCard("movie_srt", data.files.movie_srt, data.files.movie_srt_meta);
      updateFileCard("narration_srt", data.files.narration_srt, data.files.narration_srt_meta);
      if (data.files.narration_audio) {
        updateFileCard("narration_audio", data.files.narration_audio, data.files.narration_audio_meta || "");
        $("audioWave").classList.add("active");
      }

      const video = $("videoPlayer");
      video.src = data.files.movie_url;
      $("playerPlaceholder").classList.add("hide");
      await runAutoCut();
    } catch (err) {
      showError(err.message || String(err));
    }
  });

  const video = $("videoPlayer");
  video.addEventListener("timeupdate", updatePlayhead);
  video.addEventListener("loadedmetadata", updatePlayhead);

  $("btnPlay").addEventListener("click", () => {
    if (!video.src) return;
    if (video.paused) video.play();
    else video.pause();
  });
  $("btnSeekBack").addEventListener("click", () => {
    video.currentTime = Math.max(0, video.currentTime - 5);
  });
  $("btnSeekFwd").addEventListener("click", () => {
    video.currentTime = video.currentTime + 5;
  });

  $("btnZoomIn").addEventListener("click", () => {
    state.pxPerSec = Math.min(80, state.pxPerSec + 4);
    renderTimeline();
    updatePlayhead();
  });
  $("btnZoomOut").addEventListener("click", () => {
    state.pxPerSec = Math.max(8, state.pxPerSec - 4);
    renderTimeline();
    updatePlayhead();
  });
}

wireControls();
renderTimeline();
