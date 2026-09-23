/* 爱小说 Admin · 公共 UI 工具（B6 拆分） */
(function (global) {
  "use strict";

  function setText(el, val) {
    if (el) el.textContent = val;
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  function placeholderDataUri(text) {
    var t = (text || "").slice(0, 8);
    var svg =
      '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="128">' +
      '<rect width="100%" height="100%" fill="#1e2430"/>' +
      '<text x="50%" y="50%" fill="#8b93a7" font-size="12" text-anchor="middle" font-family="sans-serif">' +
      t.replace(/[<>&]/g, "") +
      "</text></svg>";
    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  }

  function bindCoverFallback(img, name) {
    if (!img) return;
    img.addEventListener("error", function onErr() {
      img.removeEventListener("error", onErr);
      img.src = placeholderDataUri(name || "");
    });
  }

  function withBusy(btn, fn, busyText) {
    return (async function () {
      if (!btn) return await fn();
      var oldText = btn.textContent;
      var oldDisabled = btn.disabled;
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
    })();
  }

  var confirmResolver = null;
  function openConfirm(message, title) {
    var els = {
      modal: document.getElementById("confirm-modal"),
      mask: document.getElementById("confirm-mask"),
      title: document.getElementById("confirm-title"),
      body: document.getElementById("confirm-body"),
      yes: document.getElementById("confirm-yes"),
    };
    return new Promise(function (resolve) {
      confirmResolver = resolve;
      if (els.title) els.title.textContent = title || "确认操作";
      if (els.body) {
        els.body.innerHTML = "";
        String(message || "").split("\n").forEach(function (line, i) {
          if (i) els.body.appendChild(document.createElement("br"));
          els.body.appendChild(document.createTextNode(line));
        });
      }
      els.modal.hidden = false;
      els.mask.hidden = false;
      if (els.yes) els.yes.focus();
    });
  }

  function closeConfirm(ok) {
    var modal = document.getElementById("confirm-modal");
    var mask = document.getElementById("confirm-mask");
    if (modal) modal.hidden = true;
    if (mask) mask.hidden = true;
    var r = confirmResolver;
    confirmResolver = null;
    if (r) r(!!ok);
  }

  function isConfirmOpen() {
    var modal = document.getElementById("confirm-modal");
    return modal && !modal.hidden;
  }

  function trapFocus(container, e) {
    if (e.key !== "Tab" || !container) return;
    var nodes = container.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    var list = Array.prototype.filter.call(nodes, function (n) {
      return !n.disabled && n.offsetParent !== null;
    });
    if (!list.length) return;
    var first = list[0];
    var last = list[list.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  // 虚拟滚动（B7）：卡片很多时只渲染可视区附近 DOM
  function renderVirtualGrid(container, items, cardHtml, onClick, rowH) {
    var h = rowH || 240;
    // 清理上一次的 scroll 监听，避免重复绑定
    if (container._vspaint) {
      container.removeEventListener("scroll", container._vspaint);
      container._vspaint = null;
    }
    if (items.length <= 40) {
      container.style.height = "";
      container.style.overflow = "";
      container.innerHTML = items.map(cardHtml).join("");
      bindCardEvents(container, onClick);
      return;
    }
    container.style.overflow = "auto";
    container.style.height = "70vh";
    var gap = 14;
    var total = items.length * (h + gap);
    var pad = document.createElement("div");
    pad.style.height = total + "px";
    pad.style.position = "relative";
    container.innerHTML = "";
    container.appendChild(pad);
    function paint() {
      var st = container.scrollTop;
      var start = Math.max(0, Math.floor(st / (h + gap)) - 2);
      var end = Math.min(items.length, start + Math.ceil(container.clientHeight / (h + gap)) + 4);
      var html = "";
      for (var i = start; i < end; i++) {
        html += '<div class="vslot" style="position:absolute;top:' + i * (h + gap) + 'px;left:0;right:0;height:' + h + 'px">' +
          cardHtml(items[i]) + "</div>";
      }
      pad.innerHTML = html;
      bindCardEvents(pad, onClick);
    }
    container._vspaint = paint;
    container.addEventListener("scroll", paint, { passive: true });
    paint();
  }

  function bindCardEvents(root, onClick) {
    root.querySelectorAll("[data-id]").forEach(function (el) {
      el.addEventListener("click", function () { onClick(Number(el.dataset.id)); });
      // B5 键盘可达
      el.setAttribute("tabindex", "0");
      el.setAttribute("role", "link");
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick(Number(el.dataset.id));
        }
      });
    });
  }

  global.AinovelUI = {
    setText: setText,
    escapeHtml: escapeHtml,
    escapeAttr: escapeAttr,
    placeholderDataUri: placeholderDataUri,
    bindCoverFallback: bindCoverFallback,
    withBusy: withBusy,
    openConfirm: openConfirm,
    closeConfirm: closeConfirm,
    isConfirmOpen: isConfirmOpen,
    trapFocus: trapFocus,
    renderVirtualGrid: renderVirtualGrid,
  };
})(window);
