"""图片转 PDF 转换器（Pillow 多页合成）。

实现说明：pypdf 6.x 已移除 add_image/ ImageReader API，
改用 Pillow 原生的多页 PDF 保存能力（save_all + append_images）。
A4 模式下先把图片等比缩放粘贴到白色 A4 画布再合成。

路径安全约定：所有来自前端的路径（输入图片、输出目标）都先经
utils.paths 的规范化函数处理，本模块不自行拼接或展开路径字符串。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from PIL import Image

from ..utils import paths as path_guard
from .exceptions import ConversionError, UnsupportedImageError

# Pillow 支持且允许合入 PDF 的格式
SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

# A4 横向/纵向尺寸（pt，Pillow PDF 页面单位）
_A4_PT = (595.28, 841.89)
# PDF 页面单位 1pt；图片按 72dpi 映射，1px = 1pt
_DPI = 72


class ImageToPdfConverter:
    """把一组图片按顺序合成一个多页 PDF。"""

    def convert(
        self,
        image_paths: list[Path],
        target: Path,
        page_size: Literal["auto", "a4"] = "auto",
        margin_mm: float = 0,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> Path:
        """把多张图片按传入顺序合成为一个 PDF（一张图一页）。

        page_size="auto" 时页面尺寸 = 图片像素尺寸（72dpi 换算，1px=1pt），
        margin_mm 作为页边距向外扩展；
        page_size="a4" 时统一 A4 页面，图片等比缩放居中，margin_mm 留白。
        返回写出路径。
        """
        if not image_paths:
            raise UnsupportedImageError("未提供任何图片")
        out = path_guard.safe_output_path(target)
        if page_size not in ("auto", "a4"):
            raise UnsupportedImageError(f"不支持的页面尺寸模式: {page_size}")
        if margin_mm < 0:
            raise UnsupportedImageError(f"边距不能为负: {margin_mm}")

        pages: list[Image.Image] = []
        total = len(image_paths)
        try:
            for i, raw_path in enumerate(image_paths):
                img_path = path_guard.resolve_input_path(raw_path)
                img = self._open_image(img_path)
                try:
                    pages.append(self._compose_page(img, page_size, margin_mm))
                finally:
                    img.close()
                if progress_cb is not None:
                    progress_cb(i + 1, total)

            first, rest = pages[0], pages[1:]
            try:
                first.save(
                    out,
                    format="PDF",
                    save_all=True,
                    append_images=rest,
                    resolution=_DPI,
                )
            except OSError as e:
                raise ConversionError(f"写出 PDF 失败: {e}") from e
        finally:
            for page in pages:
                page.close()

        return out

    # ---------- 内部 ----------

    def _open_image(self, path: Path) -> Image.Image:
        if not path.is_file():
            raise UnsupportedImageError(f"图片不存在: {path}")
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise UnsupportedImageError(f"不支持的图片格式: {path.suffix}")
        try:
            img = Image.open(path)
            img.load()
        except Exception as e:
            raise UnsupportedImageError(f"图片无法解码: {path} ({e})") from e
        return img

    def _compose_page(
        self,
        img: Image.Image,
        page_size: Literal["auto", "a4"],
        margin_mm: float,
    ) -> Image.Image:
        """把单张图合成为一页画布（RGB，RGBA/调色板图统一转换）。

        返回的新画布由调用方负责关闭；传入 img 不被修改。
        """
        rgb = img.convert("RGB")
        margin_px = max(0, round(margin_mm / 25.4 * _DPI))

        if page_size == "auto":
            # auto：画布 = 图片尺寸 + 边距（1px = 1pt @72dpi）
            canvas = Image.new(
                "RGB",
                (rgb.width + 2 * margin_px, rgb.height + 2 * margin_px),
                color="white",
            )
            canvas.paste(rgb, (margin_px, margin_px))
        else:
            # a4：画布固定 A4（pt → px @72dpi），图片等比缩放居中
            page_w, page_h = round(_A4_PT[0]), round(_A4_PT[1])
            avail_w, avail_h = page_w - 2 * margin_px, page_h - 2 * margin_px
            if avail_w <= 0 or avail_h <= 0:
                raise ConversionError("边距过大，A4 页面无法容纳内容")
            canvas = Image.new("RGB", (page_w, page_h), color="white")
            scale = min(avail_w / rgb.width, avail_h / rgb.height)
            new_size = (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale)))
            resized = rgb.resize(new_size, Image.Resampling.LANCZOS)
            try:
                tx = (page_w - new_size[0]) // 2
                ty = (page_h - new_size[1]) // 2
                canvas.paste(resized, (tx, ty))
            finally:
                resized.close()
        rgb.close()
        return canvas
