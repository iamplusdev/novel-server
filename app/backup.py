"""备份打包 / WebDAV 上传 / 还原 / 自动备份调度。

备份内容（关键数据）：SQLite 数据库 + covers 封面目录 + manifest。
不打包 novels/ 源 TXT（体量大，通常另有原件）。
WebDAV 密码落盘时用 auth secret 做流加密（A8），避免明文。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import settings
from .webdav import WebDAVClient, WebDAVError

BACKUP_PREFIX = "novel-server"
BACKUP_EXT = ".zip"
CONFIG_FILE_NAME = "backup_config.json"
_MANIFEST_NAME = "manifest.json"

_ops_lock = threading.Lock()
_scheduler_thread: threading.Thread | None = None
_scheduler_stop = threading.Event()

_status: dict = {
    "running": False,
    "action": "",
    "message": "",
    "last_backup_at": "",
    "last_restore_at": "",
    "last_error": "",
    "history": [],
}


@dataclass
class BackupConfig:
    webdav_url: str = ""
    username: str = ""
    password: str = ""
    remote_path: str = "novel-server-backups"
    books_path: str = "books"
    auto_enabled: bool = False
    interval_hours: int = 24
    keep_count: int = 7
    last_backup_at: str = ""

    def to_public_dict(self) -> dict:
        """返回给前端：密码打码。"""
        return {
            "webdav_url": self.webdav_url,
            "username": self.username,
            "password_set": bool(self.password),
            "remote_path": self.remote_path,
            "books_path": self.books_path,
            "auto_enabled": self.auto_enabled,
            "interval_hours": self.interval_hours,
            "keep_count": self.keep_count,
            "last_backup_at": self.last_backup_at,
        }

    def to_secret_dict(self) -> dict:
        return {
            "webdav_url": self.webdav_url,
            "username": self.username,
            "password": self.password,
            "remote_path": self.remote_path,
            "books_path": self.books_path,
            "auto_enabled": self.auto_enabled,
            "interval_hours": self.interval_hours,
            "keep_count": self.keep_count,
            "last_backup_at": self.last_backup_at,
        }


def config_path() -> Path:
    settings.ensure_dirs()
    return settings.database_path.parent / CONFIG_FILE_NAME


def _secret_key() -> bytes:
    """加密密钥：优先 auth.secret，否则用机器路径派生（未设账号时也能用）。"""
    try:
        from .auth import load_auth

        data = load_auth() or {}
        raw = (data.get("secret") or "") + "|" + str(settings.database_path)
    except Exception:  # noqa: BLE001
        raw = str(settings.database_path)
    return hashlib.sha256(raw.encode("utf-8")).digest()


def encrypt_secret(plain: str) -> str:
    """流加密 + HMAC 标记，返回 enc:v1:base64。仅防落盘明文，非军用级。"""
    if plain == "":
        return ""
    key = _secret_key()
    data = plain.encode("utf-8")
    # HMAC-SHA256 作密钥流
    out = bytearray()
    for i in range(0, len(data), 32):
        block = hmac.new(key, f"blk:{i // 32}".encode("ascii"), hashlib.sha256).digest()
        chunk = data[i : i + 32]
        out.extend(b ^ block[j] for j, b in enumerate(chunk))
    tag = hmac.new(key, bytes(out), hashlib.sha256).digest()
    return "enc:v1:" + base64.urlsafe_b64encode(tag + bytes(out)).decode("ascii")


def decrypt_secret(token: str) -> str:
    """解密 encrypt_secret；兼容旧明文（无 enc: 前缀）。"""
    if not token:
        return ""
    if not token.startswith("enc:v1:"):
        return token  # 旧配置明文，读入后下次保存会自动加密
    try:
        raw = base64.urlsafe_b64decode(token[len("enc:v1:") :].encode("ascii"))
        tag, body = raw[:32], raw[32:]
        key = _secret_key()
        expect = hmac.new(key, body, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expect):
            return ""
        out = bytearray()
        for i in range(0, len(body), 32):
            block = hmac.new(key, f"blk:{i // 32}".encode("ascii"), hashlib.sha256).digest()
            chunk = body[i : i + 32]
            out.extend(b ^ block[j] for j, b in enumerate(chunk))
        return bytes(out).decode("utf-8")
    except Exception:  # noqa: BLE001
        return ""


def load_config() -> BackupConfig:
    path = config_path()
    if not path.is_file():
        return BackupConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return BackupConfig()
    return BackupConfig(
        webdav_url=str(data.get("webdav_url") or ""),
        username=str(data.get("username") or ""),
        password=decrypt_secret(str(data.get("password") or "")),
        remote_path=str(data.get("remote_path") or "novel-server-backups").strip("/") or "novel-server-backups",
        books_path=(str(data.get("books_path") or "books").strip("/").replace("\\", "/") or "books"),
        auto_enabled=bool(data.get("auto_enabled")),
        interval_hours=max(1, int(data.get("interval_hours") or 24)),
        keep_count=max(1, int(data.get("keep_count") or 7)),
        last_backup_at=str(data.get("last_backup_at") or ""),
    )


def save_config(cfg: BackupConfig) -> None:
    path = config_path()
    secret = cfg.to_secret_dict()
    # 落盘加密，接口仍不回传明文
    secret["password"] = encrypt_secret(cfg.password or "")
    path.write_text(json.dumps(secret, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def get_status() -> dict:
    out = dict(_status)
    out["history"] = list(_status.get("history") or [])
    return out


def _log(message: str, action: str = "") -> None:
    _status["message"] = message
    if action:
        _status["action"] = action
    history = _status.setdefault("history", [])
    history.append({"time": datetime.now().isoformat(timespec="seconds"), "message": message})
    del history[:-30]


def _set_error(msg: str) -> None:
    _status["last_error"] = msg
    _log(msg)


def _backup_name(when: datetime | None = None) -> str:
    when = when or datetime.now()
    return f"{BACKUP_PREFIX}-{when.strftime('%Y%m%d-%H%M%S')}{BACKUP_EXT}"


def _snapshot_sqlite(dest: Path) -> None:
    """在线一致复制 SQLite（含 WAL）。"""
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    if not settings.database_path.exists():
        # 空库也生成一个空文件结构
        conn = sqlite3.connect(dest)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _placeholder (id INTEGER PRIMARY KEY)"
        )
        conn.commit()
        conn.close()
        return
    src = sqlite3.connect(f"file:{settings.database_path}?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def create_backup_zip() -> tuple[Path, dict]:
    """生成本地 zip，返回 (路径, manifest)。"""
    settings.ensure_dirs()
    manifest = {
        "app": "novel-server",
        "version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "database": "novels.db",
        "covers_dir": "covers",
        # 大体量正文在 data/contents/ 正文包，不进备份；还原后可从 novels/ 源 TXT 重新导入
        "includes": ["novels.db", "covers/"],
        "excludes": ["contents/", "novels/"],
        "note": "备份仅含小库与封面；章节正文包可从源 TXT 重建",
    }
    tmp_dir = Path(tempfile.mkdtemp(prefix="novel-backup-"))
    try:
        db_snap = tmp_dir / "novels.db"
        _snapshot_sqlite(db_snap)
        # 统计一下规模便于识别
        try:
            conn = sqlite3.connect(db_snap)
            cur = conn.execute("SELECT COUNT(*) FROM books")
            manifest["book_count"] = cur.fetchone()[0]
            cur = conn.execute("SELECT COUNT(*) FROM chapters")
            manifest["chapter_count"] = cur.fetchone()[0]
            conn.close()
        except sqlite3.Error:
            manifest["book_count"] = -1
            manifest["chapter_count"] = -1

        covers_src = settings.covers_dir
        cover_files = []
        if covers_src.is_dir():
            cover_files = [p for p in covers_src.rglob("*") if p.is_file()]
        manifest["cover_count"] = len(cover_files)

        name = _backup_name()
        out_path = settings.database_path.parent / "backups" / name
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(_MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.write(db_snap, "novels.db")
            for fp in cover_files:
                arc = "covers/" + fp.relative_to(covers_src).as_posix()
                zf.write(fp, arc)
        return out_path, manifest
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _client_from_config(cfg: BackupConfig) -> WebDAVClient:
    if not cfg.webdav_url:
        raise WebDAVError("请先填写 WebDAV 地址")
    return WebDAVClient(cfg.webdav_url, cfg.username, cfg.password)


def _remote_join(cfg: BackupConfig, filename: str) -> str:
    base = (cfg.remote_path or "").strip("/").replace("\\", "/")
    if not base:
        return filename
    return f"{base}/{filename}"


def upload_backup(cfg: BackupConfig, zip_path: Path) -> str:
    client = _client_from_config(cfg)
    cfg.remote_path = (cfg.remote_path or "novel-server-backups").strip("/") or "novel-server-backups"
    save_config(cfg)
    client.mkdir(cfg.remote_path)
    remote_name = zip_path.name
    _log(f"上传 {remote_name} …", "backup")
    client.put_file(_remote_join(cfg, remote_name), zip_path.read_bytes())
    # 更新 latest 指针，便于外部脚本抓取
    client.put_file(_remote_join(cfg, "latest.json"), json.dumps(
        {"latest": remote_name, "created_at": datetime.now().isoformat(timespec="seconds")},
        ensure_ascii=False,
    ).encode("utf-8"))
    _prune_remote(cfg, client)
    return remote_name


def _prune_remote(cfg: BackupConfig, client: WebDAVClient) -> None:
    keep = max(1, cfg.keep_count)
    try:
        names = [n for n in client.list_names(cfg.remote_path) if n.startswith(BACKUP_PREFIX) and n.endswith(BACKUP_EXT)]
    except WebDAVError:
        return
    names.sort(reverse=True)
    for old in names[keep:]:
        try:
            client.delete(_remote_join(cfg, old))
            _log(f"清理旧备份 {old}")
        except WebDAVError:
            pass


def list_remote_backups(cfg: BackupConfig) -> list[dict]:
    client = _client_from_config(cfg)
    items = client.list_items(cfg.remote_path)
    out = []
    for it in items:
        if it.is_dir:
            continue
        if not (it.name.startswith(BACKUP_PREFIX) and it.name.endswith(BACKUP_EXT)):
            continue
        out.append({
            "name": it.name,
            "size": it.size,
            "modified": it.modified,
        })
    out.sort(key=lambda x: x["name"], reverse=True)
    return out


def run_backup(local_only: bool = False) -> dict:
    """执行一次完整备份。默认打包后上传 WebDAV。"""
    if not _ops_lock.acquire(blocking=False):
        raise WebDAVError("已有备份/还原任务在执行")
    _status["running"] = True
    _status["last_error"] = ""
    try:
        _log("开始打包数据库与封面…", "backup")
        zip_path, manifest = create_backup_zip()
        result = {
            "local_file": zip_path.name,
            "local_path": str(zip_path),
            "manifest": manifest,
            "remote": None,
        }
        if not local_only:
            cfg = load_config()
            remote_name = upload_backup(cfg, zip_path)
            cfg.last_backup_at = datetime.now().isoformat(timespec="seconds")
            save_config(cfg)
            _status["last_backup_at"] = cfg.last_backup_at
            result["remote"] = remote_name
            _log(f"备份完成并已上传: {remote_name}", "backup")
        else:
            _log(f"本地备份完成: {zip_path.name}", "backup")
        return result
    except Exception as exc:  # noqa: BLE001
        _set_error(str(exc))
        raise
    finally:
        _status["running"] = False
        _ops_lock.release()


def download_backup_zip(cfg: BackupConfig, filename: str) -> bytes:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise WebDAVError("非法文件名")
    client = _client_from_config(cfg)
    return client.get_file(_remote_join(cfg, filename))


def restore_from_zip_bytes(data: bytes) -> dict:
    """用 zip 覆盖 novels.db 与 covers/。"""
    if not _ops_lock.acquire(blocking=False):
        raise WebDAVError("已有备份/还原任务在执行")
    _status["running"] = True
    try:
        _log("解压备份并还原…", "restore")
        tmp_dir = Path(tempfile.mkdtemp(prefix="novel-restore-"))
        try:
            zf_path = tmp_dir / "backup.zip"
            zf_path.write_bytes(data)
            with zipfile.ZipFile(zf_path, "r") as zf:
                names = zf.namelist()
                if "novels.db" not in names:
                    raise WebDAVError("备份文件中缺少 novels.db，无法还原")
                zf.extractall(tmp_dir)

            # 1) 还原数据库
            from . import database

            database.dispose_engine()
            db_src = tmp_dir / "novels.db"
            for suffix in ("", "-wal", "-shm"):
                p = Path(str(settings.database_path) + suffix)
                if p.exists():
                    p.unlink()
            settings.database_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_src, settings.database_path)
            database.reset_database()

            # 2) 还原封面
            covers_src = tmp_dir / "covers"
            settings.covers_dir.mkdir(parents=True, exist_ok=True)
            for old in settings.covers_dir.iterdir():
                if old.is_file():
                    old.unlink()
            if covers_src.is_dir():
                for fp in covers_src.rglob("*"):
                    if fp.is_file():
                        rel = fp.relative_to(covers_src)
                        dest = settings.covers_dir / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(fp, dest)

            manifest = {}
            mf = tmp_dir / _MANIFEST_NAME
            if mf.is_file():
                try:
                    manifest = json.loads(mf.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    manifest = {}

            _status["last_restore_at"] = datetime.now().isoformat(timespec="seconds")
            _log("还原完成，建议刷新后台数据", "restore")
            return {"ok": True, "manifest": manifest, "restored_at": _status["last_restore_at"]}
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        _set_error(str(exc))
        raise
    finally:
        _status["running"] = False
        _ops_lock.release()


def restore_from_remote(filename: str) -> dict:
    cfg = load_config()
    _log(f"从 WebDAV 下载 {filename} …", "restore")
    data = download_backup_zip(cfg, filename)
    return restore_from_zip_bytes(data)


def test_webdav(cfg: BackupConfig) -> str:
    client = _client_from_config(cfg)
    return client.test_connection()


def run_backup_job() -> None:
    """供调度器调用；失败只记日志。"""
    try:
        run_backup()
    except Exception as exc:  # noqa: BLE001
        _set_error(f"自动备份失败: {exc}")


def _scheduler_loop() -> None:
    while not _scheduler_stop.is_set():
        try:
            cfg = load_config()
            if cfg.auto_enabled and cfg.webdav_url:
                due = True
                if cfg.last_backup_at:
                    try:
                        last = datetime.fromisoformat(cfg.last_backup_at)
                        due = (datetime.now() - last).total_seconds() >= cfg.interval_hours * 3600
                    except ValueError:
                        due = True
                if due and not _status.get("running"):
                    run_backup_job()
        except Exception as exc:  # noqa: BLE001
            _set_error(f"调度异常: {exc}")
        # 粒度 5 分钟
        _scheduler_stop.wait(300)


def start_scheduler() -> None:
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, name="backup-scheduler", daemon=True)
    _scheduler_thread.start()


def stop_scheduler() -> None:
    _scheduler_stop.set()
