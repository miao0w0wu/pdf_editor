/** 主阅读区：当前页大图渲染、缩放（Ctrl+滚轮 → DPI）、翻页、懒加载。
 *
 * 渲染统一走后端 render_page（base64 PNG），前端只做小容量缓存与
 * 加载态；缩放级别即渲染 DPI（36~150，spec 5.2），变更 300ms 防抖
 * 后重新请求；翻页立即请求不防抖。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Empty, Skeleton, Space, Tooltip, Typography } from "antd";
import {
  LeftOutlined,
  RightOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from "@ant-design/icons";
import { invoke } from "../api/client";
import { useDocumentStore } from "../store/document";

const DPI_STEP = 12;

interface ViewerPage {
  pageId: number;
  sourceIndex: number;
  label: string;
}

export function ViewerPanel() {
  const pages = useDocumentStore((s) => s.pages);
  const currentPageId = useDocumentStore((s) => s.currentPageId);
  const zoom = useDocumentStore((s) => s.zoom);
  const setZoom = useDocumentStore((s) => s.setZoom);
  const setCurrentPageId = useDocumentStore((s) => s.setCurrentPageId);
  const sourcePath = useDocumentStore((s) => s.sourcePath);

  const index = pages.findIndex((p) => p.page_id === currentPageId);
  const current: ViewerPage | null =
    index >= 0 ? { pageId: pages[index].page_id, sourceIndex: pages[index].source_index, label: pages[index].label } : null;

  const [rendered, setRendered] = useState<{ key: string; url: string } | null>(null);
  // 渲染结果缓存（state 而非 ref：渲染期要读取做派生显示）
  const [cache, setCache] = useState<Map<string, string>>(() => new Map());
  const scrollRef = useRef<HTMLDivElement>(null);

  // 切换文档时清空缓存与旧图（渲染期调整状态，React 官方推荐模式）
  const [prevSource, setPrevSource] = useState(sourcePath);
  if (prevSource !== sourcePath) {
    setPrevSource(sourcePath);
    setCache(new Map());
    setRendered(null);
  }

  const sourceIndex = current?.sourceIndex;
  const currentKey = sourceIndex !== undefined ? `${sourceIndex}@${zoom}` : null;

  // 显示优先级：缓存命中 > 当前键结果 > 同页旧图（缩放过渡）> 骨架
  const cachedUrl = currentKey ? cache.get(currentKey) : undefined;
  const samePage =
    rendered !== null && currentKey !== null && rendered.key.split("@")[0] === currentKey.split("@")[0];
  const shownUrl =
    cachedUrl ??
    (rendered !== null && currentKey !== null && rendered.key === currentKey ? rendered.url || null : null) ??
    (rendered !== null && samePage ? rendered.url || null : null);
  const loading = currentKey !== null && !shownUrl;

  // 未命中时请求渲染：仅缩放防抖 300ms，翻页立即
  useEffect(() => {
    if (currentKey === null || sourceIndex === undefined) return;
    if (cache.has(currentKey)) return;
    if (rendered !== null && rendered.key === currentKey) return; // 已有结果（含失败标记）
    const delay =
      rendered !== null && rendered.key.split("@")[0] === currentKey.split("@")[0] ? 300 : 0;
    let cancelled = false;
    const timer = setTimeout(() => {
      invoke<string>("document.render_page", sourceIndex, zoom)
        .then((url) => {
          if (cancelled) return;
          setCache((prev) => {
            const next = new Map(prev);
            next.delete(currentKey); // 重新插入到末尾，实现 LRU 触碰
            next.set(currentKey, url);
            while (next.size > 16) {
              const oldest = next.keys().next().value;
              if (oldest === undefined) break;
              next.delete(oldest);
            }
            return next;
          });
          setRendered({ key: currentKey, url });
        })
        .catch((e) => {
          console.error("渲染失败", e);
          if (!cancelled) setRendered({ key: currentKey, url: "" }); // 空串标记失败
        });
    }, delay);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [currentKey, sourceIndex, zoom, rendered, cache]);

  // Ctrl+滚轮缩放：React 合成事件无法可靠 preventDefault，用原生监听
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return;
      e.preventDefault();
      const next = useDocumentStore.getState().zoom + (e.deltaY < 0 ? DPI_STEP : -DPI_STEP);
      setZoom(next);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [setZoom]);

  const goTo = useCallback(
    (i: number) => {
      const target = pages[i];
      if (target) setCurrentPageId(target.page_id);
    },
    [pages, setCurrentPageId],
  );

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!current) return;
    if (e.key === "PageDown" || e.key === "ArrowRight") goTo(Math.min(index + 1, pages.length - 1));
    else if (e.key === "PageUp" || e.key === "ArrowLeft") goTo(Math.max(index - 1, 0));
    else if (e.key === "Home") goTo(0);
    else if (e.key === "End") goTo(pages.length - 1);
    else return;
    e.preventDefault();
  };

  const zoomPercent = Math.round((zoom / 96) * 100);

  if (!current) {
    return (
      <div className="viewer-root">
        <div className="viewer-empty">
          <Empty description={sourcePath ? "文档加载中…" : "尚未打开文档"} />
          {!sourcePath && (
            <Typography.Text type="secondary">点击上方「打开」选择 PDF 文件</Typography.Text>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="viewer-root">
      <div
        ref={scrollRef}
        className="viewer-scroll"
        tabIndex={0}
        onKeyDown={onKeyDown}
        data-testid="viewer-scroll"
      >
        {loading && (
          <div className="viewer-skeleton">
            <Skeleton.Image active style={{ width: 480, height: 640 }} />
          </div>
        )}
        {shownUrl && (
          <img
            key={currentKey ?? undefined}
            src={shownUrl}
            alt={`第 ${current.label} 页`}
            className="viewer-img"
            draggable={false}
          />
        )}
      </div>
      <div className="viewer-statusbar">
        <Space>
          <Tooltip title="上一页（PageUp）">
            <Button
              data-testid="btn-prev"
              size="small"
              icon={<LeftOutlined />}
              disabled={index <= 0}
              onClick={() => goTo(index - 1)}
            />
          </Tooltip>
          <Typography.Text>
            第 {index + 1} / {pages.length} 页（{current.label}）
          </Typography.Text>
          <Tooltip title="下一页（PageDown）">
            <Button
              data-testid="btn-next"
              size="small"
              icon={<RightOutlined />}
              disabled={index >= pages.length - 1}
              onClick={() => goTo(index + 1)}
            />
          </Tooltip>
        </Space>
        <Space>
          <Tooltip title="缩小（Ctrl+滚轮）">
            <Button
              size="small"
              icon={<ZoomOutOutlined />}
              onClick={() => setZoom(zoom - DPI_STEP)}
            />
          </Tooltip>
          <Typography.Text style={{ width: 48, textAlign: "center" }}>
            {zoomPercent}%
          </Typography.Text>
          <Tooltip title="放大（Ctrl+滚轮）">
            <Button
              data-testid="btn-zoom-in"
              size="small"
              icon={<ZoomInOutlined />}
              onClick={() => setZoom(zoom + DPI_STEP)}
            />
          </Tooltip>
        </Space>
      </div>
    </div>
  );
}
