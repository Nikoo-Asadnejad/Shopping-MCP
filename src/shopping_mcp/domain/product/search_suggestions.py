"""Autocomplete projection with source and freshness."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .category_suggestion import CategorySuggestion


class SearchSuggestions(BaseModel):
    model_config = ConfigDict(frozen=True)

    suggestions: tuple[str, ...]
    categories: tuple[CategorySuggestion, ...] = ()
    source_url: str
    retrieved_at: datetime
