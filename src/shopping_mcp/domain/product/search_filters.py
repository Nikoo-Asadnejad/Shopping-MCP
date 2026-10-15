"""Store-neutral search restrictions; monetary inputs are always toman."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SearchFilters(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    min_price_toman: int | None = Field(default=None, ge=0)
    max_price_toman: int | None = Field(default=None, ge=0)
    brand_id: int | None = Field(default=None, gt=0)
    category_id: int | None = Field(default=None, gt=0)
    available_only: bool = True

    @model_validator(mode="after")
    def valid_price_range(self):
        if self.min_price_toman is not None and self.max_price_toman is not None:
            if self.min_price_toman > self.max_price_toman:
                raise ValueError("minimum price must not exceed maximum price")
        return self
