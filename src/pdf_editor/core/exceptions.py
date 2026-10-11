"""自定义异常体系。

错误码字符串与异常类名保持一致（api 层据此转换错误信封），
前端可依据 code 判断是否可重试。
"""


class PdfEditorError(Exception):
    """所有 PDF 编辑器异常的基类。"""


class PdfOpenError(PdfEditorError):
    """文件不存在 / 损坏 / 加密无法打开。"""


class PdfWriteError(PdfEditorError):
    """写出 PDF 失败。"""


class SofficeNotFoundError(PdfEditorError):
    """找不到 LibreOffice 的 soffice 可执行文件。"""


class ConversionError(PdfEditorError):
    """soffice 转换非零返回或超时。"""


class UnsupportedImageError(PdfEditorError):
    """图片格式不受支持或无法解码。"""
