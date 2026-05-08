"""公共 Pydantic schemas"""
from datetime import datetime
from pydantic import BaseModel


class PaginationParams(BaseModel):
    page: int = 1
    page_size: int = 20


class PageResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list


class MessageResponse(BaseModel):
    message: str
    data: dict | list | None = None
