// 用最小 DOM mock 执行 admin.js，抓运行时错误
const fs = require("fs");
const code = fs.readFileSync("admin.js", "utf8");

function el(id) {
  return {
    id,
    hidden: false,
    value: "",
    checked: false,
    textContent: "",
    innerHTML: "",
    className: "",
    scrollTop: 0,
    scrollHeight: 0,
    style: { setProperty() {} },
    files: null,
    src: "",
    focus() {},
    remove() {},
    setAttribute() {},
    getAttribute() { return null; },
    hasAttribute() { return false; },
    addEventListener() {},
    querySelectorAll() { return []; },
    querySelector() { return null; },
    appendChild() {},
    classList: { add() {}, remove() {}, toggle() {} },
  };
}

const store = {};
const document = {
  documentElement: {
    dataset: {},
    style: { setProperty() {} },
    appendChild() {},
  },
  body: { style: {}, appendChild() {}, removeChild() {} },
  getElementById(id) {
    if (!store[id]) store[id] = el(id);
    return store[id];
  },
  querySelectorAll() { return []; },
  querySelector() { return null; },
  createElement(tag) { return el(tag); },
  addEventListener() {},
  readyState: "complete",
};
const window = {
  matchMedia() { return { matches: false, addEventListener() {} }; },
  addEventListener() {},
  MutationObserver: class { observe() {} },
  localStorage: {
    getItem() { return null; },
    setItem() {},
    removeItem() {},
  },
};
const localStorage = window.localStorage;
const fetch = async () => ({ status: 200, text: async () => "{}" });
const URL = { createObjectURL: () => "blob:" };
const confirm = () => true;

try {
  const fn = new Function("document", "window", "localStorage", "fetch", "URL", "confirm", "MutationObserver", code + "\n;return 'ran';");
  const out = fn(document, window, localStorage, fetch, URL, confirm, window.MutationObserver);
  console.log("RUNTIME_OK", out);
} catch (e) {
  console.log("RUNTIME_ERR", e && e.stack || e);
}
