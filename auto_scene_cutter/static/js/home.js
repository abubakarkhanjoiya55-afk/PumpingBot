(() => {
  const $ = (id) => document.getElementById(id);

  function deskQuery() {
    const q = new URLSearchParams(location.search);
    return q.get("desktop") === "1" ? "?desktop=1" : "";
  }

  function goEditor() {
    location.href = `/editor${deskQuery()}`;
  }

  function fmtWhen(mtime) {
    if (!mtime) return "";
    try {
      const d = new Date(mtime * 1000);
      return d.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (_) {
      return "";
    }
  }

  function tileLetter(name) {
    const t = (name || "P").trim();
    return (t[0] || "P").toUpperCase();
  }

  async function createProject(name) {
    const res = await fetch("/api/project/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Create fail");
    goEditor();
  }

  async function openProject(filename) {
    const res = await fetch("/api/project/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Open fail");
    goEditor();
  }

  async function loadSample() {
    const res = await fetch("/api/load-sample", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Sample fail");
    goEditor();
  }

  function renderProjects(projects, into, emptyEl) {
    into.innerHTML = "";
    if (!projects.length) {
      if (emptyEl) {
        emptyEl.hidden = false;
        into.appendChild(emptyEl);
      }
      return;
    }
    if (emptyEl) emptyEl.hidden = true;
    projects.forEach((p) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = into.id === "openList" ? "open-item" : "proj-tile";
      const title = p.name || p.filename;
      const when = fmtWhen(p.mtime);
      const clips = typeof p.clips === "number" ? `${p.clips} clips` : p.meta || "";
      if (into.id === "openList") {
        btn.innerHTML = `<strong>${title}</strong><span>${when || clips}</span>`;
      } else {
        btn.innerHTML = `
          <div class="proj-thumb" aria-hidden="true">${tileLetter(title)}</div>
          <div class="proj-meta">
            <strong>${title}</strong>
            <span>${when}${clips ? " · " + clips : ""}</span>
          </div>`;
      }
      btn.addEventListener("click", () => {
        openProject(p.filename).catch((err) => alert(err.message || String(err)));
      });
      into.appendChild(btn);
    });
  }

  async function fetchProjects() {
    const res = await fetch("/api/project/list");
    const data = await res.json();
    return data.projects || [];
  }

  async function refreshLists() {
    const projects = await fetchProjects();
    const empty = $("recentEmpty");
    renderProjects(projects, $("recentGrid"), empty);
    renderProjects(projects, $("openList"), null);
    if (!$("openList").children.length) {
      $("openList").innerHTML =
        `<div class="recent-empty">Koi saved project nahi. Pehle New project + Export/Save karo.</div>`;
    }
  }

  function openNameModal() {
    const modal = $("nameModal");
    const input = $("projectNameInput");
    const n = new Date();
    const stamp = `${n.getMonth() + 1}-${n.getDate()}`;
    input.value = `My Project ${stamp}`;
    modal.hidden = false;
    setTimeout(() => {
      input.focus();
      input.select();
    }, 30);
  }

  function closeNameModal() {
    $("nameModal").hidden = true;
  }

  function closeOpenModal() {
    $("openModal").hidden = true;
  }

  async function quitDesktop() {
    try {
      await fetch("/api/shutdown", { method: "POST" });
      setTimeout(() => window.close(), 300);
    } catch (err) {
      alert(err.message || String(err));
    }
  }

  function wire() {
    $("btnNewProject")?.addEventListener("click", openNameModal);
    $("btnHomeOpen")?.addEventListener("click", async () => {
      $("openModal").hidden = false;
      await refreshLists();
    });
    $("btnOpenProject")?.addEventListener("click", async () => {
      $("openModal").hidden = false;
      await refreshLists();
    });
    $("btnOpenCancel")?.addEventListener("click", closeOpenModal);
    $("btnNameCancel")?.addEventListener("click", closeNameModal);
    $("btnNameCreate")?.addEventListener("click", () => {
      const name = ($("projectNameInput").value || "").trim() || "Untitled Project";
      closeNameModal();
      createProject(name).catch((err) => alert(err.message || String(err)));
    });
    $("projectNameInput")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") $("btnNameCreate")?.click();
      if (e.key === "Escape") closeNameModal();
    });
    $("btnSample")?.addEventListener("click", () => {
      loadSample().catch((err) => alert(err.message || String(err)));
    });
    $("btnQuitHome")?.addEventListener("click", quitDesktop);

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeNameModal();
        closeOpenModal();
      }
    });
  }

  async function boot() {
    wire();
    try {
      const desk = await fetch("/api/desktop").then((r) => r.json());
      const q = new URLSearchParams(location.search).get("desktop");
      if ((desk && desk.desktop) || q === "1") {
        const btn = $("btnQuitHome");
        if (btn) btn.hidden = false;
      }
    } catch (_) {
      /* web */
    }
    try {
      await refreshLists();
    } catch (_) {
      /* empty ok */
    }
  }

  boot();
})();
