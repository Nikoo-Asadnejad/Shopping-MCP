"""Public operation validation, independent of MCP transport."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from shopping_mcp.domain.product.reference import product_id
from shopping_mcp.domain.product.search_filters import SearchFilters
from shopping_mcp.domain.text import normalize


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)


class SearchInput(Input):
    query: str = Field(min_length=1, max_length=200)
    page: int = Field(default=1, ge=1, le=100)
    filters: SearchFilters = Field(default_factory=SearchFilters)


class ProductInput(Input):
    product: str

    @field_validator("product", mode="before")
    @classmethod
    def validate_reference(cls, value):
        return product_id(value)


class CompareInput(Input):
    products: list[str] = Field(min_length=2, max_length=4)

    @field_validator("products", mode="before")
    @classmethod
    def validate_references(cls, values):
        if not isinstance(values, (list, tuple)):
            raise ValueError("provide 2 to 4 product references")
        return [product_id(value) for value in values]

    @model_validator(mode="after")
    def distinct(self):
        if len(set(self.products)) != len(self.products):
            raise ValueError("comparison requires distinct products")
        return self


class ReviewInput(ProductInput):
    max_reviews: int = Field(default=40, ge=1, le=60)


class MatchInput(SearchInput):
    budget_toman: int = Field(gt=0)
    required_features: list[str] = Field(default_factory=list, max_length=10)
    priorities: list[Literal["value", "reviews"]] = Field(
        default_factory=list, max_length=2
    )
    product_type: str | None = Field(default=None, min_length=1, max_length=80)
    candidate_limit: int = Field(default=6, ge=1, le=8)
    max_reviews: int = Field(default=20, ge=1, le=40)

    @field_validator("required_features")
    @classmethod
    def valid_features(cls, values):
        if any(not normalize(value) or len(value) > 100 for value in values):
            raise ValueError("features must contain 1 to 100 characters")
        return values

    @model_validator(mode="after")
    def budget_range(self):
        if (
            self.filters.min_price_toman is not None
            and self.filters.min_price_toman > self.budget_toman
        ):
            raise ValueError("minimum price exceeds the budget")
        return self
