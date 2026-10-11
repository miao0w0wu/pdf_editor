/** 提取页面对话框：把选中的页面导出为新 PDF 文件。
 *
 * 两种选择方式：勾选页面（用左侧缩略图的勾选状态）或直接输入页码
 * （如 "1,3,5-8"，按当前页序 1-based，与缩略图标签一致）。
 * 提取是同步操作（pypdf 写出很快），无任务事件。
 */
import { useState } from "react";
import { Alert, App, Button, Input, Modal, Radio, Space, Typography } from "antd";
import { FolderOpenOutlined } from "@ant-design/icons";
import {
  errorMessage,
  openPdfAtPath,
  parsePageNumbers,
  pickExtractSaveTarget,
  writeExtractedPages,
} from "../../api/commands";
import { useDocumentStore } from "../../store/document";

type SelectMode = "checked" | "input";

export function ExtractPagesDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { message } = App.useApp();
  const pages = useDocumentStore((s) => s.pages);
  const selectedIds = useDocumentStore((s) => s.selectedIds);

  const [mode, setMode] = useState<SelectMode>("checked");
  const [input, setInput] = useState("");
  const [target, setTarget] = useState<string | null>(null);
  const [resultPath, setResultPath] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  // 输入模式下的实时解析预览（错误只提示，不阻塞继续输入）
  let parsedIds: number[] | null = null;
  let parseError: string | null = null;
  if (mode === "input") {
    try {
      parsedIds = parsePageNumbers(input, pages);
      if (parsedIds.length === 0) parseError = "请输入页码，例如：1,3,5-8";
    } catch (e) {
      parseError = e instanceof Error ? e.message : String(e);
    }
  }

  const checkedIds = [...selectedIds];
  const effectiveIds = mode === "checked" ? checkedIds : parsedIds ?? [];
  const canStart = !running && target !== null && effectiveIds.length > 0 && parseError === null;

  // 关闭时重置本地状态（渲染期调整，props 变化时同步）
  const [prevOpen, setPrevOpen] = useState(open);
  if (prevOpen !== open) {
    setPrevOpen(open);
    if (!open) {
      setMode("checked");
      setInput("");
      setTarget(null);
      setResultPath(null);
      setRunning(false);
    }
  }

  const labelsOf = (ids: number[]) =>
    ids
      .map((id) => pages.find((p) => p.page_id === id)?.label ?? String(id))
      .join("、");

  const pickTarget = async () => {
    try {
      // 先做一次页码解析校验，避免选完路径才发现输入无效
      if (mode === "input") parsePageNumbers(input, pages);
      else if (checkedIds.length === 0) {
        void message.warning("请先在左侧缩略图勾选页面");
        return;
      }
      const picked = await pickExtractSaveTarget();
      if (picked) setTarget(picked);
    } catch (e) {
      void message.error(errorMessage(e));
    }
  };

  const start = async () => {
    if (!canStart || !target) return;
    setRunning(true);
    try {
      const ids = mode === "checked" ? checkedIds : parsePageNumbers(input, pages);
      await writeExtractedPages(ids, target);
      setResultPath(target);
      void message.success(`已提取 ${ids.length} 页`);
    } catch (e) {
      void message.error(`提取失败：${errorMessage(e)}`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <Modal
      title="提取页面为新 PDF"
      open={open}
      onCancel={onClose}
      maskClosable={false}
      width={560}
      footer={
        resultPath
          ? [
              <Button
                key="open"
                type="primary"
                icon={<FolderOpenOutlined />}
                onClick={() => {
                  void openPdfAtPath(resultPath).catch((e) =>
                    message.error(`打开失败：${errorMessage(e)}`),
                  );
                  onClose();
                }}
              >
                打开生成的 PDF
              </Button>,
              <Button key="close" onClick={onClose}>
                完成
              </Button>,
            ]
          : [
              <Button key="close" onClick={onClose}>
                关闭
              </Button>,
              <Button key="start" type="primary" disabled={!canStart} onClick={() => void start()}>
                提取{effectiveIds.length > 0 ? `（${effectiveIds.length} 页）` : ""}
              </Button>,
            ]
      }
    >
      {resultPath ? (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Typography.Text>提取完成，新文件已保存到：</Typography.Text>
          <Typography.Text copyable code>
            {resultPath}
          </Typography.Text>
        </Space>
      ) : (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Radio.Group
            value={mode}
            onChange={(e) => setMode(e.target.value as SelectMode)}
            optionType="button"
            options={[
              { value: "checked", label: "勾选页面" },
              { value: "input", label: "输入页码" },
            ]}
          />
          {mode === "checked" ? (
            <Typography.Text type="secondary">
              使用左侧缩略图勾选的页面（当前已勾选 {checkedIds.length} 页）
            </Typography.Text>
          ) : (
            <>
              <Input
                data-testid="extract-page-input"
                placeholder="例如：1,3,5-8（按当前页序，逗号分隔，支持范围）"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                allowClear
              />
              {parseError ? (
                <Alert type="warning" showIcon message={parseError} />
              ) : (
                parsedIds &&
                parsedIds.length > 0 && (
                  <Typography.Text type="secondary">
                    将提取第 {labelsOf(parsedIds)} 页
                  </Typography.Text>
                )
              )}
            </>
          )}
          <Space wrap>
            <Button onClick={() => void pickTarget()}>{target ? "更改保存路径" : "选择保存路径"}</Button>
            {target && (
              <Typography.Text code ellipsis style={{ maxWidth: 320 }} title={target}>
                {target}
              </Typography.Text>
            )}
          </Space>
        </Space>
      )}
    </Modal>
  );
}
