"""对话助手 Schemas"""
from pydantic import BaseModel, Field
from typing import Any, Literal


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = ""


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = []
    conversation_id: str = ""


class ActionBlock(BaseModel):
    label: str
    action: str
    params: dict[str, Any] = {}
    confirmTitle: str = ""
    confirmDetail: str = ""


class ChartBlock(BaseModel):
    type: Literal["chart"]
    chartType: str
    data: dict


class TableBlock(BaseModel):
    type: Literal["table"]
    columns: list[dict[str, str]]
    rows: list[dict[str, Any]]


class ActionsBlock(BaseModel):
    type: Literal["actions"]
    actions: list[ActionBlock]


MessageBlock = ChartBlock | TableBlock | ActionsBlock | dict


class ChatResponse(BaseModel):
    conversation_id: str = ""
    content: str = ""
    blocks: list[dict] = []


class ExecuteRequest(BaseModel):
    conversation_id: str = ""
    action: str
    params: dict[str, Any] = {}


class ExecuteResult(BaseModel):
    success: bool
    message: str
    related_id: int | None = None
    link: str | None = None
