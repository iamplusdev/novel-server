/* 爱小说 Admin SPA — vanilla JS, no framework */
(function () {
  "use strict";

  const TOKEN_KEY = "novel_admin_token"; // 历史键名；会话已改为 Cookie（A7），不再写入
  const THEME_KEY = "novel_theme_mode";
  const GRID_SIZE_KEY = "novel_grid_size";
  const DRAWER_W_KEY = "novel_drawer_width";
  const state = {
    // 会话优先 HttpOnly Cookie；token 仅存内存（A7）
    token: "",
    page: 1,
    pageSize: 24,
    total: 0,
    items: [],
    totalPages: 1,
    theme: localStorage.getItem(THEME_KEY) || "auto",
    source: "", // 书源行："" 全部 / 起点 / 番茄
    category: "",
    tag: "",
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
    sideUser: $("side-user"),
    sideLogout: $("side-logout"),
    settingsUser: $("settings-user"),
    settingsEnv: $("settings-env"),
    confirmMask: $("confirm-mask"),
    confirmModal: $("confirm-modal"),
    confirmTitle: $("confirm-title"),
    confirmBody: $("confirm-body"),
    confirmYes: $("confirm-yes"),
    confirmNo: $("confirm-no"),
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
    sourceBar: $("source-bar"),
    sortSelect: $("sort-select"),
    themeSelect: $("theme-select"),
    gridSize: $("grid-size"),
    gridWrap: $("grid-wrap"),
    prevPage: $("prev-page"),
    nextPage: $("next-page"),
    pageLabel: $("page-label"),
    pageInput: $("page-input"),
    navToggle: $("nav-toggle"),
    importBtn: $("import-btn"),
    importCancel: $("import-cancel"),
    importRefresh: $("import-refresh"),
    importLog: $("import-log"),
    importProgress: $("import-progress"),
    importProgressFill: $("import-progress-fill"),
    importProgressText: $("import-progress-text"),
    sourcePreview: $("source-preview"),
    copySource: $("copy-source"),
    checkSummary: $("check-summary"),
    dupList: $("dup-list"),
    issueList: $("issue-list"),
    checkScan: $("check-scan"),
    checkRepairAll: $("check-repair-all"),
    checkRelocate: $("check-relocate"),
    batchScrapePreview: $("batch-scrape-preview"),
    batchScrapeSource: $("batch-scrape-source"),
    batchScrapeRun: $("batch-scrape-run"),
    batchScrapeCancel: $("batch-scrape-cancel"),
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
    editSource: $("edit-source"),
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

  // 书源两级分类：起点-都市 / 番茄-西方奇幻（与 novels/<书源>/<分类>/ 一致）
  const FALLBACK_CATEGORIES = [
    "起点-玄幻", "起点-奇幻", "起点-武侠", "起点-仙侠", "起点-都市", "起点-现实",
    "起点-军事", "起点-历史", "起点-游戏", "起点-体育", "起点-科幻", "起点-诸天无限",
    "起点-悬疑灵异", "起点-轻小说", "起点-短篇",
    "番茄-西方奇幻", "番茄-东方仙侠", "番茄-科幻末世", "番茄-都市日常", "番茄-都市修真",
    "番茄-都市高武", "番茄-历史古代", "番茄-战神赘婿", "番茄-都市种田", "番茄-传统玄幻",
    "番茄-历史脑洞", "番茄-悬疑脑洞", "番茄-都市脑洞", "番茄-玄幻脑洞", "番茄-悬疑灵异",
    "番茄-抗战谍战", "番茄-游戏体育", "番茄-动漫衍生", "番茄-男频衍生",
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
    // 卡片大小变化 → 重算每页数量，保证行占满
    schedulePageSizeRefresh();
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
    const opts = Object.assign({ credentials: "same-origin" }, options, { headers });
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
      if (els.sortSelect) els.sortSelect.value = state.sort || "updated";
      if (els.sourceBar) renderSourceBar();
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
    // A7：token 只放内存，持久化交给 HttpOnly Cookie
    if (payload && payload.token) {
      state.token = payload.token;
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
    try {
      const me = await api("/api/auth/me");
      state.username = me.username;
      applyUserUI();
    } catch (_) { /* 会话仍在则继续 */ }
    showApp();
    // 登录后按当前网格宽度/卡片大小确定每页数量
    state.pageSize = computePageSize();
    try {
      await Promise.all([loadStats(), loadBooks(), loadSourceJson()]);
    } catch (e) {
      toast(e.message || "加载数据失败", "err");
    }
  }

  // 侧栏 / 设置页展示当前用户
  function applyUserUI() {
    const name = state.username || "—";
    if (els.sideUser) setText(els.sideUser, name);
    if (els.settingsUser) setText(els.settingsUser, "当前用户：" + name);
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
      const res = await api("/api/auth/login", {
        method: "POST",
        skipAuth: true,
        body: { username: username, password: password },
      });
      saveSession(res);
      state.username = res.username;
      applyUserUI();
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
      applyUserUI();
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
      applyUserUI();
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
    state.username = "";
    applyUserUI();
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

  // —— 两级分类：书源 + 站内分类（默认兜底；登录后由 category_tree 覆盖）——
  const CATEGORY_TREE = {
    "": {
      label: "本地",
      categories: [
        "玄幻", "奇幻", "武侠", "仙侠", "都市", "现实", "军事", "历史",
        "游戏", "体育", "科幻", "诸天无限", "悬疑灵异", "轻小说", "短篇", "未分类",
      ],
    },
    "起点": {
      label: "起点",
      categories: [
        "玄幻", "奇幻", "武侠", "仙侠", "都市", "现实", "军事", "历史",
        "游戏", "体育", "科幻", "诸天无限", "悬疑灵异", "轻小说", "短篇",
      ],
    },
    "番茄": {
      label: "番茄",
      categories: [
        "西方奇幻", "东方仙侠", "科幻末世", "都市日常", "都市修真", "都市高武",
        "历史古代", "战神赘婿", "都市种田", "传统玄幻", "历史脑洞", "悬疑脑洞",
        "都市脑洞", "玄幻脑洞", "悬疑灵异", "抗战谍战", "游戏体育", "动漫衍生", "男频衍生",
      ],
    },
  };

  // A5：后端 category_tree → 前端分类树，避免前后端双份维护
  function applyCategoryTree(tree) {
    if (!Array.isArray(tree) || !tree.length) return;
    tree.forEach((node) => {
      const key = node.key == null ? "" : String(node.key);
      const cats = Array.isArray(node.categories) ? node.categories.slice() : [];
      if (!cats.length) return;
      CATEGORY_TREE[key] = { label: node.label || key || "本地", categories: cats };
    });
  }

  function sourceKeys() {
    return Object.keys(CATEGORY_TREE);
  }

  function fillSourceSelect(current) {
    const sel = els.editSource;
    if (!sel) return;
    const cur = current == null ? sel.value : current;
    sel.innerHTML = "";
    sourceKeys().forEach((k) => {
      const opt = document.createElement("option");
      opt.value = k;
      opt.textContent = (CATEGORY_TREE[k] && CATEGORY_TREE[k].label) || k || "本地";
      sel.appendChild(opt);
    });
    if (cur != null) sel.value = cur;
    if (sel.value !== cur && cur != null) {
      // 未知书源落到本地
      sel.value = "";
    }
  }

  function categoryListFor(srcKey) {
    const node = CATEGORY_TREE[srcKey] || CATEGORY_TREE[""];
    return node.categories.slice();
  }

  function fillCategorySelect(srcKey, currentCat) {
    const sel = els.editCategory;
    if (!sel) return;
    const names = categoryListFor(srcKey);
    sel.innerHTML = "";
    names.forEach((n) => {
      const opt = document.createElement("option");
      opt.value = n;
      opt.textContent = n;
      sel.appendChild(opt);
    });
    let cur = currentCat != null ? currentCat : sel.value;
    if (cur && !names.includes(cur)) {
      // 刮削来的细分/未知分类：临时选项，保证能选中
      ensureOption(sel, cur);
    }
    if (cur) sel.value = cur;
  }

  // 切换书源时刷新分类列表（尽量保留原分类）
  function bindSourceCategoryLink() {
    if (!els.editSource || els.editSource._linked) return;
    els.editSource._linked = true;
    els.editSource.addEventListener("change", () => {
      fillCategorySelect(els.editSource.value, els.editCategory.value);
    });
  }

  function setTwoLevelCategory(srcKey, catName) {
    bindSourceCategoryLink();
    fillSourceSelect(srcKey || "");
    fillCategorySelect(els.editSource.value || "", catName || "");
  }

  function getTwoLevelCategory() {
    return {
      category_source: els.editSource ? els.editSource.value : "",
      category_name: els.editCategory ? els.editCategory.value : "",
    };
  }

  // 从合成串/字段拆两级（兼容旧数据）
  function splitCategory(combo, source) {
    const s = (combo || "").trim();
    const keys = sourceKeys().filter((k) => k);
    for (let i = 0; i < keys.length; i++) {
      const p = keys[i];
      for (const sep of ["-", "/", "·"]) {
        if (s.startsWith(p + sep) && s.length > p.length + 1) {
          return { category_source: p, category_name: s.slice(p.length + 1).trim() };
        }
      }
    }
    const src = (source || "").trim();
    return {
      category_source: CATEGORY_TREE[src] ? src : "",
      category_name: s || "未分类",
    };
  }

  function fillCategorySelects(_categories) {
    // 保留接口兼容；两级下拉在 openDrawer / setTwoLevelCategory 里填
    bindSourceCategoryLink();
    if (els.editSource && !els.editSource.options.length) {
      const lv = splitCategory(els.editCategory.value, "");
      fillSourceSelect(lv.category_source);
      fillCategorySelect(lv.category_source, lv.category_name);
    }
  }

  async function loadStats() {
    const data = await api("/api/admin/stats");
    state.stats = data;
    // 统计卡片 DOM 已移除，这里只保留会话内状态
    setText(els.baseUrlLabel, data.public_base_url || location.origin);
    setText(els.apiBase, data.public_base_url || location.origin);
    // A5：用服务端分类树覆盖本地兜底
    if (data.category_tree) applyCategoryTree(data.category_tree);
    fillCategorySelects(data.categories);
    renderSourceBar();
    renderCategoryBar();
    renderImportLog(data.import);
    // 设置页 · 运行环境
    if (els.settingsEnv) {
      const lines = [
        "对外地址  " + (data.public_base_url || location.origin),
        "书籍目录  " + (data.novels_dir || "—"),
        "数据库    " + (data.database_path || "—"),
        "封面目录  " + (data.covers_dir || "—"),
      ];
      setText(els.settingsEnv, lines.join("\n"));
    }
    applyUserUI();
  }

  // 标签筛选已从界面移除
  function loadTagBar() {
    return Promise.resolve();
  }

  // —— 书库动态分页：page_size = 列数 × 行数，保证非末页每行占满且约等于一屏 ——
  const GRID_GAP = 14;

  function computeGridCols() {
    const wrap = els.gridWrap;
    if (!wrap) return 4;
    const styles = window.getComputedStyle(wrap);
    const coverW = parseFloat(styles.getPropertyValue("--cover-w")) || 150;
    const width = wrap.clientWidth || wrap.getBoundingClientRect().width || 0;
    if (width <= 0) return 4;
    // 与 CSS auto-fill minmax(cover-w, 1fr) + gap 对齐，估算每行列数
    return Math.max(2, Math.floor((width + GRID_GAP) / (coverW + GRID_GAP)));
  }

  function gridUsableHeight() {
    // 网格区实际可用高度：视口底 − 网格顶 − 分页器 − 底边距
    const wrap = els.gridWrap;
    if (!wrap) return window.innerHeight * 0.55;
    const top = wrap.getBoundingClientRect().top || 200;
    const pager = document.querySelector(".pager");
    const pagerH = pager ? pager.offsetHeight + 18 : 42;
    const bottomPad = 12;
    const h = window.innerHeight - top - pagerH - bottomPad;
    return Math.max(120, h);
  }

  function estimateCardHeight() {
    // 优先量已渲染卡片；否则按列宽估算（封面 3:4 + 元信息区）
    const wrap = els.gridWrap;
    if (wrap) {
      const sample = wrap.querySelector(".book-card");
      if (sample && sample.offsetHeight > 0) return sample.offsetHeight;
    }
    const cols = computeGridCols();
    const width = (wrap && (wrap.clientWidth || wrap.getBoundingClientRect().width)) || 320;
    const colW = Math.max(110, (width - (cols - 1) * GRID_GAP) / cols);
    // aspect-ratio: 3/4 → 高 = 宽 × 4/3；元信息约 58px（双行书名 + 作者）
    return colW * (4 / 3) + 58;
  }

  function rowsFromHeight(usableH, cardH) {
    // 整行放得下的行数
    const slot = cardH + GRID_GAP;
    const fitted = Math.floor((usableH + GRID_GAP) / slot);
    if (fitted <= 0) return 1;
    // 剩余约半张卡时 +1 行：宁可溢出一点，也不空半截
    const used = fitted * cardH + Math.max(0, fitted - 1) * GRID_GAP;
    const leftover = usableH - used;
    if (leftover >= cardH * 0.45) return fitted + 1;
    return fitted;
  }

  function rowsFloorFromHeight(usableH, cardH) {
    // 仅完整放下、不额外 +1（明显超屏时收紧用）
    return Math.max(1, Math.floor((usableH + GRID_GAP) / (cardH + GRID_GAP)));
  }

  function computeGridRows() {
    // 卡片越大行越少、越小行越多；略可溢出，不必刚好一屏
    return rowsFromHeight(gridUsableHeight(), estimateCardHeight());
  }

  function computePageSize() {
    const cols = computeGridCols();
    const rows = computeGridRows();
    // 必须是列数整数倍，前面页每行才铺满；至少一整行
    return Math.min(200, cols * rows);
  }

  function computeRowsWithCardHeight(cardH) {
    return rowsFromHeight(gridUsableHeight(), cardH);
  }

  // 渲染后微调：仅明显超出一屏时收紧；允许略溢出，不为“刚好满”加行
  let refineSig = "";
  function refinePageSizeAfterRender() {
    const wrap = els.gridWrap;
    if (!wrap || !booksLoadedOnce) return;
    const sample = wrap.querySelector(".book-card");
    if (!sample || !sample.offsetHeight) return;
    const cardH = sample.offsetHeight;
    const cols = computeGridCols();
    const usableH = gridUsableHeight();
    const gridH = wrap.scrollHeight || 0;
    // 超出约 3/4 张卡才算“太多”
    const overflow = gridH > usableH + cardH * 0.75;
    const rows = overflow
      ? rowsFloorFromHeight(usableH, cardH)
      : computeRowsWithCardHeight(cardH);
    const next = Math.min(200, cols * rows);
    const sig = cols + "x" + rows + "@" + Math.round(cardH) + ":" + (overflow ? "o" : "k");
    // 布局未变则不重复校正，避免加载回环
    if (sig === refineSig) return;
    refineSig = sig;
    if (!overflow) return;
    if (next >= state.pageSize) return;
    // 只记录更合适的 page_size 供下次分页使用，不在此二次请求
    //（避免分类切换时「拉两次」造成卡顿）
    state.pageSize = next;
  }

  let pageSizeTimer = null;
  let booksLoadedOnce = false;
  function schedulePageSizeRefresh() {
    clearTimeout(pageSizeTimer);
    pageSizeTimer = setTimeout(() => {
      const oldSize = state.pageSize || 24;
      const next = computePageSize();
      if (next === oldSize) return;
      // 尽量保持当前阅读位置附近的页
      const firstIndex = (state.page - 1) * oldSize;
      state.pageSize = next;
      state.page = Math.floor(firstIndex / next) + 1;
      // 仅书库已加载过才拉列表，避免启动/登录前误请求
      if (booksLoadedOnce && els.app && !els.app.hidden) {
        loadBooks().catch(() => {});
      }
    }, 160);
  }

  function currentQuery() {
    const params = new URLSearchParams();
    params.set("page", String(state.page));
    params.set("page_size", String(state.pageSize));
    params.set("sort", state.sort || "updated");
    if (els.searchInput && els.searchInput.value.trim()) {
      params.set("q", els.searchInput.value.trim());
    }
    // 书源 + 分类：分开传；分类传纯名（后端兼容合成串）
    const src = (state.source || "").trim();
    const cat = (state.category || "").trim();
    if (src) params.set("source", src);
    if (cat) params.set("category", cat);
    return params.toString();
  }

  // —— 书源行：全部 / 起点 / 番茄 ——
  const SOURCE_OPTS = ["", "起点", "番茄"];
  const SOURCE_LABEL = { "": "全部", "起点": "起点", "番茄": "番茄" };

  function catListForSource(src) {
    // 默认（全部）只展示第一个书源的分类，避免并集过长；
    // 点选书源后再切换到对应栏目
    if (src === "番茄") return CATEGORY_TREE["番茄"].categories.slice();
    return CATEGORY_TREE["起点"].categories.slice();
  }

  function renderSourceBar() {
    const bar = els.sourceBar;
    if (!bar) return;
    bar.innerHTML = SOURCE_OPTS.map((s) => {
      const on = (state.source || "") === s;
      // 用 data-v 避免与元素 src 属性语义混淆
      return (
        '<button type="button" class="cat-chip' + (on ? " active" : "") +
        '" data-v="' + escapeAttr(s) + '">' + escapeHtml(SOURCE_LABEL[s] || s || "全部") + "</button>"
      );
    }).join("");
  }

  function renderCategoryBar() {
    const bar = els.categoryBar;
    if (!bar) return;
    const names = catListForSource(state.source || "");
    const chips = [
      '<button type="button" class="cat-chip' + (state.category ? "" : " active") +
      '" data-cat="">全部</button>',
    ];
    names.forEach((n) => {
      chips.push(
        '<button type="button" class="cat-chip' + (state.category === n ? " active" : "") +
        '" data-cat="' + escapeAttr(n) + '">' + escapeHtml(n) + "</button>"
      );
    });
    bar.innerHTML = chips.join("");
  }

  // 书源/分类条：事件委托只绑一次，切换时仅重绘 HTML
  function bindBarDelegates() {
    if (els.sourceBar) {
      els.sourceBar.addEventListener("click", (e) => {
        const btn = e.target.closest && e.target.closest("[data-v]");
        if (!btn || !els.sourceBar.contains(btn)) return;
        state.source = btn.getAttribute("data-v") || "";
        // 换书源后分类回到「全部」
        state.category = "";
        state.page = 1;
        renderSourceBar();
        renderCategoryBar();
        loadBooks().catch((e2) => toast(e2.message, "err"));
      });
    }
    if (els.categoryBar) {
      els.categoryBar.addEventListener("click", (e) => {
        const btn = e.target.closest && e.target.closest("[data-cat]");
        if (!btn || !els.categoryBar.contains(btn)) return;
        state.category = btn.getAttribute("data-cat") || "";
        state.page = 1;
        renderCategoryBar();
        loadBooks().catch((e2) => toast(e2.message, "err"));
      });
    }
  }

  // 书库请求序号：只应用最后一次结果，避免连点分类时旧响应覆盖新列表
  let booksReqSeq = 0;

  async function loadBooks() {
    booksLoadedOnce = true;
    const seq = ++booksReqSeq;
    const wrap = els.gridWrap;
    if (wrap) wrap.classList.add("is-loading");
    try {
      const data = await api("/api/admin/books?" + currentQuery());
      // 过期响应直接丢弃
      if (seq !== booksReqSeq) return;
      state.items = data.items || [];
      state.total = data.total || 0;
      setText(els.libCount, String(state.total));
      const pages = Math.max(1, Math.ceil(state.total / state.pageSize));
      state.totalPages = pages;
      if (state.page > pages) state.page = pages;
      setText(els.pageLabel, state.page + " / " + pages);
      if (els.pageInput) {
        els.pageInput.max = String(pages);
        if (document.activeElement !== els.pageInput) {
          els.pageInput.value = String(state.page);
        }
      }
      els.prevPage.disabled = state.page <= 1;
      els.nextPage.disabled = state.page >= pages;
      renderLibrary();
      // 实测卡高后微调每页数量（只记账，不二次请求）
      refinePageSizeAfterRender();
    } finally {
      // 仅当前请求负责收起 loading
      if (seq === booksReqSeq && wrap) wrap.classList.remove("is-loading");
    }
  }

  // A3：页码跳转
  function gotoPage(n) {
    const pages = state.totalPages || Math.max(1, Math.ceil(state.total / state.pageSize));
    const p = Math.min(pages, Math.max(1, Math.floor(Number(n) || 1)));
    if (p === state.page) {
      if (els.pageInput) els.pageInput.value = String(p);
      return;
    }
    state.page = p;
    if (els.pageInput) els.pageInput.value = String(p);
    loadBooks().catch((e) => toast(e.message, "err"));
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
    // 书库仅封面墙（列表展示已移除）
    const emptyText = "暂无书籍，请到「导入」页导入 TXT。";
    const emptyHtml = '<div class="empty-hint">' + emptyText + "</div>";
    if (!state.items.length) {
      els.gridWrap.innerHTML = emptyHtml;
      return;
    }
    const cardHtml = (b) => {
      const coverSrc = b.cover_path || b.cover_url;
      const cover = coverSrc
        ? // 固定宽高属性，减少图片解码引起的布局抖动
          `<img src="${escapeAttr(coverSrc)}" alt="" width="150" height="200" loading="lazy" decoding="async" data-fallback="${escapeAttr(b.name || "")}" />`
        : `<div class="placeholder">${escapeHtml(b.name)}</div>`;
      return `
        <article class="book-card" data-id="${b.id}" tabindex="0" role="link">
          <div class="book-cover">${cover}</div>
          <div class="book-meta">
            <div class="book-name" title="${escapeAttr(b.name)}">${escapeHtml(b.name)}</div>
            <div class="book-sub">
              <span>${escapeHtml(b.author || "佚名")}</span>
            </div>
          </div>
        </article>`;
    };
    // 分页封面墙：单页条数有限，始终用普通网格，保证多列行占满
    //（虚拟网格按一卡一行定位，与 auto-fill 多列布局不兼容）
    els.gridWrap.innerHTML = state.items.map(cardHtml).join("");
    // 只为封面绑 fallback；卡片点击用委托（见 bindGridDelegates）
    els.gridWrap.querySelectorAll(".book-card img").forEach((img) => {
      bindCoverFallback(img, img.dataset.fallback || "");
    });
  }

  // 封面墙点击/键盘：事件委托只绑一次
  function bindGridDelegates() {
    const wrap = els.gridWrap;
    if (!wrap) return;
    wrap.addEventListener("click", (e) => {
      const card = e.target.closest && e.target.closest(".book-card");
      if (!card || !wrap.contains(card)) return;
      openDrawer(Number(card.dataset.id));
    });
    wrap.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const card = e.target.closest && e.target.closest(".book-card");
      if (!card || !wrap.contains(card)) return;
      e.preventDefault();
      openDrawer(Number(card.dataset.id));
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
    // 两级分类：优先 API 拆分字段，否则从合成串解析
    const lv = (book.category_source !== undefined || book.category_name !== undefined)
      ? { category_source: book.category_source || "", category_name: book.category_name || "" }
      : splitCategory(book.category, book.source);
    setTwoLevelCategory(lv.category_source, lv.category_name);
    els.editStatus.value = book.status || "完结";
    els.editTags.value = (book.tags || []).join(", ");
    els.editIntro.value = book.intro || "";
    els.coverPreview.src = book.cover_path || book.cover_url || placeholderDataUri(book.name || "");
    els.coverPreview.alt = book.name || "封面";
    bindCoverFallback(els.coverPreview, book.name || "");
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
    // 刮削弹窗书源默认与当前书源一致
    if (els.scrapeSource) {
      const map = { "起点": "qidian", "番茄": "fanqie", "qidian": "qidian", "fanqie": "fanqie" };
      els.scrapeSource.value = map[book.source] || map[lv.category_source] || "qidian";
    }
    els.scrapeResults.innerHTML = "";
    els.drawer.hidden = false;
    els.drawerMask.hidden = false;
  }

  function openScrapeModal() {
    const localName = (els.editTitle.value || "").trim();
    els.scrapeKeyword.value = localName;
    // 选择书源后第一级（书源）自动匹配
    const srcKey = (els.editSource && els.editSource.value) || "";
    const map = { "起点": "qidian", "番茄": "fanqie" };
    if (els.scrapeSource && map[srcKey]) els.scrapeSource.value = map[srcKey];
    els.scrapeLocal.innerHTML =
      "当前书籍：<strong>" + escapeHtml(localName || "(未命名)") + "</strong>" +
      (els.editAuthor.value ? " · " + escapeHtml(els.editAuthor.value) : "") +
      (srcKey ? " · 书源 " + escapeHtml(srcKey) : "");
    els.scrapeTip.textContent = "结果只预览，点「采用并写入」才会改当前这本书。采用后书源自动匹配，分类按刮削结果填入。";
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
      <p style="margin:0 0 10px">确认把<strong>当前这本书</strong>的元数据替换为${escapeHtml(hit.source || "站外")}结果？</p>
      <div class="scrape-local">
        <div>本地：<strong>${escapeHtml(localName)}</strong>${localAuthor ? " · " + escapeHtml(localAuthor) : ""}</div>
        <div>${escapeHtml(hit.source || "站外")}：<strong>${escapeHtml(hit.name || "")}</strong>${hit.author ? " · " + escapeHtml(hit.author) : ""}</div>
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
          hint_word_count: Number(hit.word_count) || 0,
        },
      });
      els.editTitle.value = res.name || "";
      els.editAuthor.value = res.author || "";
      // 手动刮削：书源自动匹配 + 按刮削具体分类填入二级
      const lv = (res.category_source !== undefined || res.category_name !== undefined)
        ? { category_source: res.category_source || "", category_name: res.category_name || "" }
        : splitCategory(res.category, res.source);
      setTwoLevelCategory(lv.category_source, lv.category_name);
      if (els.scrapeSource) {
        const map = { "起点": "qidian", "番茄": "fanqie" };
        if (map[lv.category_source]) els.scrapeSource.value = map[lv.category_source];
      }
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

  // —— 统一确认框：替代原生 confirm，支持 Esc / 焦点回收 ——
  let confirmResolver = null;
  function openConfirm(message, title) {
    return new Promise((resolve) => {
      confirmResolver = resolve;
      if (els.confirmTitle) els.confirmTitle.textContent = title || "确认操作";
      if (els.confirmBody) {
        els.confirmBody.innerHTML = "";
        // 保留换行，同时避免注入 HTML
        message.split("\n").forEach((line, i) => {
          if (i) els.confirmBody.appendChild(document.createElement("br"));
          els.confirmBody.appendChild(document.createTextNode(line));
        });
      }
      els.confirmModal.hidden = false;
      els.confirmMask.hidden = false;
      if (els.confirmYes) els.confirmYes.focus();
    });
  }
  function closeConfirm(ok) {
    els.confirmModal.hidden = true;
    els.confirmMask.hidden = true;
    const r = confirmResolver;
    confirmResolver = null;
    if (r) r(!!ok);
  }

  // —— 弹层焦点陷阱 + Esc 关闭 ——
  function trapFocus(container, e) {
    if (e.key !== "Tab" || !container) return;
    const nodes = container.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const list = Array.prototype.filter.call(nodes, (n) => !n.disabled && n.offsetParent !== null);
    if (!list.length) return;
    const first = list[0];
    const last = list[list.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  function activeOverlay() {
    if (els.confirmModal && !els.confirmModal.hidden) return els.confirmModal;
    if (els.pwModal && !els.pwModal.hidden) return els.pwModal;
    if (els.scrapeConfirm && !els.scrapeConfirm.hidden) return els.scrapeConfirm;
    if (els.scrapeModal && !els.scrapeModal.hidden) return els.scrapeModal;
    if (els.drawer && !els.drawer.hidden) return els.drawer;
    return null;
  }

  function closeTopOverlay() {
    if (els.confirmModal && !els.confirmModal.hidden) { closeConfirm(false); return true; }
    if (els.pwModal && !els.pwModal.hidden) { closePwModal(); return true; }
    if (els.scrapeConfirm && !els.scrapeConfirm.hidden) { closeScrapeConfirm(); return true; }
    if (els.scrapeModal && !els.scrapeModal.hidden) { closeScrapeModal(); return true; }
    if (els.drawer && !els.drawer.hidden) { closeDrawer(); return true; }
    return false;
  }

  async function saveBook() {
    const id = Number(els.editId.value);
    if (!id) return;
    const lv = getTwoLevelCategory();
    const payload = {
      title: els.editTitle.value.trim(),
      author: els.editAuthor.value.trim() || "佚名",
      category_source: lv.category_source,
      category_name: lv.category_name,
      status: els.editStatus.value,
      tags: els.editTags.value,
      intro: els.editIntro.value,
    };
    await withBusy(els.saveBtn, async () => {
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
    }, "保存中…");
  }

  async function deleteBook() {
    const id = Number(els.editId.value);
    const name = els.editTitle.value;
    if (!id) return;
    if (!await openConfirm("确认删除《" + name + "》？\n章节与封面将一并删除，源 TXT 文件保留。", "删除书籍")) return;
    await withBusy(els.deleteBtn, async () => {
      try {
        await api("/api/admin/books/" + id, { method: "DELETE" });
        toast("已删除《" + name + "》", "ok");
        closeDrawer();
        await Promise.all([loadBooks(), loadStats()]);
      } catch (err) {
        toast(err.message || "删除失败", "err");
      }
    }, "删除中…");
  }

  function setImportProgressVisible(on) {
    if (!els.importProgress) return;
    els.importProgress.hidden = !on;
  }

  function updateImportProgressBar(pct) {
    const n = Math.min(100, Math.max(0, Number(pct) || 0));
    if (els.importProgressFill) {
      els.importProgressFill.style.width = n + "%";
    }
    return n;
  }

  function renderImportLog(importStatus) {
    if (!importStatus) {
      setImportProgressVisible(false);
      els.importLog.textContent = "尚未运行导入。";
      return;
    }
    if (importStatus.running) {
      // 实时进度：进度条 + 已处理/总数 + 当前文件 + 四类计数
      setImportProgressVisible(true);
      const total = Number(importStatus.total) || 0;
      const done = Number(importStatus.done) || 0;
      const pct = updateImportProgressBar(
        importStatus.percent != null
          ? importStatus.percent
          : total
            ? Math.floor((done * 100) / total)
            : 0
      );
      const counts =
        "新增 " + (importStatus.added_n || 0) +
        " · 更新 " + (importStatus.updated_n || 0) +
        " · 跳过 " + (importStatus.skipped_n || 0) +
        " · 失败 " + (importStatus.failed_n || 0);
      const head = total
        ? "导入中 " + done + " / " + total + "（" + pct + "%）"
        : "正在扫描 novels 目录…";
      if (els.importProgressText) {
        els.importProgressText.textContent =
          head + (importStatus.current ? "　当前: " + importStatus.current : "");
      }
      const lines = [];
      lines.push(head);
      if (importStatus.current) lines.push("当前: " + importStatus.current);
      lines.push(counts);
      if (importStatus.cancel_requested) lines.push("（已请求停止…）");
      const recent = importStatus.recent || [];
      if (recent.length) {
        lines.push("");
        lines.push("[最近]");
        recent.forEach((x) => lines.push("  " + x));
      }
      els.importLog.textContent = lines.join("\n");
      return;
    }
    // 结束：展示满格进度条与完整结果日志
    const last = importStatus.last;
    if (!last) {
      setImportProgressVisible(false);
      els.importLog.textContent = "尚未运行导入。";
      return;
    }
    updateImportProgressBar(importStatus.percent != null ? importStatus.percent : 100);
    if (els.importProgressText) {
      els.importProgressText.textContent = "已完成";
    }
    setImportProgressVisible(true);
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
    // 仅本地导入
    await withBusy(els.importBtn, async () => {
      try {
        const res = await api("/api/admin/import?mode=local", { method: "POST" });
        toast(res.started ? "本地导入已开始" : "导入已在进行中", "ok");
        renderImportLog(res.import);
        pollImport();
      } catch (err) {
        toast(err.message || "导入失败", "err");
      }
    }, "启动中…");
  }

  // A6：请求停止导入
  async function cancelImport() {
    try {
      const res = await api("/api/admin/import/cancel", { method: "POST" });
      toast(res.ok ? "已请求停止导入" : "当前没有进行中的导入", res.ok ? "ok" : "err");
      renderImportLog(res.import);
    } catch (err) {
      toast(err.message || "停止失败", "err");
    }
  }

  function pollImport() {
    // C5：优先 SSE，失败回退轮询
    if (window.EventSource) {
      try {
        const es = new EventSource("/api/admin/import/stream");
        es.onmessage = (ev) => {
          try {
            const st = JSON.parse(ev.data);
            renderImportLog(st);
            if (!st.running) {
              es.close();
              loadBooks().catch(() => {});
              loadStats().catch(() => {});
              toast("导入完成", "ok");
            }
          } catch (_) {}
        };
        es.onerror = () => {
          es.close();
          pollImportFallback();
        };
        return;
      } catch (_) { /* fallthrough */ }
    }
    pollImportFallback();
  }

  function pollImportFallback() {
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
      els.dupList.innerHTML = '<div class="empty-hint">没有发现重复书。</div>';
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
        btn.addEventListener("click", async () => {
          const g = dups[Number(btn.dataset.merge)];
          if (!g) return;
          const del = (g.books || []).filter((b) => b.id !== g.keep_id).map((b) => b.id);
          if (!await openConfirm(`合并《${g.title}》\n保留 ID ${g.keep_id}，删除 ${del.join(", ")}？`, "合并重复书")) return;
          mergeDup(g.keep_id, del);
        });
      });
    }

    // 异常
    if (!issues.length) {
      els.issueList.innerHTML = '<div class="empty-hint">没有发现异常，书库健康。</div>';
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
    if (!await openConfirm("对所有异常书执行自动修复？\n（清理字符，必要时从源 TXT 重解析）", "修复全部")) return;
    await withBusy(els.checkRepairAll, async () => {
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
    }, "修复中…");
  }

  // 按分类归位：把源 TXT 移到与书籍分类一致的文件夹
  async function relocateAll() {
    if (!await openConfirm("按书籍分类归位源 TXT？\n将把「未分类」等目录中的文件移到对应分类文件夹（只移动位置，不改内容）。", "按分类归位")) return;
    await withBusy(els.checkRelocate, async () => {
      try {
        const res = await api("/api/admin/library/relocate", {
          method: "POST",
          body: {},
        });
        toast(
          "归位完成：移动 " + (res.moved || 0) + " 本 · 失败 " + (res.failed || 0) + " 本",
          res.failed ? "err" : "ok"
        );
        await Promise.all([loadLibraryReport(), loadBooks(), loadStats()]);
      } catch (err) {
        toast(err.message || "归位失败", "err");
      }
    }, "归位中…");
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
    const btn = dryRun ? els.batchScrapePreview : els.batchScrapeRun;
    await withBusy(btn, async () => {
      try {
        const res = await api("/api/admin/scrape/batch/start", {
          method: "POST",
          body: {
            // 按面板所选刮削源（起点/番茄）批量写入元数据
            source: (els.batchScrapeSource && els.batchScrapeSource.value) || "qidian",
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
    }, dryRun ? "预览中…" : "启动中…");
  }

  function pollBatchScrape() {
    // C5：优先 SSE
    if (window.EventSource) {
      try {
        const es = new EventSource("/api/admin/scrape/batch/stream");
        es.onmessage = (ev) => {
          try {
            const st = JSON.parse(ev.data);
            renderBatchStatus(st);
            if (!st.running) {
              es.close();
              Promise.all([
                loadBooks(),
                loadStats(),
                loadLibraryReport().catch(() => {}),
              ]).then(() => toast("批处理完成", "ok"));
            }
          } catch (_) {}
        };
        es.onerror = () => {
          es.close();
          pollBatchFallback();
        };
        return;
      } catch (_) { /* fallthrough */ }
    }
    pollBatchFallback();
  }

  function pollBatchFallback() {
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

  // A6：请求停止批量刮削
  async function cancelBatchScrape() {
    try {
      const res = await api("/api/admin/scrape/batch/cancel", { method: "POST" });
      toast(res.ok ? "已请求停止刮削" : "当前没有进行中的任务", res.ok ? "ok" : "err");
      renderBatchStatus(res.status);
    } catch (err) {
      toast(err.message || "停止失败", "err");
    }
  }

  async function refreshBatchStatus() {
    const st = await api("/api/admin/scrape/batch/status");
    renderBatchStatus(st);
  }

  function switchView(name) {
    document.querySelectorAll("[data-view]").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === name);
    });
    ["library", "import", "check", "api", "settings"].forEach((v) => {
      const el = $("view-" + v);
      if (el) el.hidden = v !== name;
    });
    if (name === "check") {
      loadLibraryReport().catch((e) => toast(e.message, "err"));
      refreshBatchStatus().catch(() => {});
    }
  }

  function on(el, ev, fn) {
    if (el && el.addEventListener) el.addEventListener(ev, fn);
  }

  // 按钮忙碌态：禁用 + 文案提示，防止连点重复提交
  async function withBusy(btn, fn, busyText) {
    if (!btn) return await fn();
    const oldText = btn.textContent;
    const oldDisabled = btn.disabled;
    btn.disabled = true;
    btn.classList.add("is-loading");
    if (busyText) btn.textContent = busyText;
    try {
      return await fn();
    } finally {
      btn.classList.remove("is-loading");
      btn.disabled = oldDisabled;
      btn.textContent = oldText;
    }
  }

  // 封面加载失败时回退占位
  function bindCoverFallback(img, name) {
    if (!img) return;
    img.addEventListener("error", function onErr() {
      img.removeEventListener("error", onErr);
      img.src = placeholderDataUri(name || "");
    });
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
  on(els.sideLogout, "click", () => logout(true));
  on(els.confirmYes, "click", () => closeConfirm(true));
  on(els.confirmNo, "click", () => closeConfirm(false));
  on(els.confirmMask, "click", () => closeConfirm(false));
  // Esc 关闭顶层弹层；Tab 在打开的弹层内循环
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (closeTopOverlay()) e.preventDefault();
      return;
    }
    const overlay = activeOverlay();
    if (overlay) trapFocus(overlay, e);
  });
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
  // A3：输入页码后回车/失焦跳转
  if (els.pageInput) {
    on(els.pageInput, "keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        gotoPage(els.pageInput.value);
      }
    });
    on(els.pageInput, "change", () => gotoPage(els.pageInput.value));
    on(els.pageInput, "blur", () => {
      if (els.pageInput) els.pageInput.value = String(state.page);
    });
  }
  // A7：窄屏折叠导航
  if (els.navToggle) {
    const sidebar = document.querySelector(".sidebar");
    // 小屏默认收起，减少顶栏占高
    if (window.matchMedia && window.matchMedia("(max-width: 860px)").matches && sidebar) {
      sidebar.classList.add("collapsed");
      els.navToggle.setAttribute("aria-expanded", "false");
    }
    on(els.navToggle, "click", () => {
      if (!sidebar) return;
      const collapsed = sidebar.classList.toggle("collapsed");
      els.navToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      els.navToggle.setAttribute("aria-label", collapsed ? "展开导航" : "收起导航");
    });
  }
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
  on(els.gridSize, "input", () => applyGridSize(els.gridSize.value));
  // 窗口尺寸变化 → 重算列数与每页数量
  window.addEventListener("resize", () => {
    schedulePageSizeRefresh();
  });
  on(els.themeSelect, "change", () => applyTheme(els.themeSelect.value));
  if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      if (state.theme === "auto") applyTheme("auto");
    });
  }
  on(els.importBtn, "click", () => startImport("local"));
  on(els.importCancel, "click", cancelImport);
  on(els.importRefresh, "click", () => refreshImport().catch(toast));
  on(els.copySource, "click", copySource);
  on(els.checkScan, "click", () => {
    withBusy(els.checkScan, () => loadLibraryReport().catch((e) => toast(e.message, "err")), "扫描中…");
  });
  on(els.checkRepairAll, "click", repairAll);
  on(els.checkRelocate, "click", relocateAll);
  on(els.batchScrapePreview, "click", () => startBatchScrape(true));
  on(els.batchScrapeRun, "click", async () => {
    if (!await openConfirm("开始对全库一键刮削？\n将按书名/作者最近匹配写入元数据。", "一键刮削")) return;
    startBatchScrape(false);
  });
  on(els.batchScrapeStatus, "click", () => refreshBatchStatus().catch(toast));
  on(els.batchScrapeCancel, "click", cancelBatchScrape);
  on(els.drawerClose, "click", closeDrawer);
  on(els.cancelBtn, "click", closeDrawer);
  on(els.drawerMask, "click", closeDrawer);
  on(els.saveBtn, "click", saveBook);
  on(els.scrapeOpenBtn, "click", openScrapeModal);
  on(els.scrapeSearchBtn, "click", runScrapeSearch);
  // 刮削源变更 → 同步编辑页第一级书源
  on(els.scrapeSource, "change", () => {
    const map = { qidian: "起点", fanqie: "番茄" };
    const want = map[els.scrapeSource.value] || "";
    if (els.editSource && els.editSource.value !== want) {
      setTwoLevelCategory(want, els.editCategory.value);
    }
  });
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
  // 初始化封面大小（不触发列表请求，登录后再按布局定 page_size）
  applyGridSize(localStorage.getItem(GRID_SIZE_KEY) || 150);
  applyDrawerWidth(localStorage.getItem(DRAWER_W_KEY) || 520);
  initDrawerResize();
  // 分类/书源条与封面墙：事件委托只绑一次
  bindBarDelegates();
  bindGridDelegates();
  if (els.sortSelect) els.sortSelect.value = state.sort || "updated";
  Promise.resolve()
    .then(() => bootAuth())
    .catch((e) => {
      showLogin();
      showAuthPane("login");
      authError(e.message || "无法连接服务端");
    });
})();

