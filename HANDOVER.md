# PDF 编辑工具 — 开发交接文档

> 初版交接日期：2026-10-10；最近更新：2026-10-11
> 依据文档：`PDF_EDITOR_SPEC.md`（本项目唯一开发依据，接手前必须通读）
> 项目路径：`D:\project\python\pdf_editor\`

---

## 1. 项目概述

跨平台（Linux/Windows）PDF 编辑桌面工具：Python 后端（业务逻辑）+ pywebview 窗口壳 + React 前端（Ant Design 5），前后端通过 pywebview JS Bridge 通信。

功能模块：阅读器（渲染/缩放/翻页）、页面操作（分割/删除/拖拽排序/提取页面）、转换器（图片转 PDF、Word 转 PDF、页面转扫描件）。

## 2. 当前进度总览（2026-10-11）

| 阶段 | 内容 | 状态 |
|------|------|------|
| P0 | 环境准备（依赖安装） | ✅ 完成 |
| P1 | 骨架：core/api/main + frontend 脚手架 + E2E ping | ✅ 完成 |
| P2 | 渲染与阅读：render_page + ViewerPanel（缩放/翻页/懒加载）+ 缩略图事件 | ✅ 完成（真实窗口 E2E 验证） |
| P3 | 拖拽与分割：dnd-kit 排序 → reorder、SplitDialog → split | ✅ 完成（E2E：分割后保存落盘 7 页验证） |
| P4 | 转换器 dialog 组件 + 进度事件 + 密码弹窗 | ✅ 完成（代码完成；真实 soffice 转换未验——本机无 LibreOffice） |
| P5 | 收尾：static_server ✅、README ✅、PyInstaller ✅（Windows 实测打包+启动） | ✅ 完成 |
| P6 | 提取页面（勾选/页码输入 → 新 PDF）+ 转扫描件（背景压平白底黑字） | ✅ 完成（单测 14 项 + 真实窗口 E2E 验证） |

**质量门禁全绿**：pytest 72 passed / 2 skipped（无 soffice 环境 skip）；ruff（src/tests/scripts/launcher.py）零错误；mypy --strict（core/models/utils 12 文件）零错误；前端 tsc --noEmit 零错误；前端 eslint（react-hooks 严格规则）零错误；E2E 冒烟 8/8。

## 3. 环境说明（本机）

| 项 | 值 |
|----|-----|
| Python | 3.14.7，用 `py` launcher 调用；**Git Bash 里 `py` 不可用，用 `py.cmd`** |
| Node | v24.21.0 / npm 12.0.2（仅前端构建期需要） |
| 已装 Python 包 | pypdf 6.20.0、PyMuPDF 1.28.2、Pillow 12.3.0、pywebview 5.x、numpy、opencv-python 5.0.0（转扫描件纸面检测用；headless 变体等价可替换）、pytest 9.1.1、pytest-cov、ruff、mypy、pyinstaller 6.22.3 |
| 运行测试 | 在 `pdf_editor/` 下执行 `PYTHONPATH=src py.cmd -m pytest tests/` |
| LibreOffice | 本机**未安装**，soffice 相关测试自动 skip（2 个） |
| 前端 lint | `cd frontend && npm run lint`（eslint 10 + typescript-eslint + eslint-plugin-react-hooks@7） |

注意：`pip --version` 显示 pip 26.2.1，安装包用 `py.cmd -m pip install ...`。

## 4. 文件清单（本次新增/改动）

### 后端

```
src/pdf_editor/
├── __main__.py                  # ★ 新增：python -m pdf_editor 入口（此前缺失，-m 方式实际跑不通）
├── api/
│   ├── dialog_api.py            # ★ 新增 pick_output_directory()（FOLDER_DIALOG，Word 转换选输出目录）
│   ├── converter_api.py         # ★ P6 改动：+convert_pages_to_scan 任务（注入 service/scan_converter）
│   └── （其余 P1 已交付）
├── core/pdf_renderer.py         # ★ 改动：加 threading.Lock（PyMuPDF 非线程安全，缩略图线程与 JS API 线程并发）
├── core/scan_converter.py       # ★ P6 新增：ScanConverter 页面转扫描件（背景估计+相减二值化）
├── core/pdf_document.py         # ★ P6 改动：+source_path/source_password 属性、+page_source_info()
└── core/image_converter.py      # ★ 改动：Image.LANCZOS → Image.Resampling.LANCZOS（mypy）
```

### 前端（P2~P4 全部）

```
frontend/src/
├── api/commands.ts              # ★ 新增：组合命令层（open/save/delete/reorder/split + 对话框编排 + 防覆盖源文件）
├── api/client.ts                # P1 已交付（invoke 解包 + pywebviewready 排队 + 事件订阅）
├── store/document.ts            # ★ 重写：+缩略图缓存(source_index 键)、任务进度镜像、密码弹窗状态、setSelected
├── types.ts                     # ★ +ConverterTaskHandle
├── components/
│   ├── BackendEvents.tsx        # ★ 新增：全局事件订阅→store+toast（须挂在 AntApp 内）
│   ├── ViewerPanel.tsx          # ★ 新增：渲染缓存(16条 LRU)、Ctrl+滚轮缩放(300ms 防抖)、翻页、Skeleton、键盘导航
│   ├── ThumbnailGrid.tsx        # ★ 新增：缩略图列表 + dnd-kit 排序 + 勾选删除（drop 后提交后端，不做乐观更新）
│   ├── Toolbar.tsx              # ★ 重写：打开/保存/导出所选/提取页面/分割/两转换/转扫描件全部接线 + 连接状态 Tag + data-testid
│   └── dialogs/
│       ├── SplitDialog.tsx      # ★ 新增：预览+水平/垂直+2~6 段比例；分割线语义=后端（horizontal 首段在底部）
│       ├── ImageToPdfDialog.tsx # ★ 新增：多选→拖拽排序→auto/A4+边距→保存路径→任务进度/取消→打开产物
│       ├── WordToPdfDialog.tsx  # ★ 新增：docx→输出目录→soffice 阶段进度（无取消，子进程不可中断）
│       ├── ExtractPagesDialog.tsx # ★ P6 新增：提取页面（勾选页面/输入页码 1,3,5-8 两模式）→ 新 PDF
│       ├── ScanDialog.tsx       # ★ P6 新增：转扫描件（全部/勾选/页码 + 分辨率/阈值 + 任务进度/取消）
│       └── PasswordDialog.tsx   # ★ 新增：加密 PDF 密码重试
├── eslint.config.js             # ★ 新增（spec 9 要求 eslint 零错误）
└── package.json                 # ★ +@dnd-kit/utilities 显式依赖、+lint 脚本、+eslint devDeps
```

### 工程化（P5）

```
pdf_editor.spec     # ★ PyInstaller --onedir/--windowed；入口 launcher.py；按平台注入 pywebview hiddenimports
launcher.py         # ★ 打包专用入口（绝对导入——PyInstaller 不能用包内 __main__.py 的相对导入）
README.md           # ★ 新增（Linux WebKitGTK 依赖、WebView2、运行/打包/测试说明）
scripts/e2e_smoke.py# ★ 真实窗口 E2E：stub 对话框 + evaluate_js 驱动 UI，6 项断言
```

### 核心公开接口（不变，照旧）

- `PdfDocumentService`：open/save/save_page_range/delete_pages/reorder_pages/split_page/split_at/close；属性 state/is_open；P6 增 `source_path`/`source_password` 属性与 `page_source_info(page_id)`
- `PdfRenderer`：open/page_count/render_page(source_index, dpi=96)/clear_cache/close
- `ImageToPdfConverter.convert(...)`、`WordToPdfConverter.convert(...)`、`ScanConverter.convert(...)`（P6）
- JsApi 根对象：`document.* / converter.* / dialog.*`，根上 `ping`/`api_version`；dialog 新增 `pick_output_directory`；converter 新增 `convert_pages_to_scan(page_ids, target, dpi, threshold)`（kind=`pages_to_scan`）

### 设计决策（新增，接续 P1 的 5 条）

6. **PdfRenderer 内部加锁**：PyMuPDF Document 非线程安全；P2 起缩略图后台线程与 JS API 线程并发访问同一文档，所有 doc 访问经 `_render_lock` 串行化。不改公开签名。
7. **保存防覆盖源文件**：`commands.saveDocumentAs` 默认名 `<源名>-edited.pdf`；前端 `samePath` 保守判断目标=源文件时抛 `SaveOverSource` 错误（pypdf/pymupdf 持有源文件句柄，就地覆盖会损坏后续渲染）。
8. **分割子页显示限制**：分割只改内存模型，render 走源文件，因此保存前子页/缩略图显示为原页整页内容（标签 a/b 区分），落盘才真正裁剪。已在 README「已知限制」注明。
9. **mypy 模块级放宽**：pyproject 对 `core.pdf_renderer` 单独关 `disallow_untyped_calls`/`warn_return_any`（PyMuPDF API 未完整标注类型），有注释说明，其余 core 仍 strict。
10. **前端 react-hooks 严格化**：eslint-plugin-react-hooks@7 的 `set-state-in-effect`/`refs` 规则强制了两个模式——任务结果从 store **派生**（`resultPath = task.status==="done" ? task.result : null`），弹窗重置/文档切换用**渲染期调整状态**（prevOpen/prevSource 对比模式），ViewerPanel 缓存用 state 而非 ref（渲染期要读）。
11. **扫描件算法（P6，2026-10-11 重写为 WPS 风格）**：渲染彩色位图 → 纸面检测（降采样图上 Otsu+形态学取最大亮区四角 → 四边向内吸附真实亮暗边界：逐点走查+滑动中位数剔离群+L1 拟合；仍压深色背景的区段整线内移，贴边≤4px 不算）→ 透视矫正裁出纸面（亮区≈整页的原生页面自动跳过裁剪）→ 逐通道大尺度高斯背景估计并相除提白（保留签字/印章灰阶与纸上宽黑条纹，不硬二值化）→ 黑白场拉伸（threshold 映射黑场）+ 轻度锐化。拍照页输出页面尺寸=纸面按 dpi 换算的物理尺寸；未裁剪页=裁剪区域 pt 尺寸。旧版"相减+阈值 ramp 二值化"会把照片四周深色背景反转成黑框、且丢失灰阶，已弃用。
12. **扫描件写出偏离"pypdf 负责写"**：pypdf 6.x 无图片嵌入 API（image_converter 已同款偏离改用 Pillow），ScanConverter 需要"图像页+精确 pt 尺寸"，用既有依赖 PyMuPDF 写出并在模块注释说明理由；mypy 对 `core.scan_converter` 放宽与 renderer 相同的两条规则（PyMuPDF API 未完整标注）。
13. **分割子页的扫描/后续渲染**：`PdfDocumentService.page_source_info(page_id)` 把 `_SplitSpec` 归一化为 mediabox 分数裁剪框（左下原点），ScanConverter 换算为 PyMuPDF 显示坐标 clip（按 /Rotate 0/90/180/270 四种映射），分割子页转扫描件只渲染可见区域。
14. **密码驻留**：`open()` 把密码存内存（`_password`），`source_password` 供转换器重新打开加密源文件使用；`close()` 清除。仅驻留内存、随会话销毁。
15. **页码输入语义（前端解析）**：`commands.parsePageNumbers` 把 "1,3,5-8"（支持全角逗号/分号/空白）按**当前页序 1-based** 解析为 page_id（与缩略图标签一致，分割子页算独立一页），升序去重；解析在前端做（UI 关切），后端只收 page_id。
16. **提取/扫描选路径与执行分离**：`pickExtractSaveTarget`/`pickScanSaveTarget` 只选路径（默认名 `<源名>-extract/-scan.pdf`，统一 `assertNotSourcePath` 防覆盖源文件），`writeExtractedPages`/`startScanConversion` 执行——避免"选完路径点开始时又弹一次路径框"。

## 5. 关键调试经验（新增踩坑）

### 5.1 前次遗留（仍适用）

- PDF 坐标原点左下、y 向上：水平对半分割后原页文本落在**下半**子页；验证分割用子页尺寸/渲染像素，别用 get_text。
- split 循环内多次取 `_next_page_id_locked()` 会导致子页 page_id 冲突——新逻辑沿用"循环外取号、循环内递增"。
- pypdf extract_text 可能把 "Page 1" 拆开，测试用 `Page\s*(\d+)`。
- Mimosa 安全 hook：拒绝 Bash heredoc 写源码（用 Write/Edit）；路径操作收敛在 utils/paths.py。

### 5.2 本次新增

- **PyInstaller 入口相对导入**：spec 入口若指向包内 `__main__.py`，运行时报 `attempted relative import with no known parent package`——PyInstaller 把入口当独立顶层脚本。解法：根目录 `launcher.py` 绝对导入 + spec `pathex=["src"]`。
- **缩放百分比断言**：96+12=108dpi → `Math.round(108/96*100)=113`（JS 四舍五入 .5 向上），E2E 断言写 113 不是 112。
- **antd Tooltip 不产生 title 属性**：按钮定位/E2E 用 `data-testid`（antd Button 透传），别依赖 tooltip。
- **stub 原生对话框做 E2E**：实例属性覆盖 `api.dialog.pick_pdf_file = lambda: {"ok": True, "data": path}`（返回**信封 dict**，与 client.ts 约定一致），即可用 `evaluate_js` 点按钮驱动全流程，绕开原生对话框无法自动化的问题。
- **React effect 依赖对象引用**：`current` 每轮渲染都是新对象，进依赖数组会造成反复请求——依赖只用原始值（sourceIndex/zoom），或用键控派生模式。
- **antd 按钮带动态计数后缀**：E2E 按文本点按钮要兼容前缀（「开始转换」实际渲染为「开始转换（7 页）」），`click_modal_button` 用精确+startsWith 双匹配。
- **React 受控输入的 E2E 赋值**：直接改 input.value 不触发 onChange；必须取原型 setter（`Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set`）再 `dispatchEvent(new Event('input',{bubbles:true}))`。
- **Git Bash 下 `py.cmd -c` 多行内联脚本静默失败**（无输出、exit 0）：复杂冒烟脚本写成 .py 文件再跑。

## 6. 待办工作明细

全部阶段（P1~P5）已交付。后续可选增强（均非验收缺口）：

- **Word 转 PDF 真实转换验证**：本机装 LibreOffice（或设 `SOFFICE_PATH`）后跑 `pytest tests/test_word_converter.py` 与 UI 实测。
- 拖放导入文件（检测 `File.path` 可用时启用，spec 12 预留）。
- 旋转功能（`rotation` 字段已预留）。
- 分割子页保存前按裁剪框预览渲染（需给 render_page 加可选裁剪参数，属接口扩展）。
- 前端 `client.ts` 解包逻辑的 vitest 单测（spec 建议，非强制）。
- 扫描件输出为位图页（文字不可选/不可搜索）；若要可搜索文本层需接 OCR，列为未来增强。
- vite build 827KB 单包警告（antd 体积），桌面应用可接受；要优化可加 manualChunks。

## 7. 验证方法

```bash
cd D:\project\python\pdf_editor
PYTHONPATH=src py.cmd -m pytest tests/          # 72 passed, 2 skipped
PYTHONPATH=src py.cmd -m ruff check src tests scripts launcher.py   # 全绿
PYTHONPATH=src py.cmd -m mypy                   # 12 文件零错误（配置在 pyproject）
cd frontend && npm run lint && npm run build    # eslint/tsc 零错误，产物 dist/
PYTHONPATH=src py.cmd scripts/e2e_smoke.py      # 真实窗口 E2E：8 项全过
py.cmd -m PyInstaller pdf_editor.spec --noconfirm   # 打包；产物 dist/pdf-editor/pdf-editor.exe
```

运行：开发 `cd frontend && npm run dev` + `PYTHONPATH=src py.cmd -m pdf_editor --dev`；生产 `PYTHONPATH=src py.cmd -m pdf_editor`。

E2E 覆盖点（2026-10-11 实测）：打开文档→6 缩略图渲染→主视图渲染+页码→翻页→放大 113%→水平二等分（7 页、当前页跳 1a）→保存落盘 pypdf 验证 7 页→输入页码 "1,3" 提取 2 页新 PDF→全部 7 页转扫描件落盘（含分割子页裁剪路径）。打包 exe 实测：静态服务器启动、进程存活。

## 8. 风险与备忘

- **本机无 LibreOffice**：Word 转 PDF 的真实转换测试被 skip，UI 流程代码已按事件协议实现（stage 进度 + task_done/task_error）。
- **PyMuPDF AGPL**：渲染收敛在 PdfRenderer 适配器（含线程锁），必要时整体换 pdfium2。
- **前端 payload 同步**：types.ts 手工维护；后端 payload 未再变更，P1~P4 接口已冻结。
- **epic 打包注意**：PyInstaller 产物含 `frontend/dist`（前端改版后必须重新 `npm run build` + 重新打包）。
