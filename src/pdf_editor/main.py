"""应用入口：启动静态服务器(prod)/连 dev server(dev)，创建 webview 窗口。

用法：
    python -m pdf_editor          # 生产模式：托管 frontend/dist
    python -m pdf_editor --dev    # 开发模式：加载 Vite dev server (5173)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import webview

from .api import build_api

logger = logging.getLogger("pdf_editor")

DEV_URL = "http://localhost:5173"


def _frontend_dist() -> Path:
    """定位 frontend/dist：源码布局优先，其次 PyInstaller 打包资源。"""
    here = Path(__file__).resolve()
    # src/pdf_editor/main.py -> ../../frontend/dist
    dev_dist = here.parent.parent.parent / "frontend" / "dist"
    if dev_dist.is_dir():
        return dev_dist
    # PyInstaller onedir：sys._MEIPASS/_internal 或 exe 同级
    import sys as _sys

    meipass = getattr(_sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "frontend" / "dist"
        if bundled.is_dir():
            return bundled
    raise FileNotFoundError(
        f"未找到前端构建产物 frontend/dist（尝试过 {dev_dist}）。"
        "请先在 frontend/ 执行 npm run build"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdf_editor", description="PDF 编辑器")
    parser.add_argument("--dev", action="store_true", help="加载 Vite dev server (5173)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.dev else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    api = build_api()
    if args.dev:
        logger.info("开发模式：%s", DEV_URL)
        url = DEV_URL
    else:
        from .utils.static_server import serve_directory

        url, _server = serve_directory(_frontend_dist())

    window = webview.create_window(
        title="PDF 编辑器",
        url=url,
        js_api=api,
        width=1280,
        height=800,
        min_size=(960, 600),
    )
    api.events.bind_window(window)

    try:
        webview.start()
    finally:
        logger.info("窗口已退出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
