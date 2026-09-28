"""FastAPI 入口：公开 API + Legado + 管理后台（Vue SPA）+ 静态封面。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .routers import admin, auth, batch_scrape, legado, library, public, scrape
from .importer import ensure_category_dirs

BASE_DIR = Path(__file__).resolve().parent.parent
# Vue3 前端构建产物（frontend/dist）
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


def _has_vue_dist() -> bool:
    """是否已构建 Vue 前端（存在 dist/index.html）。"""
    return (DIST_DIR / "index.html").is_file()


def _render_index() -> FileResponse:
    """托管 Vue 构建产物入口（Vite 已带 contenthash）。"""
    if not _has_vue_dist():
        raise HTTPException(
            503,
            "前端未构建：请在 frontend/ 执行 npm install && npm run build",
        )
    return FileResponse(DIST_DIR / "index.html", media_type="text/html")


@app.get("/", include_in_schema=False)
def index():
    return _render_index()


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
def admin_page():
    return _render_index()


@app.get("/legado_book_source.json", include_in_schema=False)
def legado_source_file() -> FileResponse:
    return FileResponse(BASE_DIR / "legado_book_source.json", media_type="application/json")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    # 优先 dist/public，回退仓库根目录
    for p in (DIST_DIR / "favicon.ico", BASE_DIR / "favicon.ico"):
        if p.is_file():
            return FileResponse(p, media_type="image/x-icon")
    raise HTTPException(404)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "public_base_url": settings.public_base_url}


# Vue 静态资源；须在 SPA fallback 之前挂载
if (DIST_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="vue-assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    """history 路由回退：非 API/静态请求一律返回 Vue index.html。"""
    path = "/" + full_path
    if any(path.startswith(p) for p in SPA_EXCLUDE_PREFIXES):
        raise HTTPException(status_code=404)
    if not _has_vue_dist():
        raise HTTPException(503, "前端未构建：请在 frontend/ 执行 npm install && npm run build")
    # dist 内真实静态文件（public/ 产物）
    candidate = (DIST_DIR / full_path).resolve()
    try:
        candidate.relative_to(DIST_DIR.resolve())
    except ValueError:
        return _render_index()
    if candidate.is_file():
        return FileResponse(candidate)
    return _render_index()


def create_app() -> FastAPI:
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
