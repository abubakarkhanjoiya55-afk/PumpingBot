/**
 * CapCut-style in-app update notifications.
 * - Live UI: shows What's New, then reload (no Setup download)
 * - Desktop native: can call pywebview apply_update / local /api/update/apply
 */
(function () {
  const SEEN_KEY = "scenecut_seen_version";
  const DISMISS_KEY = "scenecut_dismiss_version";

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
      #scUpdateModal .actions{margin-top:18px;display:flex;gap:10px;justify-content:flex-end}
      #scUpdateModal .actions button{
        border:0;border-radius:10px;padding:10px 14px;font:700 13px/1 "Segoe UI",sans-serif;cursor:pointer;
      }
      #scUpdateModal .primary{background:linear-gradient(180deg,#9b74ff,#7c4dff);color:#fff}
      #scUpdateModal .ghost{background:rgba(255,255,255,.06);color:#f5f5f7;border:1px solid #2e2e34}
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

  function isDesktopShell() {
    const q = new URLSearchParams(location.search).get("desktop");
    return q === "1" || Boolean(window.pywebview);
  }

  async function fetchVersion() {
    const res = await fetch("/api/version", { cache: "no-store" });
    if (!res.ok) throw new Error("version check fail");
    return res.json();
  }

  function showModal(info) {
    ensureUi();
    $("scUpdateTitle").textContent = info.title || "New version available";
    $("scUpdateVer").textContent = `Version ${info.version}`;
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

  async function applyUpdate(info) {
    hideToast();
    hideModal();

    // Native desktop bridge (best)
    try {
      if (window.pywebview?.api?.apply_update) {
        await window.pywebview.api.apply_update();
        return;
      }
    } catch (_) {
      /* fall through */
    }

    // Local desktop server
    try {
      const res = await fetch("/api/update/apply", { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        if (data.ok) {
          markSeen(info.version);
          // Live UI: soft reload is enough
          if (data.action === "reload" || !isDesktopShell()) {
            location.reload();
            return;
          }
          // Local apply will restart app process
          return;
        }
      }
    } catch (_) {
      /* fall through */
    }

    // Already on live site — just reload + remember
    markSeen(info.version);
    location.reload();
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
      const info = await fetchVersion();
      if (!info || !info.version) return;

      // Expose for debug / settings
      window.SceneCutVersion = info;

      const seen = seenVersion();
      const dismissed = dismissedVersion();

      // First visit on this version → What's New
      if (seen && seen === info.version) return;
      if (dismissed && dismissed === info.version) return;

      wire(info);

      // CapCut-style: modal once for desktop shell, toast elsewhere
      if (isDesktopShell() || !seen) {
        showModal(info);
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
