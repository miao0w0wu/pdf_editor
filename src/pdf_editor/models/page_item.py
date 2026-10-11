"""核心数据模型：PageItem / DocumentState。

page_id 是打开文档时分配的稳定 ID，不随重排改变；
删除和拖拽过程中 source_index 会失效，前端选择状态必须锚定在 page_id 上。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PageItem:
    """单页的内存模型。"""

    page_id: int  # 打开文档时分配的稳定 ID，不随重排改变
    source_index: int  # 该页在当前 pypdf reader 中的原始下标
    rotation: int = 0  # 0/90/180/270，预留扩展
    label: str = ""  # UI 显示名，如 "3"


class DocumentState:
    """文档状态：pages 的列表顺序即当前逻辑顺序。

    前端持有的只是本模型的 JSON 镜像；所有变更以后端返回值为准。
    """

    def __init__(self, pages: list[PageItem]) -> None:
        self.pages: list[PageItem] = pages

    def logical_order(self) -> list[int]:
        """返回 source_index 列表（按当前逻辑顺序），供导出。"""
        return [p.source_index for p in self.pages]

    def page_ids(self) -> list[int]:
        """返回 page_id 列表（按当前逻辑顺序）。"""
        return [p.page_id for p in self.pages]

    def get_page(self, page_id: int) -> PageItem:
        """按 page_id 查找页面，找不到时抛 KeyError 的语义由调用方转换为业务异常。"""
        for p in self.pages:
            if p.page_id == page_id:
                return p
        raise KeyError(f"page_id {page_id} 不存在")

    def to_dict(self) -> dict[str, Any]:
        """序列化为 Bridge 传输结构（与 frontend/src/types.ts 的 DocumentStatePayload 对应）。"""
        return {
            "pages": [
                {
                    "page_id": p.page_id,
                    "source_index": p.source_index,
                    "rotation": p.rotation,
                    "label": p.label,
                }
                for p in self.pages
            ]
        }

    @staticmethod
    def from_payload(payload: dict[str, Any]) -> DocumentState:
        """从 Bridge 传输结构还原（主要用于测试）。"""
        pages = [PageItem(**p) for p in payload["pages"]]
        return DocumentState(pages)
