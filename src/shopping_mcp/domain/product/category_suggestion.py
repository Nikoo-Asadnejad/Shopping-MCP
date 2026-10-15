"""A category identified by the store for a search phrase."""

from pydantic import BaseModel, ConfigDict, Field


class CategorySuggestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int = Field(gt=0, strict=True)
    title: str = Field(min_length=1, max_length=200)
    keywords: tuple[str, ...] = ()
