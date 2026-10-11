"""stdlib http.server 托管 frontend/dist（生产模式）。

单页面应用、无路由，不需要 history fallback（spec 第 10 节）。
绑定 127.0.0.1 随机端口，返回实际端口号供 webview 加载。
"""

from __future__ import annotations

import http.server
import logging
import socket
import threading
from functools import partial
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class _SpaHandler(http.server.SimpleHTTPRequestHandler):
    """静态文件 handler：关掉访问日志噪音，禁用缓存便于开发调试。"""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 — 基类签名
        logger.debug("static: %s", format % args)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve_directory(directory: Path) -> tuple[str, object]:
    """在 127.0.0.1 随机端口托管 directory，返回 (url, server)。

    server 在守护线程中运行；进程退出时随之结束。
    """
    if not directory.is_dir():
        raise FileNotFoundError(f"前端产物目录不存在: {directory}（先执行 npm run build）")

    handler = partial(_SpaHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port: int = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="static-server")
    thread.start()
    url = f"http://127.0.0.1:{port}"
    logger.info("静态服务器已启动: %s", url)
    return url, server


def stop_server(server: object) -> None:
    """停止静态服务器（容忍重复调用）。"""
    try:
        server.shutdown()  # type: ignore[attr-defined]
        server.server_close()  # type: ignore[attr-defined]
    except Exception as e:  # noqa: BLE001 — 退出路径不允许抛异常
        logger.debug("停止静态服务器失败（忽略）: %s", e)


def free_port() -> int:
    """获取一个空闲端口（保留工具，dev 模式探测 Vite 端口时可能用到）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
