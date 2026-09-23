/* 爱小说 Admin SPA — vanilla JS, no framework */
(function () {
  "use strict";

  // 移除预览/注入的 AI 水印，避免占位与滚动条
  (function stripAigc() {
    function wipe(root) {
      (root || document).querySelectorAll("[data-aigc-mark]").forEach((el) => el.remove());
      (root || document).querySelectorAll("p").forEach((el) => {
        if ((el.textContent || "").trim() === "AI生成") el.remove();
      });
    }
    wipe();
    const style = document.createElement("style");
    style.textContent = "[data-aigc-mark],p[data-aigc-mark='1']{display:none!important;margin:0!important;height:0!important;overflow:hidden!important;position:absolute!important;left:-9999px!important}";
    document.documentElement.appendChild(style);
    if (window.MutationObserver) {
      const mo = new MutationObserver((muts) => {
        for (const m of muts) {
          m.addedNodes && m.addedNodes.forEach((n) => {
            if (n.nodeType === 1) {
              if (n.hasAttribute && n.hasAttribute("data-aigc-mark")) n.remove();
              else wipe(n.parentNode || document);
            }
          });
        }
        wipe();
      });
      mo.observe(document.documentElement, { childList: true, subtree: true });
    }
  })();

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
    category: "",
    sort: localStorage.getItem("novel_sort") || "updated",
    stats: null,
    sourceJson: null,
    pendingScrapeHit: null,
  };

  const $ = (id) => document.getElementById(id);
  const els = {
    login: $("login"),
    app: $("app"),
    authSubtitle: $("auth-subtitle"),
    authLogin: $("auth-login"),
    authSetup: $("auth-setup"),
    authForgot: $("auth-forgot"),
    authRecovery: $("auth-recovery"),
    loginUser: $("login-user"),
    loginPass: $("login-pass"),
    loginBtn: $("login-btn"),
    showForgot: $("show-forgot"),
    showLogin: $("show-login"),
    setupUser: $("setup-user"),
    setupPass: $("setup-pass"),
    setupPass2: $("setup-pass2"),
    setupBtn: $("setup-btn"),
    forgotCode: $("forgot-code"),
    forgotUser: $("forgot-user"),
    forgotPass: $("forgot-pass"),
    forgotBtn: $("forgot-btn"),
    recoveryCode: $("recovery-code"),
    copyRecovery: $("copy-recovery"),
    recoveryDone: $("recovery-done"),
    loginError: $("login-error"),
    logoutBtn: $("logout-btn"),
    changePassBtn: $("change-pass-btn"),
    pwMask: $("pw-mask"),
    pwModal: $("pw-modal"),
    pwOld: $("pw-old"),
    pwNew: $("pw-new"),
    pwNew2: $("pw-new2"),
    pwSave: $("pw-save"),
    pwCancel: $("pw-cancel"),
    pwClose: $("pw-close"),
    baseUrlLabel: $("base-url-label"),
    apiBase: $("api-base"),
    novelsPath: $("novels-path"),
    libCount: $("lib-count"),
    searchInput: $("search-input"),
    categoryBar: $("category-bar"),
    sortSelect: $("sort-select"),
    viewMode: $("view-mode"),
    gridSize: $("grid-size"),
    listSize: $("list-size"),
    themeSelect: $("theme-select"),
    gridWrap: $("grid-wrap"),
    listWrap: $("list-wrap"),
    prevPage: $("prev-page"),
    nextPage: $("next-page"),
    pageLabel: $("page-label"),
    importBtn: $("import-btn"),
    importWebdavBtn: $("import-webdav-btn"),
    importRefresh: $("import-refresh"),
    importLog: $("import-log"),
    sourcePreview: $("source-preview"),
    copySource: $("copy-source"),
    backupAutoPill: $("backup-auto-pill"),
    backupRun: $("backup-run"),
    backupListRefresh: $("backup-list-refresh"),
    davUrl: $("dav-url"),
    davPath: $("dav-path"),
    davBooks: $("dav-books"),
    davUser: $("dav-user"),
    davPass: $("dav-pass"),
    davInterval: $("dav-interval"),
    davKeep: $("dav-keep"),
    davAuto: $("dav-auto"),
    davSave: $("dav-save"),
    davTest: $("dav-test"),
    backupTableBody: $("backup-table-body"),
    backupLog: $("backup-log"),
    checkSummary: $("check-summary"),
    dupList: $("dup-list"),
    issueList: $("issue-list"),
    checkScan: $("check-scan"),
    checkRepairAll: $("check-repair-all"),
    batchScrapePreview: $("batch-scrape-preview"),
    batchScrapeRun: $("batch-scrape-run"),
    batchScrapeStatus: $("batch-scrape-status"),
    batchOnlyMissing: $("batch-only-missing"),
    batchMinScore: $("batch-min-score"),
    batchScrapeLog: $("batch-scrape-log"),
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
    scrapeOpenBtn: $("scrape-open-btn"),
    scrapeKeyword: $("scrape-keyword"),
    scrapeSource: $("scrape-source"),
    scrapeSearchBtn: $("scrape-search-btn"),
    scrapeResults: $("scrape-results"),
    scrapeOrigin: $("scrape-origin"),
    scrapeTip: $("scrape-tip"),
    scrapeLocal: $("scrape-local"),
    scrapeMask: $("scrape-mask"),
    scrapeModal: $("scrape-modal"),
    scrapeClose: $("scrape-close"),
    scrapeCancel: $("scrape-cancel"),
    scrapeConfirm: $("scrape-confirm"),
    scrapeConfirmMask: $("scrape-confirm-mask"),
    scrapeConfirmBody: $("scrape-confirm-body"),
    scrapeConfirmYes: $("scrape-confirm-yes"),
    scrapeConfirmNo: $("scrape-confirm-no"),
    saveBtn: $("save-btn"),
    cancelBtn: $("cancel-btn"),
    deleteBtn: $("delete-btn"),
    toast: $("toast"),
  };

  const FALLBACK_CATEGORIES = [
    "玄幻", "奇幻", "武侠", "仙侠", "都市", "现实", "军事", "历史",
    "游戏", "体育", "科幻", "诸天无限", "悬疑灵异", "轻小说", "短篇", "未分类",
  ];

  function setText(el, val) {
    if (el) el.textContent = val;
  }

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

  function applyListSize(px) {
    const n = Math.min(360, Math.max(160, Number(px) || 220));
    if (els.listSize) els.listSize.value = String(n);
    if (els.listWrap) els.listWrap.style.setProperty("--list-w", n + "px");
    localStorage.setItem("novel_list_size", String(n));
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
    if (state.token && !options?.skipAuth) headers.Authorization = "Bearer " + state.token;
    const opts = Object.assign({}, options, { headers });
    if (opts.body && !(opts.body instanceof FormData) && typeof opts.body !== "string") {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, opts);
    const isAuthPath = String(path).indexOf("/api/auth/") === 0;
    // 仅 /me 失效才登出，避免书库等接口 401 把用户踢回登录页
    if (res.status === 401 && !options?.skipAuth && String(path) === "/api/auth/me") {
      logout(false);
      throw new Error("登录已失效，请重新登录");
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
    try {
      if (els.login) els.login.hidden = true;
      if (els.app) els.app.hidden = false;
      if (els.viewMode) els.viewMode.value = state.viewMode;
      if (els.sortSelect) els.sortSelect.value = state.sort || "updated";
      if (els.categoryBar) renderCategoryBar();
    } catch (e) {
      if (els.login) els.login.hidden = true;
      if (els.app) els.app.hidden = false;
    }
  }

  function showAuthPane(name) {
    const panes = {
      login: els.authLogin,
      setup: els.authSetup,
      forgot: els.authForgot,
      recovery: els.authRecovery,
    };
    Object.keys(panes).forEach((k) => {
      if (panes[k]) panes[k].hidden = k !== name;
    });
    els.loginError.hidden = true;
    if (name === "setup") {
      setText(els.authSubtitle, "首次使用 · 创建管理账号");
    } else if (name === "forgot") {
      setText(els.authSubtitle, "忘记密码 · 恢复码重设");
    } else if (name === "recovery") {
      setText(els.authSubtitle, "保存恢复码");
    } else {
      setText(els.authSubtitle, "管理后台 · 账号登录");
    }
  }

  function authError(msg) {
    els.loginError.hidden = false;
    setText(els.loginError, msg || "操作失败");
  }

  function saveSession(payload) {
    if (payload && payload.token) {
      state.token = payload.token;
      localStorage.setItem(TOKEN_KEY, payload.token);
    }
  }

  function pendingRecovery(code) {
    state.pendingRecovery = code;
    els.recoveryCode.textContent = code;
    showAuthPane("recovery");
  }

  async function bootAuth() {
    const st = await api("/api/auth/status", { skipAuth: true, headers: {} });
    if (st.setup_required) {
      showLogin();
      showAuthPane("setup");
      if (els.authSubtitle) setText(els.authSubtitle, "首次使用 · 请创建管理账号");
      return;
    }
    // 已有本地会话则尝试 /me
    try {
      const me = await api("/api/auth/me", { skipAuth: false });
      if (me && me.username) {
        state.username = me.username;
        showApp();
        try { await afterLogin(); } catch (e) { toast(e.message || "加载数据失败", "err"); }
        return;
      }
    } catch (_) {
      /* cookie/token 都无效则停在登录页 */
    }
    showLogin();
    showAuthPane("login");
  }

  async function afterLogin() {
    // 先切换界面，避免加载失败卡在登录页
    showApp();
    try {
      await loadStats();
      renderCategoryBar();
      await Promise.all([loadBooks(), loadSourceJson()]);
    } catch (err) {
      toast(err.message || "加载数据失败", "err");
    }
  }

  async function login() {
    try {
    const username = (els.loginUser && els.loginUser.value || "").trim();
    const password = (els.loginPass && els.loginPass.value) || "";
    if (!username || !password) {
      authError("请输入用户名和密码");
      return;
    }
    els.loginError.hidden = true;
    try {
      state.token = "";
      localStorage.removeItem(TOKEN_KEY);
      const res = await api("/api/auth/login", {
        method: "POST",
        skipAuth: true,
        body: { username: username, password: password },
      });
      saveSession(res);
      state.username = res.username;
      if (els.loginPass) els.loginPass.value = "";
      showApp();
      try { await afterLogin(); } catch (e) { toast(e.message || '加载数据失败', 'err'); }
    } catch (err) {
      const msg = (err && err.message) || "登录失败";
      if (String(msg).indexOf("尚未设置") >= 0 || String(msg).indexOf("创建") >= 0) {
        showAuthPane("setup");
        authError("首次使用请先创建账号（下方表单）");
      } else {
        authError(msg);
      }
    }
    } catch (e) {
      authError(e.message || "登录失败");
    }
  }

  async function setupAccount() {
    try {
    const username = (els.setupUser && els.setupUser.value || "").trim();
    const password = (els.setupPass && els.setupPass.value) || "";
    const password2 = (els.setupPass2 && els.setupPass2.value) || "";
    if (!username) return authError("请填写用户名");
    if (!password || password.length < 6) return authError("密码至少 6 位");
    if (password !== password2) return authError("两次密码不一致");
    els.loginError.hidden = true;
    try {
      const res = await api("/api/auth/setup", {
        method: "POST",
        body: { username: username, password: password },
      });
      saveSession(res);
      state.username = res.username;
      if (res.recovery_code) {
        pendingRecovery(res.recovery_code);
        toast("账号已创建，请保存恢复码", "ok");
      } else {
        await afterLogin();
      }
    } catch (err) {
      authError(err.message || "创建失败");
    }
    } catch (e) {
      authError(e.message || "创建失败");
    }
  }

  async function forgotPassword() {
    const code = els.forgotCode.value.trim();
    const password = els.forgotPass.value;
    const username = els.forgotUser.value.trim();
    if (!code) return authError("请填写恢复码");
    if (!password || password.length < 6) return authError("新密码至少 6 位");
    els.loginError.hidden = true;
    try {
      const res = await api("/api/auth/forgot", {
        method: "POST",
        body: {
          recovery_code: code,
          username: username || null,
          new_password: password,
        },
      });
      saveSession(res);
      state.username = res.username;
      if (res.recovery_code) {
        pendingRecovery(res.recovery_code);
        toast("已重设账号，恢复码已更换", "ok");
      } else {
        await afterLogin();
      }
    } catch (err) {
      authError(err.message || "重设失败");
    }
  }

  function openPwModal() {
    els.pwOld.value = "";
    els.pwNew.value = "";
    els.pwNew2.value = "";
    els.pwModal.hidden = false;
    els.pwMask.hidden = false;
    els.pwOld.focus();
  }

  function closePwModal() {
    els.pwModal.hidden = true;
    els.pwMask.hidden = true;
  }

  async function saveNewPassword() {
    const oldPassword = els.pwOld.value;
    const newPassword = els.pwNew.value;
    const newPassword2 = els.pwNew2.value;
    if (!oldPassword) return toast("请输入当前密码", "err");
    if (!newPassword || newPassword.length < 6) return toast("新密码至少 6 位", "err");
    if (newPassword !== newPassword2) return toast("两次新密码不一致", "err");
    try {
      const res = await api("/api/auth/change-password", {
        method: "POST",
        body: { old_password: oldPassword, new_password: newPassword },
      });
      saveSession(res);
      closePwModal();
      toast("密码已修改", "ok");
    } catch (err) {
      toast(err.message || "修改失败", "err");
    }
  }

  async function logout(notify) {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch (_) { /* ignore */ }
    state.token = "";
    localStorage.removeItem(TOKEN_KEY);
    showLogin();
    showAuthPane("login");
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
    function fill(select) {
      if (!select) return;
      const current = select.value;
      select.innerHTML = "";
      names.forEach((n) => {
        const opt = document.createElement("option");
        opt.value = n;
        opt.textContent = n;
        select.appendChild(opt);
      });
      if (current && names.includes(current)) select.value = current;
    }
    fill(els.editCategory);
  }

  async function loadStats() {
    const data = await api("/api/admin/stats");
    state.stats = data;
    // 统计卡片 DOM 已移除，这里只保留会话内状态
    setText(els.baseUrlLabel, data.public_base_url || location.origin);
    setText(els.apiBase, data.public_base_url || location.origin);
    fillCategorySelects(data.categories);
    renderCategoryBar();
    renderImportLog(data.import);
  }

  function currentQuery() {
    const params = new URLSearchParams();
    params.set("page", String(state.page));
    params.set("page_size", String(state.pageSize));
    params.set("sort", state.sort || "updated");
    if (els.searchInput.value.trim()) params.set("q", els.searchInput.value.trim());
    if (state.category) params.set("category", state.category);
    return params.toString();
  }

  function renderCategoryBar() {
    const cats = (state.stats && state.stats.by_category) || [];
    const names = [];
    const seen = new Set();
    // 固定分类顺序 + 有书的其它分类
    const fallback = (state.stats && state.stats.categories) || FALLBACK_CATEGORIES;
    fallback.forEach((n) => {
      if (!seen.has(n)) { seen.add(n); names.push(n); }
    });
    cats.forEach((c) => {
      if (c && c.name && !seen.has(c.name)) { seen.add(c.name); names.push(c.name); }
    });
    const countMap = {};
    cats.forEach((c) => { countMap[c.name] = c.count || 0; });
    const total = (state.stats && state.stats.total_books) || 0;

    const chips = [];
    chips.push(`<button type="button" class="cat-chip${state.category === "" ? " active" : ""}" data-cat="">全部<span class="n">${total}</span></button>`);
    names.forEach((n) => {
      const cnt = countMap[n] || 0;
      if (!cnt && n !== state.category) return; // 无书且未选中则不展示
      chips.push(
        `<button type="button" class="cat-chip${state.category === n ? " active" : ""}" data-cat="${escapeAttr(n)}">${escapeHtml(n)}<span class="n">${cnt}</span></button>`
      );
    });
    els.categoryBar.innerHTML = chips.join("");
    els.categoryBar.querySelectorAll(".cat-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.category = btn.dataset.cat || "";
        state.page = 1;
        renderCategoryBar();
        loadBooks().catch((e) => toast(e.message, "err"));
      });
    });
  }

  async function loadBooks() {
    const data = await api("/api/admin/books?" + currentQuery());
    state.items = data.items || [];
    state.total = data.total || 0;
    setText(els.libCount, String(state.total));
    const pages = Math.max(1, Math.ceil(state.total / state.pageSize));
    if (state.page > pages) state.page = pages;
    setText(els.pageLabel, state.page + " / " + pages);
    els.prevPage.disabled = state.page <= 1;
    els.nextPage.disabled = state.page >= pages;
    renderLibrary();
  }

  function statusChip(status) {
    if (status === "连载") return '<span class="chip run">连载</span>';
    if (status === "完结") return '<span class="chip ok">完结</span>';
    return '<span class="chip">未知</span>';
  }

  function sourceChip(source) {
    if (!source) return "";
    return `<span class="chip src" title="刮削来源">${escapeHtml(source)}</span>`;
  }

  function renderLibrary() {
    const grid = state.viewMode === "grid";
    // 封面墙/列表共用同一套大小滑条显隐
    if (els.gridSize) els.gridSize.hidden = !grid;
    if (els.listSize) els.listSize.hidden = grid;
    els.gridWrap.hidden = !grid;
    els.listWrap.hidden = grid;
    const emptyText = "暂无书籍，请到「导入」页导入 TXT。";

    if (grid) {
      if (!state.items.length) {
        els.gridWrap.innerHTML = '<div class="muted" style="grid-column:1/-1;padding:32px;text-align:center">' + emptyText + "</div>";
        return;
      }
      els.gridWrap.innerHTML = state.items.map((b) => {
        const coverSrc = b.cover_path || b.cover_url;
        const cover = coverSrc
          ? `<img src="${escapeAttr(coverSrc)}" alt="" loading="lazy" />`
          : `<div class="placeholder">${escapeHtml(b.name)}</div>`;
        return `
          <article class="book-card" data-id="${b.id}">
            <div class="book-cover">${cover}</div>
            <div class="book-meta">
              <div class="book-name" title="${escapeAttr(b.name)}">${escapeHtml(b.name)}</div>
              <div class="book-sub">
                <span>${escapeHtml(b.author || "佚名")}</span>
              </div>
            </div>
          </article>`;
      }).join("");
      els.gridWrap.querySelectorAll(".book-card").forEach((card) => {
        card.addEventListener("click", () => openDrawer(Number(card.dataset.id)));
      });
      return;
    }

    // 列表模式：有数据才渲染卡片，空列表给提示
    if (!state.items.length) {
      els.listWrap.innerHTML = '<div class="muted" style="padding:32px;text-align:center">' + emptyText + "</div>";
      return;
    }
    els.listWrap.innerHTML = state.items.map((b) => {
      const coverSrc = b.cover_path || b.cover_url;
      const cover = coverSrc
        ? `<img src="${escapeAttr(coverSrc)}" alt="" loading="lazy" />`
        : `<div class="placeholder">${escapeHtml((b.name || "").slice(0, 6))}</div>`;
      return `
        <article class="book-row" data-id="${b.id}">
          <div class="row-cover">${cover}</div>
          <div class="row-body">
            <div class="row-title">${escapeHtml(b.name)}</div>
            <div class="row-meta">${escapeHtml(b.author || "佚名")}</div>
          </div>
        </article>`;
    }).join("");
    els.listWrap.querySelectorAll(".book-row").forEach((row) => {
      row.addEventListener("click", () => openDrawer(Number(row.dataset.id)));
    });
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
    els.coverPreview.src = book.cover_path || book.cover_url || placeholderDataUri(book.name || "");
    els.coverPreview.alt = book.name || "封面";
    els.editMeta.textContent = [
      "ID " + book.id,
      "章节 " + (book.chapter_count || 0),
      "字数 " + fmtWords(book.word_count),
      book.source ? "来源 " + book.source + (book.source_id ? "#" + book.source_id : "") : "",
      book.source_path ? "源 " + book.source_path : "",
    ].filter(Boolean).join(" · ");
    els.scrapeKeyword.value = book.name || "";
    els.scrapeOrigin.textContent = book.source
      ? ("来源：" + book.source + (book.source_id ? " · " + book.source_id : ""))
      : "来源：未刮削";
    els.scrapeResults.innerHTML = "";
    els.drawer.hidden = false;
    els.drawerMask.hidden = false;
  }

  function openScrapeModal() {
    const localName = (els.editTitle.value || "").trim();
    els.scrapeKeyword.value = localName;
    els.scrapeLocal.innerHTML =
      "当前书籍：<strong>" + escapeHtml(localName || "(未命名)") + "</strong>" +
      (els.editAuthor.value ? " · " + escapeHtml(els.editAuthor.value) : "");
    els.scrapeTip.textContent = "结果只预览，点「采用并写入」才会改当前这本书。请核对书名/作者是否一致。";
    els.scrapeResults.innerHTML = '<div class="muted tiny">输入关键词后点「搜索」。</div>';
    els.scrapeModal.hidden = false;
    els.scrapeMask.hidden = false;
    els.scrapeKeyword.focus();
  }

  function closeScrapeModal() {
    els.scrapeModal.hidden = true;
    els.scrapeMask.hidden = true;
    closeScrapeConfirm();
  }

  function closeScrapeConfirm() {
    els.scrapeConfirm.hidden = true;
    els.scrapeConfirmMask.hidden = true;
    state.pendingScrapeHit = null;
  }

  function renderScrapeHits(items, localName) {
    if (!items || !items.length) {
      els.scrapeResults.innerHTML = '<div class="muted tiny">没有匹配结果，可换关键词再搜。</div>';
      return;
    }
    const local = (localName || "").trim();
    els.scrapeResults.innerHTML = items.map((it, idx) => {
      const mismatch = local && it.name && it.name !== local &&
        !it.name.includes(local) && !local.includes(it.name);
      return `
      <div class="scrape-item" data-idx="${idx}">
        <div class="t">${escapeHtml(it.name || "(无题)")}</div>
        <div class="m">
          <span class="chip src">${escapeHtml(it.source || "起点")}</span>
          <span>${escapeHtml(it.author || "佚名")}</span>
          <span>ID ${escapeHtml(it.source_id || "")}</span>
          ${it.status ? `<span class="chip">${escapeHtml(it.status)}</span>` : ""}
        </div>
        <div class="ch" title="${escapeAttr(it.latest_chapter || "")}">最新：${escapeHtml(it.latest_chapter || "—")}</div>
        ${mismatch ? `<div class="diff">⚠ 与当前书名不一致，请确认是否选对</div>` : ""}
        <div class="ops">
          <button type="button" class="btn btn-primary btn-sm" data-use="${idx}">采用并写入</button>
        </div>
      </div>`;
    }).join("");
    els.scrapeResults.querySelectorAll("[data-use]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const it = items[Number(btn.dataset.use)];
        if (it) askScrapeConfirm(it);
      });
    });
  }

  function askScrapeConfirm(hit) {
    state.pendingScrapeHit = hit;
    const localName = els.editTitle.value || "";
    const localAuthor = els.editAuthor.value || "";
    const nameDiff = (hit.name || "") !== localName;
    const authorDiff = hit.author && localAuthor && hit.author !== localAuthor;
    els.scrapeConfirmBody.innerHTML = `
      <p style="margin:0 0 10px">确认把<strong>当前这本书</strong>的元数据替换为起点结果？</p>
      <div class="scrape-local">
        <div>本地：<strong>${escapeHtml(localName)}</strong>${localAuthor ? " · " + escapeHtml(localAuthor) : ""}</div>
        <div>起点：<strong>${escapeHtml(hit.name || "")}</strong>${hit.author ? " · " + escapeHtml(hit.author) : ""}</div>
        <div>ID ${escapeHtml(hit.source_id || "")} · 来源 ${escapeHtml(hit.source || "起点")}</div>
        ${hit.latest_chapter ? `<div>最新：${escapeHtml(hit.latest_chapter)}</div>` : ""}
      </div>
      ${(nameDiff || authorDiff) ? '<p class="error" style="margin:0">书名或作者与本地不一致，请再次确认！</p>' : ""}
    `;
    els.scrapeConfirm.hidden = false;
    els.scrapeConfirmMask.hidden = false;
  }

  async function runScrapeSearch() {
    const keyword = (els.scrapeKeyword.value || els.editTitle.value || "").trim();
    if (!keyword) {
      toast("请填写书名或书号/链接", "err");
      return;
    }
    const src0 = (els.scrapeSource && els.scrapeSource.value) || "qidian";
    const idLike = /^\d{5,24}$/.test(keyword) || /qidian\.com\/book\/\d+|fanqienovel\.com\/page\/\d+/.test(keyword);
    if (idLike) {
      els.scrapeSearchBtn.disabled = true;
      els.scrapeResults.innerHTML = '<div class="muted tiny">按书号拉取详情…</div>';
      try {
        const res = await api("/api/admin/scrape/detail", {
          method: "POST",
          body: { source: src0, source_book_id: keyword },
        });
        const hit = Object.assign({}, res, { source_id: res.source_id || keyword });
        renderScrapeHits([hit], els.editTitle.value);
        askScrapeConfirm(hit);
      } catch (err) {
        els.scrapeResults.innerHTML = '<div class="muted tiny">' + escapeHtml(err.message || "详情失败") + "</div>";
        toast(err.message || "详情失败", "err");
      } finally {
        els.scrapeSearchBtn.disabled = false;
      }
      return;
    }
    els.scrapeSearchBtn.disabled = true;
    els.scrapeResults.innerHTML = '<div class="muted tiny">正在搜索…</div>';
    try {
      const res = await api("/api/admin/scrape/search", {
        method: "POST",
        body: {
          keyword: keyword,
          source: els.scrapeSource.value || "qidian",
          limit: 10,
        },
      });
      renderScrapeHits(res.items || [], els.editTitle.value);
      if ((res.items || []).length) {
        toast("找到 " + res.items.length + " 条，请核对后点「采用并写入」", "ok");
      } else {
        toast("无匹配结果", "err");
      }
    } catch (err) {
      els.scrapeResults.innerHTML = '<div class="muted tiny">' + escapeHtml(err.message || "搜索失败") + "</div>";
      toast(err.message || "搜索失败", "err");
    } finally {
      els.scrapeSearchBtn.disabled = false;
    }
  }

  async function applyScrapeHit(hit) {
    const bookId = Number(els.editId.value);
    if (!bookId || !hit || !hit.source_id) return;
    els.scrapeResults.innerHTML = '<div class="muted tiny">正在拉取详情并写入…</div>';
    try {
      const res = await api("/api/admin/scrape/books/" + bookId + "/apply", {
        method: "POST",
        body: {
          source: (els.scrapeSource && els.scrapeSource.value) || "qidian",
          source_book_id: String(hit.source_id),
          with_cover: true,
          hint_name: hit.name || null,
          hint_author: hit.author || null,
          hint_intro: hit.intro || null,
          hint_status: hit.status || null,
          hint_cover_url: hit.cover_url || null,
          hint_tags: (hit.tags || []).filter(function (t) {
            return t && !/字$/.test(t) && t !== "连载" && t !== "完结";
          }),
        },
      });
      els.editTitle.value = res.name || "";
      els.editAuthor.value = res.author || "";
      ensureOption(els.editCategory, res.category);
      els.editCategory.value = res.category || "";
      els.editStatus.value = res.status || "完结";
      els.editTags.value = (res.tags || []).join(", ");
      els.editIntro.value = res.intro || "";
      if (res.cover_path || res.cover_url) els.coverPreview.src = res.cover_path || res.cover_url;
      els.scrapeOrigin.textContent = (res.source || "起点") + (res.source_id ? " · " + res.source_id : "");
      els.editMeta.textContent = [
        "ID " + res.id,
        "章节 " + (res.chapter_count || 0),
        "字数 " + fmtWords(res.word_count),
        "来源 " + (res.source || "起点") + (res.source_id ? "#" + res.source_id : ""),
      ].join(" · ");
      closeScrapeConfirm();
      els.scrapeResults.innerHTML = "";
      closeScrapeModal();
      toast("已写入（来源：" + (res.source || "起点") + "）", "ok");
      await Promise.all([loadBooks(), loadStats()]);
    } catch (err) {
      closeScrapeConfirm();
      els.scrapeResults.innerHTML = '<div class="muted tiny">' + escapeHtml(err.message || "刮削失败") + "</div>";
      toast(err.message || "刮削失败", "err");
    }
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
      els.coverPreview.src = updated.cover_path || updated.cover_url || placeholderDataUri(updated.name);
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

  async function startImport(mode) {
    try {
      const res = await api("/api/admin/import?mode=" + (mode || "local"), { method: "POST" });
      toast(res.started ? (mode === "webdav" ? "WebDAV 导入已开始" : "本地导入已开始") : "导入已在进行中", "ok");
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
        // 兼容数组/对象，统一注入当前访问基址
        const items = Array.isArray(json) ? json : [json];
        items.forEach((item) => {
          if (item && typeof item === "object") item.bookSourceUrl = base;
        });
        json = items;
      }
      // Legado 导入要求根节点为数组，预览与复制保持该格式
      if (!Array.isArray(json)) json = [json];
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
    if (els.davBooks) els.davBooks.value = cfg.books_path || "books";
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
      books_path: (els.davBooks && els.davBooks.value.trim()) || "books",
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

  // —— 书库体检 ——
  function kindLabel(kind) {
    const map = {
      chapter_parse: "未分章",
      encoding: "乱码",
      control_chars: "控制符",
      empty_chapters: "空章节",
      source_missing: "缺源文件",
    };
    return map[kind] || kind;
  }

  function renderLibraryReport(rep) {
    const dups = rep.duplicates || [];
    const issues = rep.issues || [];
    els.checkSummary.textContent = `重复 ${rep.duplicate_groups || 0} 组 · 异常 ${rep.issue_count || 0}`;

    // 重复
    if (!dups.length) {
      els.dupList.innerHTML = '<div class="muted tiny">没有发现重复书。</div>';
    } else {
      els.dupList.innerHTML = dups.map((g, gi) => {
        const keep = g.keep_id;
        const del = (g.books || []).filter((b) => b.id !== keep).map((b) => b.id);
        const rows = (g.books || []).map((b) => {
          const tag = b.id === keep ? '<span class="chip ok">保留</span>' : '<span class="chip">待删</span>';
          return `<div class="muted tiny">${tag} ID ${b.id} · ${b.chapter_count} 章 · ${fmtWords(b.word_count)} · <span class="mono">${escapeHtml(b.source_path || "")}</span></div>`;
        }).join("");
        return `
          <div class="check-item" data-g="${gi}">
            <div class="body">
              <div class="t">${escapeHtml(g.title)}${g.author ? " · " + escapeHtml(g.author) : ""}</div>
              <div class="m">${rows}</div>
            </div>
            <div class="ops">
              <button class="btn btn-primary btn-sm" data-merge="${gi}">一键合并</button>
            </div>
          </div>`;
      }).join("");
      els.dupList.querySelectorAll("[data-merge]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const g = dups[Number(btn.dataset.merge)];
          if (!g) return;
          const del = (g.books || []).filter((b) => b.id !== g.keep_id).map((b) => b.id);
          if (!confirm(`合并《${g.title}》：保留 ID ${g.keep_id}，删除 ${del.join(", ")}？`)) return;
          mergeDup(g.keep_id, del);
        });
      });
    }

    // 异常
    if (!issues.length) {
      els.issueList.innerHTML = '<div class="muted tiny">没有发现异常，书库健康。</div>';
    } else {
      els.issueList.innerHTML = issues.map((it) => `
        <div class="check-item">
          <div class="body">
            <div class="t">${escapeHtml(it.title)} <span class="chip kind-${escapeAttr(it.kind)}">${escapeHtml(kindLabel(it.kind))}</span></div>
            <div class="m">${escapeHtml(it.message)} · ID ${it.book_id}</div>
          </div>
          <div class="ops">
            <button class="btn btn-ghost btn-sm" data-repair="${it.book_id}">修复</button>
            <button class="btn btn-ghost btn-sm" data-edit-book="${it.book_id}">编辑</button>
          </div>
        </div>`).join("");
      els.issueList.querySelectorAll("[data-repair]").forEach((btn) => {
        btn.addEventListener("click", () => repairOne(Number(btn.dataset.repair)));
      });
      els.issueList.querySelectorAll("[data-edit-book]").forEach((btn) => {
        btn.addEventListener("click", () => openDrawer(Number(btn.dataset.editBook)));
      });
    }
  }

  async function loadLibraryReport() {
    const rep = await api("/api/admin/library/report");
    renderLibraryReport(rep);
  }

  async function mergeDup(keepId, deleteIds) {
    try {
      const res = await api("/api/admin/library/merge", {
        method: "POST",
        body: { keep_id: keepId, delete_ids: deleteIds },
      });
      toast("已合并，删除 " + (res.deleted || []).length + " 本", "ok");
      await Promise.all([loadLibraryReport(), loadBooks(), loadStats()]);
    } catch (err) {
      toast(err.message || "合并失败", "err");
    }
  }

  async function repairOne(bookId, mode) {
    try {
      const res = await api("/api/admin/library/repair/" + bookId + "?mode=" + (mode || "auto"), {
        method: "POST",
      });
      toast((res.title || "") + "：" + (res.actions || []).join("；"), "ok");
      await Promise.all([loadLibraryReport(), loadBooks(), loadStats()]);
    } catch (err) {
      toast(err.message || "修复失败", "err");
    }
  }

  async function repairAll() {
    if (!confirm("对所有异常书执行自动修复？（清理字符，必要时从源 TXT 重解析）")) return;
    try {
      const res = await api("/api/admin/library/repair", {
        method: "POST",
        body: { mode: "auto" },
      });
      toast("已修复 " + (res.count || 0) + " 本", "ok");
      await Promise.all([loadLibraryReport(), loadBooks(), loadStats()]);
    } catch (err) {
      toast(err.message || "修复失败", "err");
    }
  }

  function renderBatchStatus(st) {
    if (!st) return;
    const lines = [];
    if (st.running) lines.push("运行中… 进度 " + (st.done || 0) + "/" + (st.total || 0));
    else lines.push("进度 " + (st.done || 0) + "/" + (st.total || 0) + (st.dry_run ? "（预览）" : ""));
    lines.push("写入 " + (st.matched || 0) + " · 跳过 " + (st.skipped || 0) + " · 失败 " + (st.failed || 0));
    if (st.last_error) lines.push("错误: " + st.last_error);
    if ((st.log || []).length) {
      lines.push("");
      (st.log || []).slice(-40).forEach((e) => lines.push(e.time + "  " + e.message));
    }
    els.batchScrapeLog.textContent = lines.join("\n") || "尚未运行。";
    els.batchScrapeLog.scrollTop = els.batchScrapeLog.scrollHeight;
  }

  async function startBatchScrape(dryRun) {
    try {
      const res = await api("/api/admin/scrape/batch/start", {
        method: "POST",
        body: {
          source: "qidian",
          only_missing: !!els.batchOnlyMissing.checked,
          min_score: Number(els.batchMinScore.value) || 0.55,
          dry_run: !!dryRun,
        },
      });
      toast(res.started ? (dryRun ? "预览匹配已开始" : "一键刮削已开始") : "批处理已在运行", "ok");
      renderBatchStatus(res.status);
      pollBatchScrape();
    } catch (err) {
      toast(err.message || "启动失败", "err");
    }
  }

  function pollBatchScrape() {
    let n = 0;
    const timer = setInterval(async () => {
      n += 1;
      try {
        const st = await api("/api/admin/scrape/batch/status");
        renderBatchStatus(st);
        if (!st.running) {
          clearInterval(timer);
          await Promise.all([loadBooks(), loadStats(), loadLibraryReport().catch(() => {})]);
          toast("批处理完成", "ok");
        }
      } catch (_) {
        clearInterval(timer);
      }
      if (n > 180) clearInterval(timer);
    }, 1500);
  }

  async function refreshBatchStatus() {
    const st = await api("/api/admin/scrape/batch/status");
    renderBatchStatus(st);
  }

  function switchView(name) {
    document.querySelectorAll("[data-view]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === name);
    });
    ["library", "import", "check", "backup", "api", "settings"].forEach((v) => {
      const el = $("view-" + v);
      if (el) el.hidden = v !== name;
    });
    if (name === "backup") {
      loadBackupConfig().catch(() => {});
      loadBackupList().catch(() => {});
      loadBackupStatus().catch(() => {});
    }
    if (name === "check") {
      loadLibraryReport().catch((e) => toast(e.message, "err"));
      refreshBatchStatus().catch(() => {});
    }
  }

  function on(el, ev, fn) {
    if (el && el.addEventListener) el.addEventListener(ev, fn);
  }

  // Events
  on(els.loginBtn, "click", login);
  on(els.loginPass, "keydown", (e) => { if (e.key === "Enter") login(); });
  on(els.loginUser, "keydown", (e) => { if (e.key === "Enter") els.loginPass.focus(); });
  on(els.setupBtn, "click", setupAccount);
  on(els.forgotBtn, "click", forgotPassword);
  on(els.showForgot, "click", () => showAuthPane("forgot"));
  on(els.showLogin, "click", () => showAuthPane("login"));
  on(els.copyRecovery, "click", () => {
    const text = els.recoveryCode.textContent || "";
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => toast("恢复码已复制", "ok"))
        .catch(() => fallbackCopy(text));
    } else fallbackCopy(text);
  });
  on(els.recoveryDone, "click", () => afterLogin().catch((e) => authError(e.message)));
  on(els.logoutBtn, "click", () => logout(true));
  on(els.changePassBtn, "click", openPwModal);
  on(els.pwSave, "click", saveNewPassword);
  on(els.pwCancel, "click", closePwModal);
  on(els.pwClose, "click", closePwModal);
  on(els.pwMask, "click", closePwModal);
  document.querySelectorAll("[data-view]").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });
  on(els.prevPage, "click", () => { if (state.page > 1) { state.page -= 1; loadBooks().catch(toast); } });
  on(els.nextPage, "click", () => {
    const pages = Math.max(1, Math.ceil(state.total / state.pageSize));
    if (state.page < pages) { state.page += 1; loadBooks().catch(toast); }
  });
  let searchTimer = null;
  on(els.searchInput, "input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.page = 1; loadBooks().catch(() => {}); }, 300);
  });
  on(els.sortSelect, "change", () => {
    state.sort = els.sortSelect.value || "updated";
    localStorage.setItem("novel_sort", state.sort);
    state.page = 1;
    loadBooks().catch((e) => toast(e.message, "err"));
  });
  on(els.viewMode, "change", () => {
    state.viewMode = els.viewMode.value;
    localStorage.setItem("novel_view_mode", state.viewMode);
    renderLibrary();
  });
  on(els.gridSize, "input", () => applyGridSize(els.gridSize.value));
  els.listSize && on(els.listSize, "input", () => applyListSize(els.listSize.value));
  on(els.themeSelect, "change", () => applyTheme(els.themeSelect.value));
  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      if (state.theme === "auto") applyTheme("auto");
    });
  }
  on(els.importBtn, "click", () => startImport("local"));
  on(els.importWebdavBtn, "click", () => startImport("webdav"));
  on(els.importRefresh, "click", () => refreshImport().catch(toast));
  on(els.copySource, "click", copySource);
  on(els.backupRun, "click", runBackupNow);
  on(els.backupListRefresh, "click", () => loadBackupList().catch((e) => toast(e.message, "err")));
  on(els.davSave, "click", saveBackupConfig);
  on(els.davTest, "click", testBackupConn);
  on(els.checkScan, "click", () => loadLibraryReport().catch((e) => toast(e.message, "err")));
  on(els.checkRepairAll, "click", repairAll);
  on(els.batchScrapePreview, "click", () => startBatchScrape(true));
  on(els.batchScrapeRun, "click", () => {
    if (!confirm("开始对全库一键刮削？将按书名/作者最近匹配写入元数据。")) return;
    startBatchScrape(false);
  });
  on(els.batchScrapeStatus, "click", () => refreshBatchStatus().catch(toast));
  on(els.drawerClose, "click", closeDrawer);
  on(els.cancelBtn, "click", closeDrawer);
  on(els.drawerMask, "click", closeDrawer);
  on(els.saveBtn, "click", saveBook);
  on(els.scrapeOpenBtn, "click", openScrapeModal);
  on(els.scrapeSearchBtn, "click", runScrapeSearch);
  on(els.scrapeKeyword, "keydown", (e) => { if (e.key === "Enter") runScrapeSearch(); });
  on(els.scrapeClose, "click", closeScrapeModal);
  on(els.scrapeCancel, "click", closeScrapeModal);
  on(els.scrapeMask, "click", closeScrapeModal);
  on(els.scrapeConfirmYes, "click", () => {
    const hit = state.pendingScrapeHit;
    if (hit) applyScrapeHit(hit);
  });
  on(els.scrapeConfirmNo, "click", closeScrapeConfirm);
  on(els.scrapeConfirmMask, "click", closeScrapeConfirm);
  on(els.deleteBtn, "click", deleteBook);
  on(els.coverFile, "change", () => {
    const f = els.coverFile.files && els.coverFile.files[0];
    if (!f) return;
    const url = URL.createObjectURL(f);
    els.coverPreview.src = url;
  });

  window.doSetup = function () { return Promise.resolve(setupAccount()).catch(function (e) { authError(e.message || '创建失败'); }); };
  window.doLogin = function () { return Promise.resolve(login()).catch(function (e) { authError(e.message || '登录失败'); }); };

  // Boot
  applyTheme(state.theme);
  applyGridSize(localStorage.getItem(GRID_SIZE_KEY) || 150);
  applyListSize(localStorage.getItem('novel_list_size') || 220);
  applyDrawerWidth(localStorage.getItem(DRAWER_W_KEY) || 520);
  initDrawerResize();
  if (els.sortSelect) els.sortSelect.value = state.sort || "updated";
  Promise.resolve()
    .then(() => bootAuth())
    .catch((e) => {
      showLogin();
      showAuthPane("login");
      authError(e.message || "无法连接服务端");
    });
})();

