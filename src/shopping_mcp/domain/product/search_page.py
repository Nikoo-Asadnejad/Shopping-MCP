"""A page of product search results."""

from pydantic import BaseModel, ConfigDict, Field

from .product_summary import ProductSummary


class SearchPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    page: int = Field(ge=1)
    total_pages: int = Field(ge=0)
    total_items: int = Field(ge=0)
    products: tuple[ProductSummary, ...]
