"""Buyer feedback for a product, the root of the review aggregate."""

from pydantic import BaseModel, ConfigDict, Field


class Review(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    body: str
    rating_stars: int | None = Field(default=None, ge=1, le=5)
    is_buyer: bool
    advantages: tuple[str, ...] = ()
    disadvantages: tuple[str, ...] = ()
