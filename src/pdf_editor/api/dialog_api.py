"""原生文件对话框封装。

WebView 内拖放拿不到真实文件路径（spec 第 12 节），文件导入一律走
webview.create_file_dialog。本模块只做对话框类型选择与结果透传，
不含业务逻辑。
"""

from __future__ import annotations

import logging

import webview

from .envelope import envelope

logger = logging.getLogger(__name__)

# 文件类型过滤器（对话框展示用）
IMAGE_FILTERS = ("图片文件 (*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff;*.webp)", "所有文件 (*.*)")
PDF_FILTERS = ("PDF 文件 (*.pdf)", "所有文件 (*.*)")
WORD_FILTERS = ("Word 文档 (*.docx;*.doc)", "所有文件 (*.*)")


def _first_or_none(result):
    """create_file_dialog 取消时返回 None/空；单选结果归一化为首项或 None。"""
    if not result:
        return None
    if isinstance(result, (list, tuple)):
        return result[0] if result else None
    return result


class DialogApi:
    """依赖注入窗口 getter，测试时可注入 stub 而不依赖真实 webview 窗口。"""

    def __init__(self, window_getter) -> None:
        """window_getter: Callable[[], webview.Window | None]。"""
        self._window_getter = window_getter

    def _window(self):
        window = self._window_getter()
        if window is None:
            raise RuntimeError("窗口尚未创建，无法打开原生对话框")
        return window

    @envelope
    def pick_pdf_file(self) -> str | None:
        """选择单个 PDF 文件，取消时返回 None。"""
        result = self._window().create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False, file_types=PDF_FILTERS
        )
        return _first_or_none(result)

    @envelope
    def pick_docx_file(self) -> str | None:
        """选择单个 Word 文档，取消时返回 None。"""
        result = self._window().create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False, file_types=WORD_FILTERS
        )
        return _first_or_none(result)

    @envelope
    def pick_image_files(self) -> list[str] | None:
        """多选图片，取消时返回 None。"""
        result = self._window().create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True, file_types=IMAGE_FILTERS
        )
        if result is None:
            return None
        return list(result)

    @envelope
    def pick_save_pdf_path(self, default_name: str = "output.pdf") -> str | None:
        """选择 PDF 保存路径（SAVE_DIALOG），取消时返回 None。"""
        result = self._window().create_file_dialog(
            webview.SAVE_DIALOG, save_filename=default_name, file_types=PDF_FILTERS
        )
        return _first_or_none(result)

    @envelope
    def pick_output_directory(self) -> str | None:
        """选择输出目录（FOLDER_DIALOG），取消时返回 None。"""
        result = self._window().create_file_dialog(webview.FOLDER_DIALOG)
        return _first_or_none(result)
