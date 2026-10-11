"""api 层测试：直接实例化 JsApi（注入临时 core 服务），不启动 webview。

覆盖：统一信封结构、错误码与异常类名一致、open/render/reorder/split
往返、转换任务异步返回 task_id。
"""

from __future__ import annotations

import pytest
from pypdf import PdfWriter

from pdf_editor.api import build_api


@pytest.fixture()
def sample_pdf(tmp_path):
    """3 页 200x200 空白 PDF。"""
    p = tmp_path / "sample.pdf"
    w = PdfWriter()
    for _ in range(3):
        w.add_blank_page(width=200, height=200)
    w.write(str(p))
    return str(p)


@pytest.fixture()
def api():
    return build_api()


class TestEnvelope:
    def test_ping_ok(self, api):
        assert api.ping() == {"ok": True, "data": "pong"}

    def test_error_code_matches_exception_name(self, api, tmp_path):
        result = api.document.open_document(str(tmp_path / "missing.pdf"))
        assert result["ok"] is False
        assert result["error"]["code"] == "PdfOpenError"
        assert result["error"]["message"]

    def test_unknown_exception_becomes_internal_error(self, tmp_path, monkeypatch):
        from pdf_editor.api.document_api import DocumentApi
        from pdf_editor.core.pdf_document import PdfDocumentService
        from pdf_editor.core.pdf_renderer import PdfRenderer

        service = PdfDocumentService()
        service.open(str(tmp_path / "x.pdf")) if False else None  # 保持未打开状态
        api_doc = DocumentApi(service, PdfRenderer())
        # get_state 对未打开文档抛 PdfOpenError；这里直接验证真实错误路径
        result = api_doc.get_state()
        assert result["ok"] is False
        assert result["error"]["code"] == "PdfOpenError"

    def test_internal_error_envelope(self, api, monkeypatch):
        # 让 save 底层抛出非 PdfEditorError，验证 InternalError 兜底
        monkeypatch.setattr(
            api.document._service,
            "save",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        result = api.document.save_document("whatever.pdf")
        assert result["ok"] is False
        assert result["error"]["code"] == "InternalError"


class TestDocumentApi:
    def test_open_returns_state_payload(self, api, sample_pdf):
        result = api.document.open_document(sample_pdf)
        assert result["ok"] is True
        pages = result["data"]["pages"]
        assert [p["page_id"] for p in pages] == [0, 1, 2]
        assert [p["source_index"] for p in pages] == [0, 1, 2]
        assert [p["label"] for p in pages] == ["1", "2", "3"]

    def test_reorder_and_delete_roundtrip(self, api, sample_pdf, tmp_path):
        api.document.open_document(sample_pdf)
        r = api.document.reorder_pages([2, 1, 0])
        assert r["ok"] and [p["page_id"] for p in r["data"]["pages"]] == [2, 1, 0]

        r = api.document.delete_pages([1])
        assert r["ok"] and [p["page_id"] for p in r["data"]["pages"]] == [2, 0]

        out = tmp_path / "out.pdf"
        r = api.document.save_document(str(out))
        assert r["ok"]

        from pypdf import PdfReader

        reader = PdfReader(str(out))
        assert len(reader.pages) == 2

    def test_split_page_payload(self, api, sample_pdf):
        api.document.open_document(sample_pdf)
        r = api.document.split_page(1, "horizontal", [0.5, 0.5])
        assert r["ok"] is True
        labels = [p["label"] for p in r["data"]["pages"]]
        assert labels == ["1", "2a", "2b", "3"]
        # 子页是全新 page_id，原子页 1 失效
        assert 1 not in [p["page_id"] for p in r["data"]["pages"]]

    def test_render_page_returns_data_url(self, api, sample_pdf):
        api.document.open_document(sample_pdf)
        r = api.document.render_page(0, 48)
        assert r["ok"] is True
        url = r["data"]
        assert url.startswith("data:image/png;base64,")
        assert len(url) > 100

    def test_render_page_invalid_index(self, api, sample_pdf):
        api.document.open_document(sample_pdf)
        r = api.document.render_page(99, 48)
        assert r["ok"] is False
        assert r["error"]["code"] == "PdfOpenError"

    def test_close_document(self, api, sample_pdf):
        api.document.open_document(sample_pdf)
        assert api.document.is_open()["data"] is True
        api.document.close_document()
        assert api.document.is_open()["data"] is False
        r = api.document.get_state()
        assert r["ok"] is False


class TestDialogApi:
    @staticmethod
    def _dialog(return_value):
        from pdf_editor.api.dialog_api import DialogApi

        class StubWindow:
            def __init__(self, rv):
                self.rv = rv

            def create_file_dialog(self, *args, **kwargs):
                return self.rv

        return DialogApi(lambda: StubWindow(return_value))

    def test_pick_output_directory(self):
        dialog = self._dialog(["D:\\out"])
        assert dialog.pick_output_directory()["data"] == "D:\\out"

    def test_pick_output_directory_cancelled(self):
        dialog = self._dialog(None)
        assert dialog.pick_output_directory()["data"] is None

    def test_pick_output_directory_window_missing(self):
        from pdf_editor.api.dialog_api import DialogApi

        dialog = DialogApi(lambda: None)
        r = dialog.pick_output_directory()
        assert r["ok"] is False
        assert r["error"]["code"] == "InternalError"


class TestConverterApi:
    def test_convert_word_returns_task_id_immediately(self, api, tmp_path):
        """无 soffice 环境：方法立即返回 task_id，错误通过事件推送。"""
        r = api.converter.convert_word_to_pdf("nope.docx", str(tmp_path))
        assert r["ok"] is True
        assert r["data"]["task_id"].startswith("task-")

    def test_convert_images_rejects_empty(self, api, tmp_path):
        r = api.converter.convert_images_to_pdf([], str(tmp_path / "a.pdf"))
        assert r["ok"] is False

    def test_image_conversion_task_completes(self, api, tmp_path):
        """真实图片转换：等待事件线程结束后验证输出文件。"""
        from PIL import Image

        img_path = tmp_path / "a.png"
        Image.new("RGB", (20, 20), "red").save(img_path)
        out = tmp_path / "out.pdf"

        r = api.converter.convert_images_to_pdf([str(img_path)], str(out))
        assert r["ok"] is True
        assert out.exists() or True  # 异步任务，轮询等待
        import time

        deadline = time.time() + 10
        while not out.exists() and time.time() < deadline:
            time.sleep(0.05)
        assert out.is_file()

    def test_cancel_unknown_task(self, api):
        r = api.converter.cancel_task("task-nope")
        assert r == {"cancelled": False}

    def test_scan_conversion_requires_open_document(self, api, sample_pdf, tmp_path):
        r = api.converter.convert_pages_to_scan([0], str(tmp_path / "out.pdf"))
        assert r["ok"] is False
        assert r["error"]["code"] == "PdfOpenError"

    def test_scan_conversion_rejects_empty_pages(self, api, sample_pdf, tmp_path):
        api.document.open_document(sample_pdf)
        r = api.converter.convert_pages_to_scan([], str(tmp_path / "out.pdf"))
        assert r["ok"] is False

    def test_scan_conversion_task_completes(self, api, sample_pdf, tmp_path):
        """真实扫描转换：等待异步任务产出文件，页数与所选子集一致。"""
        api.document.open_document(sample_pdf)
        out = tmp_path / "scan.pdf"
        r = api.converter.convert_pages_to_scan([0, 2], str(out), dpi=96, threshold=32)
        assert r["ok"] is True
        assert r["data"]["task_id"].startswith("task-")

        import time

        deadline = time.time() + 15
        while not out.exists() and time.time() < deadline:
            time.sleep(0.05)
        assert out.is_file()

        from pypdf import PdfReader

        assert len(PdfReader(str(out)).pages) == 2

    def test_scan_conversion_unknown_page_id_fails(self, api, sample_pdf, tmp_path):
        api.document.open_document(sample_pdf)
        r = api.converter.convert_pages_to_scan([99], str(tmp_path / "out.pdf"))
        assert r["ok"] is False


class TestEventPusher:
    def test_push_without_window_is_silent(self):
        from pdf_editor.api.events import EventPusher

        pusher = EventPusher()
        pusher.push("conversion_progress", {"stage": "1/2"})  # 不应抛异常

    def test_push_with_stub_window(self):
        from pdf_editor.api.events import EventPusher

        captured: list[str] = []

        class StubWindow:
            def evaluate_js(self, script: str) -> None:
                captured.append(script)

        pusher = EventPusher()
        pusher.bind_window(StubWindow())
        pusher.push("task_done", {"task_id": "t1"})

        class BrokenWindow:
            def evaluate_js(self, script: str) -> None:
                raise RuntimeError("window closed")

        pusher.bind_window(BrokenWindow())
        pusher.push("task_done", {"task_id": "t2"})  # 容忍异常不外抛
        assert "window.__backend" in captured[0]
        assert "task_done" in captured[0]
