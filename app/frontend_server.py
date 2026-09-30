"""前端入口端口（默认 :7311）：与 API 同一 ASGI 应用，仅多监听一个端口。

不再单独跑 ThreadingHTTPServer / HTTP 反代：静态资源与 /api 同源，
Cookie 会话天然可用，也省掉一套请求处理栈的内存。
"""
from __future__ import annotations

import threading

import uvicorn


def start_in_thread(
    *,
    app,
    host: str,
    port: int,
    api_host: str | None = None,  # 兼容旧签名，已不使用
    api_port: int | None = None,
) -> threading.Thread:
    """在守护线程里用 uvicorn 托管同一 app（前端端口）。"""
    config = uvicorn.Config(app, host=host, port=port, log_config=None, access_log=False)
    server = uvicorn.Server(config)

    def _run() -> None:
        # 避免 uvicorn 捕获 SIGINT 与主线程抢信号
        server.run()

    t = threading.Thread(target=_run, daemon=True, name="frontend-http")
    t.start()
    return t
