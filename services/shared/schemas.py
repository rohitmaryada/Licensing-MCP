import math
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


class PageInfo(BaseModel):
    currentPage: int
    pageSize: int
    totalPages: int
    totalElements: int
    hasNextPage: bool


class Page(BaseModel, Generic[T]):
    items: list[T]
    pageInfo: PageInfo


class Change(BaseModel, Generic[T]):
    before: T
    after: T


class ErrorResponse(BaseModel):
    detail: str
    detailType: str
    detailMessages: list[str] = []


class PageParams:
    def __init__(
        self,
        page: int = Query(default=0, ge=0),
        size: int = Query(default=100, ge=1),
    ):
        if size > 100:
            from services.shared.errors import BadRequestError

            raise BadRequestError(
                detail="size exceeds max page size of 100",
                detail_messages=[f"requested size={size}"],
            )
        self.page = page
        self.size = size


def build_page(items: list[T], total_elements: int, params: PageParams) -> Page[T]:
    total_pages = math.ceil(total_elements / params.size) if params.size else 0
    return Page(
        items=items,
        pageInfo=PageInfo(
            currentPage=params.page,
            pageSize=params.size,
            totalPages=total_pages,
            totalElements=total_elements,
            hasNextPage=(params.page + 1) < total_pages,
        ),
    )
