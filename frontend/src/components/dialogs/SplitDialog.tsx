/** 分割对话框：当前页预览 + 水平/垂直方向 + 各段比例输入。
 *
 * 预览分割线与后端 _SplitSpec 语义一致（spec 5.1，PDF 原点在左下）：
 * horizontal 首段为页面底部条带（线从底部累计），vertical 首段为左侧
 * 条带（线从左侧累计）。分割成功后跳到第一个子页。
 */
import { useEffect, useMemo, useState } from "react";
import { App, Button, InputNumber, Modal, Radio, Space, Typography } from "antd";
import { ScissorOutlined } from "@ant-design/icons";
import { invoke } from "../../api/client";
import { errorMessage, splitPage } from "../../api/commands";
import { useDocumentStore } from "../../store/document";

type SplitMode = "horizontal" | "vertical";

const MIN_SEGMENTS = 2;
const MAX_SEGMENTS = 6;

export function SplitDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pages = useDocumentStore((s) => s.pages);
  const currentPageId = useDocumentStore((s) => s.currentPageId);
  const setCurrentPageId = useDocumentStore((s) => s.setCurrentPageId);
  const { message } = App.useApp();

  const current = pages.find((p) => p.page_id === currentPageId) ?? null;
  const [mode, setMode] = useState<SplitMode>("horizontal");
  const [ratios, setRatios] = useState<number[]>([1, 1]);
  const [preview, setPreview] = useState<{ key: string; url: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // 预览按 page_id 键控：打开/换页未命中时显示加载态并请求
  const previewKey = open && current ? `${current.page_id}` : null;
  const shownPreview = preview !== null && preview.key === previewKey ? preview.url : null;
  const currentSourceIndex = current?.source_index;
  useEffect(() => {
    if (previewKey === null || currentSourceIndex === undefined) return;
    if (preview !== null && preview.key === previewKey) return;
    let cancelled = false;
    invoke<string>("document.render_page", currentSourceIndex, 72)
      .then((url) => {
        if (!cancelled) setPreview({ key: previewKey, url });
      })
      .catch((e) => {
        void message.error(`预览渲染失败：${errorMessage(e)}`);
        if (!cancelled) setPreview({ key: previewKey, url: "" });
      });
    return () => {
      cancelled = true;
    };
  }, [previewKey, currentSourceIndex, preview, message]);

  // 归一化占比（与后端 ratios 归一化一致）
  const fracs = useMemo(() => {
    const total = ratios.reduce((a, b) => a + b, 0) || 1;
    return ratios.map((r) => r / total);
  }, [ratios]);

  // 分界线位置：horizontal 自底部累计，vertical 自左侧累计
  const lines = useMemo(() => {
    const acc: number[] = [];
    let sum = 0;
    for (let i = 0; i < fracs.length - 1; i += 1) {
      sum += fracs[i];
      acc.push(sum);
    }
    return acc;
  }, [fracs]);

  const setRatio = (i: number, v: number | null) => {
    setRatios((rs) => rs.map((r, j) => (j === i ? (v ?? 0.1) : r)));
  };

  const handleOk = async () => {
    if (!current) return;
    setSubmitting(true);
    try {
      const state = await splitPage(current.page_id, mode, ratios);
      const firstSub = state.pages.find((p) => p.label === `${current.label}a`);
      if (firstSub) setCurrentPageId(firstSub.page_id);
      void message.success(`已把第 ${current.label} 页分割为 ${fracs.length} 页`);
      onClose();
    } catch (e) {
      void message.error(`分割失败：${errorMessage(e)}`);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={`分割第 ${current?.label ?? ""} 页`}
      open={open}
      onCancel={onClose}
      width={720}
      footer={[
        <Button key="cancel" onClick={onClose}>
          取消
        </Button>,
        <Button
          key="ok"
          type="primary"
          icon={<ScissorOutlined />}
          loading={submitting}
          disabled={!current}
          onClick={() => void handleOk()}
        >
          分割
        </Button>,
      ]}
    >
      <div className="split-body">
        <div className="split-preview">
          {shownPreview === null ? (
            <Typography.Text type="secondary">预览加载中…</Typography.Text>
          ) : shownPreview === "" ? (
            <Typography.Text type="danger">预览渲染失败</Typography.Text>
          ) : (
            <div className={`split-canvas ${mode}`}>
              <img src={shownPreview} alt="分割预览" draggable={false} />
              {lines.map((c, i) => (
                <div
                  key={i}
                  className={mode === "horizontal" ? "split-line-h" : "split-line-v"}
                  style={mode === "horizontal" ? { bottom: `${c * 100}%` } : { left: `${c * 100}%` }}
                />
              ))}
            </div>
          )}
        </div>
        <div className="split-controls">
          <Space direction="vertical" style={{ width: "100%" }} size="middle">
            <div>
              <Typography.Text strong>方向：</Typography.Text>
              <Radio.Group
                value={mode}
                onChange={(e) => setMode(e.target.value as SplitMode)}
                optionType="button"
                options={[
                  { value: "horizontal", label: "水平（切成上下几条）" },
                  { value: "vertical", label: "垂直（切成左右几条）" },
                ]}
              />
            </div>
            <div>
              <Typography.Text strong>各段占比：</Typography.Text>
              <Space wrap style={{ marginTop: 8 }}>
                {ratios.map((r, i) => (
                  <span key={i}>
                    <InputNumber
                      min={0.1}
                      max={10}
                      step={0.1}
                      value={r}
                      onChange={(v) => setRatio(i, v)}
                      style={{ width: 80 }}
                    />
                    <Typography.Text type="secondary" style={{ marginLeft: 4 }}>
                      {Math.round(fracs[i] * 100)}%
                    </Typography.Text>
                  </span>
                ))}
              </Space>
            </div>
            <Space>
              <Button
                size="small"
                disabled={ratios.length >= MAX_SEGMENTS}
                onClick={() => setRatios((rs) => [...rs, 1])}
              >
                添加一段
              </Button>
              <Button
                size="small"
                disabled={ratios.length <= MIN_SEGMENTS}
                onClick={() => setRatios((rs) => rs.slice(0, -1))}
              >
                删除一段
              </Button>
              <Button size="small" onClick={() => setRatios([1, 1])}>
                二等分
              </Button>
              <Button size="small" onClick={() => setRatios([1, 1, 1])}>
                三等分
              </Button>
            </Space>
            <Typography.Text type="secondary">
              分割在保存写盘时生效；子页标签为原页号加 a/b/c 后缀。
            </Typography.Text>
          </Space>
        </div>
      </div>
    </Modal>
  );
}
