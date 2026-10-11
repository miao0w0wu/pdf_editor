"""WordToPdfConverter 单元测试（无 soffice 环境自动跳过实际转换）。"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

import pytest

from pdf_editor.core.exceptions import ConversionError
from pdf_editor.core.word_converter import WordToPdfConverter

soffice_missing = shutil.which("soffice") is None and "SOFFICE_PATH" not in os.environ


def make_minimal_docx(path: Path, text: str = "Hello PDF") -> None:
    """构造一个最小可用的 .docx（zip + 必要 XML），不引入 python-docx 依赖。"""
    content_types = (
        '<?xml version="1.0"?><Types '
        'xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/word/document.xml" ContentType='
        '"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    document = (
        '<?xml version="1.0"?><w:document '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("word/document.xml", document)


class TestValidation:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConversionError):
            WordToPdfConverter().convert(tmp_path / "no.docx", tmp_path)

    def test_wrong_suffix_raises(self, tmp_path: Path) -> None:
        fake = tmp_path / "notes.txt"
        fake.write_text("hello")
        with pytest.raises(ConversionError):
            WordToPdfConverter().convert(fake, tmp_path)

    def test_missing_out_dir_raises(self, tmp_path: Path) -> None:
        docx = tmp_path / "a.docx"
        docx.write_bytes(b"placeholder")
        with pytest.raises(ConversionError):
            WordToPdfConverter().convert(docx, tmp_path / "no_such_dir")


@pytest.mark.skipif(soffice_missing, reason="需要系统安装 LibreOffice (soffice)")
class TestRealConversion:
    def test_convert_docx(self, tmp_path: Path) -> None:
        docx = tmp_path / "hello.docx"
        make_minimal_docx(docx)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = WordToPdfConverter().convert(docx, out_dir, timeout_s=60)
        assert result.is_file()
        assert result.suffix == ".pdf"

    def test_progress_stages(self, tmp_path: Path) -> None:
        """进度回调至少包含定位/启动/完成阶段。"""
        stages: list[str] = []
        docx = tmp_path / "tiny.docx"
        make_minimal_docx(docx, "tiny")
        out_dir = tmp_path / "out2"
        out_dir.mkdir()
        WordToPdfConverter().convert(docx, out_dir, timeout_s=60, progress_cb=stages.append)
        assert len(stages) >= 2
