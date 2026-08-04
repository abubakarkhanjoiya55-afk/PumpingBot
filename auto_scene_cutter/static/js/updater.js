/**
 * CapCut-style in-app update notifications.
 * Desktop: compare LOCAL build vs LIVE host, then silent Setup / student-pack sync.
 * Browser: What's New + reload.
 */
(function () {
  const SEEN_KEY = "scenecut_seen_version";
  const DISMISS_KEY = "scenecut_dismiss_version";
  const LIVE_FALLBACK = "https://scenecut-production.up.railway.app";

  function $(id) {
    return document.getElementById(id);
  }

  function ensureUi() {
    if ($("scUpdateModal")) return;
    const style = document.createElement("style");
    style.textContent = `
      #scUpdateToast{
        position:fixed;left:50%;bottom:22px;transform:translateX(-50%) translateY(20px);
        z-index:80;opacity:0;pointer-events:none;
        background:#1c1c1e;border:1px solid #2e2e34;color:#f5f5f7;
        border-radius:14px;padding:12px 14px;display:flex;gap:12px;align-items:center;
        box-shadow:0 16px 40px rgba(0,0,0,.45);font:600 14px/1.3 "Segoe UI",sans-serif;
        transition:opacity .25s ease, transform .25s ease; max-width:min(520px,92vw);
      }
      #scUpdateToast.show{opacity:1;pointer-events:auto;transform:translateX(-50%) translateY(0)}
      #scUpdateToast button{
        border:0;border-radius:10px;padding:8px 12px;font:700 13px/1 "Segoe UI",sans-serif;cursor:pointer;
      }
      #scUpdateToast .go{background:linear-gradient(180deg,#9b74ff,#7c4dff);color:#fff}
      #scUpdateToast .later{background:transparent;color:#a1a1aa}
      #scUpdateModal{
        position:fixed;inset:0;z-index:90;background:rgba(0,0,0,.55);
        display:none;place-items:center;padding:20px;backdrop-filter:blur(4px);
      }
      #scUpdateModal.open{display:grid}
      #scUpdateModal .card{
        width:min(440px,100%);background:#1c1c1e;border:1px solid #2e2e34;border-radius:16px;
        padding:22px;color:#f5f5f7;font-family:"Segoe UI",sans-serif;
        box-shadow:0 20px 50px rgba(0,0,0,.5);
      }
      #scUpdateModal h3{margin:0 0 6px;font-size:1.2rem}
      #scUpdateModal .ver{color:#a78bfa;font-size:.85rem;margin:0 0 12px}
      #scUpdateModal ul{margin:0;padding-left:18px;color:#a1a1aa;line-height:1.55}
      #scUpdateModal .actions{margin-top:18px;display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap}
      #scUpdateModal .actions button{
        border:0;border-radius:10px;padding:10px 14px;font:700 13px/1 "Segoe UI",sans-serif;cursor:pointer;
      }
      #scUpdateModal .primary{background:linear-gradient(180deg,#9b74ff,#7c4dff);color:#fff}
      #scUpdateModal .ghost{background:rgba(255,255,255,.06);color:#f5f5f7;border:1px solid #2e2e34}
      #scUpdateModal .busy{opacity:.7;pointer-events:none}
    `;
    document.head.appendChild(style);

    const toast = document.createElement("div");
    toast.id = "scUpdateToast";
    toast.innerHTML = `
      <div>
        <div id="scToastTitle">New version available</div>
        <div id="scToastSub" style="font-weight:500;color:#a1a1aa;font-size:12px;margin-top:2px"></div>
      </div>
      <button type="button" class="later" id="scToastLater">Later</button>
      <button type="button" class="go" id="scToastGo">Update</button>
    `;
    document.body.appendChild(toast);

    const modal = document.createElement("div");
    modal.id = "scUpdateModal";
    modal.innerHTML = `
      <div class="card" role="dialog" aria-labelledby="scUpdateTitle">
        <h3 id="scUpdateTitle">New version</h3>
        <p class="ver" id="scUpdateVer"></p>
        <ul id="scUpdateNotes"></ul>
        <div class="actions">
          <button type="button" class="ghost" id="scUpdateLater">Later</button>
          <button type="button" class="primary" id="scUpdateNow">Update Now</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  }

  function markSeen(version) {
    try {
      localStorage.setItem(SEEN_KEY, version || "");
    } catch (_) {
      /* ignore */
    }
  }

  function markDismiss(version) {
    try {
      localStorage.setItem(DISMISS_KEY, version || "");
    } catch (_) {
      /* ignore */
    }
  }

  function seenVersion() {
    try {
      return localStorage.getItem(SEEN_KEY) || "";
    } catch (_) {
      return "";
    }
  }

  function dismissedVersion() {
    try {
      return localStorage.getItem(DISMISS_KEY) || "";
    } catch (_) {
      return "";
    }
  }

  async function detectDesktop() {
    try {
      const desk = await fetch("/api/desktop", { cache: "no-store" }).then((r) =>
        r.ok ? r.json() : null
      );
      if (desk && desk.desktop) return true;
    } catch (_) {
      /* ignore */
    }
    const q = new URLSearchParams(location.search).get("desktop");
    return q === "1" || Boolean(window.pywebview);
  }

  async function fetchJson(url) {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error("fetch fail");
    return res.json();
  }

  async function resolveUpdateInfo(isDesktop) {
    let local = null;
    try {
      local = await fetchJson("/api/version");
    } catch (_) {
      local = null;
    }

    let remote = null;
    // Prefer server-side check (desktop hits live)
    try {
      const cur = (local && local.version) || "";
      remote = await fetchJson(
        `/api/update/check?current=${encodeURIComponent(cur)}`
      );
    } catch (_) {
      remote = null;
    }

    // Browser / fallback: hit live host directly
    if (!remote || !remote.latest) {
      try {
        const liveBase =
          (local && local.live_url) ||
          (window.SceneCutLiveUrl) ||
          LIVE_FALLBACK;
        const man = await fetchJson(`${liveBase}/api/version`);
        remote = {
          ok: true,
          latest: man.version,
          title: man.title,
          notes: man.notes,
          setup_url: man.setup_url || man.setup_exe,
          update_available:
            !!(man.version && local && local.version && man.version !== local.version) ||
            !(local && local.version),
        };
      } catch (_) {
        /* offline */
      }
    }

    const latest = (remote && remote.latest) || (local && local.version) || "";
    const current = (local && local.version) || "";
    const updateAvailable =
      !!(remote && remote.update_available) ||
      !!(latest && current && latest !== current);

    return {
      version: latest,
      current,
      title: (remote && remote.title) || (local && local.title) || "New version",
      notes:
        (remote && remote.notes) ||
        (local && local.notes) ||
        ["Bug fixes and improvements"],
      setup_url: (remote && remote.setup_url) || (local && local.setup_url),
      update_available: updateAvailable,
      isDesktop,
      local,
    };
  }

  function showModal(info) {
    ensureUi();
    $("scUpdateTitle").textContent = info.title || "New version available";
    $("scUpdateVer").textContent = info.current
      ? `v${info.current} → v${info.version}`
      : `Version ${info.version}`;
    const ul = $("scUpdateNotes");
    ul.innerHTML = "";
    (info.notes || ["Bug fixes and improvements"]).forEach((n) => {
      const li = document.createElement("li");
      li.textContent = n;
      ul.appendChild(li);
    });
    $("scUpdateModal").classList.add("open");
  }

  function hideModal() {
    $("scUpdateModal")?.classList.remove("open");
  }

  function showToast(info) {
    ensureUi();
    $("scToastTitle").textContent = info.title || "New version available";
    $("scToastSub").textContent = `v${info.version} — Update Now`;
    $("scUpdateToast").classList.add("show");
  }

  function hideToast() {
    $("scUpdateToast")?.classList.remove("show");
  }

  function setUpdatingUi(on) {
    const btn = $("scUpdateNow");
    const card = document.querySelector("#scUpdateModal .card");
    if (btn) btn.textContent = on ? "Updating…" : "Update Now";
    if (card) card.classList.toggle("busy", !!on);
  }

  async function applyUpdate(info) {
    hideToast();
    setUpdatingUi(true);

    // 1) Desktop dedicated endpoint
    try {
      const resDesk = await fetch("/api/desktop/update", { method: "POST" });
      if (resDesk.ok) {
        const data = await resDesk.json();
        if (data.ok || data.updated) {
          markSeen(info.version);
          $("scUpdateTitle").textContent = "Update installing…";
          $("scUpdateVer").textContent = "App restart hogi — 20-40 sec wait";
          return;
        }
      }
    } catch (_) {
      /* fall through */
    }

    // 2) Generic apply
    try {
      const res = await fetch("/api/update/apply", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        if (data.ok) {
          markSeen(info.version);
          if (data.action === "reload" || !info.isDesktop) {
            location.reload();
            return;
          }
          $("scUpdateTitle").textContent = "Update installing…";
          $("scUpdateVer").textContent = "App restart hogi — wait…";
          return;
        }
      }
    } catch (_) {
      /* fall through */
    }

    // 3) Open Setup.exe download as last resort
    if (info.setup_url) {
      window.open(info.setup_url, "_blank");
    }
    markSeen(info.version);
    setUpdatingUi(false);
    hideModal();
    if (!info.isDesktop) location.reload();
  }

  function wire(info) {
    ensureUi();
    $("scToastLater").onclick = () => {
      markDismiss(info.version);
      hideToast();
    };
    $("scToastGo").onclick = () => applyUpdate(info);
    $("scUpdateLater").onclick = () => {
      markDismiss(info.version);
      hideModal();
    };
    $("scUpdateNow").onclick = () => applyUpdate(info);
  }

  async function run() {
    try {
      const isDesktop = await detectDesktop();
      const info = await resolveUpdateInfo(isDesktop);
      if (!info || !info.version) return;

      window.SceneCutVersion = info;

      // Nothing new
      if (!info.update_available) {
        // Still show What's New once for this version on first open
        const seen = seenVersion();
        if (seen === info.version) return;
        const dismissed = dismissedVersion();
        if (dismissed === info.version) return;
        wire(info);
        if (!seen) showModal(info);
        return;
      }

      // Update available — always nudge (ignore old dismiss for older version)
      const dismissed = dismissedVersion();
      if (dismissed && dismissed === info.version && !isDesktop) return;

      wire(info);
      if (isDesktop) {
        showModal(info);
        // CapCut-style: desktop pe auto-start update after short beat
        setTimeout(() => {
          if ($("scUpdateModal")?.classList.contains("open")) {
            applyUpdate(info);
          }
        }, 1200);
      } else {
        showToast(info);
      }
    } catch (_) {
      /* offline / ignore */
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
