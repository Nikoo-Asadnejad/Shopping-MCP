"""Compact product view used in search and recommendations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    shop: str
    id: str
    title: str
    url: str
    available: bool
    price_toman: int | None = Field(default=None, ge=0)
    rating_stars: float | None = Field(default=None, ge=0, le=5)
    rating_count: int = Field(ge=0)
    retrieved_at: datetime
