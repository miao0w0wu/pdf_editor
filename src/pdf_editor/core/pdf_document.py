"""文档级读写门面，所有页面操作的唯一入口。

实现"非破坏性编辑"模式：编辑操作只改内存中的 DocumentState，
save() 时按逻辑顺序一次性构建 PdfWriter 并写出。

分割页的实现方式：把源页平移合并到空白子页上（pypdf 的
add_blank_page + merge_transformed_page），使目标区域落入子页。
page_id 语义（spec 第 4 节，本设计最容易出错的一点）：
- page_id 在打开文档时分配，不随重排改变；
- 分割后原子页失效，子页获得全新 page_id；
- 前端选择状态必须锚定在 page_id 上。

路径安全：open 与 save 的路径参数统一经 utils.paths 的
resolve_input_path 与 safe_output_path 规范化（校验非空与非法字符、
折叠相对路径分量、拒绝目录目标），写出时不再二次拼接路径。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Literal

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.errors import PyPdfError
from pypdf.generic import NameObject, RectangleObject

from ..models.page_item import DocumentState, PageItem
from ..utils.paths import resolve_input_path, safe_output_path
from .exceptions import PdfOpenError, PdfWriteError


class _SplitSpec:
    """一次分割产生的子页裁剪信息（归一化坐标，原点在左下角）。

    mode="horizontal"：y 方向 [start, end]，x 全宽；
    mode="vertical"：x 方向 [start, end]，y 全宽或 [y_start, y_end]（split_at 用）。
    """

    def __init__(
        self,
        mode: Literal["horizontal", "vertical"],
        start: float,
        end: float,
        y_start: float = 0.0,
        y_end: float = 1.0,
    ) -> None:
        self.mode = mode
        self.start = start
        self.end = end
        self.y_start = y_start
        self.y_end = y_end

    def append_to_writer(self, writer: PdfWriter, reader: PdfReader, source_index: int) -> None:
        """把本子页作为裁剪副本写入 writer，不修改原 reader。"""
        src = reader.pages[source_index]
        box = src.mediabox
        page_w = float(box.width)
        page_h = float(box.height)

        if self.mode == "horizontal":
            x0, x1 = 0.0, page_w
            y0 = self.start * page_h
            y1 = self.end * page_h
        else:
            x0 = self.start * page_w
            x1 = self.end * page_w
            y0 = self.y_start * page_h
            y1 = self.y_end * page_h

        sub_w = x1 - x0
        sub_h = y1 - y0
        page = writer.add_blank_page(width=round(sub_w), height=round(sub_h))
        page.merge_transformed_page(src, Transformation().translate(tx=-x0, ty=-y0))
        page.mediabox = RectangleObject((0, 0, sub_w, sub_h))

        # 同步其它边界框，避免某些阅读器仍按原始框显示
        rect = RectangleObject((0, 0, sub_w, sub_h))
        for attr in ("CropBox", "BleedBox", "TrimBox", "ArtBox"):
            page[NameObject(f"/{attr}")] = rect

        # 继承源页旋转属性（平移合成后旋转语义保持）
        rotate = src.get("/Rotate")
        if rotate:
            page[NameObject("/Rotate")] = rotate


class PdfDocumentService:
    """打开/保存/删除/重排/分割。线程安全（内部锁串行化写操作）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reader: PdfReader | None = None
        self._source_path: Path | None = None
        self._password: str | None = None
        self._state: DocumentState | None = None
        self._splits: dict[int, _SplitSpec] = {}  # page_id -> 分割信息

    # ---------- 打开 / 状态 ----------

    def open(self, path: str | Path, password: str | None = None) -> DocumentState:
        """打开 PDF 文件，建立 DocumentState（每页分配稳定 page_id）。"""
        p = resolve_input_path(path)
        if not p.is_file():
            raise PdfOpenError(f"文件不存在: {p}")
        try:
            reader = PdfReader(str(p))
            if reader.is_encrypted:
                if password is None:
                    raise PdfOpenError("PDF 已加密，需要密码")
                if not reader.decrypt(password):
                    raise PdfOpenError("密码错误或无法解密")
            _ = len(reader.pages)  # 触发解析以尽早发现损坏文件
        except PdfOpenError:
            raise
        except Exception as e:
            raise PdfOpenError(f"无法打开 PDF（文件可能损坏）: {e}") from e

        with self._lock:
            self._reader = reader
            self._source_path = p
            self._password = password
            self._splits = {}
            pages = [
                PageItem(page_id=i, source_index=i, label=str(i + 1))
                for i in range(len(reader.pages))
            ]
            self._state = DocumentState(pages)
            return self._state

    @property
    def state(self) -> DocumentState:
        if self._state is None:
            raise PdfOpenError("尚未打开文档")
        return self._state

    @property
    def is_open(self) -> bool:
        return self._state is not None

    @property
    def source_path(self) -> Path:
        """当前打开的源文件路径（供转换器独立打开同一文件）。"""
        if self._source_path is None:
            raise PdfOpenError("尚未打开文档")
        return self._source_path

    @property
    def source_password(self) -> str | None:
        """打开源文件用的密码（仅驻留内存，供转换器重新打开时使用）。"""
        return self._password

    def page_source_info(
        self, page_id: int
    ) -> tuple[int, tuple[float, float, float, float] | None]:
        """返回 (source_index, 归一化裁剪框)。

        裁剪框为 (x0, y0, x1, y1)，值域 0~1，原点在左下角（与 mediabox
        同一坐标系）；页面未经分割时返回 None。供转换器只渲染该页的
        可见区域（分割子页与原页同源）。
        """
        with self._lock:
            item = self._find_page_locked(page_id)
            spec = self._splits.get(page_id)
            if spec is None:
                return item.source_index, None
            if spec.mode == "horizontal":
                return item.source_index, (0.0, spec.start, 1.0, spec.end)
            return item.source_index, (spec.start, spec.y_start, spec.end, spec.y_end)

    def close(self) -> None:
        """关闭文档，丢弃内存状态与分割缓存。"""
        with self._lock:
            self._reader = None
            self._source_path = None
            self._password = None
            self._state = None
            self._splits = {}

    # ---------- 保存 ----------

    def save(self, target: str | Path) -> None:
        """按当前 DocumentState 逻辑顺序写出文件。"""
        self.save_page_range(target, self.state.page_ids())

    def save_page_range(self, target: str | Path, page_ids: list[int]) -> None:
        """按给定 page_id 顺序（可为子集）写出文件（路径经 safe_output_path 校验）。"""
        out = safe_output_path(target)
        with self._lock:
            self._save_locked(out, page_ids)

    def _save_locked(self, target: Path, page_ids: list[int]) -> None:
        if self._reader is None or self._state is None:
            raise PdfOpenError("尚未打开文档")
        if not page_ids:
            raise PdfWriteError("页面列表为空，无法保存")

        writer = PdfWriter()
        for pid in page_ids:
            try:
                item = self._state.get_page(pid)
            except KeyError as e:
                raise PdfWriteError(f"page_id {pid} 不存在") from e
            spec = self._splits.get(pid)
            if spec is None:
                writer.add_page(self._reader.pages[item.source_index])
            else:
                spec.append_to_writer(writer, self._reader, item.source_index)

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # target 已由 safe_output_path 解析为绝对路径并拒绝目录；
            # 交给 PdfWriter.write 直接写出，不在本层再做路径拼接。
            writer.write(str(target))
        except OSError as e:
            raise PdfWriteError(f"写出文件失败: {e}") from e
        except PyPdfError as e:  # pypdf 自身的写出异常
            raise PdfWriteError(f"写出文件失败: {e}") from e

    # ---------- 删除 / 重排 ----------

    def delete_pages(self, page_ids: list[int]) -> DocumentState:
        """删除指定 page_id 的页面，返回新的 DocumentState。"""
        with self._lock:
            if self._state is None:
                raise PdfOpenError("尚未打开文档")
            ids = set(page_ids)
            unknown = ids - set(self._state.page_ids())
            if unknown:
                raise PdfWriteError(f"page_id 不存在: {sorted(unknown)}")
            remaining = [p for p in self._state.pages if p.page_id not in ids]
            if not remaining:
                raise PdfWriteError("不能删除所有页面")
            for pid in ids:
                self._splits.pop(pid, None)
            self._state = DocumentState(remaining)
            return self._state

    def reorder_pages(self, new_order: list[int]) -> DocumentState:
        """按新的 page_id 顺序重排页面，以后端返回的 DocumentState 为准。"""
        with self._lock:
            if self._state is None:
                raise PdfOpenError("尚未打开文档")
            current_ids = self._state.page_ids()
            if sorted(new_order) != sorted(current_ids):
                raise PdfWriteError(
                    "new_order 必须是现有 page_id 的完整排列，"
                    f"期望 {sorted(current_ids)}，收到 {sorted(new_order)}"
                )
            by_id = {p.page_id: p for p in self._state.pages}
            self._state = DocumentState([by_id[pid] for pid in new_order])
            return self._state

    # ---------- 分割 ----------

    def split_page(
        self,
        page_id: int,
        mode: Literal["horizontal", "vertical"],
        ratios: list[float],
    ) -> DocumentState:
        """按比例把一页分割为多个子页。

        horizontal: 沿水平方向切成上下几块；vertical: 沿垂直方向切成左右几块。
        ratios 为各段占比（如 [0.5, 0.5]），内部归一化，至少 2 段。
        分割后原子页 page_id 失效，子页获得全新 page_id（标签后缀 a/b/c...）。
        """
        with self._lock:
            if self._state is None:
                raise PdfOpenError("尚未打开文档")
            item = self._find_page_locked(page_id)
            if len(ratios) < 2:
                raise PdfWriteError("ratios 至少需要 2 段")
            total = sum(ratios)
            if total <= 0 or any(r <= 0 for r in ratios):
                raise PdfWriteError(f"非法比例: {ratios}")
            fracs = [r / total for r in ratios]

            sub_items: list[PageItem] = []
            offset = 0.0
            next_id = self._next_page_id_locked()
            for i, frac in enumerate(fracs):
                self._splits[next_id] = _SplitSpec(mode=mode, start=offset, end=offset + frac)
                sub_items.append(
                    PageItem(
                        page_id=next_id,
                        source_index=item.source_index,
                        label=f"{item.label}{'abcde'[i]}",
                    )
                )
                offset += frac
                next_id += 1

            self._replace_page_locked(item, sub_items)
            return self._state

    def split_at(self, page_id: int, box: tuple[float, float, float, float]) -> DocumentState:
        """把页面按归一化裁剪框 (x0, y0, x1, y1)（值域 0~1）切成框内 + 框外两页。

        框外部分取 y 方向的补集区域（x 相同），覆盖"上半/下半"的常见场景。
        """
        x0, y0, x1, y1 = box
        if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
            raise PdfWriteError(f"非法裁剪框: {box}")
        with self._lock:
            if self._state is None:
                raise PdfOpenError("尚未打开文档")
            item = self._find_page_locked(page_id)

            next_id = self._next_page_id_locked()
            inner_id = next_id
            self._splits[inner_id] = _SplitSpec(
                mode="vertical", start=x0, end=x1, y_start=y0, y_end=y1
            )
            inner = PageItem(
                page_id=inner_id, source_index=item.source_index, label=f"{item.label}a"
            )

            outer_id = next_id + 1
            self._splits[outer_id] = _SplitSpec(
                mode="vertical", start=x0, end=x1, y_start=y1, y_end=1.0
            )
            outer = PageItem(
                page_id=outer_id, source_index=item.source_index, label=f"{item.label}b"
            )

            self._replace_page_locked(item, [inner, outer])
            return self._state

    # ---------- 内部方法 ----------

    def _find_page_locked(self, page_id: int) -> PageItem:
        assert self._state is not None
        try:
            return self._state.get_page(page_id)
        except KeyError as e:
            raise PdfWriteError(f"page_id {page_id} 不存在") from e

    def _replace_page_locked(self, old: PageItem, new_pages: list[PageItem]) -> None:
        """把 old 位置替换为 new_pages（原地插入）。"""
        assert self._state is not None
        self._splits.pop(old.page_id, None)
        idx = self._state.pages.index(old)
        self._state.pages[idx : idx + 1] = new_pages

    def _next_page_id_locked(self) -> int:
        assert self._state is not None
        return max((p.page_id for p in self._state.pages), default=-1) + 1
