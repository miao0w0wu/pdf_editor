"""文档相关桥接方法：open/save/delete/reorder/split/render_page。

只做参数校验、序列化与异常转换，禁止业务逻辑（spec 分层规则 2）。
渲染结果转 base64 data URL 交给前端 <img>。
"""

from __future__ import annotations

import base64
import binascii
from pathlib import Path

from ..core.pdf_document import PdfDocumentService
from ..core.pdf_renderer import PdfRenderer
from .envelope import envelope


class DocumentApi:
    """依赖注入 core 服务实例，便于 pytest 直接实例化测试。"""

    def __init__(self, service: PdfDocumentService, renderer: PdfRenderer) -> None:
        self._service = service
        self._renderer = renderer
        self._source_path: Path | None = None

    # ---------- 文档生命周期 ----------

    @envelope
    def open_document(self, path: str, password: str | None = None) -> dict:
        """打开 PDF：文档服务与渲染器共享同一文件，返回 DocumentState 镜像。"""
        state = self._service.open(path, password=password)
        self._renderer.close()
        self._renderer.open(path, password=password)
        self._source_path = Path(path).expanduser().resolve()
        return state.to_dict()

    @envelope
    def close_document(self) -> None:
        """关闭文档并清空渲染缓存。"""
        self._service.close()
        self._renderer.close()
        self._source_path = None

    @envelope
    def is_open(self) -> bool:
        return self._service.is_open

    @envelope
    def get_state(self) -> dict:
        return self._service.state.to_dict()

    @envelope
    def get_source_path(self) -> str | None:
        """当前文档的源文件路径（渲染共享用；未打开返回 None）。"""
        return str(self._source_path) if self._source_path else None

    # ---------- 保存 / 编辑 ----------

    @envelope
    def save_document(self, target: str) -> None:
        self._service.save(target)

    @envelope
    def save_document_as(self, target: str, page_ids: list[int]) -> None:
        """按给定 page_id 顺序（可为子集）另存。"""
        self._service.save_page_range(target, page_ids)

    @envelope
    def delete_pages(self, page_ids: list[int]) -> dict:
        if not isinstance(page_ids, list):
            raise ValueError("page_ids 必须是列表")
        return self._service.delete_pages([int(p) for p in page_ids]).to_dict()

    @envelope
    def reorder_pages(self, new_order: list[int]) -> dict:
        if not isinstance(new_order, list):
            raise ValueError("new_order 必须是列表")
        return self._service.reorder_pages([int(p) for p in new_order]).to_dict()

    @envelope
    def split_page(self, page_id: int, mode: str, ratios: list[float]) -> dict:
        if mode not in ("horizontal", "vertical"):
            raise ValueError(f"不支持的分割模式: {mode}")
        return self._service.split_page(int(page_id), mode, [float(r) for r in ratios]).to_dict()

    @envelope
    def split_at(self, page_id: int, box: list[float]) -> dict:
        if len(box) != 4:
            raise ValueError("box 必须是 [x0, y0, x1, y1]")
        return self._service.split_at(int(page_id), tuple(float(v) for v in box)).to_dict()

    # ---------- 渲染 ----------

    @envelope
    def render_page(self, source_index: int, dpi: int = 96) -> str:
        """渲染指定源页，返回 PNG 的 data URL（image/png;base64）。"""
        png = self._renderer.render_page(int(source_index), int(dpi))
        return "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    @envelope
    def page_count(self) -> int:
        return self._renderer.page_count()


def png_bytes_to_data_url(png: bytes) -> str:
    """PNG 字节流转 data URL（供其它 api 模块复用，如缩略图事件）。"""
    if not png.startswith(b"\x89PNG"):
        raise binascii.Error("not a png")
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
