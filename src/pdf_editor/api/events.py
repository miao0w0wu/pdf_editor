"""后端 → 前端事件推送封装。

线程安全：evaluate_js 的调用方可能是任意工作线程（转换任务线程、
缩略图生成线程），这里用一把全局锁串行化，避免并发 evaluate_js 在
部分 WebView 后端上产生交错脚本。

窗口未就绪 / 已关闭时 evaluate_js 可能抛异常，按 spec 第 6 节要求
捕获后记日志，不向上抛。
"""

from __future__ import annotations

import json
import logging
import threading

logger = logging.getLogger(__name__)

_evaluate_lock = threading.Lock()


class EventPusher:
    """把事件 payload 推送到前端 window.__backend 分发器。"""

    def __init__(self) -> None:
        self._window: object | None = None  # webview.Window，延迟注入避免 import webview

    def bind_window(self, window: object) -> None:
        """注入 pywebview 窗口对象（main.py 创建窗口后调用）。"""
        self._window = window

    def push(self, event_type: str, payload: dict) -> None:
        """推送事件到前端；窗口未就绪时静默丢弃（记日志）。"""
        window = self._window
        if window is None:
            logger.debug("窗口尚未创建，丢弃事件 %s", event_type)
            return
        payload_json = json.dumps({"type": event_type, "payload": payload})
        script = f"window.__backend && window.__backend.dispatch({payload_json})"
        try:
            with _evaluate_lock:
                window.evaluate_js(script)  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001 — 必须容忍窗口未就绪/已关闭
            logger.warning("事件推送失败（%s）: %s", event_type, e)
