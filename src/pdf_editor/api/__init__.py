"""api 包：JsApi 根对象组装。

build_api() 返回的对象通过 webview.create_window(js_api=...) 注入；
前端以 window.pywebview.api.<method>() 调用（Promise）。
本层只做参数校验、序列化与异常→错误码转换（spec 分层规则 2）。
"""

from __future__ import annotations

import webview

from ..core.image_converter import ImageToPdfConverter as _ImageConverter
from ..core.pdf_document import PdfDocumentService
from ..core.pdf_renderer import PdfRenderer
from ..core.scan_converter import ScanConverter as _ScanConverter
from ..core.word_converter import WordToPdfConverter as _WordConverter
from .converter_api import ConverterApi
from .dialog_api import DialogApi
from .document_api import DocumentApi
from .events import EventPusher


class JsApi:
    """暴露给前端的根对象：子 API 以属性方式组合，前端调用路径形如
    window.pywebview.api.document.open_document(...)。"""

    def __init__(
        self,
        document: DocumentApi,
        converter: ConverterApi,
        dialog: DialogApi,
        pusher: EventPusher,
    ) -> None:
        self.document = document
        self.converter = converter
        self.dialog = dialog
        self.events = pusher

    # ---------- 基础 ----------

    def ping(self) -> dict:
        """连通性检查（P1 验收用）。"""
        return {"ok": True, "data": "pong"}

    def api_version(self) -> dict:
        return {"ok": True, "data": "0.1.0"}


def build_api(
    service: PdfDocumentService | None = None,
    renderer: PdfRenderer | None = None,
    window_getter=None,
    image_converter: _ImageConverter | None = None,
    word_converter: _WordConverter | None = None,
    scan_converter: _ScanConverter | None = None,
) -> JsApi:
    """组装 JsApi 根对象。

    core 服务实例可注入（pytest 直接实例化，不启动窗口）；
    window_getter 缺省时返回当前 webview 窗口（首窗口）。
    """
    service = service or PdfDocumentService()
    renderer = renderer or PdfRenderer()
    pusher = EventPusher()
    if window_getter is None:

        def window_getter():  # noqa: ANN001 — 简单闭包
            return webview.windows[0] if webview.windows else None

    document = DocumentApi(service, renderer)
    converter = ConverterApi(
        pusher,
        image_converter=image_converter,
        word_converter=word_converter,
        scan_converter=scan_converter,
        service=service,
    )
    converter.bind_thumbnails_renderer(renderer)
    dialog = DialogApi(window_getter)
    return JsApi(document, converter, dialog, pusher)


__all__ = ["JsApi", "build_api", "EventPusher"]
