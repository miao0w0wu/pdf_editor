"""重排（reorder）与分割（split）的落盘验证测试。"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from pdf_editor.core.exceptions import PdfWriteError
from pdf_editor.core.pdf_document import PdfDocumentService


def extract_page_text(path: Path, index: int) -> str:
    with pymupdf.open(str(path)) as doc:
        return doc[index].get_text().strip()


class TestSplitPage:
    def test_horizontal_split_two_halves(self, sample_pdf: Path, tmp_path: Path) -> None:
        """P3 验收标准：分割后子页内容与原页对应区域一致。"""
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        target = state.pages[0]
        new_state = svc.split_page(target.page_id, "horizontal", [0.5, 0.5])
        assert len(new_state.pages) == 6  # 1 页变 2 页，其余 4 页不变

        out = tmp_path / "split_h.pdf"
        svc.save(out)
        with pymupdf.open(str(out)) as doc:
            assert doc.page_count == 6
            top, bottom = doc[0], doc[1]
            # PDF 坐标自底向上：文本位于 PDF y=400（页高 842），落在下半子页；
            # 子页尺寸约为原页一半高
            assert top.rect.height == pytest.approx(421, abs=2)
            assert bottom.rect.height == pytest.approx(421, abs=2)
            assert "Page 1" in bottom.get_text()

    def test_vertical_split(self, sample_pdf: Path, tmp_path: Path) -> None:
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        target = state.pages[1]
        new_state = svc.split_page(target.page_id, "vertical", [0.3, 0.7])
        assert len(new_state.pages) == 6
        out = tmp_path / "split_v.pdf"
        svc.save(out)
        with pymupdf.open(str(out)) as doc:
            # 目标页是第 2 页（index 0 = 原 Page 1），分割页位于 doc[1] 与 doc[2]
            left, right = doc[1], doc[2]
            assert left.rect.width == pytest.approx(595 * 0.3, abs=2)
            assert right.rect.width == pytest.approx(595 * 0.7, abs=2)

    def test_split_ratios_normalized(self, sample_pdf: Path, tmp_path: Path) -> None:
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        target = state.pages[0]
        # 占比之和不为 1 也应归一化
        new_state = svc.split_page(target.page_id, "horizontal", [1, 3])
        assert len(new_state.pages) == 6
        out = tmp_path / "split_norm.pdf"
        svc.save(out)
        with pymupdf.open(str(out)) as doc:
            assert doc[0].rect.height == pytest.approx(842 * 0.25, abs=2)
            assert doc[1].rect.height == pytest.approx(842 * 0.75, abs=2)

    def test_split_invalid_ratios(self, sample_pdf: Path) -> None:
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        with pytest.raises(PdfWriteError):
            svc.split_page(state.pages[0].page_id, "horizontal", [0.5])
        with pytest.raises(PdfWriteError):
            svc.split_page(state.pages[0].page_id, "horizontal", [0.5, -0.5])
        with pytest.raises(PdfWriteError):
            svc.split_page(state.pages[0].page_id, "horizontal", [0, 0])

    def test_split_new_page_ids_differ_from_old(self, sample_pdf: Path) -> None:
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        old_id = state.pages[0].page_id
        new_state = svc.split_page(old_id, "vertical", [0.5, 0.5])
        assert old_id not in new_state.page_ids()
        # 新子页 label 带后缀
        assert new_state.pages[0].label.endswith("a")
        assert new_state.pages[1].label.endswith("b")

    def test_split_unknown_page_id(self, sample_pdf: Path) -> None:
        svc = PdfDocumentService()
        svc.open(sample_pdf)
        with pytest.raises(PdfWriteError):
            svc.split_page(999, "horizontal", [0.5, 0.5])

    def test_split_reordered_document_targets_correct_source(
        self, sample_pdf: Path, tmp_path: Path
    ) -> None:
        """重排后分割：page_id 锚定，不受逻辑顺序影响。"""
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        ids = state.page_ids()
        svc.reorder_pages([ids[4], ids[3], ids[2], ids[1], ids[0]])
        state = svc.split_page(ids[2], "horizontal", [0.5, 0.5])
        assert len(state.pages) == 6
        out = tmp_path / "split_reordered.pdf"
        svc.save(out)
        # 重排后逻辑顺序为 [P5, P4, P3a, P3b, P2, P1]，P3 文本在下半子页
        assert "Page 3" in extract_page_text(out, 3)


class TestSplitAt:
    def test_split_at_box(self, sample_pdf: Path, tmp_path: Path) -> None:
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        target = state.pages[0]
        new_state = svc.split_at(target.page_id, (0.0, 0.0, 1.0, 0.5))
        assert len(new_state.pages) == 6
        out = tmp_path / "split_at.pdf"
        svc.save(out)
        with pymupdf.open(str(out)) as doc:
            assert doc.page_count == 6
            assert doc[0].rect.height == pytest.approx(421, abs=2)

    def test_split_at_invalid_box(self, sample_pdf: Path) -> None:
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        with pytest.raises(PdfWriteError):
            svc.split_at(state.pages[0].page_id, (0.5, 0.5, 0.5, 0.1))
        with pytest.raises(PdfWriteError):
            svc.split_at(state.pages[0].page_id, (1.5, 0.0, 2.0, 0.5))
