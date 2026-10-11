/** zustand：DocumentState 镜像 + 选中集合 + 缩放 + 缩略图缓存 + 任务进度。
 *
 * 所有变更都来自 invoke 的返回值或后端事件，不做乐观更新（spec 5.6）。
 * 当前页锚定在稳定 page_id 上：删除/重排/分割后 source_index 会变，
 * page_id 不变（spec 第 4 节）。
 */

import { create } from "zustand";
import type { DocumentStatePayload, PageItemPayload } from "../types";

/** 一次转换任务的进度镜像（来自 conversion_progress / task_done / task_error 事件） */
export interface TaskInfo {
  taskId: string;
  kind: string;
  status: "running" | "done" | "error";
  stage?: string;
  done?: number;
  total?: number;
  result?: string; // task_done 推送的输出路径
  code?: string;
  message?: string;
}

interface DocumentStore {
  bridgeReady: boolean;
  sourcePath: string | null;
  pages: PageItemPayload[];
  selectedIds: Set<number>;
  currentPageId: number | null;
  zoom: number; // 渲染 DPI，36~150
  thumbnails: Record<number, string>; // key = source_index，值 = data URL
  tasks: Record<string, TaskInfo>;
  passwordPrompt: { path: string } | null;

  setBridgeReady: (ready: boolean) => void;
  setSourcePath: (path: string | null) => void;
  // 以后端返回的 DocumentState 为准，不做乐观更新
  applyDocumentState: (state: DocumentStatePayload) => void;
  resetDocument: () => void;
  toggleSelected: (pageId: number) => void;
  setSelected: (ids: number[]) => void;
  setCurrentPageId: (pageId: number) => void;
  setZoom: (dpi: number) => void;
  setThumbnail: (sourceIndex: number, dataUrl: string | null) => void;
  clearThumbnails: () => void;
  upsertTask: (info: Partial<TaskInfo> & { taskId: string }) => void;
  setPasswordPrompt: (prompt: { path: string } | null) => void;
}

const clampDpi = (dpi: number) => Math.max(36, Math.min(150, Math.round(dpi)));

export const useDocumentStore = create<DocumentStore>((set) => ({
  bridgeReady: false,
  sourcePath: null,
  pages: [],
  selectedIds: new Set<number>(),
  currentPageId: null,
  zoom: 96,
  thumbnails: {},
  tasks: {},
  passwordPrompt: null,

  setBridgeReady: (ready) => set({ bridgeReady: ready }),
  setSourcePath: (path) => set({ sourcePath: path }),
  applyDocumentState: (state) =>
    set((s) => {
      const pages = state.pages;
      const currentExists =
        s.currentPageId !== null && pages.some((p) => p.page_id === s.currentPageId);
      return {
        pages,
        selectedIds: new Set<number>(),
        // 当前页被删除/分割失效时回落到第一页
        currentPageId: currentExists ? s.currentPageId : (pages[0]?.page_id ?? null),
      };
    }),
  resetDocument: () =>
    set({
      sourcePath: null,
      pages: [],
      selectedIds: new Set<number>(),
      currentPageId: null,
      thumbnails: {},
    }),
  toggleSelected: (pageId) =>
    set((s) => {
      const next = new Set(s.selectedIds);
      if (next.has(pageId)) next.delete(pageId);
      else next.add(pageId);
      return { selectedIds: next };
    }),
  setSelected: (ids) => set({ selectedIds: new Set(ids) }),
  setCurrentPageId: (pageId) => set({ currentPageId: pageId }),
  setZoom: (dpi) => set({ zoom: clampDpi(dpi) }),
  setThumbnail: (sourceIndex, dataUrl) =>
    set((s) => {
      const thumbnails = { ...s.thumbnails };
      if (dataUrl === null) delete thumbnails[sourceIndex];
      else thumbnails[sourceIndex] = dataUrl;
      return { thumbnails };
    }),
  clearThumbnails: () => set({ thumbnails: {} }),
  upsertTask: (info) =>
    set((s) => {
      const prev = s.tasks[info.taskId];
      return {
        tasks: {
          ...s.tasks,
          [info.taskId]: { ...prev, ...info } as TaskInfo,
        },
      };
    }),
  setPasswordPrompt: (prompt) => set({ passwordPrompt: prompt }),
}));
