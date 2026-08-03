/* SceneCut Pro+ editor — Stages 1→5 + pro controls */

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
  settings: {
    quality: "balanced",
    transition: "fade",
    max_clip_duration: 5,
    burn_subs: true,
    gap_threshold: 6,
    min_duration: 2,
    transition_duration: 0.35,
  },
  projectName: "scenecut_project",
  canUndo: false,
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
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 4500);
}

function showOk(msg) {
  const el = $("okToast");
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2800);
}

function setBusy(busy) {
  state.busy = busy;
  [
    "btnAutoCut",
    "btnAutoCutTop",
    "btnApplyRematch",
    "btnSkipClip",
    "btnSample",
    "btnSaveProject",
    "btnOpenProject",
    "btnUndo",
    "btnTrimInMinus",
    "btnTrimInPlus",
    "btnTrimOutMinus",
    "btnTrimOutPlus",
    "btnMoveLeft",
    "btnMoveRight",
    "btnToolDel",
  ].forEach((id) => {
    const el = $(id);
    if (el) el.disabled = busy;
  });
}

function setProgress(percent, message) {
  $("progressFill").style.width = `${Math.max(0, Math.min(100, percent || 0))}%`;
  $("progressMsg").textContent = message || "Idle";
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
  setProgress(0, "Idle");
}

function readSettingsFromUi() {
  state.settings = {
    ...state.settings,
    quality: $("setQuality").value,
    transition: $("setTransition").value,
    max_clip_duration: Number($("setMaxClip").value) || 5,
    burn_subs: !!$("setBurnSubs").checked,
  };
  $("statQuality").textContent = state.settings.quality;
  return state.settings;
}

function writeSettingsToUi(settings) {
  if (!settings) return;
  state.settings = { ...state.settings, ...settings };
  if (settings.quality) $("setQuality").value = settings.quality;
  if (settings.transition) $("setTransition").value = settings.transition;
  if (settings.max_clip_duration != null)
    $("setMaxClip").value = settings.max_clip_duration;
  if (settings.burn_subs != null) $("setBurnSubs").checked = !!settings.burn_subs;
  $("statQuality").textContent = state.settings.quality;
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
        $("videoPlayer").src = state.movieUrl;
        $("playerPlaceholder").classList.add("hide");
      }
      if (kind === "narration_audio") $("audioWave").classList.add("active");
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
  sel.innerHTML = "";
  const skip = document.createElement("option");
  skip.value = "";
  skip.textContent = "— Skip / Unmatch —";
  sel.appendChild(skip);
  (state.scenes || []).forEach((scene) => {
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
    block.innerHTML = `<div class="sid">${String(clip.index).padStart(3, "0")}</div><div class="sdur">${clip.clip_duration.toFixed(1)}s</div>`;
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

  $("propEmpty").hidden = true;
  $("propDetails").hidden = false;
  $("propTitle").textContent = clip.matched
    ? `Scene_${String(clip.scene_id ?? clip.index).padStart(3, "0")}`
    : `Narration_${clip.narration_index} (skipped)`;
  $("propStart").textContent =
    clip.clip_start != null ? fmtTime(clip.clip_start) : "—";
  $("propEnd").textContent = clip.clip_end != null ? fmtTime(clip.clip_end) : "—";
  $("propDur").textContent = clip.matched ? fmtTime(clip.clip_duration) : "—";
  $("propScore").textContent =
    clip.score != null ? Number(clip.score).toFixed(3) : "—";
  $("propSceneId").textContent =
    clip.scene_id != null ? String(clip.scene_id) : "—";

  const flags = [
    clip.matched ? null : "skipped",
    clip.trimmed ? "trimmed" : null,
    clip.reused_scene ? "reused scene" : null,
  ]
    .filter(Boolean)
    .join(" · ");
  $("propNote").textContent = [
    clip.narration_text ? `VO: ${clip.narration_text}` : null,
    clip.scene_text ? `Scene: ${clip.scene_text}` : null,
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

function showDownloads(show, reportUrl) {
  const block = $("downloadBlock");
  if (!block) return;
  if (show) block.removeAttribute("hidden");
  else block.setAttribute("hidden", "");
  const report = $("dlReport");
  if (report) report.style.display = reportUrl ? "block" : "none";
}

function applyPlanResult(data, opts = {}) {
  state.matchPlan = data.match_plan || [];
  state.scenes = data.scenes || state.scenes || [];
  state.clips = buildClipsFromMatchPlan(state.matchPlan);
  state.canUndo = !!data.can_undo;
  if (data.settings) writeSettingsToUi(data.settings);
  if (data.project_name) {
    state.projectName = data.project_name;
    $("projectNameLabel").textContent = `Project: ${state.projectName}`;
  }
  if (data.subtitle_count != null) $("statSubs").textContent = String(data.subtitle_count);

  renderTimeline();
  const keepKey = opts.keepKey;
  const next =
    (keepKey && state.clips.find((c) => c.key === keepKey)) ||
    state.clips.find((c) => c.matched) ||
    state.clips[0];
  if (next) selectClip(next.key);
  else {
    $("propEmpty").hidden = false;
    $("propDetails").hidden = true;
  }

  if (data.final_video_url) {
    $("videoPlayer").src = `${data.final_video_url}?t=${Date.now()}`;
    $("playerPlaceholder").classList.add("hide");
    showDownloads(true, data.report_url);
  }
}

function markStagesFromJob(job) {
  const stage = job.stage;
  const order = [
    "analyze_movie",
    "analyze_narration",
    "matching",
    "cutting",
    "export",
  ];
  const idx = order.indexOf(stage);
  order.forEach((s, i) => {
    if (job.status === "done") setStatus(s, "done");
    else if (idx < 0) return;
    else if (i < idx) setStatus(s, "done");
    else if (i === idx) setStatus(s, "active", job.message || "…");
  });
  setProgress(job.percent || 0, job.message || stage || "Working…");
}

async function pollJobUntilDone() {
  while (true) {
    const res = await fetch("/api/progress");
    const job = await res.json();
    markStagesFromJob(job);
    if (job.status === "done") return job;
    if (job.status === "error") throw new Error(job.error || "Job failed");
    await new Promise((r) => setTimeout(r, 400));
  }
}

async function runAutoCut() {
  resetStatus();
  showDownloads(false);
  setBusy(true);
  const settings = readSettingsFromUi();

  try {
    setStatus("analyze_movie", "active");
    const res = await fetch("/api/auto-cut", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: "full",
        async: true,
        use_sample: !state.files.movie_srt || !state.files.movie,
        ...settings,
      }),
    });
    const start = await res.json();
    if (!res.ok) throw new Error(start.error || "Auto cut fail");

    const job = await pollJobUntilDone();
    const data = job.result || {};
    const stats = data.stats || {};

    setStatus("analyze_movie", "done", `${data.subtitle_count || 0} subs`);
    setStatus("analyze_narration", "done", `${data.narration_lines || 0} lines`);
    setStatus(
      "matching",
      "done",
      `${stats.matched || 0}/${stats.total_narration_lines || 0}`
    );
    setStatus("cutting", "done", `${data.cut_clip_count || stats.matched || 0} clips`);
    setStatus("export", "done", "done");
    setProgress(100, "Done");

    applyPlanResult(data);
    showOk("Pro+ export ready");
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
      setProgress(100, "Re-export done");
    }
    applyPlanResult(data, { keepKey: `n${clip.narration_index}` });
  } catch (err) {
    setStatus("matching", "error", "fail");
    showError(err.message || String(err));
  } finally {
    setBusy(false);
  }
}

async function trimSelected(deltaStart, deltaEnd) {
  const clip = state.clips.find((c) => c.key === state.selectedClipKey);
  if (!clip || !clip.matched) {
    showError("Matched clip select karo.");
    return;
  }
  setBusy(true);
  try {
    const res = await fetch("/api/clip/trim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        narration_index: clip.narration_index,
        delta_start: deltaStart,
        delta_end: deltaEnd,
        reexport: true,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Trim fail");
    applyPlanResult(data, { keepKey: clip.key });
    showOk("Trim applied");
  } catch (err) {
    showError(err.message || String(err));
  } finally {
    setBusy(false);
  }
}

async function moveSelected(dir) {
  const clip = state.clips.find((c) => c.key === state.selectedClipKey);
  if (!clip) return;
  const order = state.matchPlan.map((m) => m.narration_index);
  const i = order.indexOf(clip.narration_index);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= order.length) return;
  const next = order.slice();
  [next[i], next[j]] = [next[j], next[i]];

  setBusy(true);
  try {
    const res = await fetch("/api/clip/reorder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ narration_order: next, reexport: true }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Reorder fail");
    applyPlanResult(data, { keepKey: clip.key });
    showOk("Order updated");
  } catch (err) {
    showError(err.message || String(err));
  } finally {
    setBusy(false);
  }
}

async function undoLast() {
  setBusy(true);
  try {
    const res = await fetch("/api/undo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reexport: true }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Undo fail");
    applyPlanResult(data);
    showOk("Undo done");
  } catch (err) {
    showError(err.message || String(err));
  } finally {
    setBusy(false);
  }
}

async function saveProject() {
  const name = window.prompt("Project name?", state.projectName || "scenecut_project");
  if (!name) return;
  setBusy(true);
  try {
    const res = await fetch("/api/project/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Save fail");
    state.projectName = data.project_name;
    $("projectNameLabel").textContent = `Project: ${state.projectName}`;
    showOk(`Saved ${data.filename}`);
  } catch (err) {
    showError(err.message || String(err));
  } finally {
    setBusy(false);
  }
}

function closeOpenModal() {
  $("openModal").hidden = true;
}

async function refreshRecentProjects() {
  const box = $("recentProjects");
  box.innerHTML = `<div class="recent-empty">Loading…</div>`;
  try {
    const res = await fetch("/api/project/list");
    const data = await res.json();
    const projects = data.projects || [];
    if (!projects.length) {
      box.innerHTML = `<div class="recent-empty">No saved projects yet. Use Save after Auto Cut.</div>`;
      return;
    }
    box.innerHTML = "";
    projects.forEach((p) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "recent-item";
      btn.innerHTML = `<strong>${p.filename}</strong><span>${p.meta || ""}</span>`;
      btn.addEventListener("click", () => loadProjectByFilename(p.filename));
      box.appendChild(btn);
    });
  } catch (err) {
    box.innerHTML = `<div class="recent-empty">${err.message || "Could not list projects"}</div>`;
  }
}

async function openProjectModal() {
  $("openModal").hidden = false;
  await refreshRecentProjects();
}

async function applyLoadedProject(data) {
  if (data.files) {
    if (data.files.movie) updateFileCard("movie", data.files.movie, "");
    if (data.files.movie_srt) updateFileCard("movie_srt", data.files.movie_srt, "");
    if (data.files.narration_srt)
      updateFileCard("narration_srt", data.files.narration_srt, "");
  }
  resetStatus();
  ["analyze_movie", "analyze_narration", "matching", "cutting", "export"].forEach((s) =>
    setStatus(s, "done", "loaded")
  );
  setProgress(data.final_video_url ? 100 : 0, data.final_video_url ? "Loaded" : "Plan loaded");
  applyPlanResult(data);
  if (data.source_movie_url && !data.final_video_url) {
    $("videoPlayer").src = data.source_movie_url;
    $("playerPlaceholder").classList.add("hide");
  }
  showDownloads(!!data.final_video_url, data.report_url);
  showOk(`Opened ${data.loaded || data.project_name || "project"}`);
}

async function loadProjectByFilename(filename) {
  setBusy(true);
  try {
    const res = await fetch("/api/project/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Open fail");
    closeOpenModal();
    await applyLoadedProject(data);
  } catch (err) {
    showError(err.message || String(err));
  } finally {
    setBusy(false);
  }
}

async function loadProjectFromFile(file) {
  setBusy(true);
  try {
    const body = new FormData();
    body.append("file", file);
    const res = await fetch("/api/project/load", { method: "POST", body });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Open fail");
    closeOpenModal();
    await applyLoadedProject(data);
  } catch (err) {
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
  $("btnToolDel").addEventListener("click", () => rematchSelected(null, true));
  $("btnUndo").addEventListener("click", undoLast);
  $("btnSaveProject").addEventListener("click", saveProject);
  $("btnOpenProject").addEventListener("click", openProjectModal);
  $("btnCloseOpen").addEventListener("click", closeOpenModal);
  $("btnCloseOpen2").addEventListener("click", closeOpenModal);
  $("btnBrowseProject").addEventListener("click", () => $("fileProject").click());
  $("fileProject").addEventListener("change", (e) => {
    const file = e.target.files && e.target.files[0];
    if (file) loadProjectFromFile(file);
    e.target.value = "";
  });
  $("openModal").addEventListener("click", (e) => {
    if (e.target === $("openModal")) closeOpenModal();
  });

  $("btnTrimInMinus").addEventListener("click", () => trimSelected(0.25, 0));
  $("btnTrimInPlus").addEventListener("click", () => trimSelected(-0.25, 0));
  $("btnTrimOutMinus").addEventListener("click", () => trimSelected(0, -0.25));
  $("btnTrimOutPlus").addEventListener("click", () => trimSelected(0, 0.25));
  $("btnMoveLeft").addEventListener("click", () => moveSelected(-1));
  $("btnMoveRight").addEventListener("click", () => moveSelected(1));

  ["setQuality", "setTransition", "setMaxClip", "setBurnSubs"].forEach((id) => {
    $(id).addEventListener("change", async () => {
      const settings = readSettingsFromUi();
      try {
        await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(settings),
        });
      } catch (_) {
        /* ignore */
      }
    });
  });

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
      if (data.settings) writeSettingsToUi(data.settings);
      $("videoPlayer").src = data.files.movie_url;
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

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      if (!state.busy) undoLast();
    }
  });
}

async function quitDesktop() {
  try {
    await fetch("/api/shutdown", { method: "POST" });
    showOk("Closing SceneCut Pro+…");
    setTimeout(() => {
      window.close();
    }, 400);
  } catch (err) {
    showError(err.message || String(err));
  }
}

/* ——— CapCut-style mobile sheets ——— */
const mobileSheetState = {
  node: null,
  parent: null,
  next: null,
  name: null,
};

function isMobileUi() {
  return window.matchMedia("(max-width: 900px)").matches;
}

function closeMobileSheet() {
  const sheet = $("mobileSheet");
  const backdrop = $("mobileBackdrop");
  if (mobileSheetState.node && mobileSheetState.parent) {
    const node = mobileSheetState.node;
    node.style.display = "";
    node.style.border = "";
    node.style.background = "";
    node.style.overflow = "";
    if (mobileSheetState.next) {
      mobileSheetState.parent.insertBefore(node, mobileSheetState.next);
    } else {
      mobileSheetState.parent.appendChild(node);
    }
  }
  mobileSheetState.node = null;
  mobileSheetState.parent = null;
  mobileSheetState.next = null;
  mobileSheetState.name = null;
  if (sheet) sheet.hidden = true;
  if (backdrop) backdrop.hidden = true;
  document.querySelectorAll(".m-dock-item").forEach((b) => b.classList.remove("active"));
}

function openMobileSheet(name, title, sourceNode) {
  if (!sourceNode) return;
  closeMobileSheet();
  const sheet = $("mobileSheet");
  const backdrop = $("mobileBackdrop");
  const scroll = $("mobileSheetScroll");
  const titleEl = $("mobileSheetTitle");
  if (!sheet || !scroll) return;

  mobileSheetState.node = sourceNode;
  mobileSheetState.parent = sourceNode.parentNode;
  mobileSheetState.next = sourceNode.nextSibling;
  mobileSheetState.name = name;

  // Show panel content inside sheet (desktop CSS hides .panel on mobile)
  sourceNode.style.display = "block";
  sourceNode.style.border = "0";
  sourceNode.style.background = "transparent";
  sourceNode.style.overflow = "visible";
  scroll.innerHTML = "";
  scroll.appendChild(sourceNode);

  if (titleEl) titleEl.textContent = title;
  sheet.hidden = false;
  if (backdrop) backdrop.hidden = false;

  document.querySelectorAll(".m-dock-item").forEach((b) => {
    b.classList.toggle("active", b.dataset.sheet === name);
  });
}

function wireMobileUi() {
  const left = document.querySelector(".panel.left");
  const right = document.querySelector(".panel.right");

  document.querySelectorAll(".m-dock-item").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const name = btn.dataset.sheet;
      if (name === "media") {
        openMobileSheet("media", "Media & Render", left);
      } else if (name === "edit") {
        openMobileSheet("edit", "Edit clip", right);
      } else if (name === "export") {
        openMobileSheet("export", "Export", left);
        // jump downloads into view if present
        setTimeout(() => {
          const dl = document.getElementById("downloadBlock");
          if (dl) dl.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 50);
      } else if (name === "auto") {
        closeMobileSheet();
        if (!state.busy) await runAutoCut();
      }
    });
  });

  $("btnCloseSheet")?.addEventListener("click", closeMobileSheet);
  $("mobileBackdrop")?.addEventListener("click", closeMobileSheet);

  $("btnMobileExport")?.addEventListener("click", () => {
    openMobileSheet("export", "Export", left);
    setTimeout(() => {
      const dl = document.getElementById("downloadBlock");
      if (dl) {
        dl.hidden = false;
        dl.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, 50);
  });

  $("btnMobileMenu")?.addEventListener("click", () => {
    const choice = window.prompt(
      "Quick actions:\n1 Sample\n2 Open project\n3 Save\n4 Undo\n\nType number:"
    );
    if (choice === "1") $("btnSample").click();
    else if (choice === "2") $("btnOpenProject").click();
    else if (choice === "3") $("btnSaveProject").click();
    else if (choice === "4") $("btnUndo").click();
  });

  window.addEventListener("resize", () => {
    if (!isMobileUi()) closeMobileSheet();
  });
}

async function boot() {
  try {
    const res = await fetch("/api/settings");
    const data = await res.json();
    if (data.settings) writeSettingsToUi(data.settings);
  } catch (_) {
    writeSettingsToUi(state.settings);
  }

  // Show Quit when launched as desktop app
  try {
    const desk = await fetch("/api/desktop").then((r) => r.json());
    const q = new URLSearchParams(location.search).get("desktop");
    if ((desk && desk.desktop) || q === "1") {
      const btn = $("btnQuitDesktop");
      if (btn) {
        btn.hidden = false;
        btn.addEventListener("click", quitDesktop);
      }
    }
  } catch (_) {
    /* browser-only mode */
  }

  wireControls();
  wireMobileUi();
  renderTimeline();
}

boot();
