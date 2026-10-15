"""Conservative, attributed synthesis of bounded review evidence."""

from collections import defaultdict
from datetime import datetime

from shopping_mcp.domain.product import ProductDetails
from shopping_mcp.domain.review import Review
from shopping_mcp.domain.text import normalize

from .results import ReviewSummary, ReviewTheme


def is_experience(review: Review) -> bool:
    text = normalize(f"{review.title} {review.body}")
    question = any(mark in text for mark in ("؟", "?")) or text.startswith(
        ("آیا ", "ایا ", "does ", "is it ", "can ", "how ", "what ")
    )
    solicitation = any(
        phrase in text
        for phrase in (
            "ارسال کنید",
            "موجود کنید",
            "لطفا موجود",
            "please restock",
            "please send",
        )
    )
    # Buyer status alone does not make a question or blank comment an experience.
    return (
        bool(text.strip() or review.advantages or review.disadvantages)
        and not question
        and not solicitation
        and bool(
            review.is_buyer
            or review.rating_stars is not None
            or review.advantages
            or review.disadvantages
        )
    )


def summarize(
    details: ProductDetails,
    reviews: list[Review],
    total: int,
    pages: list[int],
    retrieved_at: datetime | None = None,
) -> ReviewSummary:
    usable = [review for review in reviews if is_experience(review)]
    source = f"{details.url.split('#')[0]}#comments"

    def themes(positive: bool):
        groups = defaultdict(list)
        labels = {}
        for review in usable:
            values = review.advantages if positive else review.disadvantages
            for value in {
                normalize(value): value for value in values if normalize(value)
            }.values():
                key = normalize(value)
                labels.setdefault(key, value)
                groups[key].append(review)
        return tuple(
            ReviewTheme(
                text=labels[key],
                mentions=len(items),
                verified_buyer_mentions=sum(item.is_buyer for item in items),
                review_ids=tuple(item.id for item in items),
                source_url=source,
            )
            for key, items in sorted(
                groups.items(), key=lambda entry: (-len(entry[1]), entry[0])
            )[:8]
        )

    positives, negatives = themes(True), themes(False)
    overlap = {normalize(theme.text) for theme in positives} & {
        normalize(theme.text) for theme in negatives
    }
    notes = [
        f"Examined {len(reviews)} of {total} comments from pages {pages}; bounded upstream order, not a random or statistically representative sample.",
        "Only explicit advantages/disadvantages become themes; singleton mentions are individual opinions, not recurring findings.",
        "Digikala overview and its advantages/disadvantages are upstream content, separate from our sample synthesis.",
    ]
    if len(usable) < 5:
        notes.append("Too few usable experiences for a confident review conclusion.")
    ratings = [
        review.rating_stars for review in usable if review.rating_stars is not None
    ]
    if any(rate <= 2 for rate in ratings) and any(rate >= 4 for rate in ratings):
        notes.append("Sample includes both satisfied and dissatisfied reviewers.")
    if overlap:
        notes.append(
            "Some explicit themes appear in both positive and negative feedback."
        )
    return ReviewSummary(
        product_id=details.id,
        source_url=source,
        retrieved_at=retrieved_at or details.retrieved_at,
        rating_stars=details.rating_stars,
        rating_count=details.rating_count,
        total_reviews=total,
        examined=len(reviews),
        usable_reviews=len(usable),
        verified_buyer_reviews=sum(item.is_buyer for item in usable),
        unrated_reviews=sum(item.rating_stars is None for item in reviews),
        upstream_overview=details.buyer_overview,
        upstream_advantages=details.buyer_advantages,
        upstream_disadvantages=details.buyer_disadvantages,
        positives=positives,
        negatives=negatives,
        examples=tuple(usable[:5]),
        conflicting_themes=tuple(sorted(overlap)),
        coverage_notes=tuple(notes),
    )
