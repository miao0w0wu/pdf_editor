"""路径工具：soffice 定位、输入/输出路径规范化校验。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..core.exceptions import PdfOpenError, PdfWriteError, SofficeNotFoundError

# spec 第 5.4 节规定的查找顺序
_WINDOWS_CANDIDATES = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]

_LINUX_CANDIDATES = [
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "/snap/bin/soffice",
]


def find_soffice() -> Path:
    """定位 LibreOffice 的 soffice 可执行文件。

    优先级：
    1. 环境变量 SOFFICE_PATH（最高，方便用户覆盖）
    2. Windows 常见安装路径
    3. Linux：shutil.which 与常见路径
    找不到时抛 SofficeNotFoundError。
    """
    env = os.environ.get("SOFFICE_PATH")
    if env:
        p = Path(env)
        if p.is_file():
            return p
        raise SofficeNotFoundError(f"环境变量 SOFFICE_PATH 指向的文件不存在: {env}")

    import sys

    if sys.platform == "win32":
        for cand in _WINDOWS_CANDIDATES:
            p = Path(cand)
            if p.is_file():
                return p
    else:
        which = shutil.which("soffice")
        if which:
            return Path(which)
        for cand in _LINUX_CANDIDATES:
            p = Path(cand)
            if p.is_file():
                return p
        # /opt/libreoffice*/program/soffice 通配
        for p in Path("/opt").glob("libreoffice*/program/soffice"):
            if p.is_file():
                return p

    raise SofficeNotFoundError(
        "未找到 LibreOffice (soffice)。请安装 LibreOffice，"
        "或设置环境变量 SOFFICE_PATH 指向 soffice 可执行文件。"
    )


def _check_raw_path(raw: str, kind: str) -> None:
    """路径字符串基础校验：非空、无空字节。"""
    label = "输出路径" if kind == "out" else "输入路径"
    exc = PdfWriteError if kind == "out" else PdfOpenError
    if not raw.strip():
        raise exc(f"{label}为空")
    if "\x00" in raw:
        raise exc(f"{label}包含非法字符")


def safe_output_path(target: str | Path) -> Path:
    """规范化并校验输出路径。

    - 基础校验（非空、无空字节）；
    - 解析相对分量（折叠 ``..``、``.``、双分隔符），得到绝对路径，
      防止相对分量逃逸到预期目录之外；
    - 拒绝指向已存在目录的路径。
    上层（api 层）只应传入原生保存对话框返回的路径。
    """
    raw = str(target)
    _check_raw_path(raw, "out")
    p = Path(raw).expanduser().resolve()
    if p.is_dir():
        raise PdfWriteError(f"输出路径是目录: {p}")
    return p


def resolve_input_path(path: str | Path) -> Path:
    """规范化并校验待打开的输入路径。

    - 基础校验（非空、无空字节）；
    - 解析相对分量（折叠 ``..`` 等）后再交给调用方做存在性判断。
    """
    raw = str(path)
    _check_raw_path(raw, "in")
    return Path(raw).expanduser().resolve()
