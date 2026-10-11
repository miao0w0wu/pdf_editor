# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（--onedir，无控制台）。

先构建前端，再打包：
    cd frontend && npm run build
    pyinstaller pdf_editor.spec --noconfirm

入口为 launcher.py（绝对导入；PyInstaller 把入口当独立顶层脚本执行，
不能用包内 __main__.py 的相对导入）。frontend/dist 被打入
_internal/frontend/dist，运行时由 main.py 的 _frontend_dist() 从
sys._MEIPASS 定位。
"""

import sys

hiddenimports = [
    # pywebview 按平台动态导入后端，PyInstaller 静态分析发现不了
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
]
if sys.platform != "win32":
    hiddenimports = ["webview.platforms.gtk"]

a = Analysis(
    ["launcher.py"],
    pathex=["src"],
    binaries=[],
    datas=[("frontend/dist", "frontend/dist")],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pdf-editor",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # 等价 --windowed，桌面应用不弹控制台
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="pdf-editor",
)
