"""FastAPI 入口：公开 API + Legado + 管理后台 + 静态封面/前端。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .routers import admin, auth, backup, legado, public
from .importer import ensure_category_dirs
from .backup import start_scheduler

BASE_DIR = Path(__file__).resolve().parent.parent

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
app.include_router(backup.router)

settings.ensure_dirs()
ensure_category_dirs()
init_db()
start_scheduler()

# 封面静态目录
app.mount("/covers", StaticFiles(directory=str(settings.covers_dir)), name="covers")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "index.html")


@app.get("/admin", include_in_schema=False)
@app.get("/admin/", include_in_schema=False)
def admin_page() -> FileResponse:
    return FileResponse(BASE_DIR / "index.html")


@app.get("/admin.css", include_in_schema=False)
def admin_css() -> FileResponse:
    return FileResponse(BASE_DIR / "admin.css", media_type="text/css")


@app.get("/admin.js", include_in_schema=False)
def admin_js() -> FileResponse:
    return FileResponse(BASE_DIR / "admin.js", media_type="application/javascript")


@app.get("/legado_book_source.json", include_in_schema=False)
def legado_source_file() -> FileResponse:
    return FileResponse(BASE_DIR / "legado_book_source.json", media_type="application/json")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "public_base_url": settings.public_base_url}


def create_app() -> FastAPI:
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
