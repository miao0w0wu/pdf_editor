"""PyInstaller 打包专用入口。

PyInstaller 将入口脚本作为独立顶层模块执行（不处于 pdf_editor 包内），
`python -m pdf_editor` 使用的 __main__.py 相对导入在此不可用，
故用绝对导入并依赖 spec 的 pathex=['src'] 解析包。
"""

from __future__ import annotations

import sys

from pdf_editor.main import main

if __name__ == "__main__":
    sys.exit(main())
