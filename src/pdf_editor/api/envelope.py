"""api 层公共设施：统一返回信封与异常 → 错误码转换。

信封约定（spec 第 5.5 节，必须）：
    {"ok": True, "data": ...}
    {"ok": False, "error": {"code": "...", "message": "..."}}
code 与 core 异常类名保持一致；未知异常记日志后转 "InternalError"。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..core.exceptions import PdfEditorError

logger = logging.getLogger(__name__)


def ok(data: Any = None) -> dict:
    """成功信封。"""
    return {"ok": True, "data": data}


def err(code: str, message: str) -> dict:
    """失败信封。"""
    return {"ok": False, "error": {"code": code, "message": message}}


def envelope(fn: Callable[..., Any]) -> Callable[..., dict]:
    """装饰 JsApi 方法：捕获 PdfEditorError 转错误信封，未知异常转 InternalError。"""

    def wrapper(*args: Any, **kwargs: Any) -> dict:
        try:
            return ok(fn(*args, **kwargs))
        except PdfEditorError as e:
            code = type(e).__name__
            logger.info("业务错误 %s: %s", code, e)
            return err(code, str(e))
        except Exception as e:  # noqa: BLE001 — 桥接边界必须兜底
            logger.exception("未预期异常")
            return err("InternalError", f"{type(e).__name__}: {e}")

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper
