/* SceneCut Pro+ editor — Stages 1→5 + pro controls */

const state = {
  files: {
    movie: null,
    movie_srt: null,
    narration_audio: null,
    narration_srt: null,
  },
  // CapCut-style: keep local File instantly; sync to server in background
  localFiles: {
    movie: null,
    movie_srt: null,
    narration_audio: null,
    narration_srt: null,
  },
  synced: {
    movie: false,
    movie_srt: false,
    narration_audio: false,
    narration_srt: false,
  },
  uploadJobs: {},
  deferredSync: {},
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
  const frames = Math.floor((sec - whole) * 25); // 25fps display like reference
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(whole).padStart(2, "0")}:${String(frames).padStart(2, "0")}`;
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
    "btnAutoCutTop",
    "btnApplyRematch",
    "btnSkipClip",
    "btnSample",
    "btnRerunCut",
    "btnRerunCutMain",
    "btnSaveProject",
    "btnOpenProject",
    "btnUndo",
    "btnUndoTool",
    "btnTrimInMinus",
    "btnTrimInPlus",
    "btnTrimOutMinus",
    "btnTrimOutPlus",
    "btnMoveLeft",
    "btnMoveRight",
    "btnToolDel",
    "btnMoreMenu",
  ].forEach((id) => {
    const el = $(id);
    if (el) el.disabled = busy;
  });
}

function countSubtitleLines(text) {
  if (!text) return 0;
  return String(text)
    .split(/[.!?]+|\n+/)
    .map((s) => s.trim())
    .filter(Boolean).length || 1;
}

function closeMoreMenu() {
  const menu = $("moreMenu");
  if (menu) menu.hidden = true;
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
    quality: $("setQuality")?.value || state.settings.quality,
    transition: $("setTransition")?.value || state.settings.transition,
    max_clip_duration: Number($("setMaxClip")?.value) || state.settings.max_clip_duration || 5,
    burn_subs: $("setBurnSubs") ? !!$("setBurnSubs").checked : state.settings.burn_subs,
  };
  if ($("statQuality")) $("statQuality").textContent = state.settings.quality;
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

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatBytes(size) {
  const n = Number(size) || 0;
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n} B`;
}

function fileCardEl(key) {
  return (
    document.querySelector(`.file-row[data-key="${key}"]`) ||
    document.querySelector(`.file-card[data-key="${key}"]`)
  );
}

function updateFileCard(key, name, meta, flags = {}) {
  const card = fileCardEl(key);
  if (!card) return;
  card.classList.remove("empty");
  card.classList.toggle("syncing", !!flags.syncing);
  card.classList.toggle("sync-error", !!flags.error);
  card.classList.toggle("ready", !!flags.ready && !flags.syncing && !flags.error);
  const kind =
    key === "movie" ? "movie" : key.includes("audio") ? "audio" : "srt";
  const label =
    key === "movie"
      ? "Movie File"
      : key === "narration_audio"
        ? "Narration Audio"
        : key === "narration_srt"
          ? "Narration Timestamps"
          : "Movie SRT";
  const safeName = escapeHtml(name);
  const safeMeta = escapeHtml(meta || label);
  if (card.classList.contains("file-row")) {
    card.innerHTML = `
      <span class="fico ${kind}" aria-hidden="true"></span>
      <span class="fname">
        <strong title="${safeName}">${safeName}</strong>
        <em>${safeMeta}</em>
      </span>
      <span class="fcheck" aria-hidden="true"></span>`;
  } else {
    card.innerHTML = `<strong>${safeName}</strong><div class="meta">${safeMeta}</div>`;
  }
  state.files[key] = name;
  const save = $("autoSaveLabel");
  if (save) save.textContent = "Auto-saved just now";
  updateFilesHint();
}

function setCardSyncMeta(key, meta, flags = {}) {
  const card = fileCardEl(key);
  if (!card) return;
  card.classList.toggle("syncing", !!flags.syncing);
  card.classList.toggle("sync-error", !!flags.error);
  card.classList.toggle("ready", !!flags.ready && !flags.syncing && !flags.error);
  const em = card.querySelector(".fname em") || card.querySelector(".meta");
  if (em) em.textContent = meta;
}

function updateFilesHint(extraTip) {
  const el = $("filesHint");
  if (!el) return;
  const need = [];
  if (!state.files.movie) need.push("Movie File");
  if (!state.files.movie_srt) need.push("Movie SRT");
  if (!state.files.narration_srt) need.push("Narration SRT");
  el.classList.remove("ready", "bad");
  if (!need.length) {
    el.classList.add("ready");
    el.innerHTML =
      "Imported ✓ — CapCut style. Ab <strong>Export</strong> dabao.";
  } else {
    el.classList.add("bad");
    el.innerHTML = `Select karo: <strong>${need.join(", ")}</strong> — foran ready ho jayega.`;
  }
  if (extraTip) showOk(extraTip);
}

async function readJsonSafe(res) {
  const text = await res.text();
  try {
    return text ? JSON.parse(text) : {};
  } catch (_) {
    if (res.status === 413)
      return {
        error:
          "File limit cross — compress karo ya /download Student Pack desktop use karo (2GB+ wahan easy).",
      };
    return {
      error: text
        ? `Upload/path failed (HTTP ${res.status}). Server response parse nahi hui.`
        : `Upload/path failed (HTTP ${res.status}).`,
    };
  }
}

function formatUploadError(err) {
  const msg = (err && err.message) || String(err || "");
  if (/SERVER_DOWN/i.test(msg)) {
    return "Server band / nahi mil raha. Page refresh karo. Desktop app hai to SceneCut dobara kholo.";
  }
  if (/bahut bari|limit ~|disk (kam|full)|fit nahi/i.test(msg)) {
    return msg;
  }
  if (/failed to fetch|networkerror|load failed|abort/i.test(msg)) {
    return "Upload toot gaya (net slow / bari file). Wi‑Fi + dobara try, ya /download Student Pack desktop use karo — wahan 2GB+ movie foran chalti hai.";
  }
  return msg || "Upload/path failed";
}

async function ensureServerUp() {
  try {
    const res = await fetch("/health", { cache: "no-store" });
    if (!res.ok) throw new Error("SERVER_DOWN");
    return true;
  } catch (_) {
    throw new Error("SERVER_DOWN");
  }
}

async function fetchWithRetry(url, options, tries = 3) {
  let lastErr;
  for (let i = 0; i < tries; i++) {
    try {
      const res = await fetch(url, options);
      return res;
    } catch (err) {
      lastErr = err;
      await new Promise((r) => setTimeout(r, 350 * (i + 1)));
    }
  }
  throw lastErr || new Error("failed to fetch");
}

function isLocalHost() {
  const h = location.hostname;
  return h === "localhost" || h === "127.0.0.1" || h === "::1";
}

function pickChunkSize(fileSize) {
  // Large chunks = fewer HTTP round-trips (critical for multi‑GB prepare)
  if (fileSize >= 1024 * 1024 * 1024) return 32 * 1024 * 1024;
  if (fileSize >= 512 * 1024 * 1024) return 16 * 1024 * 1024;
  if (fileSize >= 128 * 1024 * 1024) return 8 * 1024 * 1024;
  if (fileSize >= 32 * 1024 * 1024) return 4 * 1024 * 1024;
  return 2 * 1024 * 1024;
}

function pickConcurrency(fileSize) {
  // Higher parallelism = prepare finishes while match runs
  if (isLocalHost()) return 12;
  if (fileSize >= 1024 * 1024 * 1024) return 10;
  if (fileSize >= 200 * 1024 * 1024) return 8;
  return 6;
}

function formatEta(seconds) {
  const s = Math.max(0, Math.round(seconds || 0));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m < 60) return `${m}m ${r}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

async function uploadOneChunk(uploadId, index, blob) {
  let lastErr = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const fd = new FormData();
      fd.append("upload_id", uploadId);
      fd.append("index", String(index));
      fd.append("chunk", blob, `chunk_${index}`);
      const res = await fetch("/api/upload/chunk", {
        method: "POST",
        body: fd,
        // Avoid browser caching / connection stalls on long prepares
        cache: "no-store",
      });
      const data = await readJsonSafe(res);
      if (!res.ok) throw new Error(data.error || `Chunk ${index} fail`);
      return data;
    } catch (err) {
      lastErr = err;
      await new Promise((r) => setTimeout(r, 150 * (attempt + 1)));
    }
  }
  throw lastErr || new Error("Upload chunk failed");
}

async function uploadFileResilient(file, kind, onProgress) {
  await ensureServerUp();
  const CHUNK = pickChunkSize(file.size);
  const useChunks = file.size > 3 * 1024 * 1024;

  if (!useChunks) {
    onProgress?.(35, null);
    const body = new FormData();
    body.append("kind", kind);
    body.append("file", file);
    const res = await fetchWithRetry("/api/upload", { method: "POST", body }, 3);
    const data = await readJsonSafe(res);
    if (!res.ok) throw new Error(data.error || "Upload/path failed");
    onProgress?.(100, null);
    return data;
  }

  onProgress?.(1, null);
  const initRes = await fetchWithRetry(
    "/api/upload/init",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind,
        filename: file.name,
        size: file.size,
        chunk_size: CHUNK,
      }),
    },
    3
  );
  const init = await readJsonSafe(initRes);
  if (!initRes.ok) throw new Error(init.error || "Upload init fail");

  const chunkSize = init.chunk_size || CHUNK;
  const total = init.total_chunks || Math.ceil(file.size / chunkSize);
  const concurrency = Math.min(pickConcurrency(file.size), total);
  let nextIndex = 0;
  let finished = 0;
  let bytesDone = 0;
  const startedAt = performance.now();
  const workers = [];

  const runWorker = async () => {
    while (true) {
      const index = nextIndex++;
      if (index >= total) return;
      const start = index * chunkSize;
      const end = Math.min(file.size, start + chunkSize);
      const piece = file.slice(start, end);
      await uploadOneChunk(init.upload_id, index, piece);
      finished += 1;
      bytesDone += end - start;
      const pct = Math.round((finished / total) * 96);
      const elapsed = (performance.now() - startedAt) / 1000;
      const mbps = bytesDone / (1024 * 1024) / Math.max(0.5, elapsed);
      const remainBytes = file.size - bytesDone;
      const eta = remainBytes / (1024 * 1024) / Math.max(0.05, mbps);
      onProgress?.(pct, eta, mbps);
    }
  };

  for (let i = 0; i < concurrency; i++) workers.push(runWorker());
  await Promise.all(workers);

  const doneRes = await fetchWithRetry(
    "/api/upload/complete",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: init.upload_id }),
    },
    3
  );
  const done = await readJsonSafe(doneRes);
  if (!doneRes.ok) throw new Error(done.error || "Upload complete fail");
  onProgress?.(100, 0);
  return done;
}

function previewLocalMedia(kind, file) {
  if (kind === "movie") {
    if (state.movieUrl) URL.revokeObjectURL(state.movieUrl);
    state.movieUrl = URL.createObjectURL(file);
    const player = $("videoPlayer");
    if (player) {
      player.src = state.movieUrl;
      player.load();
      // CapCut-like: show first frame ASAP
      player.muted = true;
      const kick = () => {
        player.currentTime = 0.05;
        player.pause();
      };
      player.addEventListener("loadeddata", kick, { once: true });
    }
    $("playerPlaceholder")?.classList.add("hide");
  }
  if (kind === "narration_audio") $("audioWave")?.classList.add("active");
}

function kindForKey(key) {
  if (key === "movie") return "movie";
  if (key === "movie_srt") return "movie_srt";
  if (key === "narration_audio") return "narration_audio";
  return "narration_srt";
}

function markFileRowReady(key, file, label) {
  updateFileCard(key, file.name, label || `${formatBytes(file.size)} · ready`, {
    ready: true,
    syncing: false,
    error: false,
  });
  const card = fileCardEl(key);
  if (card) {
    card.classList.remove("syncing", "sync-error", "empty");
    card.classList.add("ready");
  }
}

function applyLocalFileInstant(key, kind, file) {
  // CapCut rule: import = instant green ready. NEVER show sync on the file row.
  state.localFiles[key] = file;
  state.synced[key] = false;
  markFileRowReady(key, file);
  previewLocalMedia(kind, file);
  showOk(`${file.name} imported ✓`);
  const modal = $("importModal");
  if (modal) modal.hidden = true;
  updateFilesHint();
}

function startBackgroundSync(key, kind, file, opts = {}) {
  // quiet=true (default): CapCut — progress NEVER on Project Files row
  const quiet = opts.quiet !== false;
  delete state.deferredSync[key];
  const job = (async () => {
    try {
      const data = await uploadFileResilient(file, kind, (pct, eta, mbps) => {
        if (state.localFiles[key] !== file) return;
        // Keep file row green "ready" — speed shown in Auto Cut only
        if (kind === "movie") {
          const etaTxt = eta != null && eta > 1 ? ` · ~${formatEta(eta)}` : "";
          const spd =
            mbps != null && mbps > 0 ? ` · ${mbps.toFixed(1)} MB/s` : "";
          setProgress(
            Math.min(92, 20 + pct * 0.7),
            `Preparing movie ${pct}%${spd}${etaTxt}`
          );
          setStatus("cutting", "active", `${pct}%`);
        }
      });
      if (state.localFiles[key] !== file) return data;
      state.synced[key] = true;
      markFileRowReady(key, file, `${data.meta || formatBytes(file.size)} · ready`);
      return data;
    } catch (err) {
      if (state.localFiles[key] !== file) throw err;
      state.synced[key] = false;
      if (!quiet || kind !== "movie") {
        setCardSyncMeta(key, `${formatBytes(file.size)} · retry`, { error: true });
      }
      // Movie stays looking ready; error goes to toast / export status
      if (kind === "movie") {
        setStatus("cutting", "error", "fail");
        setProgress(0, "Movie prepare fail");
      }
      showError(formatUploadError(err));
      updateFilesHint();
      throw err;
    }
  })();
  state.uploadJobs[key] = job;
  job.finally(() => {
    if (state.uploadJobs[key] === job) delete state.uploadJobs[key];
  });
  return job;
}

async function waitForPendingUploads() {
  const jobs = Object.values(state.uploadJobs).filter(Boolean);
  if (!jobs.length) return;
  await Promise.all(
    jobs.map((j) =>
      j.catch(() => {
        /* surfaced elsewhere */
      })
    )
  );
}

async function ensureSmallFilesSynced() {
  // SRT/audio — already look ready; quiet sync in background
  ["movie_srt", "narration_srt", "narration_audio"].forEach((key) => {
    const file = state.localFiles[key];
    if (!file || state.synced[key] || state.uploadJobs[key]) return;
    startBackgroundSync(key, kindForKey(key), file, { quiet: true });
  });
  await waitForPendingUploads();
}

async function ensureMovieSynced() {
  const file = state.localFiles.movie || state.deferredSync.movie;
  if (state.synced.movie) return true;
  if (!file) return false;
  // Never flip movie row to "sync %" — CapCut import already done
  markFileRowReady("movie", file);
  if (!state.uploadJobs.movie) {
    startBackgroundSync("movie", "movie", file, { quiet: true });
  }
  await waitForPendingUploads();
  return !!state.synced.movie;
}

async function startJob(mode, settings, useSample) {
  const res = await fetch("/api/auto-cut", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode,
      async: true,
      use_sample: !!useSample,
      ...settings,
    }),
  });
  const start = await readJsonSafe(res);
  if (!res.ok) throw new Error(start.error || "Auto cut fail");
  return pollJobUntilDone();
}

function acceptFileForKind(kind, file) {
  const name = (file.name || "").toLowerCase();
  if (kind === "movie")
    return /\.(mp4|mov|mkv|webm|avi|m4v)$/i.test(name) || file.type.startsWith("video/");
  if (kind === "narration_audio")
    return /\.(mp3|m4a|wav|aac|ogg|flac)$/i.test(name) || file.type.startsWith("audio/");
  if (kind === "movie_srt" || kind === "narration_srt")
    return /\.(srt|txt)$/i.test(name) || file.type === "application/x-subrip" || !file.type;
  return true;
}

function ingestSelectedFile(key, kind, file) {
  if (!file) return;
  if (!acceptFileForKind(kind, file)) {
    showError(
      kind === "movie"
        ? "Movie ke liye MP4/MOV select karo."
        : kind.includes("srt")
          ? "SRT file select karo (.srt)."
          : "Sahi audio file select karo."
    );
    return;
  }

  // CapCut: EVERY file type imports in ~0ms UI — green ready immediately
  applyLocalFileInstant(key, kind, file);

  if (kind === "movie") {
    // Movie stays local until Export cut — NO upload on import (this was the bug)
    state.deferredSync.movie = file;
    state.synced.movie = false;
    if (state.uploadJobs.movie) delete state.uploadJobs.movie;
    return;
  }

  // Tiny SRT/audio: quiet server copy (row stays ready, no sync spinner)
  startBackgroundSync(key, kind, file, { quiet: true });
}

function bindFileInput(inputId, key, kind) {
  const input = $(inputId);
  if (!input) return;
  input.addEventListener("change", (e) => {
    const file = e.target.files && e.target.files[0];
    // Reset so same file can be re-picked instantly
    e.target.value = "";
    if (!file) return;
    ingestSelectedFile(key, kind, file);
  });
}

function wireInstantImportDrop() {
  const zones = [
    document.querySelector(".project-files"),
    document.querySelector(".player-frame"),
    document.querySelector(".panel.left"),
  ].filter(Boolean);

  const onDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.add("drop-hot");
  };
  const onLeave = (e) => {
    e.preventDefault();
    e.currentTarget.classList.remove("drop-hot");
  };
  const onDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    e.currentTarget.classList.remove("drop-hot");
    const files = [...(e.dataTransfer?.files || [])];
    if (!files.length) return;
    files.forEach((file) => {
      const name = (file.name || "").toLowerCase();
      if (acceptFileForKind("movie", file)) ingestSelectedFile("movie", "movie", file);
      else if (acceptFileForKind("narration_audio", file))
        ingestSelectedFile("narration_audio", "narration_audio", file);
      else if (/\.srt$/i.test(name)) {
        // Prefer empty SRT slot; default movie_srt then narration
        if (!state.files.movie_srt) ingestSelectedFile("movie_srt", "movie_srt", file);
        else ingestSelectedFile("narration_srt", "narration_srt", file);
      } else showError(`Ye file type support nahi: ${file.name}`);
    });
  };
  zones.forEach((z) => {
    z.addEventListener("dragenter", onDrag);
    z.addEventListener("dragover", onDrag);
    z.addEventListener("dragleave", onLeave);
    z.addEventListener("drop", onDrop);
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

function renderRuler(maxEnd, width) {
  const ruler = $("timeRuler");
  if (!ruler) return;
  ruler.innerHTML = "";
  ruler.style.minWidth = `${width}px`;
  const step = state.pxPerSec >= 40 ? 1 : state.pxPerSec >= 20 ? 5 : 10;
  for (let t = 0; t <= maxEnd + step; t += step) {
    const mark = document.createElement("div");
    mark.className = "ruler-mark";
    mark.style.left = `${t * state.pxPerSec}px`;
    const m = Math.floor(t / 60);
    const s = Math.floor(t % 60);
    mark.textContent = `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    ruler.appendChild(mark);
  }
}

function renderTimeline() {
  const track = $("trackScenes");
  const audioTrack = $("trackAudio");
  const wave = $("audioWave");
  track.innerHTML = "";

  const clips = (state.clips || []).filter((c) => c.matched);
  if (!clips.length) {
    track.style.minWidth = "100%";
    audioTrack.style.minWidth = "100%";
    if (wave) {
      wave.classList.remove("active");
      wave.style.width = "";
    }
    renderRuler(30, 800);
    state.outputDuration = 0;
    updateFooterStats();
    return;
  }

  const maxEnd = Math.max(...clips.map((c) => c.timeline_end || 0), 1);
  state.outputDuration = maxEnd;
  const width = Math.max(800, maxEnd * state.pxPerSec + 80);
  track.style.minWidth = `${width}px`;
  audioTrack.style.minWidth = `${width}px`;
  renderRuler(maxEnd, width);

  if (wave) {
    wave.classList.add("active");
    wave.style.width = `${Math.max(40, maxEnd * state.pxPerSec)}px`;
  }

  clips.forEach((clip) => {
    const left = clip.timeline_start * state.pxPerSec;
    const w = Math.max(52, clip.clip_duration * state.pxPerSec - 3);
    const block = document.createElement("button");
    block.type = "button";
    block.className =
      "scene-block" + (state.selectedClipKey === clip.key ? " selected" : "");
    block.style.left = `${left}px`;
    block.style.width = `${w}px`;
    const n = String(clip.index).padStart(2, "0");
    const id = String(clip.scene_id ?? clip.index).padStart(3, "0");
    const durLabel = fmtTime(clip.clip_duration).slice(3, 8); // MM:SS
    block.innerHTML = `
      <span class="handle left"></span>
      <span class="badge">${n}</span>
      <span class="sid">SC_${id}</span>
      <span class="sdur">${durLabel}</span>
      <span class="handle right"></span>`;
    block.title = clip.scene_text || clip.narration_text || "";
    block.addEventListener("click", () => selectClip(clip.key));
    track.appendChild(block);
  });

  $("timelineScaleLabel").textContent = `Scale: ${state.pxPerSec}px/s`;
  const zoom = $("zoomSlider");
  if (zoom) zoom.value = String(state.pxPerSec);
  updateFooterStats();
}

function selectClip(key) {
  state.selectedClipKey = key;
  const clip = state.clips.find((c) => c.key === key);
  if (!clip) return;

  $("propEmpty").hidden = true;
  $("propDetails").hidden = false;
  if ($("propTitle")) {
    $("propTitle").textContent = clip.matched
      ? `Scene_${String(clip.scene_id ?? clip.index).padStart(3, "0")}`
      : `Narration_${clip.narration_index} (skipped)`;
  }
  const setVal = (id, val) => {
    const el = $(id);
    if (!el) return;
    if ("value" in el) el.value = val;
    else el.textContent = val;
  };
  setVal("propFile", state.files.movie || "movie.mp4");
  setVal(
    "propStart",
    clip.timeline_start != null ? fmtTime(clip.timeline_start) : "—"
  );
  setVal(
    "propEnd",
    clip.timeline_end != null ? fmtTime(clip.timeline_end) : "—"
  );
  setVal("propDur", clip.matched ? fmtTime(clip.clip_duration) : "—");
  setVal(
    "propSourceIn",
    clip.clip_start != null ? fmtTime(clip.clip_start) : "—"
  );
  setVal(
    "propSourceOut",
    clip.clip_end != null ? fmtTime(clip.clip_end) : "—"
  );

  const subText = clip.scene_text || clip.narration_text || "";
  if ($("propSubs")) $("propSubs").textContent = String(countSubtitleLines(subText));
  if ($("propNote")) {
    $("propNote").hidden = !subText;
    $("propNote").textContent = subText || "";
  }

  setVal(
    "propScore",
    clip.score != null ? Number(clip.score).toFixed(3) : "—"
  );
  setVal("propSceneId", clip.scene_id != null ? String(clip.scene_id) : "—");

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
  if ($("statClips")) $("statClips").textContent = String(clips.length);
  if ($("statSubs")) $("statSubs").textContent = String(
    Number($("statSubs").textContent) || 0
  );
  if (!clips.length) {
    $("statDuration").textContent = "00:00:00:00";
    $("statAvg").textContent = "00:00:00:00";
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
  const head = $("playheadTime");
  if (head) head.textContent = fmtTime(t).slice(0, 8);
  const dur =
    video.duration && Number.isFinite(video.duration)
      ? video.duration
      : state.outputDuration || 0;
  $("timecode").textContent = `${fmtTime(t)} / ${fmtTime(dur)}`;
  const scrub = $("scrubBar");
  if (scrub && dur > 0) scrub.value = String(Math.round((t / dur) * 1000));
  const fill = $("playerProgressFill");
  if (fill && dur > 0) fill.style.width = `${Math.min(100, (t / dur) * 100)}%`;
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
    const pl = $("projectNameLabel");
    if (pl) pl.textContent = state.projectName || "My Project 01";
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

async function runAutoCut(opts = {}) {
  const useSample = !!opts.useSample;
  if (
    !useSample &&
    (!state.files.movie || !state.files.movie_srt || !state.files.narration_srt)
  ) {
    updateFilesHint();
    showError(
      "Pehle Movie + Movie SRT + Narration SRT select karo. Sample chahiye to ⋯ → Load Sample."
    );
    return;
  }

  resetStatus();
  showDownloads(false);
  setBusy(true);
  const settings = readSettingsFromUi();

  try {
    if (useSample) {
      setStatus("analyze_movie", "active");
      const job = await startJob("full", settings, true);
      const data = job.result || {};
      const stats = data.stats || {};
      const sceneCount = (data.scenes || []).length || stats.matched || 0;
      setStatus("analyze_movie", "done", `${data.subtitle_count || 0} subs`);
      setStatus("analyze_narration", "done", `${data.narration_lines || 0} lines`);
      setStatus("matching", "done", `${sceneCount} scenes`);
      setStatus("cutting", "done", `${data.cut_clip_count || stats.matched || 0} clips`);
      setStatus("export", "done", "done");
      setProgress(100, "Done");
      applyPlanResult(data);
      showOk("Auto Cut complete");
      return;
    }

    // FAST PATH: start movie prepare IMMEDIATELY in parallel with SRT sync + match
    // (old flow waited until after match → felt stuck at Preparing 1%)
    setStatus("cutting", "active", "prepare…");
    const moviePreparePromise = ensureMovieSynced();

    setProgress(5, "SRT sync…");
    await ensureSmallFilesSynced();
    const smallFail = ["movie_srt", "narration_srt"].filter(
      (k) => state.files[k] && !state.synced[k]
    );
    if (smallFail.length) {
      throw new Error(`SRT sync fail: ${smallFail.join(", ")}. Tap retry.`);
    }

    // Match from SRT while movie prepare runs in parallel
    setStatus("analyze_movie", "active");
    showOk("Matching + preparing movie parallel (fast)…");
    const matchJob = await startJob("match_only", settings, false);
    const matchData = matchJob.result || {};
    const stats = matchData.stats || {};
    const sceneCount = (matchData.scenes || []).length || stats.matched || 0;
    setStatus("analyze_movie", "done", `${matchData.subtitle_count || 0} subs`);
    setStatus("analyze_narration", "done", `${matchData.narration_lines || 0} lines`);
    setStatus("matching", "done", `${sceneCount} scenes`);
    applyPlanResult(matchData);
    showOk("Timeline ready ✓");

    const movieOk = await moviePreparePromise;
    if (!movieOk) {
      throw new Error(
        "Movie prepare fail. Export dobara dabao, ya /download Student Pack use karo."
      );
    }

    setStatus("cutting", "active", "cutting…");
    const cutJob = await startJob("cut_export", settings, false);
    const cutData = cutJob.result || matchData;
    setStatus("cutting", "done", `${cutData.cut_clip_count || sceneCount} clips`);
    setStatus("export", "done", "done");
    setProgress(100, "Done");
    applyPlanResult(cutData);
    showOk("Auto Cut complete");
  } catch (err) {
    ["analyze_movie", "analyze_narration", "matching", "cutting", "export"].forEach(
      (s) => {
        const li = document.querySelector(`[data-step="${s}"]`);
        if (li && !li.classList.contains("done")) setStatus(s, "error", "fail");
      }
    );
    const msg = err.message || String(err);
    if (/Movie File \+ Movie SRT|Narration Timestamps|missing/i.test(msg)) {
      await syncSessionFromServer();
      showError(msg + " — Files dobara Project Files se select karo.");
    } else {
      showError(msg);
    }
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
    const pl = $("projectNameLabel");
    if (pl) pl.textContent = state.projectName || "My Project 01";
    const save = $("autoSaveLabel");
    if (save) save.textContent = "Auto-saved just now";
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
      const title = p.name || p.filename;
      btn.innerHTML = `<strong>${title}</strong><span>${p.meta || ""}</span>`;
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

  // Export button runs full auto-cut pipeline (then downloads appear)
  $("btnAutoCutTop")?.addEventListener("click", async () => {
    if (!state.files.movie && !state.files.movie_srt && !state.files.narration_srt) {
      showOk("Koi file nahi — Sample project load ho raha hai…");
      $("btnSample")?.click();
      return;
    }
    await runAutoCut({ useSample: false });
    const dl = $("downloadBlock");
    if (dl && !dl.hidden) dl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  $("btnMenuExport")?.addEventListener("click", () => $("btnAutoCutTop")?.click());
  $("btnMenuFile")?.addEventListener("click", () => {
    const menu = $("moreMenu");
    if (menu) menu.hidden = false;
    showOk("File — Home / New / Open / Save");
  });
  $("btnMenuEdit")?.addEventListener("click", () => {
    undoLast();
    showOk("Edit → Undo");
  });
  $("btnMenuView")?.addEventListener("click", () => {
    document.querySelector(".panel.left")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    showOk("View → Project Files + timeline");
  });
  $("btnMenuHelp")?.addEventListener("click", () => {
    showOk(
      "Help: 1) Movie 2) Movie SRT 3) Narration SRT select karo → Export. Sample: ⋯ menu."
    );
  });

  $("btnApplyRematch")?.addEventListener("click", () => {
    const val = $("sceneSelect")?.value;
    rematchSelected(val === "" ? null : Number(val), true);
  });
  $("btnSkipClip")?.addEventListener("click", () => rematchSelected(null, true));
  $("btnToolDel")?.addEventListener("click", () => rematchSelected(null, true));
  $("btnUndo")?.addEventListener("click", () => {
    closeMoreMenu();
    undoLast();
  });
  $("btnUndoTool")?.addEventListener("click", () => undoLast());
  $("btnSaveProject")?.addEventListener("click", () => {
    closeMoreMenu();
    saveProject();
  });
  $("btnOpenProject")?.addEventListener("click", () => {
    closeMoreMenu();
    openProjectModal();
  });
  $("btnHome")?.addEventListener("click", () => {
    closeMoreMenu();
    const q = new URLSearchParams(location.search).get("desktop") === "1" ? "?desktop=1" : "";
    location.href = `/home${q}`;
  });
  $("btnNewProject")?.addEventListener("click", async () => {
    closeMoreMenu();
    const name = window.prompt("New project name?", "My Project");
    if (!name) return;
    try {
      const res = await fetch("/api/project/new", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Create fail");
      const q = new URLSearchParams(location.search).get("desktop") === "1" ? "?desktop=1" : "";
      location.href = `/editor${q}`;
    } catch (err) {
      showError(err.message || String(err));
    }
  });
  $("brandHome")?.addEventListener("click", (e) => {
    e.preventDefault();
    const q = new URLSearchParams(location.search).get("desktop") === "1" ? "?desktop=1" : "";
    location.href = `/home${q}`;
  });
  $("btnResetProps")?.addEventListener("click", () => {
    if (!state.selectedClipKey) {
      showError("Pehle timeline se clip select karo.");
      return;
    }
    undoLast();
    showOk("Last edit undo / reset");
  });
  $("sceneSelect")?.addEventListener("change", () => {
    showOk("Scene option select hui — ab Apply Scene dabao.");
  });

  $("btnMoreMenu")?.addEventListener("click", (e) => {
    e.stopPropagation();
    const menu = $("moreMenu");
    if (menu) menu.hidden = !menu.hidden;
  });
  const openAdvanced = () => {
    closeMoreMenu();
    const box = $("advancedBox");
    if (box) {
      box.open = true;
      box.scrollIntoView({ behavior: "smooth", block: "nearest" });
      showOk("Settings open");
    }
  };
  $("btnToggleAdvanced")?.addEventListener("click", openAdvanced);
  $("btnRailSettings")?.addEventListener("click", openAdvanced);
  const openImportModal = () => {
    const m = $("importModal");
    if (m) m.hidden = false;
  };
  const closeImportModal = () => {
    const m = $("importModal");
    if (m) m.hidden = true;
  };
  $("btnRailImport")?.addEventListener("click", openImportModal);
  $("btnCloseImport")?.addEventListener("click", closeImportModal);
  $("importModal")?.addEventListener("click", (e) => {
    if (e.target === $("importModal")) closeImportModal();
  });
  document.querySelectorAll(".import-item[data-input]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-input");
      closeImportModal();
      if (id && $(id)) $(id).click();
    });
  });
  $("btnImportSample")?.addEventListener("click", () => {
    closeImportModal();
    $("btnSample")?.click();
  });
  document.querySelectorAll(".file-row[data-input]").forEach((row) => {
    row.addEventListener("click", () => {
      const key = row.getAttribute("data-key");
      // CapCut-like retry: failed sync → tap retries instantly (no picker)
      // Only retry failed sync — don't kick off movie upload just by tapping (keeps CapCut feel)
      if (key && state.localFiles[key] && row.classList.contains("sync-error")) {
        showOk("Sync retry (parallel)…");
        startBackgroundSync(key, kindForKey(key), state.localFiles[key]);
        return;
      }
      const id = row.getAttribute("data-input");
      if (id && $(id)) $(id).click();
      else showError("File picker open nahi hua — page refresh karo.");
    });
  });
  wireInstantImportDrop();
  const railActions = {
    media: () => {
      document.querySelector(".panel.left")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      showOk("Media — Project Files se movie/SRT select karo");
    },
    import: () => openImportModal(),
    subs: () => {
      document.querySelector('.file-row[data-key="movie_srt"]')?.click();
      showOk("Subtitles — Movie SRT select karo");
    },
    scenes: () => {
      document.querySelector(".timeline")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      showOk("Scenes — timeline pe clip click karke edit karo");
    },
    audio: () => {
      document.querySelector('.file-row[data-key="narration_audio"]')?.click();
      showOk("Audio — Narration Audio select karo");
    },
    text: () => {
      document.querySelector('.ptab[data-tab="subs"]')?.click();
      document.querySelector(".panel.right")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      showOk("Text / Subtitles panel");
    },
    trans: () => {
      openAdvanced();
      const tr = $("setTransition");
      if (tr) tr.focus();
      showOk("Transitions — Settings mein Transition choose karo");
    },
    fx: () => showOk("Effects next update mein aayenge — abhi Auto Cut use karo"),
    tools: () => {
      document.querySelector(".edit-tools")?.setAttribute("open", "");
      document.querySelector(".panel.right")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      showOk("Tools — pehle timeline clip select karo, phir Edit Tools");
    },
  };
  document.querySelectorAll(".rail-btn[data-rail]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".rail-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const action = railActions[btn.dataset.rail];
      if (action) action();
      else showOk(btn.dataset.rail || "Tool");
    });
  });
  document.querySelectorAll(".ptab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".ptab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      showOk(`${tab.textContent.trim()} tab`);
    });
  });
  document.querySelectorAll(".timeline-toolbar .tool:not([id])").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".timeline-toolbar .tool").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      showOk(`${btn.title || "Tool"} selected`);
    });
  });
  // Disabled transform sliders — explain instead of silent no-op
  document.querySelectorAll(".prop-card input:disabled, .prop-card select:disabled").forEach((el) => {
    el.parentElement?.addEventListener("click", () => {
      showOk("Yeh control Auto Cut ke baad fixed hai — Trim / Rematch Edit Tools se use karo.");
    });
  });
  $("btnAddTrack")?.addEventListener("click", () => {
    showOk("Extra tracks next update mein — abhi Narration + Scenes tracks kaafi hain");
  });
  document.addEventListener("click", (e) => {
    const wrap = document.querySelector(".menu-wrap");
    if (wrap && !wrap.contains(e.target)) closeMoreMenu();
  });
  $("btnCloseOpen")?.addEventListener("click", closeOpenModal);
  $("btnCloseOpen2")?.addEventListener("click", closeOpenModal);
  $("btnBrowseProject")?.addEventListener("click", () => $("fileProject")?.click());
  $("fileProject")?.addEventListener("change", (e) => {
    const file = e.target.files && e.target.files[0];
    if (file) loadProjectFromFile(file);
    e.target.value = "";
  });
  $("openModal")?.addEventListener("click", (e) => {
    if (e.target === $("openModal")) closeOpenModal();
  });

  $("btnTrimInMinus")?.addEventListener("click", () => trimSelected(0.25, 0));
  $("btnTrimInPlus")?.addEventListener("click", () => trimSelected(-0.25, 0));
  $("btnTrimOutMinus")?.addEventListener("click", () => trimSelected(0, -0.25));
  $("btnTrimOutPlus")?.addEventListener("click", () => trimSelected(0, 0.25));
  $("btnMoveLeft")?.addEventListener("click", () => moveSelected(-1));
  $("btnMoveRight")?.addEventListener("click", () => moveSelected(1));

  ["setQuality", "setTransition", "setMaxClip", "setBurnSubs"].forEach((id) => {
    $(id)?.addEventListener("change", async () => {
      const settings = readSettingsFromUi();
      try {
        await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(settings),
        });
        showOk("Setting saved");
      } catch (_) {
        /* ignore */
      }
    });
  });

  const loadSampleAndCut = async () => {
    resetStatus();
    showDownloads(false);
    closeMoreMenu();
    try {
      const res = await fetch("/api/load-sample", { method: "POST" });
      const data = await readJsonSafe(res);
      if (!res.ok) throw new Error(data.error || "Sample load fail");
      const markReady = (key, name, meta) => {
        state.synced[key] = true;
        state.localFiles[key] = null;
        updateFileCard(key, name, `${meta || ""} · ready`.replace(/^ ·/, ""), {
          ready: true,
        });
      };
      markReady("movie", data.files.movie, data.files.movie_meta);
      markReady("movie_srt", data.files.movie_srt, data.files.movie_srt_meta);
      markReady(
        "narration_srt",
        data.files.narration_srt,
        data.files.narration_srt_meta
      );
      if (data.files.narration_audio) {
        markReady(
          "narration_audio",
          data.files.narration_audio,
          data.files.narration_audio_meta || ""
        );
        $("audioWave")?.classList.add("active");
      }
      if (data.settings) writeSettingsToUi(data.settings);
      if ($("videoPlayer") && data.files.movie_url)
        $("videoPlayer").src = data.files.movie_url;
      $("playerPlaceholder")?.classList.add("hide");
      const pl = $("projectNameLabel");
      if (pl) pl.textContent = "My Project 01";
      updateFilesHint("Sample files ready ✓");
      await runAutoCut({ useSample: true });
    } catch (err) {
      showError(err.message || String(err));
    }
  };
  $("btnSample")?.addEventListener("click", loadSampleAndCut);
  $("btnRerunCut")?.addEventListener("click", () => {
    closeMoreMenu();
    runAutoCut({ useSample: false });
  });
  $("btnRerunCutMain")?.addEventListener("click", () => {
    if (!state.files.movie && !state.files.movie_srt) loadSampleAndCut();
    else runAutoCut({ useSample: false });
  });

  const video = $("videoPlayer");
  video.addEventListener("timeupdate", updatePlayhead);
  video.addEventListener("loadedmetadata", updatePlayhead);
  $("btnPlay").addEventListener("click", () => {
    if (!video.src) return;
    if (video.paused) {
      video.play();
      $("btnPlay").textContent = "❚❚";
    } else {
      video.pause();
      $("btnPlay").textContent = "▶";
    }
  });
  $("btnSeekBack").addEventListener("click", () => {
    video.currentTime = Math.max(0, video.currentTime - 5);
  });
  $("btnSeekFwd").addEventListener("click", () => {
    video.currentTime = video.currentTime + 5;
  });
  $("btnSeekStart")?.addEventListener("click", () => {
    video.currentTime = 0;
  });
  $("btnSeekEnd")?.addEventListener("click", () => {
    if (video.duration && Number.isFinite(video.duration))
      video.currentTime = Math.max(0, video.duration - 0.05);
  });
  $("volSlider")?.addEventListener("input", (e) => {
    video.volume = Math.max(0, Math.min(1, Number(e.target.value) / 100));
  });
  $("btnFullscreen")?.addEventListener("click", () => {
    const frame = document.querySelector(".player-frame");
    if (!frame) return;
    if (document.fullscreenElement) document.exitFullscreen();
    else frame.requestFullscreen?.();
  });
  $("scrubBar")?.addEventListener("input", (e) => {
    const dur =
      video.duration && Number.isFinite(video.duration)
        ? video.duration
        : state.outputDuration || 0;
    if (!dur) return;
    video.currentTime = (Number(e.target.value) / 1000) * dur;
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
  $("zoomSlider")?.addEventListener("input", (e) => {
    state.pxPerSec = Number(e.target.value) || 24;
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
    if (window.pywebview && window.pywebview.api && window.pywebview.api.quit) {
      await window.pywebview.api.quit();
      return;
    }
    await fetch("/api/shutdown", { method: "POST" });
    showOk("Closing SceneCut Pro+…");
    setTimeout(() => {
      window.close();
    }, 400);
  } catch (err) {
    try {
      window.close();
    } catch (_) {
      showError(err.message || String(err));
    }
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

async function syncSessionFromServer() {
  try {
    const res = await fetch("/api/session");
    const data = await readJsonSafe(res);
    if (!res.ok || !data.files) return;
    const map = {
      movie: "movie",
      movie_srt: "movie_srt",
      narration_audio: "narration_audio",
      narration_srt: "narration_srt",
    };
    Object.keys(map).forEach((key) => {
      const info = data.files[key];
      if (info && info.filename) {
        state.synced[key] = true;
        state.localFiles[key] = null;
        updateFileCard(key, info.filename, `${info.meta || ""} · ready`, {
          ready: true,
        });
        if (key === "movie" && info.url) {
          $("videoPlayer").src = info.url + "?t=" + Date.now();
          $("playerPlaceholder")?.classList.add("hide");
        }
        if (key === "narration_audio") $("audioWave")?.classList.add("active");
      } else if (!state.localFiles[key]) {
        state.files[key] = null;
        state.synced[key] = false;
      }
    });
    if (data.project_name && $("projectNameLabel")) {
      $("projectNameLabel").textContent = data.project_name;
    }
    updateFilesHint();
  } catch (_) {
    /* first paint without session is fine */
  }
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
  await syncSessionFromServer();
  updateFilesHint();
}

boot();
