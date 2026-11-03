"""进程内定时体检调度（单进程；项目默认单 worker）。"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta

from . import maintenance_settings
from .library_check import start_library_scan

CHECK_SECONDS = 60
_log = logging.getLogger("maintenance")
_start_lock = threading.Lock()
_stop = threading.Event()
_started = False


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    # 手工配置可能带时区；统一按本地 naive 时间比较
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def is_due(now: datetime | None = None) -> bool:
    """当前配置是否已到下一次体检时间。"""
    cfg = maintenance_settings.load()
    if not cfg["scan_enabled"]:
        return False
    current = now or datetime.now()
    last = _parse_time(str(cfg.get("last_scan_at") or ""))
    if last is None:
        return True
    try:
        return current >= last + timedelta(hours=int(cfg["scan_interval_hours"]))
    except (TypeError, ValueError):
        return True


def run_if_due(now: datetime | None = None) -> bool:
    """到点则启动后台体检；任务互斥时返回 False，下个周期重试。"""
    if not is_due(now):
        return False
    cfg = maintenance_settings.load()
    try:
        started = start_library_scan(bool(cfg["scan_deep"]))
    except Exception as exc:  # noqa: BLE001
        maintenance_settings.mark_error(str(exc))
        _log.exception("自动体检启动失败: %s", exc)
        return False
    if started:
        maintenance_settings.mark_started(datetime.now().isoformat(timespec="seconds"))
        _log.info("自动体检已启动（deep=%s）", cfg["scan_deep"])
    return started


def _loop() -> None:
    while not _stop.is_set():
        try:
            run_if_due()
        except Exception as exc:  # noqa: BLE001
            _log.exception("自动体检调度异常: %s", exc)
        _stop.wait(CHECK_SECONDS)


def start_scheduler() -> None:
    """启动守护线程；重复调用无副作用。"""
    if os.environ.get("MAINTENANCE_SCHEDULER", "1").strip().lower() in ("0", "false", "off"):
        return
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
        _stop.clear()
    threading.Thread(target=_loop, daemon=True, name="maintenance-scheduler").start()


def stop_scheduler() -> None:
    global _started
    _stop.set()
    with _start_lock:
        _started = False
