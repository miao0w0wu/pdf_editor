/** 缩略图侧栏：批量缩略图展示（后端逐页推送）、勾选删除、dnd-kit 拖拽排序。
 *
 * 拖拽 drop 后把新 page_id 顺序提交 reorder_pages，以后端返回的
 * DocumentState 为准更新 store，不做乐观更新（spec 5.6）。
 * 缩略图按 source_index 缓存（分割子页与原页同源，显示同图）。
 */
import { useMemo } from "react";
import { useState } from "react";
import { App, Button, Checkbox, Skeleton, Typography } from "antd";
import { DeleteOutlined, HolderOutlined } from "@ant-design/icons";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { PageItemPayload } from "../types";
import { errorMessage, reorderPages, deleteSelected } from "../api/commands";
import { useDocumentStore } from "../store/document";

function SortableThumb({
  page,
  isCurrent,
  selected,
}: {
  page: PageItemPayload;
  isCurrent: boolean;
  selected: boolean;
}) {
  const thumbnail = useDocumentStore((s) => s.thumbnails[page.source_index]);
  const toggleSelected = useDocumentStore((s) => s.toggleSelected);
  const setCurrentPageId = useDocumentStore((s) => s.setCurrentPageId);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: page.page_id,
  });

  return (
    <div
      ref={setNodeRef}
      className={`thumb-item${isCurrent ? " thumb-current" : ""}`}
      style={{
        transform: transform ? CSS.Transform.toString(transform) : undefined,
        transition,
        zIndex: isDragging ? 10 : undefined,
        opacity: isDragging ? 0.85 : undefined,
      }}
      onClick={() => setCurrentPageId(page.page_id)}
    >
      <span
        className="thumb-handle"
        title="拖拽排序"
        {...attributes}
        {...listeners}
        onClick={(e) => e.stopPropagation()}
      >
        <HolderOutlined />
      </span>
      <Checkbox
        className="thumb-check"
        checked={selected}
        onClick={(e) => e.stopPropagation()}
        onChange={() => toggleSelected(page.page_id)}
      />
      <div className="thumb-box">
        {thumbnail ? (
          <img src={thumbnail} alt={`第 ${page.label} 页`} draggable={false} />
        ) : (
          <Skeleton.Image active style={{ width: 120, height: 160 }} />
        )}
      </div>
      <div className="thumb-label">{page.label}</div>
    </div>
  );
}

export function ThumbnailGrid() {
  const pages = useDocumentStore((s) => s.pages);
  const selectedIds = useDocumentStore((s) => s.selectedIds);
  const currentPageId = useDocumentStore((s) => s.currentPageId);
  const setSelected = useDocumentStore((s) => s.setSelected);
  const { message, modal } = App.useApp();
  const [deleting, setDeleting] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const pageIds = useMemo(() => pages.map((p) => p.page_id), [pages]);
  const allSelected = pages.length > 0 && selectedIds.size === pages.length;

  const onDragEnd = (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const from = pageIds.indexOf(active.id as number);
    const to = pageIds.indexOf(over.id as number);
    if (from < 0 || to < 0) return;
    reorderPages(arrayMove(pageIds, from, to)).catch((err) => {
      void message.error(`重排失败：${errorMessage(err)}`);
    });
  };

  const onDeleteSelected = () => {
    const ids = [...selectedIds];
    modal.confirm({
      title: `删除选中的 ${ids.length} 页？`,
      content: "仅在内存中删除，不重新保存不会影响磁盘文件。",
      okText: "删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        setDeleting(true);
        try {
          await deleteSelected();
          void message.success(`已删除 ${ids.length} 页`);
        } catch (err) {
          void message.error(`删除失败：${errorMessage(err)}`);
        } finally {
          setDeleting(false);
        }
      },
    });
  };

  return (
    <div className="thumb-panel">
      <div className="thumb-toolbar">
        <Checkbox
          checked={allSelected}
          indeterminate={selectedIds.size > 0 && !allSelected}
          disabled={pages.length === 0}
          onChange={(e) => setSelected(e.target.checked ? pages.map((p) => p.page_id) : [])}
        >
          全选
        </Checkbox>
        <Button
          size="small"
          danger
          icon={<DeleteOutlined />}
          disabled={selectedIds.size === 0}
          loading={deleting}
          onClick={onDeleteSelected}
        >
          删除所选{selectedIds.size > 0 ? `（${selectedIds.size}）` : ""}
        </Button>
      </div>
      <Typography.Text type="secondary" className="thumb-hint">
        拖动 ⠿ 调整页序，点击查看
      </Typography.Text>
      <div className="thumb-list">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={pageIds} strategy={verticalListSortingStrategy}>
            {pages.map((page) => (
              <SortableThumb
                key={page.page_id}
                page={page}
                isCurrent={page.page_id === currentPageId}
                selected={selectedIds.has(page.page_id)}
              />
            ))}
          </SortableContext>
        </DndContext>
      </div>
    </div>
  );
}
