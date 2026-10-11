"""WordToPdfConverter：Word 转 PDF（LibreOffice soffice 子进程）。"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

from ..utils.paths import find_soffice, resolve_input_path
from .exceptions import ConversionError

logger = logging.getLogger(__name__)


class WordToPdfConverter:
    """通过 LibreOffice 的 soffice 命令行把 .docx 转换为 PDF。"""

    def convert(
        self,
        docx_path: Path,
        out_dir: Path,
        timeout_s: int = 120,
        progress_cb: Callable[[str], None] | None = None,
    ) -> Path:
        """调用 soffice 把 docx 转换为 PDF，返回生成的 PDF 路径。

        - soffice 定位集中在 utils/paths.find_soffice()；
        - 子进程使用 list 参数（禁止 shell=True，避免中文/空格路径问题）；
        - --convert-to 用 pdf:writer_pdf_Export 保证稳定；
        - 非零返回码或超时抛 ConversionError；找不到 soffice 抛 SofficeNotFoundError。
        """
        src = resolve_input_path(docx_path)
        if not src.is_file():
            raise ConversionError(f"Word 文档不存在: {src}")
        if src.suffix.lower() not in (".docx", ".doc"):
            raise ConversionError(f"仅支持 .docx/.doc 文件: {src.name}")

        dest_dir = Path(out_dir)
        if not dest_dir.is_dir():
            raise ConversionError(f"输出目录不存在: {dest_dir}")

        if progress_cb is not None:
            progress_cb("正在定位 LibreOffice...")
        soffice = find_soffice()  # SofficeNotFoundError 向上传播

        args = [
            str(soffice),
            "--headless",
            "--norestore",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(dest_dir),
            str(src),
        ]
        if progress_cb is not None:
            progress_cb("正在启动 soffice 转换...")
        logger.info("执行 soffice 转换: %s", " ".join(args))

        try:
            proc = subprocess.run(  # noqa: S603 — 固定参数列表，无 shell
                args,
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            logger.error("soffice 转换超时（%ss）: %s", timeout_s, e)
            raise ConversionError(f"转换超时（{timeout_s}s）") from e
        except OSError as e:
            raise ConversionError(f"无法启动 soffice: {e}") from e

        stderr_text = proc.stderr.decode("utf-8", errors="replace").strip()
        if stderr_text:
            logger.info("soffice stderr: %s", stderr_text)

        if proc.returncode != 0:
            raise ConversionError(
                f"soffice 转换失败（返回码 {proc.returncode}）: {stderr_text or '无错误输出'}"
            )

        expected = dest_dir / (src.stem + ".pdf")
        if not expected.is_file():
            raise ConversionError(
                f"转换已执行但未找到输出文件: {expected}。stderr: {stderr_text or '无'}"
            )
        if progress_cb is not None:
            progress_cb("转换完成")
        return expected
