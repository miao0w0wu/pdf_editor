"""转换器桥接方法：图片/Word 转 PDF。

长任务规则（spec 第 6 节）：转换在线程中执行，立即返回 task_id；
进度与结果通过事件推送（conversion_progress / task_done），
禁止在 JsApi 方法内做耗时操作后同步返回。
任务必须支持取消标记。
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from ..core.exceptions import PdfOpenError
from ..core.image_converter import ImageToPdfConverter
from ..core.pdf_document import PdfDocumentService
from ..core.scan_converter import ScanConverter
from ..core.word_converter import WordToPdfConverter
from .document_api import png_bytes_to_data_url
from .envelope import envelope
from .events import EventPusher

logger = logging.getLogger(__name__)


class ConverterApi:
    """转换任务管理：线程执行 + 事件推送 + 取消标记。"""

    def __init__(
        self,
        pusher: EventPusher,
        image_converter: ImageToPdfConverter | None = None,
        word_converter: WordToPdfConverter | None = None,
        scan_converter: ScanConverter | None = None,
        service: PdfDocumentService | None = None,
    ) -> None:
        self._pusher = pusher
        self._image_converter = image_converter or ImageToPdfConverter()
        self._word_converter = word_converter or WordToPdfConverter()
        self._scan_converter = scan_converter or ScanConverter()
        self._service = service
        self._tasks: dict[str, dict] = {}
        self._cancel_flags: dict[str, threading.Event] = {}
        self._next_task_id = 0
        self._id_lock = threading.Lock()

    # ---------- 任务管理 ----------

    def cancel_task(self, task_id: str) -> dict:
        """置取消标记；转换循环检查点处生效（图片转换逐张检查）。"""
        flag = self._cancel_flags.get(task_id)
        if flag is not None:
            flag.set()
        return {"cancelled": flag is not None}

    def _new_task_id(self) -> str:
        with self._id_lock:
            self._next_task_id += 1
            return f"task-{self._next_task_id}"

    def _run_in_thread(self, task_id: str, kind: str, work) -> None:
        """在线程中执行 work(cancel_flag)，推送 task_done / task_error 事件。"""

        def runner() -> None:
            try:
                result = work()
                self._pusher.push(
                    "task_done", {"task_id": task_id, "kind": kind, "result": str(result)}
                )
            except Exception as e:  # noqa: BLE001 — 线程边界必须兜底
                code = type(e).__name__
                logger.info("转换任务失败 %s: %s", code, e)
                cancelled = isinstance(e, _TaskCancelled)
                if cancelled:
                    code = "TaskCancelled"
                self._pusher.push(
                    "task_error",
                    {"task_id": task_id, "kind": kind, "code": code, "message": str(e)},
                )

        threading.Thread(target=runner, name=f"convert-{task_id}", daemon=True).start()

    # ---------- 图片转 PDF ----------

    @envelope
    def convert_images_to_pdf(
        self, image_paths: list[str], target: str, page_size: str = "auto", margin_mm: float = 0
    ) -> dict:
        """多选图片 → PDF。立即返回 task_id，进度/结果走事件。"""
        if not image_paths:
            raise ValueError("未提供图片路径")
        task_id = self._new_task_id()
        cancel = threading.Event()
        self._cancel_flags[task_id] = cancel
        paths = [Path(p) for p in image_paths]
        target_path = Path(target)
        kind = "image_to_pdf"

        def on_progress(done: int, total: int) -> None:
            self._pusher.push(
                "conversion_progress",
                {"task_id": task_id, "stage": f"{done}/{total}", "done": done, "total": total},
            )
            if cancel.is_set():
                raise _TaskCancelled()

        def work() -> Path:
            try:
                return self._image_converter.convert(
                    paths,
                    target_path,
                    page_size=page_size,
                    margin_mm=margin_mm,
                    progress_cb=on_progress,
                )
            finally:
                self._cancel_flags.pop(task_id, None)

        self._run_in_thread(task_id, kind, work)
        return {"task_id": task_id}

    # ---------- Word 转 PDF ----------

    @envelope
    def convert_word_to_pdf(self, docx_path: str, out_dir: str, timeout_s: int = 120) -> dict:
        """单选 docx → PDF（soffice 子进程）。立即返回 task_id。"""
        task_id = self._new_task_id()
        cancel = threading.Event()
        self._cancel_flags[task_id] = cancel
        kind = "word_to_pdf"

        def on_progress(stage: str) -> None:
            self._pusher.push("conversion_progress", {"task_id": task_id, "stage": stage})

        def work() -> Path:
            try:
                return self._word_converter.convert(
                    Path(docx_path),
                    Path(out_dir),
                    timeout_s=timeout_s,
                    progress_cb=on_progress,
                )
            finally:
                self._cancel_flags.pop(task_id, None)

        self._run_in_thread(task_id, kind, work)
        return {"task_id": task_id}

    # ---------- 页面转扫描件 ----------

    @envelope
    def convert_pages_to_scan(
        self,
        page_ids: list[int],
        target: str,
        dpi: int = 200,
        threshold: int = 32,
        tone: str = "bw",
    ) -> dict:
        """把当前文档的指定页面转为扫描件，写出新 PDF。

        立即返回 task_id，进度/结果走事件（conversion_progress / task_done）。
        tone："bw" 白底黑字（默认），"color" 保留原色的彩色扫描件。
        page_ids 为当前文档的 page_id（按逻辑顺序），依据打开时的文档状态
        解析出源页下标与分割裁剪框后交给转换器，不感知后续编辑操作。
        """
        if not isinstance(page_ids, list) or not page_ids:
            raise ValueError("page_ids 必须是非空列表")
        if self._service is None or not self._service.is_open:
            raise PdfOpenError("尚未打开文档")
        if not isinstance(target, str) or not target.strip():
            raise ValueError("缺少输出路径")

        source_path = self._service.source_path
        password = self._service.source_password
        # 逻辑顺序 = 传入 page_ids 的顺序（允许子集/自定义顺序）
        pages = [self._service.page_source_info(int(pid)) for pid in page_ids]

        task_id = self._new_task_id()
        cancel = threading.Event()
        self._cancel_flags[task_id] = cancel
        kind = "pages_to_scan"

        def on_progress(done: int, total: int) -> None:
            self._pusher.push(
                "conversion_progress",
                {"task_id": task_id, "stage": f"{done}/{total}", "done": done, "total": total},
            )
            if cancel.is_set():
                raise _TaskCancelled()

        def work() -> Path:
            try:
                return self._scan_converter.convert(
                    source_path,
                    pages,
                    Path(target),
                    dpi=int(dpi),
                    threshold=int(threshold),
                    password=password,
                    progress_cb=on_progress,
                    tone=str(tone),
                )
            finally:
                self._cancel_flags.pop(task_id, None)

        self._run_in_thread(task_id, kind, work)
        return {"task_id": task_id}

    # ---------- 缩略图批量生成（P2 使用，随 api 层一并交付） ----------

    @envelope
    def generate_thumbnails(self, dpi: int = 72) -> dict:
        """逐页渲染缩略图并以 thumbnails_ready 事件推送（每页一个事件，避免大载荷）。"""
        renderer = self._thumbs_renderer
        count = renderer.page_count()
        task_id = self._new_task_id()
        threading.Thread(
            target=self._thumbs_worker,
            args=(task_id, renderer, int(dpi), count),
            name="thumbnails",
            daemon=True,
        ).start()
        return {"task_id": task_id, "page_count": count}

    def _thumbs_worker(self, task_id: str, renderer, dpi: int, count: int) -> None:
        for idx in range(count):
            try:
                png = renderer.render_page(idx, dpi)
                self._pusher.push(
                    "thumbnails_ready",
                    {"task_id": task_id, "index": idx, "data_url": png_bytes_to_data_url(png)},
                )
            except Exception as e:  # noqa: BLE001 — 单页失败不阻断其它页
                logger.warning("缩略图渲染失败（第 %d 页）: %s", idx, e)
                self._pusher.push(
                    "thumbnails_ready", {"task_id": task_id, "index": idx, "data_url": None}
                )

    def bind_thumbnails_renderer(self, renderer) -> None:
        """注入渲染器（build_api 时绑定，避免与 DocumentApi 的实例耦合）。"""
        self._thumbs_renderer = renderer

    _thumbs_renderer = None  # 类级默认，未绑定时 generate_thumbnails 会失败

    @envelope
    def ping(self) -> str:
        return "pong"


class _TaskCancelled(Exception):
    """取消标记触发时在检查点抛出，转成 TaskCancelled 事件。"""
