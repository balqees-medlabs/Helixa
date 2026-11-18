"""Shared Pydantic schemas: error shape and pagination (api-overview.md)."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Error(BaseModel):
    """The uniform error body: ``{ "detail": "<reason>" }``."""

    detail: str


class Page(BaseModel, Generic[T]):
    """Pagination envelope for list endpoints."""

    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200, default=50)
    offset: int = Field(ge=0, default=0)
