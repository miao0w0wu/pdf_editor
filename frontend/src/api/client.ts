/**
 * pywebview JS Bridge 封装：唯一允许接触 window.pywebview.api 的模块。
 *
 * - invoke()：统一解包后端信封，ok=false 时抛出带 code 的 ApiError；
 * - pywebviewready 之前调用会排队，组件无需关心启动时序（spec 5.6）；
 * - subscribe()：订阅后端 evaluate_js 推送的事件（window.__backend 分发器）。
 */
import type {
  BackendEvent,
  Envelope,
} from "../types";

export class ApiError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
  }
}

type BridgeApi = Record<string, Record<string, (...args: unknown[]) => Promise<Envelope>>>;

declare global {
  interface Window {
    pywebview?: { api: BridgeApi };
    __backend?: { dispatch: (event: BackendEvent) => void };
  }
}

type EventListener = (event: BackendEvent) => void;

// ---------- 事件分发器（后端 evaluate_js 调用入口） ----------

const listeners = new Set<EventListener>();

function ensureDispatcher(): void {
  if (window.__backend) return;
  window.__backend = {
    dispatch: (event: BackendEvent) => {
      listeners.forEach((fn) => {
        try {
          fn(event);
        } catch (e) {
          console.error("事件监听器异常", e);
        }
      });
    },
  };
}

export function subscribe(listener: EventListener): () => void {
  ensureDispatcher();
  listeners.add(listener);
  return () => listeners.delete(listener);
}

// ---------- pywebviewready 等待与调用排队 ----------

let readyPromise: Promise<void> | null = null;

export function pywebviewReady(): Promise<void> {
  if (readyPromise) return readyPromise;
  readyPromise = new Promise<void>((resolve) => {
    if (window.pywebview && window.pywebview.api) {
      resolve();
      return;
    }
    window.addEventListener("pywebviewready", () => resolve(), { once: true });
  });
  return readyPromise;
}

function bridgeMethod(path: string[]): (...args: unknown[]) => Promise<Envelope> {
  return async (...args: unknown[]) => {
    let node: unknown = (await pywebviewReady(), window.pywebview?.api);
    for (const key of path) {
      node = (node as Record<string, unknown>)?.[key];
    }
    if (typeof node !== "function") {
      throw new ApiError("BridgeError", `桥接方法不存在: ${path.join(".")}`);
    }
    return node(...args);
  };
}

/** 调用后端方法并解包信封；ok=false 时抛 ApiError（携带 code）。 */
export async function invoke<T>(method: string, ...args: unknown[]): Promise<T> {
  const path = method.split(".");
  const fn = bridgeMethod(path);
  const envelope = await fn(...args);
  if (envelope && envelope.ok === false) {
    const err = envelope.error ?? { code: "UnknownError", message: "未知错误" };
    throw new ApiError(err.code, err.message);
  }
  return (envelope ? envelope.data : undefined) as T;
}
