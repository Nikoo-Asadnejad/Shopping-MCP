"""A seller's offer for one product variant."""

from pydantic import BaseModel, ConfigDict, Field


class Offer(BaseModel):
    model_config = ConfigDict(frozen=True)

    variant_id: str
    seller: str | None
    price_toman: int | None = Field(default=None, ge=0)
    available: bool
    color: str | None
    warranty: str | None
