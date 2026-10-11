"""PdfRenderer：渲染适配器（封装 PyMuPDF）。

渲染收敛在本类中，必要时可整体替换为 pdfium2 而不影响其它层
（spec 第 8.3 节）。渲染结果 LRU 缓存，键为 (source_index, dpi)。
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

import pymupdf

from .exceptions import PdfOpenError

# spec 第 5.2 节：DPI 上限 150，防 base64 载荷过大
MAX_DPI = 150
_CACHE_SIZE = 64


class PdfRenderer:
    """PDF 页面渲染器。与 PdfDocumentService 共享同一份文件（只读）。

    PyMuPDF 的 Document 非线程安全：缩略图后台线程与 JS API 线程会并发
    调用本类，所有对文档对象的访问必须经 _render_lock 串行化。
    """

    def __init__(self, dpi_limit: int = MAX_DPI) -> None:
        self._doc: pymupdf.Document | None = None
        self._path: Path | None = None
        self._cache: OrderedDict[tuple[int, int], bytes] = OrderedDict()
        self._dpi_limit = min(dpi_limit, MAX_DPI)
        self._render_lock = threading.Lock()

    def open(self, path: str | Path, password: str | None = None) -> None:
        """打开待渲染的 PDF 文件。"""
        p = Path(path)
        if not p.is_file():
            raise PdfOpenError(f"文件不存在: {p}")
        try:
            doc = pymupdf.open(str(p))
            if doc.needs_pass:
                if password is None or not doc.authenticate(password):
                    doc.close()
                    raise PdfOpenError("PDF 已加密，需要密码")
            _ = doc.page_count
        except PdfOpenError:
            raise
        except Exception as e:
            raise PdfOpenError(f"无法打开 PDF（文件可能损坏）: {e}") from e
        self._path = p
        self._doc = doc
        self.clear_cache()

    @property
    def is_open(self) -> bool:
        return self._doc is not None

    def page_count(self) -> int:
        """返回源文档总页数。"""
        with self._render_lock:
            return self._require_doc().page_count

    def render_page(self, source_index: int, dpi: int = 96) -> bytes:
        """渲染指定源页，返回 PNG 字节流（api 层转 base64 data URL）。"""
        with self._render_lock:
            doc = self._require_doc()
            if not 0 <= source_index < doc.page_count:
                raise PdfOpenError(f"页码越界: {source_index}")
            dpi = max(36, min(int(dpi), self._dpi_limit))
            key = (source_index, dpi)
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached
            page = doc.load_page(source_index)
            zoom = dpi / 72.0
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            png_bytes = pix.tobytes("png")
            self._cache[key] = png_bytes
            while len(self._cache) > _CACHE_SIZE:
                self._cache.popitem(last=False)
            return png_bytes

    def clear_cache(self) -> None:
        """清空渲染缓存（文档关闭或切换时调用）。"""
        self._cache.clear()

    def close(self) -> None:
        """关闭文档并清空缓存。"""
        if self._doc is not None:
            self._doc.close()
        self._doc = None
        self._path = None
        self.clear_cache()

    def _require_doc(self) -> pymupdf.Document:
        if self._doc is None:
            raise PdfOpenError("渲染器尚未打开文档")
        return self._doc
