/** 与后端 payload 对应的 TS 类型（手工同步，参照 models/page_item.py::to_dict）。 */

export interface PageItemPayload {
  page_id: number;
  source_index: number;
  rotation: number;
  label: string;
}

export interface DocumentStatePayload {
  pages: PageItemPayload[];
}

/** 后端统一返回信封（spec 5.5） */
export interface Envelope<T = unknown> {
  ok: boolean;
  data?: T;
  error?: { code: string; message: string };
}

/** 后端事件（api/events.py 推送） */
export interface BackendEvent {
  type: "conversion_progress" | "thumbnails_ready" | "task_done" | "task_error";
  payload: Record<string, unknown>;
}

export interface ConversionProgressPayload {
  task_id: string;
  stage: string;
  done?: number;
  total?: number;
}

export interface ThumbnailsReadyPayload {
  task_id: string;
  index: number;
  data_url: string | null;
}

export interface TaskDonePayload {
  task_id: string;
  kind: string;
  result?: string;
}

export interface TaskErrorPayload {
  task_id: string;
  kind: string;
  code: string;
  message: string;
}

/** converter.convert_* / generate_thumbnails 的同步返回值 */
export interface ConverterTaskHandle {
  task_id: string;
  page_count?: number;
}
