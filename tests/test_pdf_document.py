"""PdfDocumentService 单元测试：open/save/delete/reorder。"""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader

from pdf_editor.core.exceptions import PdfOpenError, PdfWriteError
from pdf_editor.core.pdf_document import PdfDocumentService


def read_labels(path: Path) -> list[str]:
    """用 pypdf 重新打开并提取每页文本中的页码标记（"Page N"）。"""
    import re

    reader = PdfReader(str(path))
    labels = []
    for page in reader.pages:
        text = (page.extract_text() or "").replace("\n", " ")
        m = re.search(r"Page\s*(\d+)", text)
        labels.append(f"Page{m.group(1)}" if m else "")
    return labels


class TestOpen:
    def test_open_assigns_stable_page_ids(self, sample_pdf: Path) -> None:
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        assert len(state.pages) == 5
        assert [p.page_id for p in state.pages] == [0, 1, 2, 3, 4]
        assert [p.source_index for p in state.pages] == [0, 1, 2, 3, 4]

    def test_open_missing_file(self, tmp_path: Path) -> None:
        svc = PdfDocumentService()
        with pytest.raises(PdfOpenError):
            svc.open(tmp_path / "nope.pdf")

    def test_open_invalid_file(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"not a pdf at all")
        svc = PdfDocumentService()
        with pytest.raises(PdfOpenError):
            svc.open(bad)

    def test_state_before_open_raises(self) -> None:
        svc = PdfDocumentService()
        with pytest.raises(PdfOpenError):
            _ = svc.state


class TestSave:
    def test_save_roundtrip_preserves_order(self, sample_pdf: Path, tmp_path: Path) -> None:
        svc = PdfDocumentService()
        svc.open(sample_pdf)
        out = tmp_path / "out.pdf"
        svc.save(out)
        assert read_labels(out) == ["Page1", "Page2", "Page3", "Page4", "Page5"]

    def test_save_page_range_subset(self, sample_pdf: Path, tmp_path: Path) -> None:
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        out = tmp_path / "subset.pdf"
        svc.save_page_range(out, [state.pages[1].page_id, state.pages[3].page_id])
        assert read_labels(out) == ["Page2", "Page4"]

    def test_save_with_parent_dir_creation(self, sample_pdf: Path, tmp_path: Path) -> None:
        svc = PdfDocumentService()
        svc.open(sample_pdf)
        out = tmp_path / "a" / "b" / "out.pdf"
        svc.save(out)
        assert out.is_file()

    def test_save_empty_page_list_raises(self, sample_pdf: Path, tmp_path: Path) -> None:
        svc = PdfDocumentService()
        svc.open(sample_pdf)
        with pytest.raises(PdfWriteError):
            svc.save_page_range(tmp_path / "x.pdf", [])


class TestDelete:
    def test_delete_pages(self, sample_pdf: Path, tmp_path: Path) -> None:
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        new_state = svc.delete_pages([state.pages[0].page_id, state.pages[2].page_id])
        assert len(new_state.pages) == 3
        out = tmp_path / "deleted.pdf"
        svc.save(out)
        assert read_labels(out) == ["Page2", "Page4", "Page5"]

    def test_delete_unknown_page_id(self, sample_pdf: Path) -> None:
        svc = PdfDocumentService()
        svc.open(sample_pdf)
        with pytest.raises(PdfWriteError):
            svc.delete_pages([999])

    def test_cannot_delete_all_pages(self, sample_pdf: Path) -> None:
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        all_ids = state.page_ids()
        with pytest.raises(PdfWriteError):
            svc.delete_pages(all_ids)


class TestReorder:
    def test_reorder_and_save_verifies_page_order(self, sample_pdf: Path, tmp_path: Path) -> None:
        """P1 验收标准：删除/重排后 pypdf 重新打开验证页序正确。"""
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        ids = state.page_ids()
        new_state = svc.reorder_pages([ids[2], ids[0], ids[4], ids[1], ids[3]])
        assert [p.source_index for p in new_state.pages] == [2, 0, 4, 1, 3]
        out = tmp_path / "reordered.pdf"
        svc.save(out)
        assert read_labels(out) == ["Page3", "Page1", "Page5", "Page2", "Page4"]

    def test_reorder_requires_full_permutation(self, sample_pdf: Path) -> None:
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        ids = state.page_ids()
        with pytest.raises(PdfWriteError):
            svc.reorder_pages(ids[:3])

    def test_page_id_stable_across_reorder(self, sample_pdf: Path) -> None:
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        ids = state.page_ids()
        new_state = svc.reorder_pages(list(reversed(ids)))
        assert new_state.page_ids() == list(reversed(ids))

    def test_delete_then_reorder_with_original_ids_fails(self, sample_pdf: Path) -> None:
        """page_id 语义：删除后旧 id 失效。"""
        svc = PdfDocumentService()
        state = svc.open(sample_pdf)
        ids = state.page_ids()
        svc.delete_pages([ids[0]])
        with pytest.raises(PdfWriteError):
            svc.reorder_pages(ids)


class TestClose:
    def test_close_resets_state(self, sample_pdf: Path) -> None:
        svc = PdfDocumentService()
        svc.open(sample_pdf)
        svc.close()
        assert not svc.is_open
        with pytest.raises(PdfOpenError):
            _ = svc.state
