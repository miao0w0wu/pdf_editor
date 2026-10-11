# PDF 编辑工具

跨平台（Linux / Windows）PDF 编辑桌面工具：Python 后端（业务逻辑）+ pywebview 窗口壳 + React 18 前端（Ant Design 5），前后端通过 pywebview JS Bridge 通信。

## 功能

| 模块 | 功能 |
|------|------|
| 阅读器 | 页面渲染显示、Ctrl+滚轮缩放（36~150 DPI）、翻页（按钮 / PageUp / PageDown / 方向键） |
| 页面操作 | 勾选删除、拖拽调整页序（@dnd-kit）、当前页分割（水平/垂直、2~6 段比例可调，保存时生效）、提取页面组成新 PDF（勾选或输入页码如 `1,3,5-8`） |
| 转换器 | 图片转 PDF（Pillow，多选、拖拽排序、auto/A4 + 边距）、Word 转 PDF（LibreOffice 子进程）、页面转扫描件（WPS 扫描件风格：自动裁出纸面并透视矫正，白底提亮、文字加深，保留签字/印章等灰阶内容；可调分辨率与去底强度） |
| 其它 | 缩略图侧栏（后台逐页生成）、导出所选页、加密 PDF 密码输入 |

所有编辑都是**非破坏性**的：只修改内存中的页面模型，点「保存」另存新文件时才落盘（默认不覆盖源文件）。

## 环境要求

| 依赖 | 说明 |
|------|------|
| Python ≥ 3.10 | 运行时 |
| Node ≥ 18 | 仅前端开发/构建期需要，运行时不需要 |
| LibreOffice | 可选；Word 转 PDF 需要（`soffice`），不装则该功能提示 `SofficeNotFoundError` |
| Windows | Win10 21H2+ 通常预装 Edge WebView2 Runtime。启动失败或白屏时安装微软官方离线包：<https://developer.microsoft.com/microsoft-edge/webview2/#download-section> |
| Linux | 需要 WebKitGTK 系统依赖，见下节 |

## Linux 系统依赖（首次运行前）

Debian / Ubuntu：

```bash
sudo apt install libwebkit2gtk-4.1-0 gir1.2-webkit2-4.1 python3-gi
```

Fedora：

```bash
sudo dnf install webkit2gtk4.1
```

无法安装时的兜底方案（QtWebEngine 后端，体积大，仅作备选）：

```bash
pip install pywebview[qt]
```

## 从源码运行

```bash
# 1. Python 依赖
pip install -e ".[dev]"

# 2. 前端依赖与构建（生产模式需要）
cd frontend
npm install
npm run build
cd ..

# 3. 启动（托管 frontend/dist）
python -m pdf_editor
```

开发模式（前端 HMR）：

```bash
# 终端 1
cd frontend && npm run dev        # Vite dev server @ 5173
# 终端 2
PYTHONPATH=src python -m pdf_editor --dev   # 窗口加载 http://localhost:5173
```

Windows 上若 `python` 指向 Microsoft Store 占位符，请使用 `py` launcher（如 `py -m pdf_editor`）。

## 打包（PyInstaller）

```bash
cd frontend && npm run build && cd ..
pyinstaller pdf_editor.spec --noconfirm

py -m pdf_editor
py -m pytest tests/
py -m ruff check src tests scripts launcher.py
# 产物：dist/pdf-editor/pdf-editor(.exe)（onedir 模式，整目录分发）
```

Linux 下同样的 spec 可用（pywebview 后端 hiddenimports 按 `sys.platform` 自动切换为 gtk）。

## 测试与质量

```bash
PYTHONPATH=src python -m pytest tests/     # 单元测试（Word 转换在无 soffice 环境自动 skip）
PYTHONPATH=src python -m ruff check src tests scripts launcher.py
PYTHONPATH=src python -m mypy              # core/models/utils 层 strict 检查
cd frontend && npm run lint                # 前端 eslint（react-hooks 严格规则）
# 真实窗口 E2E 冒烟（打开 → 缩略图 → 翻页缩放 → 分割 → 保存落盘 → 提取页面 → 转扫描件）：
PYTHONPATH=src python scripts/e2e_smoke.py
```

## Word 转 PDF 注意事项

- 转换由 `soffice --headless --convert-to pdf` 子进程完成，依赖本机 LibreOffice 版本的保真度，`.docx` 效果最佳。
- 未安装 LibreOffice 时会给出明确错误提示；也可用环境变量 `SOFFICE_PATH` 指向 soffice 可执行文件覆盖自动定位。

## 已知限制

- 分割后的子页在保存前显示为原页整页内容（非破坏性编辑，落盘时才真正裁剪）。
- 转扫描件会把页面栅格化成位图（文字不再可选/可搜索），输出分辨率 150/200/300 DPI 可选；输出始终为新文件，不改动原 PDF。
- WebView 内拖放文件拿不到真实路径，文件导入一律走原生文件对话框（spec 第 12 节）。
- 渲染使用 PyMuPDF（AGPL）；如需更换许可，`PdfRenderer` 为独立适配器，可整体替换为 pdfium2 而不影响其它层。

## 目录结构

```
pdf_editor/
├── pyproject.toml            # Python 依赖与 pytest/ruff/mypy 配置
├── pdf_editor.spec           # PyInstaller 打包配置
├── launcher.py               # 打包专用入口（绝对导入）
├── src/pdf_editor/           # 后端：core(纯逻辑) / models / api(桥接) / utils
├── frontend/                 # React 18 + TS + antd5 + dnd-kit + zustand（Vite 工程）
├── tests/                    # pytest（core/api 层）
└── scripts/e2e_smoke.py      # 真实窗口 E2E 冒烟
```
