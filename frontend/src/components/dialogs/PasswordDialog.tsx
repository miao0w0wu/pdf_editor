/** 加密 PDF 密码弹窗：open_document 抛 PdfOpenError(加密) 时出现，
 * 输入密码后携带 password 重试（spec 第 12 节）。
 */
import { useState } from "react";
import { App, Input, Modal, Space, Typography } from "antd";
import { errorMessage, openPdfAtPath } from "../../api/commands";
import { useDocumentStore } from "../../store/document";

export function PasswordDialog() {
  const prompt = useDocumentStore((s) => s.passwordPrompt);
  const setPasswordPrompt = useDocumentStore((s) => s.setPasswordPrompt);
  const { message } = App.useApp();
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // 每次弹出新文档的密码框时清空旧输入（渲染期调整状态）
  const [prevPrompt, setPrevPrompt] = useState(prompt);
  if (prevPrompt !== prompt) {
    setPrevPrompt(prompt);
    if (prompt) setPassword("");
  }

  const close = () => setPasswordPrompt(null);

  const handleOk = async () => {
    if (!prompt) return;
    setSubmitting(true);
    try {
      await openPdfAtPath(prompt.path, password);
    } catch (e) {
      // 密码错误：保持弹窗让用户重试；其它错误关闭并提示
      if (e instanceof Error && /加密|密码/.test(e.message)) {
        void message.error(`密码错误：${e.message}`);
        setSubmitting(false);
        return;
      }
      void message.error(`打开失败：${errorMessage(e)}`);
      close();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="PDF 已加密"
      open={prompt !== null}
      onCancel={close}
      maskClosable={false}
      confirmLoading={submitting}
      onOk={() => void handleOk()}
      okText="打开"
      cancelText="取消"
      destroyOnClose
    >
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <Typography.Text ellipsis style={{ maxWidth: 420 }}>
          {prompt?.path}
        </Typography.Text>
        <Input.Password
          autoFocus
          placeholder="请输入打开密码"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onPressEnter={() => void handleOk()}
        />
      </Space>
    </Modal>
  );
}
