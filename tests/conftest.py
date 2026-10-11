"""pytest fixtures：现场生成小型测试用 PDF / 图片。"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from PIL import Image


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """生成 5 页 PDF，每页居中写页码文本，用于页序与分割验证。"""
    path = tmp_path / "sample.pdf"
    doc = pymupdf.open()
    for i in range(5):
        page = doc.new_page(width=595, height=842)  # A4 pt
        page.insert_text(
            (250, 400),
            f"Page {i + 1}",
            fontsize=32,
            fontname="helv",
        )
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def rgb_image(tmp_path: Path) -> Path:
    """生成一张 RGB 测试图片。"""
    path = tmp_path / "test_rgb.png"
    Image.new("RGB", (200, 100), color=(200, 30, 30)).save(path)
    return path


@pytest.fixture
def rgba_image(tmp_path: Path) -> Path:
    """生成一张带透明通道的测试图片（必须能被正确转换）。"""
    path = tmp_path / "test_rgba.png"
    Image.new("RGBA", (120, 80), color=(10, 200, 10, 128)).save(path)
    return path


@pytest.fixture
def palette_image(tmp_path: Path) -> Path:
    """生成一张调色板模式（P）测试图片。"""
    path = tmp_path / "test_palette.png"
    Image.new("P", (64, 64), color=3).save(path)
    return path
