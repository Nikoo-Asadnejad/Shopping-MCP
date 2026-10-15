"""Compact structured projections for shopping decisions."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from shopping_mcp.domain.product import ProductDetails
from shopping_mcp.domain.product.category_suggestion import CategorySuggestion
from shopping_mcp.domain.review import Review


class Result(BaseModel):
    model_config = ConfigDict(frozen=True)


class SpecificationDifference(Result):
    group: str
    name: str
    values_by_product: dict[str, tuple[str, ...] | None]


class Comparison(Result):
    products: tuple[ProductDetails, ...]
    differences: tuple[SpecificationDifference, ...]
    notes: tuple[str, ...]


class ReviewTheme(Result):
    text: str
    mentions: int
    verified_buyer_mentions: int
    review_ids: tuple[str, ...]
    source_url: str


class ReviewSummary(Result):
    product_id: str
    source_url: str
    retrieved_at: datetime
    rating_stars: float | None
    rating_count: int
    total_reviews: int
    examined: int
    usable_reviews: int
    verified_buyer_reviews: int
    unrated_reviews: int
    upstream_overview: str | None
    upstream_advantages: tuple[str, ...]
    upstream_disadvantages: tuple[str, ...]
    summary_method: str = "Our summary counts explicit advantages/disadvantages in sampled experience reviews; body text is supplied as attributed examples only."
    positives: tuple[ReviewTheme, ...]
    negatives: tuple[ReviewTheme, ...]
    examples: tuple[Review, ...]
    conflicting_themes: tuple[str, ...]
    coverage_notes: tuple[str, ...]


class MatchCandidate(Result):
    product: ProductDetails
    review_evidence: ReviewSummary | None
    review_score: float
    value_score: float
    reasons: tuple[str, ...]
    tradeoffs: tuple[str, ...]


class BestMatch(Result):
    category_options: tuple[CategorySuggestion, ...] = ()
    category_source_url: str | None = None
    candidates: tuple[MatchCandidate, ...]
    best_value_id: str | None
    best_reviewed_id: str | None
    confident_winner: bool
    explanation: str
    candidates_examined: int
    excluded: dict[str, str]
    limits: dict[str, int]
    source_url: str
    retrieved_at: datetime
    notes: tuple[str, ...]
