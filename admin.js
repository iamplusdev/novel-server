/* 爱小说 Admin SPA — vanilla JS, no framework */
(function () {
  "use strict";

  const TOKEN_KEY = "novel_admin_token";
  const THEME_KEY = "novel_theme_mode";
  const GRID_SIZE_KEY = "novel_grid_size";
  const DRAWER_W_KEY = "novel_drawer_width";
  const state = {
    token: localStorage.getItem(TOKEN_KEY) || "",
    page: 1,
    pageSize: 24,
    total: 0,
    items: [],
    viewMode: localStorage.getItem("novel_view_mode") || "grid",
    theme: localStorage.getItem(THEME_KEY) || "auto",
    stats: null,
    sourceJson: null,
  };

  const $ = (id) => document.getElementById(id);
  const els = {
    login: $("login"),
    app: $("app"),
    tokenInput: $("token-input"),
    loginBtn: $("login-btn"),
    loginError: $("login-error"),
    logoutBtn: $("logout-btn"),
    baseUrlLabel: $("base-url-label"),
    apiBase: $("api-base"),
    novelsPath: $("novels-path"),
    statBooks: $("stat-books"),
    statWords: $("stat-words"),
    libCount: $("lib-count"),
    searchInput: $("search-input"),
    categoryFilter: $("category-filter"),
    statusFilter: $("status-filter"),
    viewMode: $("view-mode"),
    gridSize: $("grid-size"),
    themeSelect: $("theme-select"),
    refreshBtn: $("refresh-btn"),
    gridWrap: $("grid-wrap"),
    listWrap: $("list-wrap"),
    prevPage: $("prev-page"),
    nextPage: $("next-page"),
    pageLabel: $("page-label"),
    importBtn: $("import-btn"),
    importRefresh: $("import-refresh"),
    importLog: $("import-log"),
    sourcePreview: $("source-preview"),
    copySource: $("copy-source"),
    backupAutoPill: $("backup-auto-pill"),
    backupRun: $("backup-run"),
    backupListRefresh: $("backup-list-refresh"),
    davUrl: $("dav-url"),
    davPath: $("dav-path"),
    davUser: $("dav-user"),
    davPass: $("dav-pass"),
    davInterval: $("dav-interval"),
    davKeep: $("dav-keep"),
    davAuto: $("dav-auto"),
    davSave: $("dav-save"),
    davTest: $("dav-test"),
    backupTableBody: $("backup-table-body"),
    backupLog: $("backup-log"),
    drawer: $("drawer"),
    drawerMask: $("drawer-mask"),
    drawerResize: $("drawer-resize"),
    drawerTitle: $("drawer-title"),
    drawerClose: $("drawer-close"),
    editId: $("edit-id"),
    coverPreview: $("cover-preview"),
    coverFile: $("cover-file"),
    editTitle: $("edit-title"),
    editAuthor: $("edit-author"),
    editCategory: $("edit-category"),
    editStatus: $("edit-status"),
    editTags: $("edit-tags"),
    editIntro: $("edit-intro"),
    editMeta: $("edit-meta"),
    saveBtn: $("save-btn"),
    cancelBtn: $("cancel-btn"),
    deleteBtn: $("delete-btn"),
    toast: $("toast"),
  };

  const FALLBACK_CATEGORIES = [
    "玄幻", "奇幻", "武侠", "仙侠", "都市", "现实", "军事", "历史",
    "游戏", "体育", "科幻", "诸天无限", "悬疑灵异", "轻小说", "短篇", "未分类",
  ];

  function toast(msg, type) {
    els.toast.textContent = msg;
    els.toast.hidden = false;
    els.toast.className = "toast " + (type || "");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { els.toast.hidden = true; }, 2600);
  }

  function applyTheme(mode) {
    state.theme = mode || "auto";
    localStorage.setItem(THEME_KEY, state.theme);
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const dark = state.theme === "dark" || (state.theme === "auto" && prefersDark);
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    if (els.themeSelect && els.themeSelect.value !== state.theme) {
      els.themeSelect.value = state.theme;
    }
  }

  function applyGridSize(px) {
    const n = Math.min(240, Math.max(110, Number(px) || 150));
    if (els.gridSize) els.gridSize.value = String(n);
    if (els.gridWrap) els.gridWrap.style.setProperty("--cover-w", n + "px");
    localStorage.setItem(GRID_SIZE_KEY, String(n));
  }

  function applyDrawerWidth(px) {
    const n = Math.min(Math.round(window.innerWidth * 0.9), Math.max(360, Number(px) || 520));
    document.documentElement.style.setProperty("--drawer-width", n + "px");
    localStorage.setItem(DRAWER_W_KEY, String(n));
  }

  function initDrawerResize() {
    const handle = els.drawerResize;
    if (!handle) return;
    let dragging = false;
    let startX = 0;
    let startW = 0;
    const onMove = (e) => {
      if (!dragging) return;
      const x = e.touches ? e.touches[0].clientX : e.clientX;
      const next = startW + (startX - x);
      applyDrawerWidth(next);
    };
    const onUp = () => {
      dragging = false;
      handle.classList.remove("active");
      document.body.style.userSelect = "";
    };
    handle.addEventListener("mousedown", (e) => {
      dragging = true;
      startX = e.clientX;
      startW = els.drawer.getBoundingClientRect().width;
      handle.classList.add("active");
      document.body.style.userSelect = "none";
      e.preventDefault();
    });
    handle.addEventListener("touchstart", (e) => {
      dragging = true;
      startX = e.touches[0].clientX;
      startW = els.drawer.getBoundingClientRect().width;
      handle.classList.add("active");
    }, { passive: true });
    window.addEventListener("mousemove", onMove);
    window.addEventListener("touchmove", onMove, { passive: true });
    window.addEventListener("mouseup", onUp);
    window.addEventListener("touchend", onUp);
    handle.addEventListener("dblclick", () => applyDrawerWidth(520));
  }

  async function api(path, options) {
    const headers = Object.assign({ Accept: "application/json" }, (options && options.headers) || {});
    if (state.token) headers.Authorization = "Bearer " + state.token;
    const opts = Object.assign({}, options, { headers });
    if (opts.body && !(opts.body instanceof FormData) && typeof opts.body !== "string") {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, opts);
    if (res.status === 401) {
      logout(false);
      throw new Error("Token 无效或已过期");
    }
    let data = null;
    const text = await res.text();
    try { data = text ? JSON.parse(text) : null; } catch (_) { data = { detail: text }; }
    if (!res.ok) {
      const detail = data && data.detail;
      throw new Error(typeof detail === "string" ? detail : "请求失败 " + res.status);
    }
    return data;
  }

  function showLogin() {
    els.login.hidden = false;
    els.app.hidden = true;
  }

  function showApp() {
    els.login.hidden = true;
    els.app.hidden = false;
    els.viewMode.value = state.viewMode;
  }

  async function login() {
    const token = els.tokenInput.value.trim();
    if (!token) { els.loginError.hidden = false; els.loginError.textContent = "请输入 Token"; return; }
    state.token = token;
    localStorage.setItem(TOKEN_KEY, token);
    els.loginError.hidden = true;
    try {
      await loadStats();
      showApp();
      await Promise.all([loadBooks(), loadSourceJson()]);
    } catch (err) {
      els.loginError.hidden = false;
      els.loginError.textContent = err.message || "登录失败";
      state.token = "";
      localStorage.removeItem(TOKEN_KEY);
    }
  }

  function logout(notify) {
    state.token = "";
    localStorage.removeItem(TOKEN_KEY);
    showLogin();
    if (notify !== false) toast("已退出登录");
  }

  function fmtWords(n) {
    if (!n && n !== 0) return "—";
    if (n >= 100000000) return (n / 100000000).toFixed(1) + " 亿";
    if (n >= 10000) return (n / 10000).toFixed(1) + " 万";
    return String(n);
  }

  function fillCategorySelects(categories) {
    const names = (categories && categories.length)
      ? categories.map((c) => (typeof c === "string" ? c : c.name))
      : FALLBACK_CATEGORIES;
    function fill(select, keepAll) {
      const current = select.value;
      select.innerHTML = "";
      if (keepAll) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "全部分类";
        select.appendChild(opt);
      }
      names.forEach((n) => {
        const opt = document.createElement("option");
        opt.value = n;
        opt.textContent = n;
        select.appendChild(opt);
      });
      if (current && names.includes(current)) select.value = current;
    }
    fill(els.categoryFilter, true);
    fill(els.editCategory, false);
  }

  async function loadStats() {
    const data = await api("/api/admin/stats");
    state.stats = data;
    els.statBooks.textContent = data.total_books ?? 0;
    els.statWords.textContent = fmtWords(data.total_words);
    els.baseUrlLabel.textContent = data.public_base_url || location.origin;
    els.apiBase.textContent = data.public_base_url || location.origin;
    fillCategorySelects(data.categories);
    renderImportLog(data.import);
  }

  function currentQuery() {
    const params = new URLSearchParams();
    params.set("page", String(state.page));
    params.set("page_size", String(state.pageSize));
    if (els.searchInput.value.trim()) params.set("q", els.searchInput.value.trim());
    if (els.categoryFilter.value) params.set("category", els.categoryFilter.value);
    if (els.statusFilter.value) params.set("status", els.statusFilter.value);
    return params.toString();
  }

  async function loadBooks() {
    const data = await api("/api/admin/books?" + currentQuery());
    state.items = data.items || [];
    state.total = data.total || 0;
    els.libCount.textContent = String(state.total);
    const pages = Math.max(1, Math.ceil(state.total / state.pageSize));
    if (state.page > pages) state.page = pages;
    els.pageLabel.textContent = state.page + " / " + pages;
    els.prevPage.disabled = state.page <= 1;
    els.nextPage.disabled = state.page >= pages;
    renderLibrary();
  }

  function statusChip(status) {
    if (status === "连载") return '<span class="chip run">连载</span>';
    if (status === "完结") return '<span class="chip ok">完结</span>';
    return '<span class="chip">未知</span>';
  }

  function renderLibrary() {
    const grid = state.viewMode === "grid";
    els.gridWrap.hidden = !grid;
    els.listWrap.hidden = grid;
    const emptyText = "暂无书籍，请到「导入」页导入 TXT。";

    if (grid) {
      if (!state.items.length) {
        els.gridWrap.innerHTML = '<div class="muted" style="grid-column:1/-1;padding:32px;text-align:center">' + emptyText + "</div>";
        return;
      }
      els.gridWrap.innerHTML = state.items.map((b) => {
        const cover = b.cover_url
          ? `<img src="${escapeAttr(b.cover_url)}" alt="" loading="lazy" />`
          : `<div class="placeholder">${escapeHtml(b.name)}</div>`;
        return `
          <article class="book-card" data-id="${b.id}">
            <div class="book-cover">${cover}</div>
            <div class="book-meta">
              <div class="book-name" title="${escapeAttr(b.name)}">${escapeHtml(b.name)}</div>
              <div class="book-sub">
                <span class="chip cat">${escapeHtml(b.category || "—")}</span>
                ${statusChip(b.status)}
                <span>${escapeHtml(b.author || "佚名")}</span>
              </div>
            </div>
          </article>`;
      }).join("");
      els.gridWrap.querySelectorAll(".book-card").forEach((card) => {
        card.addEventListener("click", () => openDrawer(Number(card.dataset.id)));
      });
    } else {
      if (!state.items.length) {
        els.listWrap.innerHTML = '<div class="muted" style="padding:32px;text-align:center">' + emptyText + "</div>";
        return;
      }
      els.listWrap.innerHTML = state.items.map((b) => {
        const cover = b.cover_url
          ? `<img src="${escapeAttr(b.cover_url)}" alt="" loading="lazy" />`
          : `<div class="placeholder">${escapeHtml((b.name || "").slice(0, 6))}</div>`;
        const intro = b.intro ? escapeHtml(b.intro) : "暂无简介";
        return `
          <article class="book-row" data-id="${b.id}">
            <div class="row-cover">${cover}</div>
            <div class="row-body">
              <div class="row-title" title="${escapeAttr(b.name)}">${escapeHtml(b.name)}</div>
              <div class="row-meta">
                <span class="chip cat">${escapeHtml(b.category || "—")}</span>
                ${statusChip(b.status)}
                <span>${escapeHtml(b.author || "佚名")}</span>
                ${(b.tags || []).slice(0, 4).map((t) => `<span class="chip">${escapeHtml(t)}</span>`).join("")}
              </div>
              <div class="row-intro">${intro}</div>
            </div>
            <div class="row-side">
              <span>${fmtWords(b.word_count)}字</span>
              <span>${b.chapter_count ?? 0} 章</span>
              <button class="btn btn-ghost btn-sm" data-edit="${b.id}">编辑</button>
            </div>
          </article>`;
      }).join("");
      els.listWrap.querySelectorAll(".book-row").forEach((row) => {
        row.addEventListener("click", () => openDrawer(Number(row.dataset.id)));
      });
      els.listWrap.querySelectorAll("[data-edit]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          openDrawer(Number(btn.dataset.edit));
        });
      });
    }
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function escapeAttr(s) { return escapeHtml(s).replace(/'/g, "&#39;"); }

  async function openDrawer(id) {
    const book = await api("/api/admin/books/" + id);
    els.editId.value = String(book.id);
    els.drawerTitle.textContent = "编辑 · " + book.name;
    els.editTitle.value = book.name || "";
    els.editAuthor.value = book.author || "";
    ensureOption(els.editCategory, book.category);
    els.editCategory.value = book.category || "";
    els.editStatus.value = book.status || "完结";
    els.editTags.value = (book.tags || []).join(", ");
    els.editIntro.value = book.intro || "";
    els.coverPreview.src = book.cover_url || placeholderDataUri(book.name || "");
    els.coverPreview.alt = book.name || "封面";
    els.editMeta.textContent = [
      "ID " + book.id,
      "章节 " + (book.chapter_count || 0),
      "字数 " + fmtWords(book.word_count),
      book.source_path ? "源 " + book.source_path : "",
    ].filter(Boolean).join(" · ");
    els.drawer.hidden = false;
    els.drawerMask.hidden = false;
  }

  function ensureOption(select, value) {
    if (!value) return;
    const has = Array.from(select.options).some((o) => o.value === value);
    if (!has) {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = value;
      select.appendChild(opt);
    }
  }

  function placeholderDataUri(text) {
    const t = (text || "").slice(0, 8);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="128"><rect width="100%" height="100%" fill="#1e2430"/><text x="50%" y="50%" fill="#8b93a7" font-size="12" text-anchor="middle" font-family="sans-serif">${t.replace(/[<>&]/g, "")}</text></svg>`;
    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  }

  function closeDrawer() {
    els.drawer.hidden = true;
    els.drawerMask.hidden = true;
  }

  async function saveBook() {
    const id = Number(els.editId.value);
    if (!id) return;
    const payload = {
      title: els.editTitle.value.trim(),
      author: els.editAuthor.value.trim() || "佚名",
      category: els.editCategory.value,
      status: els.editStatus.value,
      tags: els.editTags.value,
      intro: els.editIntro.value,
    };
    try {
      if (els.coverFile.files && els.coverFile.files[0]) {
        const fd = new FormData();
        fd.append("file", els.coverFile.files[0]);
        await api("/api/admin/books/" + id + "/cover", { method: "POST", body: fd });
      }
      const updated = await api("/api/admin/books/" + id, {
        method: "PATCH",
        body: payload,
      });
      els.coverPreview.src = updated.cover_url || placeholderDataUri(updated.name);
      els.coverFile.value = "";
      toast("已保存", "ok");
      await Promise.all([loadBooks(), loadStats()]);
    } catch (err) {
      toast(err.message || "保存失败", "err");
    }
  }

  async function deleteBook() {
    const id = Number(els.editId.value);
    const name = els.editTitle.value;
    if (!id) return;
    if (!confirm("确认删除《" + name + "》？章节与封面将一并删除，源 TXT 文件保留。")) return;
    try {
      await api("/api/admin/books/" + id, { method: "DELETE" });
      toast("已删除《" + name + "》", "ok");
      closeDrawer();
      await Promise.all([loadBooks(), loadStats()]);
    } catch (err) {
      toast(err.message || "删除失败", "err");
    }
  }

  function renderImportLog(importStatus) {
    if (!importStatus) {
      els.importLog.textContent = "尚未运行导入。";
      return;
    }
    if (importStatus.running) {
      els.importLog.textContent = "导入进行中…\n请稍候刷新。";
      return;
    }
    const last = importStatus.last;
    if (!last) {
      els.importLog.textContent = "尚未运行导入。";
      return;
    }
    const lines = [];
    lines.push("结果: " + (last.summary || ""));
    lines.push("时间: " + (last.finished_at || ""));
    lines.push("");
    if (last.added && last.added.length) {
      lines.push("[新增 " + last.added.length + "]");
      last.added.forEach((x) => lines.push("  + " + x));
      lines.push("");
    }
    if (last.updated && last.updated.length) {
      lines.push("[更新 " + last.updated.length + "]");
      last.updated.forEach((x) => lines.push("  ~ " + x));
      lines.push("");
    }
    if (last.skipped && last.skipped.length) {
      lines.push("[跳过 " + last.skipped.length + "]（内容未变化）");
      last.skipped.slice(0, 20).forEach((x) => lines.push("  · " + x));
      if (last.skipped.length > 20) lines.push("  … 共 " + last.skipped.length + " 本");
      lines.push("");
    }
    if (last.failed && last.failed.length) {
      lines.push("[失败 " + last.failed.length + "]");
      last.failed.forEach((x) => lines.push("  ! " + x));
    }
    els.importLog.textContent = lines.join("\n");
  }

  async function startImport() {
    try {
      const res = await api("/api/admin/import", { method: "POST" });
      toast(res.started ? "导入已开始" : "导入已在进行中", "ok");
      renderImportLog(res.import);
      pollImport();
    } catch (err) {
      toast(err.message || "导入失败", "err");
    }
  }

  function pollImport() {
    let n = 0;
    const timer = setInterval(async () => {
      n += 1;
      try {
        const st = await api("/api/admin/import/status");
        renderImportLog(st);
        if (!st.running) {
          clearInterval(timer);
          await Promise.all([loadBooks(), loadStats()]);
          toast("导入完成", "ok");
        }
      } catch (_) {
        clearInterval(timer);
      }
      if (n > 60) clearInterval(timer);
    }, 1500);
  }

  async function refreshImport() {
    const st = await api("/api/admin/import/status");
    renderImportLog(st);
  }

  async function loadSourceJson() {
    try {
      let json = null;
      try {
        json = await api("/api/legado/book-source");
      } catch (_) {
        const res = await fetch("/legado_book_source.json");
        if (!res.ok) throw new Error("书源文件不存在");
        json = await res.json();
        const base = (state.stats && state.stats.public_base_url) || location.origin;
        json.bookSourceUrl = base;
      }
      state.sourceJson = json;
      els.sourcePreview.textContent = JSON.stringify(json, null, 2);
    } catch (err) {
      els.sourcePreview.textContent = "无法加载书源: " + (err.message || err);
    }
  }

  function copySource() {
    const text = els.sourcePreview.textContent || "";
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => toast("书源 JSON 已复制", "ok"))
        .catch(() => fallbackCopy(text));
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); toast("已复制", "ok"); }
    catch (_) { toast("复制失败，请手动选择", "err"); }
    document.body.removeChild(ta);
  }

  // —— WebDAV 备份 ——
  function fmtSize(n) {
    if (!n && n !== 0) return "—";
    if (n >= 1048576) return (n / 1048576).toFixed(1) + " MB";
    if (n >= 1024) return (n / 1024).toFixed(1) + " KB";
    return n + " B";
  }

  function backupLog(text) {
    els.backupLog.textContent = text || "";
  }

  function appendBackupLog(text) {
    const prev = els.backupLog.textContent || "";
    const line = "[" + new Date().toLocaleTimeString() + "] " + text;
    els.backupLog.textContent = (prev && prev !== "尚未操作。" ? prev + "\n" : "") + line;
    els.backupLog.scrollTop = els.backupLog.scrollHeight;
  }

  async function loadBackupConfig() {
    const cfg = await api("/api/admin/backup/config");
    els.davUrl.value = cfg.webdav_url || "";
    els.davPath.value = cfg.remote_path || "novel-server-backups";
    els.davUser.value = cfg.username || "";
    els.davPass.placeholder = cfg.password_set ? "已保存，留空表示不修改" : "输入 WebDAV 密码";
    els.davInterval.value = cfg.interval_hours || 24;
    els.davKeep.value = cfg.keep_count || 7;
    els.davAuto.checked = !!cfg.auto_enabled;
    els.backupAutoPill.textContent = cfg.auto_enabled
      ? ("自动备份 · 每 " + (cfg.interval_hours || 24) + "h")
      : "未启用自动";
  }

  async function collectBackupConfig() {
    const payload = {
      webdav_url: els.davUrl.value.trim(),
      username: els.davUser.value.trim(),
      remote_path: els.davPath.value.trim() || "novel-server-backups",
      auto_enabled: els.davAuto.checked,
      interval_hours: Number(els.davInterval.value) || 24,
      keep_count: Number(els.davKeep.value) || 7,
    };
    const pass = els.davPass.value;
    if (pass) payload.password = pass;
    return payload;
  }

  async function saveBackupConfig() {
    try {
      const payload = await collectBackupConfig();
      const saved = await api("/api/admin/backup/config", { method: "PUT", body: payload });
      els.davPass.value = "";
      els.davPass.placeholder = saved.password_set ? "已保存，留空表示不修改" : "输入 WebDAV 密码";
      els.backupAutoPill.textContent = saved.auto_enabled
        ? ("自动备份 · 每 " + saved.interval_hours + "h")
        : "未启用自动";
      appendBackupLog("配置已保存");
      toast("备份配置已保存", "ok");
    } catch (err) {
      toast(err.message || "保存失败", "err");
    }
  }

  async function testBackupConn() {
    try {
      const payload = await collectBackupConfig();
      const res = await api("/api/admin/backup/test", { method: "POST", body: payload });
      appendBackupLog("测试连接: " + res.message);
      toast(res.message || "连接成功", "ok");
    } catch (err) {
      appendBackupLog("测试失败: " + (err.message || err));
      toast(err.message || "连接失败", "err");
    }
  }

  function renderBackupList(items) {
    if (!items || !items.length) {
      els.backupTableBody.innerHTML = '<tr><td colspan="4" class="muted" style="text-align:center;padding:18px">暂无备份，点「立即备份」创建</td></tr>';
      return;
    }
    els.backupTableBody.innerHTML = items.map((it) => `
      <tr data-name="${escapeAttr(it.name)}">
        <td class="mono">${escapeHtml(it.name)}</td>
        <td>${fmtSize(it.size)}</td>
        <td class="muted tiny">${escapeHtml(it.modified || "")}</td>
        <td class="actions">
          <button class="btn btn-ghost btn-sm" data-restore="${escapeAttr(it.name)}">还原</button>
        </td>
      </tr>`).join("");
    els.backupTableBody.querySelectorAll("[data-restore]").forEach((btn) => {
      btn.addEventListener("click", () => restoreBackup(btn.dataset.restore));
    });
  }

  async function loadBackupList() {
    const res = await api("/api/admin/backup/list");
    renderBackupList(res.items || []);
  }

  async function runBackupNow() {
    els.backupRun.disabled = true;
    try {
      appendBackupLog("开始备份…");
      const res = await api("/api/admin/backup/run", { method: "POST" });
      appendBackupLog("本地: " + res.local_file + " · 远程: " + (res.remote || "(仅本地)"));
      if (res.manifest) {
        appendBackupLog("规模: 书 " + res.manifest.book_count + " · 章 " + res.manifest.chapter_count + " · 封面 " + res.manifest.cover_count);
      }
      toast("备份完成", "ok");
      await Promise.all([loadBackupList(), loadBackupStatus(), loadStats()]);
    } catch (err) {
      appendBackupLog("备份失败: " + (err.message || err));
      toast(err.message || "备份失败", "err");
    } finally {
      els.backupRun.disabled = false;
    }
  }

  async function restoreBackup(filename) {
    if (!confirm("确认从备份「" + filename + "」还原？当前数据库与封面将被覆盖，操作不可撤销。")) return;
    els.backupRun.disabled = true;
    try {
      appendBackupLog("还原 " + filename + " …");
      const res = await api("/api/admin/backup/restore", {
        method: "POST",
        body: { filename: filename },
      });
      appendBackupLog("还原完成 " + (res.restored_at || ""));
      toast("还原完成，书库数据已恢复", "ok");
      state.page = 1;
      await Promise.all([loadBooks(), loadStats(), loadBackupStatus()]);
    } catch (err) {
      appendBackupLog("还原失败: " + (err.message || err));
      toast(err.message || "还原失败", "err");
    } finally {
      els.backupRun.disabled = false;
    }
  }

  function renderBackupStatus(st) {
    if (!st) return;
    const lines = [];
    if (st.last_backup_at) lines.push("上次备份: " + st.last_backup_at);
    if (st.last_restore_at) lines.push("上次还原: " + st.last_restore_at);
    if (st.running) lines.push("任务进行中: " + (st.action || ""));
    if (st.message) lines.push("最新消息: " + st.message);
    if (st.last_error) lines.push("最近错误: " + st.last_error);
    if ((st.history || []).length) {
      lines.push("");
      (st.history || []).slice(-10).forEach((h) => {
        lines.push(h.time + "  " + h.message);
      });
    }
    if (lines.length) backupLog(lines.join("\n"));
  }

  async function loadBackupStatus() {
    const st = await api("/api/admin/backup/status");
    renderBackupStatus(st);
  }

  function switchView(name) {
    document.querySelectorAll(".nav-item").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === name);
    });
    ["library", "import", "backup", "api"].forEach((v) => {
      const el = $("view-" + v);
      if (el) el.hidden = v !== name;
    });
    if (name === "backup") {
      loadBackupConfig().catch(() => {});
      loadBackupList().catch(() => {});
      loadBackupStatus().catch(() => {});
    }
  }

  // Events
  els.loginBtn.addEventListener("click", login);
  els.tokenInput.addEventListener("keydown", (e) => { if (e.key === "Enter") login(); });
  els.logoutBtn.addEventListener("click", () => logout(true));
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });
  els.refreshBtn.addEventListener("click", () => loadBooks().catch((e) => toast(e.message, "err")));
  els.prevPage.addEventListener("click", () => { if (state.page > 1) { state.page -= 1; loadBooks().catch(toast); } });
  els.nextPage.addEventListener("click", () => {
    const pages = Math.max(1, Math.ceil(state.total / state.pageSize));
    if (state.page < pages) { state.page += 1; loadBooks().catch(toast); }
  });
  let searchTimer = null;
  els.searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.page = 1; loadBooks().catch(() => {}); }, 300);
  });
  els.categoryFilter.addEventListener("change", () => { state.page = 1; loadBooks().catch(() => {}); });
  els.statusFilter.addEventListener("change", () => { state.page = 1; loadBooks().catch(() => {}); });
  els.viewMode.addEventListener("change", () => {
    state.viewMode = els.viewMode.value;
    localStorage.setItem("novel_view_mode", state.viewMode);
    renderLibrary();
  });
  els.gridSize.addEventListener("input", () => applyGridSize(els.gridSize.value));
  els.themeSelect.addEventListener("change", () => applyTheme(els.themeSelect.value));
  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      if (state.theme === "auto") applyTheme("auto");
    });
  }
  els.importBtn.addEventListener("click", startImport);
  els.importRefresh.addEventListener("click", () => refreshImport().catch(toast));
  els.copySource.addEventListener("click", copySource);
  els.backupRun.addEventListener("click", runBackupNow);
  els.backupListRefresh.addEventListener("click", () => loadBackupList().catch((e) => toast(e.message, "err")));
  els.davSave.addEventListener("click", saveBackupConfig);
  els.davTest.addEventListener("click", testBackupConn);
  els.drawerClose.addEventListener("click", closeDrawer);
  els.cancelBtn.addEventListener("click", closeDrawer);
  els.drawerMask.addEventListener("click", closeDrawer);
  els.saveBtn.addEventListener("click", saveBook);
  els.deleteBtn.addEventListener("click", deleteBook);
  els.coverFile.addEventListener("change", () => {
    const f = els.coverFile.files && els.coverFile.files[0];
    if (!f) return;
    const url = URL.createObjectURL(f);
    els.coverPreview.src = url;
  });

  // Boot
  applyTheme(state.theme);
  applyGridSize(localStorage.getItem(GRID_SIZE_KEY) || 150);
  applyDrawerWidth(localStorage.getItem(DRAWER_W_KEY) || 520);
  initDrawerResize();
  if (state.token) {
    login();
  } else {
    showLogin();
  }
})();
