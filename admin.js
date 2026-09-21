/* Novel Library Admin SPA — vanilla JS, no framework */
(function () {
  "use strict";

  const TOKEN_KEY = "novel_admin_token";
  const state = {
    token: localStorage.getItem(TOKEN_KEY) || "",
    page: 1,
    pageSize: 24,
    total: 0,
    items: [],
    viewMode: localStorage.getItem("novel_view_mode") || "grid",
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
    refreshBtn: $("refresh-btn"),
    gridWrap: $("grid-wrap"),
    tableWrap: $("table-wrap"),
    tableBody: $("table-body"),
    prevPage: $("prev-page"),
    nextPage: $("next-page"),
    pageLabel: $("page-label"),
    importBtn: $("import-btn"),
    importRefresh: $("import-refresh"),
    importLog: $("import-log"),
    sourcePreview: $("source-preview"),
    copySource: $("copy-source"),
    drawer: $("drawer"),
    drawerMask: $("drawer-mask"),
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
    els.tableWrap.hidden = grid;

    if (grid) {
      if (!state.items.length) {
        els.gridWrap.innerHTML = '<div class="muted" style="grid-column:1/-1;padding:32px;text-align:center">暂无书籍，请到「导入」页导入 TXT。</div>';
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
        els.tableBody.innerHTML = '<tr><td colspan="7" class="muted" style="text-align:center;padding:24px">暂无书籍</td></tr>';
        return;
      }
      els.tableBody.innerHTML = state.items.map((b) => `
        <tr data-id="${b.id}">
          <td>${escapeHtml(b.name)}</td>
          <td>${escapeHtml(b.author || "")}</td>
          <td><span class="chip cat">${escapeHtml(b.category || "")}</span></td>
          <td>${statusChip(b.status)}</td>
          <td>${b.chapter_count ?? 0}</td>
          <td>${fmtWords(b.word_count)}</td>
          <td class="actions"><button class="btn btn-ghost btn-sm" data-edit="${b.id}">编辑</button></td>
        </tr>`).join("");
      els.tableBody.querySelectorAll("[data-edit]").forEach((btn) => {
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

  function switchView(name) {
    document.querySelectorAll(".nav-item").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === name);
    });
    ["library", "import", "api"].forEach((v) => {
      const el = $("view-" + v);
      if (el) el.hidden = v !== name;
    });
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
  els.importBtn.addEventListener("click", startImport);
  els.importRefresh.addEventListener("click", () => refreshImport().catch(toast));
  els.copySource.addEventListener("click", copySource);
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
  if (state.token) {
    login();
  } else {
    showLogin();
  }
})();
