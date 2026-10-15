"""Compact product view used in search and recommendations."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProductSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    shop: str
    id: str
    title: str
    url: str
    image_url: str | None = None
    available: bool
    price_toman: int | None = Field(default=None, ge=0)
    rating_stars: float | None = Field(default=None, ge=0, le=5)
    rating_count: int = Field(ge=0)
    price_unit: Literal["toman"] = "toman"
    seller: str | None = None
    default_variant_id: str | None = None
    category_id: str | None = None
    category: str | None = None
    brand_id: str | None = None
    title_en: str | None = None
    shipping_cost_toman: int | None = None
    retrieved_at: datetime
