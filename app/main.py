"""FastAPI 入口：API + Legado + 管理 API + 封面/前端静态。

同一 ASGI 应用同时服务 API（PORT，默认 7312）与前端入口（FRONTEND_PORT，默认 7311），
静态与接口同源，无需反代。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .logging_setup import setup_logging
from .routers import admin, auth, batch_scrape, legado, library, public, scrape
from .importer import ensure_category_dirs

setup_logging()

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = BASE_DIR / "frontend" / "dist"

app = FastAPI(
    title="Personal Novel Library",
    description="爱小说：分类浏览 / 搜索 / 阅读 / Legado 书源 / 管理 API",
    version="1.0.0",
)

# 直连调试时放开 CORS；同源访问无需 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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


@app.get("/legado_book_source.json", include_in_schema=False)
def legado_source_file() -> FileResponse:
    return FileResponse(BASE_DIR / "legado_book_source.json", media_type="application/json")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    """favicon：优先 Vue dist，回退仓库根。"""
    for p in (DIST_DIR / "favicon.ico", BASE_DIR / "favicon.ico"):
        if p.is_file():
            return FileResponse(p, media_type="image/x-icon")
    raise HTTPException(404)


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "public_base_url": settings.public_base_url,
        "api_port": settings.port,
        "frontend_port": settings.frontend_port,
    }


# ---- 前端 SPA（history 路由回退；注册在 API 路由之后，不会抢 /api）----
if DIST_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str) -> FileResponse:
    """静态资源优先，其余路径回退 index.html；/api 未命中返回 404。"""
    # API/文档/健康检查未匹配到路由时不要回 SPA
    for prefix in ("api/", "docs", "openapi.json", "redoc", "health"):
        if full_path == prefix.rstrip("/") or full_path.startswith(prefix):
            raise HTTPException(404, "Not Found")
    index = DIST_DIR / "index.html"
    if full_path:
        candidate = (DIST_DIR / full_path).resolve()
        try:
            candidate.relative_to(DIST_DIR.resolve())
        except ValueError:
            candidate = index
        if candidate.is_file() and candidate.suffix:
            return FileResponse(candidate)
    if not index.is_file():
        raise HTTPException(503, "frontend not built: cd frontend && npm run build")
    return FileResponse(index)


def create_app() -> FastAPI:
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
