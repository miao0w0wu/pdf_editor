"""真实窗口 E2E 冒烟测试（P2~P3 验收辅助）。

流程：生成 6 页样例 PDF → stub 原生对话框（返回固定路径）→ 托管
frontend/dist 启动真实 webview 窗口 → 用 evaluate_js 驱动 React UI：
点击「打开」→ 断言缩略图与主视图渲染 → 打开分割对话框执行水平二等分
→ 断言页数与当前页标签 → 点击「保存」→ 用 pypdf 验证落盘结果。

运行（在 pdf_editor/ 目录）：
    PYTHONPATH=src py -m scripts.e2e_smoke
或直接：
    PYTHONPATH=src py scripts/e2e_smoke.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import webview  # noqa: E402

from pdf_editor.api import build_api  # noqa: E402
from pdf_editor.utils.static_server import serve_directory  # noqa: E402


def make_sample_pdf(path: Path, pages: int = 6) -> None:
    """用 pymupdf 生成带页码文本的样例 PDF（400x560pt）。"""
    import pymupdf

    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page(width=400, height=560)
        page.insert_text((60, 300), f"Page {i + 1}", fontsize=48)
    doc.save(str(path))
    doc.close()


def js(win, script: str):
    result = win.evaluate_js(script)
    return result


def wait_for(win, script: str, deadline_s: float = 15.0, expect_truthy: bool = True):
    """轮询 evaluate_js 直到表达式为真值。"""
    end = time.time() + deadline_s
    last = None
    while time.time() < end:
        last = js(win, script)
        if bool(last) == expect_truthy and last is not False:
            return last
        time.sleep(0.2)
    raise AssertionError(f"等待超时: {script} -> {last!r}")


def click_button(win, testid: str) -> None:
    """按 data-testid 点击按钮（React 合成事件可响应原生 click）。"""
    ok = js(
        win,
        f"""(() => {{
            const b = document.querySelector('button[data-testid="{testid}"]');
            if (!b) return false;
            if (b.disabled) return 'disabled';
            b.click();
            return true;
        }})()""",
    )
    if ok is not True:
        raise AssertionError(f"无法点击按钮 {testid}: {ok!r}")


def click_modal_button(win, text: str) -> None:
    """按可见文本点击当前对话框（.ant-modal）内的按钮（支持前缀匹配，如「开始转换（7 页）」）。"""
    ok = js(
        win,
        f"""(() => {{
            const btns = [...document.querySelectorAll('.ant-modal .ant-btn')];
            const b = btns.find(el => {{
                const t = el.textContent.trim();
                return t === {json.dumps(text)} || t.startsWith({json.dumps(text)});
            }});
            if (!b) return false;
            if (b.disabled) return 'disabled';
            b.click();
            return true;
        }})()""",
    )
    if ok is not True:
        raise AssertionError(f"无法点击对话框按钮 {text}: {ok!r}")


def main() -> int:
    tmp = Path(__file__).resolve().parent / "_e2e_tmp"
    tmp.mkdir(exist_ok=True)
    sample = tmp / "sample.pdf"
    saved = tmp / "saved.pdf"
    extracted = tmp / "extracted.pdf"
    scanned = tmp / "scanned.pdf"
    make_sample_pdf(sample)
    for p in (saved, extracted, scanned):
        if p.exists():
            p.unlink()

    api = build_api()

    # stub 原生对话框：文件选择/保存路径固定，E2E 不依赖人工操作。
    # 保存路径按默认文件名路由（-extract / -scan 后缀对应不同产物）。
    def fake_save_pdf_path(default_name: str = "output.pdf", **_kwargs):
        if "-extract" in default_name:
            return {"ok": True, "data": str(extracted)}
        if "-scan" in default_name:
            return {"ok": True, "data": str(scanned)}
        return {"ok": True, "data": str(saved)}

    api.dialog.pick_pdf_file = lambda: {"ok": True, "data": str(sample)}
    api.dialog.pick_save_pdf_path = fake_save_pdf_path

    dist = PROJECT_ROOT / "frontend" / "dist"
    url, server = serve_directory(dist)

    webview.create_window(
        title="E2E 冒烟",
        url=url,
        js_api=api,
        width=1280,
        height=800,
    )
    api.events.bind_window(webview.windows[0])

    checks: list[tuple[str, bool, str]] = []

    def record(name: str, fn):
        try:
            fn()
            checks.append((name, True, ""))
        except Exception as e:  # noqa: BLE001 — E2E 收集所有失败后统一汇报
            checks.append((name, False, str(e)))

    def run(win):
        # 等待 React 挂载 + 桥接就绪
        wait_for(win, "!!document.querySelector('button[data-testid=\"btn-open\"]')")
        wait_for(win, "document.body.innerText.includes('后端已连接')")

        # 1. 点击「打开」→ 文档加载 → 缩略图逐页推送
        record(
            "打开文档并渲染缩略图",
            lambda: (
                click_button(win, "btn-open"),
                wait_for(win, "document.querySelectorAll('.thumb-item').length === 6"),
            )[1],
        )

        # 2. 主视图渲染 + 页码指示
        record(
            "主视图渲染",
            lambda: (
                wait_for(win, "!!document.querySelector('.viewer-img')"),
                wait_for(win, "document.body.innerText.includes('第 1 / 6 页')"),
            )[1],
        )

        # 3. 翻页
        def flip():
            click_button(win, "btn-next")
            wait_for(win, "document.body.innerText.includes('第 2 / 6 页')")

        record("翻页", flip)

        # 4. 放大一档（96+12=108dpi → Math.round(112.5)=113%）
        def zoom():
            click_button(win, "btn-zoom-in")
            wait_for(win, "document.body.innerText.includes('113%')")

        record("缩放", zoom)

        # 5. 分割对话框：回第 1 页，水平二等分
        def split():
            click_button(win, "btn-prev")
            wait_for(win, "document.body.innerText.includes('第 1 / 6 页')")
            click_button(win, "btn-split")
            wait_for(win, "!!document.querySelector('.ant-modal')")
            wait_for(win, "!!document.querySelector('.split-canvas img')", deadline_s=20)
            ok = js(
                win,
                """(() => {
                    const btns = [...document.querySelectorAll('.ant-modal .ant-btn')];
                    const ok = btns.find(b => b.textContent.trim() === '分割');
                    if (!ok || ok.disabled) return false;
                    ok.click();
                    return true;
                })()""",
            )
            if ok is not True:
                raise AssertionError(f"分割按钮不可点: {ok!r}")
            wait_for(win, "document.querySelectorAll('.thumb-item').length === 7")
            wait_for(win, "document.body.innerText.includes('1a')")

        record("水平二等分分割", split)

        # 6. 保存 → 落盘 7 页
        def save():
            click_button(win, "btn-save")
            deadline = time.time() + 15
            while not saved.exists() and time.time() < deadline:
                time.sleep(0.2)
            if not saved.exists():
                raise AssertionError("保存文件未生成")
            from pypdf import PdfReader

            reader = PdfReader(str(saved))
            if len(reader.pages) != 7:
                raise AssertionError(f"保存后页数错误: {len(reader.pages)}")

        record("保存落盘 7 页", save)

        # 7. 提取页面：输入页码 "1,3" → 导出 2 页新 PDF
        def extract():
            click_button(win, "btn-extract")
            wait_for(win, "!!document.querySelector('.ant-modal')")
            # 切到「输入页码」模式
            ok = js(
                win,
                """(() => {
                    const radios = [...document.querySelectorAll(
                        '.ant-modal .ant-radio-button-wrapper')];
                    const r = radios.find(el => el.textContent.includes('输入页码'));
                    if (!r) return false;
                    r.click();
                    return true;
                })()""",
            )
            if ok is not True:
                raise AssertionError(f"无法切换到输入页码模式: {ok!r}")
            # React 受控输入：原生 setter + input 事件
            ok = js(
                win,
                """(() => {
                    const input = document.querySelector(
                        'input[data-testid="extract-page-input"]');
                    if (!input) return false;
                    const setter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    setter.call(input, '1,3');
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    return true;
                })()""",
            )
            if ok is not True:
                raise AssertionError("找不到页码输入框")
            # 选保存路径（stub 返回 extracted.pdf）
            click_modal_button(win, "选择保存路径")
            wait_for(win, "document.body.innerText.includes('extracted.pdf')")
            # 页脚按钮此时显示「提取（2 页）」
            click_modal_button(win, "提取（2 页）")
            deadline = time.time() + 15
            while not extracted.exists() and time.time() < deadline:
                time.sleep(0.2)
            if not extracted.exists():
                raise AssertionError("提取文件未生成")
            from pypdf import PdfReader

            reader = PdfReader(str(extracted))
            if len(reader.pages) != 2:
                raise AssertionError(f"提取页数错误: {len(reader.pages)}")

        record("提取页码 1,3 → 2 页新 PDF", extract)

        # 8. 转扫描件：全部 7 页 → 白底黑字扫描件落盘
        def scan():
            click_button(win, "btn-scan")
            wait_for(win, "!!document.querySelector('.ant-modal')")
            click_modal_button(win, "选择保存路径")
            wait_for(win, "document.body.innerText.includes('scanned.pdf')")
            click_modal_button(win, "开始转换")
            deadline = time.time() + 60
            while not scanned.exists() and time.time() < deadline:
                time.sleep(0.3)
            if not scanned.exists():
                raise AssertionError("扫描件未生成（60s 超时）")
            import pymupdf

            doc = pymupdf.open(str(scanned))
            n = doc.page_count
            doc.close()
            if n != 7:
                raise AssertionError(f"扫描件页数错误: {n}")

        record("转扫描件 7 页落盘", scan)

    exit_code = 0

    def wrapper():
        nonlocal exit_code
        win = webview.windows[0]
        try:
            time.sleep(1.0)  # 等待页面首次渲染
            run(win)
        except Exception:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            exit_code = 1
        finally:
            print("\n===== E2E 结果 =====")
            for name, ok_, err in checks:
                print(f"  [{'PASS' if ok_ else 'FAIL'}] {name}" + (f" — {err}" if err else ""))
            failed = [c for c in checks if not c[1]]
            print(f"总计 {len(checks)} 项，失败 {len(failed)} 项")
            win.destroy()

    webview.start(wrapper)
    server.shutdown()
    all_passed = exit_code == 0 and checks and all(ok_ for _, ok_, _ in checks)
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
