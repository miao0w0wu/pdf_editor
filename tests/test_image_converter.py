"""ImageToPdfConverter 单元测试。"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from pdf_editor.core.exceptions import PdfEditorError, UnsupportedImageError
from pdf_editor.core.image_converter import ImageToPdfConverter


class TestConvert:
    def test_single_image_auto_size(self, rgb_image: Path, tmp_path: Path) -> None:
        out = tmp_path / "out.pdf"
        result = ImageToPdfConverter().convert([rgb_image], out)
        assert result == out
        with pymupdf.open(str(out)) as doc:
            assert doc.page_count == 1
            # auto 模式：页面尺寸 = 图片像素尺寸（1px=1pt）
            assert doc[0].rect.width == 200
            assert doc[0].rect.height == 100

    def test_multiple_images_order(self, tmp_path: Path) -> None:
        # 用不同颜色区分页序
        paths = []
        for i in range(3):
            p = tmp_path / f"img{i}.png"
            Image.new("RGB", (50, 50), color=(i * 80, 0, 0)).save(p)
            paths.append(p)
        out = tmp_path / "multi.pdf"
        ImageToPdfConverter().convert(paths, out)
        with pymupdf.open(str(out)) as doc:
            assert doc.page_count == 3
            # 每页颜色递增（红分量）
            for i in range(3):
                pix = doc[i].get_pixmap()
                r, _, _ = pix.pixel(25, 25)[:3]
                assert abs(r - i * 80) <= 2  # JPEG 压缩允许 ±2 色差

    def test_rgba_image_converted(self, rgba_image: Path, tmp_path: Path) -> None:
        """RGBA 图必须能转换（spec 5.3：色彩模式统一处理）。"""
        out = tmp_path / "rgba.pdf"
        ImageToPdfConverter().convert([rgba_image], out)
        with pymupdf.open(str(out)) as doc:
            assert doc.page_count == 1

    def test_palette_image_converted(self, palette_image: Path, tmp_path: Path) -> None:
        """调色板图必须能转换。"""
        out = tmp_path / "pal.pdf"
        ImageToPdfConverter().convert([palette_image], out)
        with pymupdf.open(str(out)) as doc:
            assert doc.page_count == 1

    def test_a4_mode(self, rgb_image: Path, tmp_path: Path) -> None:
        out = tmp_path / "a4.pdf"
        ImageToPdfConverter().convert([rgb_image], out, page_size="a4", margin_mm=10)
        with pymupdf.open(str(out)) as doc:
            page = doc[0]
            assert page.rect.width == pytest.approx(595, abs=1)
            assert page.rect.height == pytest.approx(842, abs=1)

    def test_progress_cb_called(self, rgb_image: Path, tmp_path: Path) -> None:
        calls: list[tuple[int, int]] = []
        ImageToPdfConverter().convert(
            [rgb_image], tmp_path / "p.pdf", progress_cb=lambda i, t: calls.append((i, t))
        )
        assert calls == [(1, 1)]

    def test_empty_list_raises(self, tmp_path: Path) -> None:
        with pytest.raises(UnsupportedImageError):
            ImageToPdfConverter().convert([], tmp_path / "x.pdf")

    def test_unsupported_suffix(self, tmp_path: Path) -> None:
        fake = tmp_path / "file.svg"
        fake.write_text("<svg/>")
        with pytest.raises(UnsupportedImageError):
            ImageToPdfConverter().convert([fake], tmp_path / "x.pdf")

    def test_missing_image_raises(self, tmp_path: Path) -> None:
        with pytest.raises(UnsupportedImageError):
            ImageToPdfConverter().convert([tmp_path / "nope.png"], tmp_path / "x.pdf")

    def test_target_is_directory_raises(self, rgb_image: Path, tmp_path: Path) -> None:
        with pytest.raises(PdfEditorError):
            ImageToPdfConverter().convert([rgb_image], tmp_path)


from PIL import Image  # noqa: E402  （测试内使用的辅助导入）
