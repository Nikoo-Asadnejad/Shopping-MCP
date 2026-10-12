"""Store-neutral data returned by shop integrations."""

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


class Specification(BaseModel):
    model_config = ConfigDict(frozen=True)

    group: str
    name: str
    values: tuple[str, ...]


class Offer(BaseModel):
    model_config = ConfigDict(frozen=True)

    variant_id: str
    seller: str | None
    price_toman: int | None = Field(default=None, ge=0)
    available: bool
    color: str | None
    warranty: str | None


class ProductDetails(ProductSummary):
    specifications: tuple[Specification, ...] = ()
    offers: tuple[Offer, ...] = ()
    buyer_overview: str | None = None
    buyer_advantages: tuple[str, ...] = ()
    buyer_disadvantages: tuple[str, ...] = ()


class SearchPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    page: int = Field(ge=1)
    total_pages: int = Field(ge=0)
    total_items: int = Field(ge=0)
    products: tuple[ProductSummary, ...]


class Review(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    body: str
    rating_stars: int | None = Field(default=None, ge=1, le=5)
    is_buyer: bool
    advantages: tuple[str, ...] = ()
    disadvantages: tuple[str, ...] = ()


class ReviewPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    page: int = Field(ge=1)
    total_pages: int = Field(ge=0)
    total_items: int = Field(ge=0)
    reviews: tuple[Review, ...]
