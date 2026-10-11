/** 顶部工具栏：打开/保存/导出所选/提取页面/分割/图片转 PDF/Word 转 PDF/转扫描件。 */
import { useState } from "react";
import { App, Button, Space, Tag, Tooltip } from "antd";
import {
  BgColorsOutlined,
  ExportOutlined,
  FileImageOutlined,
  FileWordOutlined,
  FolderOpenOutlined,
  SaveOutlined,
  ScissorOutlined,
  SnippetsOutlined,
} from "@ant-design/icons";
import { errorMessage, openPdfFromDialog, saveDocumentAs } from "../api/commands";
import { useDocumentStore } from "../store/document";

interface ToolbarProps {
  onOpenSplit: () => void;
  onOpenImageToPdf: () => void;
  onOpenWordToPdf: () => void;
  onOpenExtract: () => void;
  onOpenScan: () => void;
}

export function Toolbar({
  onOpenSplit,
  onOpenImageToPdf,
  onOpenWordToPdf,
  onOpenExtract,
  onOpenScan,
}: ToolbarProps) {
  const bridgeReady = useDocumentStore((s) => s.bridgeReady);
  const pages = useDocumentStore((s) => s.pages);
  const selectedIds = useDocumentStore((s) => s.selectedIds);
  const { message } = App.useApp();
  const [opening, setOpening] = useState(false);
  const [saving, setSaving] = useState(false);

  const hasDoc = pages.length > 0;
  const disabled = !bridgeReady;

  const open = async () => {
    setOpening(true);
    try {
      await openPdfFromDialog();
    } catch (e) {
      void message.error(`打开失败：${errorMessage(e)}`);
    } finally {
      setOpening(false);
    }
  };

  const save = async (pageIds: number[] | null) => {
    setSaving(true);
    try {
      const target = await saveDocumentAs(pageIds);
      if (target) void message.success(`已保存到 ${target}`);
    } catch (e) {
      void message.error(`保存失败：${errorMessage(e)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Space style={{ padding: "0 16px", height: "100%" }} wrap={false}>
      <Tooltip title="打开 PDF 文件">
        <Button data-testid="btn-open" icon={<FolderOpenOutlined />} loading={opening} disabled={disabled} onClick={open}>
          打开
        </Button>
      </Tooltip>
      <Tooltip title="按当前页序另存为 PDF">
        <Button
          data-testid="btn-save"
          icon={<SaveOutlined />}
          disabled={disabled || !hasDoc}
          loading={saving}
          onClick={() => void save(null)}
        >
          保存
        </Button>
      </Tooltip>
      <Tooltip title="仅导出勾选的页面">
        <Button
          data-testid="btn-export-selected"
          icon={<ExportOutlined />}
          disabled={disabled || selectedIds.size === 0}
          loading={saving}
          onClick={() => void save([...selectedIds])}
        >
          导出所选
        </Button>
      </Tooltip>
      <Tooltip title="提取选中页面组成新 PDF（勾选或输入页码）">
        <Button
          data-testid="btn-extract"
          icon={<SnippetsOutlined />}
          disabled={disabled || !hasDoc}
          onClick={onOpenExtract}
        >
          提取页面
        </Button>
      </Tooltip>
      <Tooltip title="分割当前页">
        <Button data-testid="btn-split" icon={<ScissorOutlined />} disabled={disabled || !hasDoc} onClick={onOpenSplit} />
      </Tooltip>
      <Tooltip title="图片转 PDF">
        <Button data-testid="btn-image2pdf" icon={<FileImageOutlined />} disabled={disabled} onClick={onOpenImageToPdf} />
      </Tooltip>
      <Tooltip title="Word 转 PDF（需要 LibreOffice）">
        <Button data-testid="btn-word2pdf" icon={<FileWordOutlined />} disabled={disabled} onClick={onOpenWordToPdf} />
      </Tooltip>
      <Tooltip title="转换为白底黑字扫描件（压平背景，只留文字内容）">
        <Button
          data-testid="btn-scan"
          icon={<BgColorsOutlined />}
          disabled={disabled || !hasDoc}
          onClick={onOpenScan}
        >
          转扫描件
        </Button>
      </Tooltip>
      <Tag color={bridgeReady ? "green" : "red"} style={{ marginLeft: "auto" }}>
        {bridgeReady ? "后端已连接" : "连接中…"}
      </Tag>
    </Space>
  );
}
