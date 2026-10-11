/** 转扫描件对话框：把 PDF 页面处理成白底黑字的扫描件（WPS 风格）。
 *
 * 页面来源三种：全部页面 / 勾选页面 / 输入页码。
 * 转换为后台任务：立即返回 task_id，进度/结果经 store.tasks 镜像
 * （BackendEvents 统一订阅 conversion_progress / task_done / task_error）。
 */
import { useState } from "react";
import { Alert, App, Button, Input, Modal, Progress, Radio, Slider, Space, Typography } from "antd";
import { invoke } from "../../api/client";
import {
  errorMessage,
  openPdfAtPath,
  parsePageNumbers,
  pickScanSaveTarget,
  startScanConversion,
} from "../../api/commands";
import { useDocumentStore } from "../../store/document";

type SelectMode = "all" | "checked" | "input";

export function ScanDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { message } = App.useApp();
  const pages = useDocumentStore((s) => s.pages);
  const selectedIds = useDocumentStore((s) => s.selectedIds);
  const tasks = useDocumentStore((s) => s.tasks);

  const [mode, setMode] = useState<SelectMode>("all");
  const [input, setInput] = useState("");
  const [dpi, setDpi] = useState(200);
  const [threshold, setThreshold] = useState(32);
  const [target, setTarget] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);

  const task = taskId ? tasks[taskId] : undefined;
  const running = task?.status === "running";
  const resultPath = task?.status === "done" ? (task.result ?? null) : null;

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
  const allIds = pages.map((p) => p.page_id);
  const effectiveIds =
    mode === "all" ? allIds : mode === "checked" ? checkedIds : parsedIds ?? [];
  const canStart = !running && target !== null && effectiveIds.length > 0 && parseError === null;

  // 关闭时重置本地状态（渲染期调整，props 变化时同步）
  const [prevOpen, setPrevOpen] = useState(open);
  if (prevOpen !== open) {
    setPrevOpen(open);
    if (!open) {
      setMode("all");
      setInput("");
      setDpi(200);
      setThreshold(32);
      setTarget(null);
      setTaskId(null);
    }
  }

  const pickTarget = async () => {
    try {
      // 先做一次页码解析校验，避免选完路径才发现输入无效
      if (mode === "input") parsePageNumbers(input, pages);
      else if (mode === "checked" && checkedIds.length === 0) {
        void message.warning("请先在左侧缩略图勾选页面");
        return;
      }
      const picked = await pickScanSaveTarget();
      if (picked) setTarget(picked);
    } catch (e) {
      void message.error(errorMessage(e));
    }
  };

  const start = async () => {
    if (!canStart || !target) return;
    try {
      const ids =
        mode === "all" ? allIds : mode === "checked" ? checkedIds : parsePageNumbers(input, pages);
      const id = await startScanConversion(ids, target, dpi, threshold);
      setTaskId(id);
    } catch (e) {
      void message.error(`启动转换失败：${errorMessage(e)}`);
    }
  };

  const cancel = async () => {
    if (!taskId) return;
    try {
      await invoke("converter.cancel_task", taskId);
      void message.info("已请求取消，将在当前页处理完后停止");
    } catch (e) {
      void message.error(`取消失败：${errorMessage(e)}`);
    }
  };

  const percent =
    task && typeof task.done === "number" && typeof task.total === "number" && task.total > 0
      ? Math.round((task.done / task.total) * 100)
      : undefined;

  return (
    <Modal
      title="转换为扫描件（白底黑字）"
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
          : running
            ? [
                <Button key="cancel" danger onClick={() => void cancel()}>
                  取消
                </Button>,
              ]
            : [
                <Button key="close" onClick={onClose}>
                  关闭
                </Button>,
                <Button key="start" type="primary" disabled={!canStart} onClick={() => void start()}>
                  开始转换{effectiveIds.length > 0 ? `（${effectiveIds.length} 页）` : ""}
                </Button>,
              ]
      }
    >
      {resultPath ? (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Typography.Text>转换完成，扫描件已保存到：</Typography.Text>
          <Typography.Text copyable code>
            {resultPath}
          </Typography.Text>
        </Space>
      ) : running ? (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Progress percent={percent ?? 0} status="active" />
          <Typography.Text type="secondary">
            {task?.stage ?? "正在转换…"}（共 {effectiveIds.length} 页）
          </Typography.Text>
        </Space>
      ) : (
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Alert
            type="info"
            showIcon={false}
            message="压平背景底色（灰底/阴影/纸纹），只保留文字与线条，输出白底黑字的扫描件效果。原文件不受影响。"
          />
          <Radio.Group
            value={mode}
            onChange={(e) => setMode(e.target.value as SelectMode)}
            optionType="button"
            options={[
              { value: "all", label: "全部页面" },
              { value: "checked", label: "勾选页面" },
              { value: "input", label: "输入页码" },
            ]}
          />
          {mode === "checked" && (
            <Typography.Text type="secondary">
              使用左侧缩略图勾选的页面（当前已勾选 {checkedIds.length} 页）
            </Typography.Text>
          )}
          {mode === "input" && (
            <>
              <Input
                data-testid="scan-page-input"
                placeholder="例如：1,3,5-8（按当前页序，逗号分隔，支持范围）"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                allowClear
              />
              {parseError && <Alert type="warning" showIcon message={parseError} />}
            </>
          )}
          <Space wrap>
            <Typography.Text strong>分辨率：</Typography.Text>
            <Radio.Group
              value={dpi}
              onChange={(e) => setDpi(e.target.value as number)}
              optionType="button"
              options={[
                { value: 150, label: "150" },
                { value: 200, label: "200" },
                { value: 300, label: "300" },
              ]}
            />
          </Space>
          <div>
            <Typography.Text strong>去底强度阈值：{threshold}</Typography.Text>
            <Slider
              data-testid="scan-threshold"
              min={5}
              max={128}
              value={threshold}
              onChange={(v) => setThreshold(v)}
              tooltip={{ open: false }}
            />
            <Typography.Text type="secondary">
              越大背景越白、浅色笔迹越容易被丢弃；越小笔画越浓、噪点越多。默认 32。
            </Typography.Text>
          </div>
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
