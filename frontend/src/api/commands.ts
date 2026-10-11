/** 组合命令层：对话框选择 + bridge 调用 + store 更新。
 *
 * 组件只调用这里的命令，不直接拼装 invoke 序列；
 * 失败时抛出（多为 ApiError），由调用方用 antd message 展示。
 */
import { invoke, ApiError } from "./client";
import type { DocumentStatePayload, PageItemPayload } from "../types";
import { useDocumentStore } from "../store/document";

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return String(e);
}

/** Windows/Unix 分隔符统一后比较路径（仅用于“别存回源文件”的保守判断）。 */
function samePath(a: string, b: string): boolean {
  const norm = (s: string) => s.replace(/[/\\]+/g, "\\").replace(/\\+$/, "").toLowerCase();
  return norm(a) === norm(b);
}

/** 打开指定路径的 PDF 并开始批量生成缩略图。 */
export async function openPdfAtPath(path: string, password?: string): Promise<void> {
  const store = useDocumentStore.getState();
  const state = await invoke<DocumentStatePayload>("document.open_document", path, password ?? null);
  store.applyDocumentState(state);
  store.clearThumbnails();
  store.setSourcePath(path);
  store.setPasswordPrompt(null);
  void invoke("converter.generate_thumbnails", 72).catch((e) => {
    // 缩略图失败不阻塞阅读，主视图仍可渲染
    console.error("generate_thumbnails 失败", e);
  });
}

/** 走原生对话框选 PDF 并打开；取消静默返回；加密 PDF 弹密码框。 */
export async function openPdfFromDialog(): Promise<void> {
  const path = await invoke<string | null>("dialog.pick_pdf_file");
  if (!path) return;
  try {
    await openPdfAtPath(path);
  } catch (e) {
    if (e instanceof ApiError && /加密|密码/.test(e.message)) {
      useDocumentStore.getState().setPasswordPrompt({ path });
      return;
    }
    throw e;
  }
}

/** 保存路径默认名：源文件名 + 后缀（避免误覆盖打开中的源文件）。 */
function defaultSaveName(suffix: string): string {
  const { sourcePath } = useDocumentStore.getState();
  if (!sourcePath) return `output${suffix}`;
  const base = sourcePath.replace(/[/\\]+$/, "").split(/[/\\]/).pop() ?? "output";
  const stem = base.replace(/\.pdf$/i, "");
  return `${stem}${suffix}`;
}

/** 保存到用户选择的目标路径，返回目标（取消返回 null）。 */
export async function saveDocumentAs(pageIds: number[] | null): Promise<string | null> {
  const target = await invoke<string | null>(
    "dialog.pick_save_pdf_path",
    defaultSaveName("-edited.pdf"),
  );
  if (!target) return null;
  assertNotSourcePath(target);
  if (pageIds === null) {
    await invoke("document.save_document", target);
  } else {
    await invoke("document.save_document_as", target, pageIds);
  }
  return target;
}

// ---------- 页码输入解析（提取/扫描对话框共用） ----------

/**
 * 把页码输入（如 "1,3,5-8"，逗号/分号/空白分隔，支持全角）解析为
 * page_id 列表。数字是当前页序中的 1-based 序号（与缩略图标签一致，
 * 分割子页也算独立一页）；输出按文档内位置升序去重。
 * 输入无效时抛 Error（message 为可直接展示的中文提示）。
 */
export function parsePageNumbers(input: string, pages: PageItemPayload[]): number[] {
  const total = pages.length;
  if (total === 0) throw new Error("尚未打开文档");
  const tokens = input.split(/[,，;；\s]+/).filter((t) => t.length > 0);
  if (tokens.length === 0) throw new Error("请输入页码，例如：1,3,5-8");

  const positions = new Set<number>();
  for (const token of tokens) {
    const range = token.match(/^(\d+)-(\d+)$/);
    if (range) {
      const from = Number(range[1]);
      const to = Number(range[2]);
      if (from < 1 || to > total || from > to) {
        throw new Error(`页码范围 "${token}" 无效（文档共 ${total} 页）`);
      }
      for (let p = from; p <= to; p += 1) positions.add(p);
      continue;
    }
    if (!/^\d+$/.test(token)) {
      throw new Error(`无法识别的页码 "${token}"`);
    }
    const p = Number(token);
    if (p < 1 || p > total) {
      throw new Error(`页码 ${p} 超出范围（文档共 ${total} 页）`);
    }
    positions.add(p);
  }
  return [...positions].sort((a, b) => a - b).map((pos) => pages[pos - 1].page_id);
}

/** 选择提取保存路径（仅选路径，写出由 writeExtractedPages 执行）。 */
export async function pickExtractSaveTarget(): Promise<string | null> {
  const target = await invoke<string | null>(
    "dialog.pick_save_pdf_path",
    defaultSaveName("-extract.pdf"),
  );
  if (target) assertNotSourcePath(target);
  return target;
}

/** 按给定 page_id 导出新 PDF（target 须来自 pickExtractSaveTarget）。 */
export async function writeExtractedPages(pageIds: number[], target: string): Promise<void> {
  assertNotSourcePath(target);
  await invoke("document.save_document_as", target, pageIds);
}

/** 选择扫描件保存路径（仅选路径，转换由 startScanConversion 发起）。 */
export async function pickScanSaveTarget(): Promise<string | null> {
  const target = await invoke<string | null>(
    "dialog.pick_save_pdf_path",
    defaultSaveName("-scan.pdf"),
  );
  if (target) assertNotSourcePath(target);
  return target;
}

/** 发起扫描件转换（后台任务），返回 task_id，进度经事件推送。 */
export async function startScanConversion(
  pageIds: number[],
  target: string,
  dpi: number,
  threshold: number,
): Promise<string> {
  const handle = await invoke<{ task_id: string }>(
    "converter.convert_pages_to_scan",
    pageIds,
    target,
    dpi,
    threshold,
  );
  return handle.task_id;
}

function assertNotSourcePath(target: string): void {
  const { sourcePath } = useDocumentStore.getState();
  if (sourcePath && samePath(sourcePath, target)) {
    // pypdf/pymupdf 持有源文件句柄，就地覆盖会损坏后续渲染
    throw new ApiError("SaveOverSource", "不能覆盖当前打开的文件，请另选保存位置");
  }
}

export async function deleteSelected(): Promise<void> {
  const { selectedIds } = useDocumentStore.getState();
  if (selectedIds.size === 0) return;
  const state = await invoke<DocumentStatePayload>("document.delete_pages", [...selectedIds]);
  useDocumentStore.getState().applyDocumentState(state);
}

export async function reorderPages(newOrder: number[]): Promise<void> {
  const state = await invoke<DocumentStatePayload>("document.reorder_pages", newOrder);
  useDocumentStore.getState().applyDocumentState(state);
}

export async function splitPage(
  pageId: number,
  mode: "horizontal" | "vertical",
  ratios: number[],
): Promise<DocumentStatePayload> {
  const state = await invoke<DocumentStatePayload>("document.split_page", pageId, mode, ratios);
  useDocumentStore.getState().applyDocumentState(state);
  return state;
}
