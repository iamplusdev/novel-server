"""FastAPI 入口：公开 API + Legado + 管理 API + 封面静态（不含前端页面）。

前端由 app/frontend_server.py 在 FRONTEND_PORT（默认 7311）托管；
本进程只监听 PORT（默认 7312）提供 API，通过前端反代对浏览器暴露。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
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

app = FastAPI(
    title="Personal Novel Library",
    description="爱小说：分类浏览 / 搜索 / 阅读 / Legado 书源 / 管理 API",
    version="1.0.0",
)

# 直连后端调试时放开 CORS；经前端 :7311 反代则同源无需 CORS
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
    from fastapi import HTTPException

    for p in (BASE_DIR / "frontend" / "dist" / "favicon.ico", BASE_DIR / "favicon.ico"):
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


def create_app() -> FastAPI:
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
