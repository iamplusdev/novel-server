"""FastAPI 入口：公开 API + Legado + 管理后台 + 静态封面/前端。"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .routers import admin, auth, batch_scrape, legado, library, public, scrape
from .importer import ensure_category_dirs

BASE_DIR = Path(__file__).resolve().parent.parent
# Vue3 新前端构建产物目录（P1 起优先托管；P8 前旧 Vanilla 仍作回退）
DIST_DIR = BASE_DIR / "frontend" / "dist"
# SPA fallback 时不拦截的前缀（API / 静态资源 / 健康检查）
SPA_EXCLUDE_PREFIXES = ("/api", "/covers", "/health", "/legado_book_source.json", "/favicon.ico")

app = FastAPI(
    title="Personal Novel Library",
    description="爱小说：分类浏览 / 搜索 / 阅读 / Legado 书源 / 管理后台",
    version="1.0.0",
)

# 局域网内浏览器调试用；Legado 一般不走 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(public.router)
app.include_router(legado.router)
app.include_router(admin.router)
app.include_router(scrape.router)
app.include_router(library.router)
app.include_router(batch_scrape.router)

settings.ensure_dirs()
ensure_category_dirs()
init_db()

# 封面静态目录
app.mount("/covers", StaticFiles(directory=str(settings.covers_dir)), name="covers")


def _asset_ver(name: str) -> str:
    """静态资源版本号：取文件 mtime，改完 JS/CSS 后强制刷新缓存。"""
    try:
        return str(int((BASE_DIR / name).stat().st_mtime))
    except OSError:
        return "0"


def _has_vue_dist() -> bool:
    """是否已构建 Vue 新前端（存在 dist/index.html）。"""
    return (DIST_DIR / "index.html").is_file()


def _render_vue_index() -> FileResponse:
    """托管 Vue 构建产物入口（Vite 已带 contenthash，无需额外版本号）。"""
    return FileResponse(DIST_DIR / "index.html", media_type="text/html")


def _render_legacy_index() -> HTMLResponse:
    """旧 Vanilla 入口：读入 index.html，并把 css/js 的 ?v= 换成当前 mtime。"""
    html = (BASE_DIR / "index.html").read_text(encoding="utf-8")
    ver = (
        _asset_ver("admin.js")
        + _asset_ver("admin.css")
        + _asset_ver("admin.ui.js")
    )
    html = re.sub(
        r"(admin(?:\.ui)?\.js|admin\.css)\?v=[^\"']+",
        lambda m: f"{m.group(1)}?v={ver}",
        html,
    )
    return HTMLResponse(html)


def _render_index() -> HTMLResponse | FileResponse:
    """优先新前端，未构建时回退旧页面。"""
    if _has_vue_dist():
        return _render_vue_index()
    return _render_legacy_index()


@app.get("/", include_in_schema=False)
def index():
    return _render_index()


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
def admin_page():
    return _render_index()


@app.get("/admin.css", include_in_schema=False)
def admin_css() -> FileResponse:
    return FileResponse(BASE_DIR / "admin.css", media_type="text/css")


@app.get("/admin.js", include_in_schema=False)
def admin_js() -> FileResponse:
    return FileResponse(BASE_DIR / "admin.js", media_type="application/javascript")


@app.get("/admin.ui.js", include_in_schema=False)
def admin_ui_js() -> FileResponse:
    return FileResponse(BASE_DIR / "admin.ui.js", media_type="application/javascript")


@app.get("/legado_book_source.json", include_in_schema=False)
def legado_source_file() -> FileResponse:
    return FileResponse(BASE_DIR / "legado_book_source.json", media_type="application/json")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(BASE_DIR / "favicon.ico", media_type="image/x-icon")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "public_base_url": settings.public_base_url}


# Vue 静态资源（assets、favicon 等）；须在 SPA fallback 之前挂载
if _has_vue_dist():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="vue-assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    """history 路由回退：非 API/静态请求一律返回 Vue index.html。"""
    path = "/" + full_path
    if any(path.startswith(p) for p in SPA_EXCLUDE_PREFIXES):
        # API / 资源前缀不走 SPA 回退
        raise HTTPException(status_code=404)
    if _has_vue_dist():
        # dist 内真实静态文件（如 favicon 已在 public）
        candidate = (DIST_DIR / full_path).resolve()
        try:
            candidate.relative_to(DIST_DIR.resolve())
        except ValueError:
            return _render_vue_index()
        if candidate.is_file():
            return FileResponse(candidate)
        return _render_vue_index()
    return _render_legacy_index()


def create_app() -> FastAPI:
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
