"""ScanConverter 测试：灰底/渐变底压平、文字保留、页面尺寸、分割裁剪、参数校验。"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from pdf_editor.core.exceptions import ConversionError, PdfOpenError
from pdf_editor.core.pdf_document import PdfDocumentService
from pdf_editor.core.scan_converter import ScanConverter


@pytest.fixture
def gray_text_pdf(tmp_path: Path) -> Path:
    """灰底 + 黑字单页 PDF（模拟灰底扫描件）。"""
    path = tmp_path / "gray.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(page.rect, fill=(0.75, 0.75, 0.75), color=None)
    page.insert_text((72, 200), "Hello Scan", fontsize=36, fontname="helv", color=(0, 0, 0))
    doc.save(str(path))
    doc.close()
    return path


def _gray_pixels(path: Path, dpi: int = 72) -> tuple[int, int, list[int]]:
    """渲染输出页为灰度，返回 (width, height, 样本)。"""
    doc = pymupdf.open(str(path))
    pix = doc[0].get_pixmap(colorspace=pymupdf.csGRAY, alpha=False)
    samples = list(pix.samples)
    size = (pix.width, pix.height)
    doc.close()
    return size[0], size[1], samples


class TestScanConverter:
    def test_gray_background_flattened_text_kept(self, gray_text_pdf: Path, tmp_path: Path):
        out = tmp_path / "out.pdf"
        ScanConverter().convert(gray_text_pdf, [(0, None)], out, dpi=150, threshold=32)
        assert out.is_file()

        w, h, samples = _gray_pixels(out)
        # 背景四角应为纯白（原底色 0.75 ≈ 191）
        assert samples[5 * w + 5] == 255
        assert samples[5 * w + (w - 6)] == 255
        assert samples[(h - 6) * w + (w - 6)] == 255
        # 文字应保留为深色像素
        assert min(samples) < 80
        assert sum(1 for v in samples if v < 128) > 100

    def test_page_size_matches_source(self, gray_text_pdf: Path, tmp_path: Path):
        out = tmp_path / "out.pdf"
        ScanConverter().convert(gray_text_pdf, [(0, None)], out, dpi=200)
        doc = pymupdf.open(str(out))
        assert doc.page_count == 1
        assert doc[0].rect.width == pytest.approx(595, abs=1)
        assert doc[0].rect.height == pytest.approx(842, abs=1)
        doc.close()

    def test_multiple_pages_and_subset_order(self, tmp_path: Path):
        """多页 PDF：只转选中的两页，且按给定顺序输出。"""
        src = tmp_path / "multi.pdf"
        doc = pymupdf.open()
        for i in range(3):
            page = doc.new_page(width=300, height=400)
            page.insert_text((30, 100), f"P{i}", fontsize=20, color=(0, 0, 0))
        doc.save(str(src))
        doc.close()

        out = tmp_path / "subset.pdf"
        ScanConverter().convert(src, [(2, None), (0, None)], out, dpi=96)
        doc = pymupdf.open(str(out))
        assert doc.page_count == 2
        # 顺序按传入顺序：第一页来自源第 3 页
        text = doc[0].get_text()
        assert "P2" not in text  # 扫描件是图像页，无文本层
        assert doc[0].rect.width == pytest.approx(300, abs=1)
        doc.close()

    def test_split_crop_produces_half_height_page(self, tmp_path: Path):
        """分割子页转扫描件：只渲染可见区域（裁剪框生效）。"""
        src = tmp_path / "split.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=800)
        page.insert_text((40, 100), "TOP", fontsize=24, color=(0, 0, 0))
        page.insert_text((40, 700), "BOTTOM", fontsize=24, color=(0, 0, 0))
        doc.save(str(src))
        doc.close()

        service = PdfDocumentService()
        service.open(src)
        state = service.split_page(0, "horizontal", [0.5, 0.5])
        top_id, bottom_id = (p.page_id for p in state.pages)

        pages = [service.page_source_info(pid) for pid in (top_id, bottom_id)]
        assert pages[0][1] == (0.0, 0.0, 1.0, 0.5)
        assert pages[1][1] == (0.0, 0.5, 1.0, 1.0)

        out = tmp_path / "split_scan.pdf"
        ScanConverter().convert(src, pages, out, dpi=96)
        doc = pymupdf.open(str(out))
        assert doc.page_count == 2
        for p in doc:
            assert p.rect.height == pytest.approx(400, abs=1)
            assert p.rect.width == pytest.approx(400, abs=1)
        doc.close()

    def test_gradient_background_flattened(self, tmp_path: Path):
        """模拟拍照光照不均：渐变底色也必须压平成白色。"""
        src = tmp_path / "grad.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=300)
        shape = page.new_shape()
        for i in range(40):
            g = 0.95 - 0.45 * i / 40
            shape.draw_rect(pymupdf.Rect(i / 40 * 400, 0, (i + 1) / 40 * 400, 300))
            shape.finish(fill=(g, g, g), color=None)
        shape.commit()
        page.insert_text((30, 80), "GRAD", fontsize=20, color=(0, 0, 0))
        doc.save(str(src))
        doc.close()

        out = tmp_path / "grad_out.pdf"
        ScanConverter().convert(src, [(0, None)], out, dpi=120, threshold=32)
        w, h, samples = _gray_pixels(out)
        # 最暗的右侧背景也应为白色
        assert samples[(h - 4) * w + (w - 4)] == 255
        assert min(samples) < 80

    def test_empty_pages_rejected(self, gray_text_pdf: Path, tmp_path: Path):
        with pytest.raises(ConversionError):
            ScanConverter().convert(gray_text_pdf, [], tmp_path / "out.pdf")

    def test_invalid_dpi_rejected(self, gray_text_pdf: Path, tmp_path: Path):
        with pytest.raises(ConversionError):
            ScanConverter().convert(gray_text_pdf, [(0, None)], tmp_path / "out.pdf", dpi=600)

    def test_invalid_threshold_rejected(self, gray_text_pdf: Path, tmp_path: Path):
        with pytest.raises(ConversionError):
            ScanConverter().convert(gray_text_pdf, [(0, None)], tmp_path / "out.pdf", threshold=0)

    def test_missing_source_raises_pdf_open_error(self, tmp_path: Path):
        with pytest.raises(PdfOpenError):
            ScanConverter().convert(tmp_path / "missing.pdf", [(0, None)], tmp_path / "out.pdf")

    def test_encrypted_pdf_requires_password(self, tmp_path: Path):
        src = tmp_path / "enc.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=200, height=200)
        page.insert_text((20, 50), "secret", fontsize=14, color=(0, 0, 0))
        doc.save(str(src), encryption=pymupdf.PDF_ENCRYPT_AES_128, owner_pw="o", user_pw="u")
        doc.close()

        with pytest.raises(PdfOpenError):
            ScanConverter().convert(src, [(0, None)], tmp_path / "o1.pdf")
        # 正确密码可转换
        out = tmp_path / "o2.pdf"
        ScanConverter().convert(src, [(0, None)], out, password="u")
        assert out.is_file()

    def test_invalid_crop_rejected(self, gray_text_pdf: Path, tmp_path: Path):
        with pytest.raises(ConversionError):
            ScanConverter().convert(
                gray_text_pdf, [(0, (0.0, 0.8, 1.0, 0.2))], tmp_path / "out.pdf"
            )

    def test_photo_page_cropped_and_whitened(self, tmp_path: Path):
        """拍照页（深色桌面边框包住白纸）应裁出纸面：黑边消失、纸面铺满页面。"""
        from PIL import Image, ImageDraw

        paper = Image.new("RGB", (340, 250), (205, 205, 205))
        draw = ImageDraw.Draw(paper)
        draw.text((30, 110), "SCAN TEST", fill=(10, 10, 10))
        photo = Image.new("RGB", (400, 300), (30, 30, 30))
        photo.paste(paper, (25, 20))

        src = tmp_path / "photo.pdf"
        photo_path = tmp_path / "photo.png"
        photo.save(str(photo_path))
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=300)
        page.insert_image(page.rect, filename=str(photo_path))
        doc.save(str(src))
        doc.close()

        out = tmp_path / "photo_scan.pdf"
        ScanConverter().convert(src, [(0, None)], out, dpi=96, threshold=32)
        doc = pymupdf.open(str(out))
        assert doc.page_count == 1
        # 页面尺寸应为裁出的纸面；源页 400x300pt 中纸面占 340x250pt，
        # 转换按纸面物理尺寸出页（不再等于整页 400x300）
        assert doc[0].rect.width == pytest.approx(340, abs=6)
        assert doc[0].rect.height == pytest.approx(250, abs=6)
        pix = doc[0].get_pixmap(colorspace=pymupdf.csGRAY, alpha=False)
        samples = list(pix.samples)
        w, h = pix.width, pix.height
        doc.close()
        # 四角应为纸面白色（深色桌面边框已被裁掉）
        assert samples[5 * w + 5] == 255
        assert samples[5 * w + (w - 6)] == 255
        assert samples[(h - 6) * w + (w - 6)] == 255
        # 文字保留为深色
        assert min(samples) < 80

    @staticmethod
    def _color_ink_pdf(tmp_path: Path) -> Path:
        """白底 + 红色圆章 + 蓝色墨迹块的彩色单页 PDF（1px=1pt）。"""
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (400, 300), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.ellipse((280, 40, 360, 120), fill=(190, 60, 55))  # 红章
        draw.rectangle((40, 180, 200, 220), fill=(40, 70, 160))  # 蓝墨
        png = tmp_path / "color_ink.png"
        img.save(str(png))
        src = tmp_path / "color_ink.pdf"
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=300)
        page.insert_image(page.rect, filename=str(png))
        doc.save(str(src))
        doc.close()
        return src

    @staticmethod
    def _rgb_pixels(path: Path) -> tuple[int, int, list[int]]:
        doc = pymupdf.open(str(path))
        pix = doc[0].get_pixmap(colorspace=pymupdf.csRGB, alpha=False)
        samples = list(pix.samples)
        size = (pix.width, pix.height)
        doc.close()
        return size[0], size[1], samples

    def test_color_tone_preserves_ink_colors(self, tmp_path: Path):
        """彩色模式：背景提白的同时保留红章/蓝墨的色相与饱和度。"""
        src = self._color_ink_pdf(tmp_path)
        out = tmp_path / "color_out.pdf"
        ScanConverter().convert(src, [(0, None)], out, dpi=96, threshold=32, tone="color")
        w, h, px = self._rgb_pixels(out)

        def count_saturated(pred) -> int:
            n = 0
            for i in range(0, len(px), 3):
                r, g, b = px[i], px[i + 1], px[i + 2]
                if pred(r, g, b):
                    n += 1
            return n

        reds = count_saturated(lambda r, g, b: r - max(g, b) > 60)
        blues = count_saturated(lambda r, g, b: b - max(r, g) > 40)
        assert reds > 200, f"红色印章色彩丢失（红色像素 {reds}）"
        assert blues > 200, f"蓝色墨迹色彩丢失（蓝色像素 {blues}）"
        # 背景仍为白色
        assert px[5 * w * 3 + 5 * 3] == 255

    def test_bw_tone_outputs_grayscale(self, tmp_path: Path):
        """黑白模式：彩色墨迹转灰度输出（R=G=B），白底黑字行为不变。"""
        src = self._color_ink_pdf(tmp_path)
        out = tmp_path / "bw_out.pdf"
        ScanConverter().convert(src, [(0, None)], out, dpi=96, threshold=32, tone="bw")
        w, h, px = self._rgb_pixels(out)
        colored = 0
        for i in range(0, len(px), 3):
            r, g, b = px[i], px[i + 1], px[i + 2]
            if max(r, g, b) - min(r, g, b) > 8:
                colored += 1
        assert colored == 0, f"黑白模式输出含彩色像素 {colored} 个"
        assert px[5 * w * 3 + 5 * 3] == 255  # 背景白色
        assert min(px) < 80  # 内容为深色

    def test_invalid_tone_rejected(self, gray_text_pdf: Path, tmp_path: Path):
        with pytest.raises(ConversionError):
            ScanConverter().convert(
                gray_text_pdf, [(0, None)], tmp_path / "out.pdf", tone="sepia"
            )
