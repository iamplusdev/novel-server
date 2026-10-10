"""后台长任务互斥：导入 / 体检 / 批量刮削同一时刻只允许一个在跑。

三个任务都会写库或长时间占用资源，互相并发没有收益且易触发 SQLite 写锁，
故统一在此判定；各 start_* 入口在启动前调用 other_task_running 拒绝并发。
"""
from __future__ import annotations


def running_tasks() -> dict[str, bool]:
    """当前各长任务的运行状态（键：import / scan / scrape）。"""
    from .batch_scrape import get_batch_status
    from .importer import get_import_status
    from .library_check import get_scan_status

    return {
        "import": bool(get_import_status().get("running")),
        "scan": bool(get_scan_status().get("running")),
        "scrape": bool(get_batch_status().get("running")),
    }


def other_task_running(which: str) -> str:
    """返回正在运行的其它任务键（无则空串）。which 取值 import|scan|scrape。"""
    for key, running in running_tasks().items():
        if key != which and running:
            return key
    return ""


def busy_status() -> dict:
    """供前端统一查询：各任务是否在跑 + 是否忙碌。"""
    tasks = running_tasks()
    return {**tasks, "busy": any(tasks.values())}
