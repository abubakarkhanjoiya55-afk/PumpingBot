/* SceneCut Pro editor — Stages 1→5 + manual rematch */

const state = {
  files: {
    movie: null,
    movie_srt: null,
    narration_audio: null,
    narration_srt: null,
  },
  clips: [],
  scenes: [],
  matchPlan: [],
  selectedClipKey: null,
  pxPerSec: 24,
  movieUrl: null,
  outputDuration: 0,
  busy: false,
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

function setBusy(busy) {
  state.busy = busy;
  ["btnAutoCut", "btnAutoCutTop", "btnApplyRematch", "btnSkipClip", "btnSample"].forEach(
    (id) => {
      const el = $(id);
      if (el) el.disabled = busy;
    }
  );
}

function setStatus(step, mode, timeLabel) {
  const li = document.querySelector(`[data-step="${step}"]`);
  if (!li) return;
  li.classList.remove("done", "active", "error");
  if (mode) li.classList.add(mode);
  const time = li.querySelector(".time");
  if (time) {
    if (timeLabel != null) time.textContent = timeLabel;
    else if (mode === "done") time.textContent = "done";
    else if (mode === "active") time.textContent = "…";
    else time.textContent = "—";
  }
}

function resetStatus() {
  ["analyze_movie", "analyze_narration", "matching", "cutting", "export"].forEach((s) =>
    setStatus(s, null, "—")
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

function buildClipsFromMatchPlan(matchPlan) {
  const clips = [];
  let cursor = 0;
  (matchPlan || []).forEach((item, idx) => {
    const matched =
      !!item.matched && item.clip_start != null && item.clip_end != null;
    const dur = Number(item.clip_duration);
    const clipDur =
      matched && Number.isFinite(dur) && dur > 0
        ? dur
        : matched
          ? Math.max(0.05, Number(item.clip_end) - Number(item.clip_start))
          : 0;

    const timelineStart = matched ? cursor : null;
    const timelineEnd = matched ? cursor + clipDur : null;
    if (matched) cursor += clipDur;

    clips.push({
      key: `n${item.narration_index ?? idx + 1}`,
      index: clips.length + 1,
      narration_index: item.narration_index,
      narration_text: item.narration_text || "",
      scene_text: item.scene_text || "",
      scene_id: item.scene_id,
      score: item.score,
      clip_start: item.clip_start,
      clip_end: item.clip_end,
      clip_duration: clipDur,
      timeline_start: timelineStart,
      timeline_end: timelineEnd,
      reused_scene: !!item.reused_scene,
      trimmed: !!item.trimmed,
      matched,
    });
  });
  return clips;
}

function fillSceneSelect(selectedSceneId) {
  const sel = $("sceneSelect");
  if (!sel) return;
  const scenes = state.scenes || [];
  sel.innerHTML = "";

  const skip = document.createElement("option");
  skip.value = "";
  skip.textContent = "— Skip / Unmatch —";
  sel.appendChild(skip);

  scenes.forEach((scene) => {
    const opt = document.createElement("option");
    opt.value = String(scene.scene_id);
    const dur = Math.max(0, Number(scene.end) - Number(scene.start));
    const text = (scene.combined_text || "").slice(0, 42);
    opt.textContent = `Scene ${String(scene.scene_id).padStart(3, "0")} · ${dur.toFixed(1)}s · ${text}${
      (scene.combined_text || "").length > 42 ? "…" : ""
    }`;
    sel.appendChild(opt);
  });

  if (selectedSceneId != null) sel.value = String(selectedSceneId);
  else sel.value = "";
}

function renderTimeline() {
  const track = $("trackScenes");
  const audioTrack = $("trackAudio");
  track.innerHTML = "";
  audioTrack.querySelectorAll(".vo-block").forEach((n) => n.remove());

  const clips = (state.clips || []).filter((c) => c.matched);
  if (!clips.length) {
    track.style.minWidth = "100%";
    audioTrack.style.minWidth = "100%";
    state.outputDuration = 0;
    updateFooterStats();
    return;
  }

  const maxEnd = Math.max(...clips.map((c) => c.timeline_end || 0), 1);
  state.outputDuration = maxEnd;
  const width = Math.max(800, maxEnd * state.pxPerSec + 80);
  track.style.minWidth = `${width}px`;
  audioTrack.style.minWidth = `${width}px`;

  clips.forEach((clip) => {
    const left = clip.timeline_start * state.pxPerSec;
    const w = Math.max(28, clip.clip_duration * state.pxPerSec - 4);

    const block = document.createElement("button");
    block.type = "button";
    block.className =
      "scene-block" + (state.selectedClipKey === clip.key ? " selected" : "");
    block.style.left = `${left}px`;
    block.style.width = `${w}px`;
    block.innerHTML = `<div class="sid">C${String(clip.index).padStart(2, "0")}</div><div class="sdur">${clip.clip_duration.toFixed(1)}s</div>`;
    block.title = clip.scene_text || clip.narration_text || "";
    block.addEventListener("click", () => selectClip(clip.key));
    track.appendChild(block);

    const vo = document.createElement("div");
    vo.className = "vo-block";
    vo.style.left = `${left}px`;
    vo.style.width = `${w}px`;
    vo.innerHTML = `<div class="sid">VO${String(clip.index).padStart(2, "0")}</div>`;
    vo.title = clip.narration_text || "";
    audioTrack.appendChild(vo);
  });

  $("audioWave").classList.toggle("active", clips.length > 0);
  $("timelineScaleLabel").textContent = `Scale: ${state.pxPerSec}px/s`;
  updateFooterStats();
}

function selectClip(key) {
  state.selectedClipKey = key;
  const clip = state.clips.find((c) => c.key === key);
  if (!clip) return;

  $("propEmpty").style.display = "none";
  $("propDetails").style.display = "block";
  $("propTitle").textContent = clip.matched
    ? `Clip_${String(clip.index).padStart(2, "0")}`
    : `Narration_${clip.narration_index} (skipped)`;
  $("propStart").textContent =
    clip.clip_start != null ? fmtTime(clip.clip_start) : "—";
  $("propEnd").textContent = clip.clip_end != null ? fmtTime(clip.clip_end) : "—";
  $("propDur").textContent = clip.matched ? fmtTime(clip.clip_duration) : "—";
  $("propScore").textContent =
    clip.score != null ? Number(clip.score).toFixed(3) : "—";
  $("propSceneId").textContent =
    clip.scene_id != null ? String(clip.scene_id) : "—";

  const narr = clip.narration_text || "";
  const scene = clip.scene_text || "";
  const flags = [
    clip.matched ? null : "skipped",
    clip.trimmed ? "trimmed" : null,
    clip.reused_scene ? "reused scene" : null,
  ]
    .filter(Boolean)
    .join(" · ");
  $("propNote").textContent = [
    narr ? `VO: ${narr}` : null,
    scene ? `Scene: ${scene}` : null,
    flags || null,
  ]
    .filter(Boolean)
    .join("\n");

  fillSceneSelect(clip.scene_id);

  const video = $("videoPlayer");
  if (video.src && clip.matched && clip.timeline_start != null) {
    video.currentTime = Math.max(0, Number(clip.timeline_start) || 0);
  }
  renderTimeline();
  updatePlayhead();
}

function updateFooterStats() {
  const clips = (state.clips || []).filter((c) => c.matched);
  $("statScenes").textContent = String(clips.length);
  if (!clips.length) {
    $("statDuration").textContent = "00:00:00.00";
    $("statAvg").textContent = "00:00:00.00";
    return;
  }
  const total = clips.reduce((acc, c) => acc + (c.clip_duration || 0), 0);
  $("statDuration").textContent = fmtTime(total);
  $("statAvg").textContent = fmtTime(total / clips.length);
}

function updatePlayhead() {
  const video = $("videoPlayer");
  const t = video.currentTime || 0;
  $("playhead").style.left = `${t * state.pxPerSec}px`;
  const dur =
    video.duration && Number.isFinite(video.duration)
      ? video.duration
      : state.outputDuration || 0;
  $("timecode").textContent = `${fmtTime(t)} / ${fmtTime(dur)}`;
}

function showDownloads(show) {
  const block = $("downloadBlock");
  if (!block) return;
  if (show) block.removeAttribute("hidden");
  else block.setAttribute("hidden", "");
}

function applyPlanResult(data, opts = {}) {
  state.matchPlan = data.match_plan || [];
  state.scenes = data.scenes || state.scenes || [];
  state.clips = buildClipsFromMatchPlan(state.matchPlan);
  $("statSubs").textContent = String(
    data.subtitle_count != null ? data.subtitle_count : $("statSubs").textContent
  );

  renderTimeline();
  const keepKey = opts.keepKey;
  const next =
    (keepKey && state.clips.find((c) => c.key === keepKey)) ||
    state.clips.find((c) => c.matched) ||
    state.clips[0];
  if (next) selectClip(next.key);
  else {
    $("propEmpty").style.display = "block";
    $("propDetails").style.display = "none";
  }

  if (data.final_video_url) {
    const video = $("videoPlayer");
    video.src = `${data.final_video_url}?t=${Date.now()}`;
    $("playerPlaceholder").classList.add("hide");
    showDownloads(true);
  }
}

async function runAutoCut() {
  resetStatus();
  showDownloads(false);
  setBusy(true);

  const t0 = performance.now();
  try {
    setStatus("analyze_movie", "active");
    setStatus("analyze_narration", "active");

    const res = await fetch("/api/auto-cut", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: "full",
        gap_threshold: 6.0,
        min_duration: 2.0,
        max_clip_duration: 5.0,
        burn_subs: true,
        use_sample: !state.files.movie_srt || !state.files.movie,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Auto cut fail");

    const elapsed = ((performance.now() - t0) / 1000).toFixed(1) + "s";
    const stats = data.stats || {};

    setStatus("analyze_movie", "done", `${data.subtitle_count || 0} subs`);
    setStatus("analyze_narration", "done", `${data.narration_lines || 0} lines`);
    setStatus(
      "matching",
      "done",
      `${stats.matched || 0}/${stats.total_narration_lines || 0}`
    );
    setStatus("cutting", "done", `${data.cut_clip_count || stats.matched || 0} clips`);
    setStatus("export", "done", elapsed);

    applyPlanResult(data);
  } catch (err) {
    ["analyze_movie", "analyze_narration", "matching", "cutting", "export"].forEach(
      (s) => {
        const li = document.querySelector(`[data-step="${s}"]`);
        if (li && !li.classList.contains("done")) setStatus(s, "error", "fail");
      }
    );
    showError(err.message || String(err));
  } finally {
    setBusy(false);
  }
}

async function rematchSelected(sceneId, reexport = true) {
  const clip = state.clips.find((c) => c.key === state.selectedClipKey);
  if (!clip) {
    showError("Pehle timeline se clip select karo.");
    return;
  }

  setBusy(true);
  setStatus("matching", "active", "edit…");
  try {
    const res = await fetch("/api/rematch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        narration_index: clip.narration_index,
        scene_id: sceneId,
        reexport,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Rematch fail");

    const stats = data.stats || {};
    setStatus(
      "matching",
      "done",
      `${stats.matched || 0}/${stats.total_narration_lines || 0}`
    );
    if (reexport) {
      setStatus("cutting", "done", "re-cut");
      setStatus("export", "done", "re-export");
    }

    applyPlanResult(data, { keepKey: `n${clip.narration_index}` });
  } catch (err) {
    setStatus("matching", "error", "fail");
    showError(err.message || String(err));
  } finally {
    setBusy(false);
  }
}

function wireControls() {
  bindFileInput("fileMovie", "movie", "movie");
  bindFileInput("fileMovieSrt", "movie_srt", "movie_srt");
  bindFileInput("fileNarrationAudio", "narration_audio", "narration_audio");
  bindFileInput("fileNarrationSrt", "narration_srt", "narration_srt");

  $("btnAutoCut").addEventListener("click", runAutoCut);
  $("btnAutoCutTop").addEventListener("click", runAutoCut);
  $("btnApplyRematch").addEventListener("click", () => {
    const val = $("sceneSelect").value;
    rematchSelected(val === "" ? null : Number(val), true);
  });
  $("btnSkipClip").addEventListener("click", () => rematchSelected(null, true));

  $("btnSample").addEventListener("click", async () => {
    resetStatus();
    showDownloads(false);
    try {
      const res = await fetch("/api/load-sample", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Sample load fail");

      updateFileCard("movie", data.files.movie, data.files.movie_meta);
      updateFileCard("movie_srt", data.files.movie_srt, data.files.movie_srt_meta);
      updateFileCard(
        "narration_srt",
        data.files.narration_srt,
        data.files.narration_srt_meta
      );
      if (data.files.narration_audio) {
        updateFileCard(
          "narration_audio",
          data.files.narration_audio,
          data.files.narration_audio_meta || ""
        );
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
