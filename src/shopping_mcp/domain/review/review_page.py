"""A page of reviews for one product."""

from pydantic import BaseModel, ConfigDict, Field

from .review import Review


class ReviewPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    page: int = Field(ge=1)
    total_pages: int = Field(ge=0)
    total_items: int = Field(ge=0)
    reviews: tuple[Review, ...]
