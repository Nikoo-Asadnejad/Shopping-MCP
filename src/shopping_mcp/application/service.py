"""Six shopping use cases, shared by all transports."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from math import log1p

from shopping_mcp.domain.errors import ShoppingError
from shopping_mcp.domain.product import ProductDetails, SearchPage
from shopping_mcp.domain.product.search_suggestions import SearchSuggestions
from shopping_mcp.domain.text import contains, normalize
from shopping_mcp.infrastructure.shops.base import Shop

from .inputs import CompareInput, MatchInput, ProductInput, ReviewInput, SearchInput
from .results import BestMatch, Comparison, MatchCandidate, SpecificationDifference
from .reviews import summarize

_ACCESS_DENIED = {301, 302, 303, 307, 308, 401, 403}


def _available_price(product: ProductDetails) -> int | None:
    if not product.available:
        return None
    offer = product.cheapest_available_offer
    return (
        offer.price_toman
        if offer and offer.available
        else product.price_toman
        if product.available
        else None
    )


def _feature_matches(product: ProductDetails, feature: str) -> bool:
    # Features must be evidenced by specifications, not promotional copy or reviews.
    return any(
        contains(f"{spec.name} {' '.join(spec.values)}", feature)
        for spec in product.specifications
    )


class ShoppingService:
    def __init__(
        self, shop: Shop, suggestions: Callable[[str], Awaitable[SearchSuggestions]]
    ):
        self.shop = shop
        self._suggestions = suggestions

    async def search_products(self, request: SearchInput) -> SearchPage:
        result = await self.shop.search_products(
            request.query, request.page, request.filters
        )
        filters = request.filters

        def eligible(product):
            price = product.price_toman
            return (
                (not filters.available_only or product.available)
                and (
                    filters.min_price_toman is None
                    or price is not None
                    and price >= filters.min_price_toman
                )
                and (
                    filters.max_price_toman is None
                    or price is not None
                    and price <= filters.max_price_toman
                )
                and (not filters.brand_id or product.brand_id == str(filters.brand_id))
                and (
                    not filters.category_id
                    or product.category_id == str(filters.category_id)
                )
            )

        cards = tuple(product for product in result.products if eligible(product))
        notes = [
            "Shipping cost is unknown. Up to 20 cards from this upstream page; pagination totals describe upstream results."
        ]
        if len(cards) != len(result.products):
            notes.append(
                "Locally removed unverified or mismatched filter results; this page is not a complete filtered catalog."
            )
        return result.model_copy(update={"products": cards, "notes": tuple(notes)})

    async def get_product_details(self, request: ProductInput) -> ProductDetails:
        return await self.shop.get_product_details(request.product)

    async def compare_products(self, request: CompareInput) -> Comparison:
        products = tuple(
            await asyncio.gather(
                *(
                    self.shop.get_product_details(identifier)
                    for identifier in request.products
                )
            )
        )
        categories = {
            product.category_id or normalize(product.category or "")
            for product in products
        }
        notes = [
            "Compare default and cheapest available offers separately; colors, sizes and warranties may differ. Shipping cost is unknown."
        ]
        if len(categories) != 1 or "" in categories:
            return Comparison(
                products=products,
                differences=(),
                notes=tuple(
                    notes
                    + [
                        "Category match is unverified; specification names are not aligned across categories."
                    ]
                ),
            )
        groups = {}
        for product in products:
            for spec in product.specifications:
                key = (normalize(spec.group), normalize(spec.name))
                entry = groups.setdefault(
                    key, {"group": spec.group, "name": spec.name, "values": {}}
                )
                previous = entry["values"].get(product.id, ())
                entry["values"][product.id] = previous + spec.values
        differences = []
        for entry in groups.values():
            values = {
                product.id: entry["values"].get(product.id) for product in products
            }
            comparable = [
                None
                if value is None
                else tuple(sorted(normalize(item) for item in value))
                for value in values.values()
            ]
            if len(set(comparable)) > 1:
                differences.append(
                    SpecificationDifference(
                        group=entry["group"],
                        name=entry["name"],
                        values_by_product=values,
                    )
                )
        return Comparison(
            products=products, differences=tuple(differences[:60]), notes=tuple(notes)
        )

    async def _review_sample(self, product: ProductDetails, limit: int):
        first = await self.shop.get_reviews(product.id, page=1)
        # Spread a bounded sample over the first 100 pages where possible.
        max_pages = min(3, (limit + 19) // 20)
        total_pages = min(first.total_pages, 100)
        page_numbers = [1]
        if max_pages >= 2 and total_pages >= 2:
            page_numbers.append(
                total_pages if max_pages == 2 else max(2, (total_pages + 1) // 2)
            )
        if max_pages == 3 and total_pages > page_numbers[-1]:
            page_numbers.append(total_pages)
        pages = [first]
        for number in page_numbers[1:]:
            pages.append(await self.shop.get_reviews(product.id, page=number))
        reviews = []
        seen = set()
        retrieved_at = min(
            product.retrieved_at,
            *(page.retrieved_at or product.retrieved_at for page in pages),
        )
        # Interleave sampled pages so trimming still represents all fetched pages.
        for row in range(20):
            for page in pages:
                if row < len(page.reviews) and page.reviews[row].id not in seen:
                    item = page.reviews[row]
                    reviews.append(item)
                    seen.add(item.id)
                    if len(reviews) == limit:
                        return summarize(
                            product,
                            reviews,
                            first.total_items,
                            page_numbers,
                            retrieved_at,
                        )
        return summarize(
            product, reviews, first.total_items, page_numbers, retrieved_at
        )

    async def summarize_reviews(self, request: ReviewInput):
        product = await self.shop.get_product_details(request.product)
        return await self._review_sample(product, request.max_reviews)

    async def suggest_searches(self, request: SearchInput) -> SearchSuggestions:
        # Deliberately outside Shop's common contract until another store needs it.
        return await self._suggestions(request.query)

    async def find_best_match(self, request: MatchInput) -> BestMatch:
        filters = request.filters.model_copy(
            update={
                "max_price_toman": min(
                    request.budget_toman,
                    request.filters.max_price_toman
                    if request.filters.max_price_toman is not None
                    else request.budget_toman,
                ),
                "available_only": True,
            }
        )
        category_options = ()
        category_source_url = None
        category_lookups = 0
        if filters.category_id is None:
            suggestions = await self._suggestions(request.product_type or request.query)
            category_options = suggestions.categories
            category_source_url = suggestions.source_url
            category_lookups = 1
            category_ids = {category.id for category in category_options}
            if len(category_ids) != 1:
                explanation = (
                    "Digikala suggested several categories; select a category ID from category_options and pass filters.category_id to rank comparable products."
                    if category_ids
                    else "Digikala did not identify a category for this query. Refine product_type or provide filters.category_id; ordinary search remains available across all categories."
                )
                return BestMatch(
                    candidates=(),
                    best_value_id=None,
                    best_reviewed_id=None,
                    confident_winner=False,
                    explanation=explanation,
                    candidates_examined=0,
                    excluded={},
                    category_options=category_options,
                    category_source_url=category_source_url,
                    limits={
                        "category_lookups": 1,
                        "search_pages": 0,
                        "candidate_details": 0,
                        "review_pages_per_candidate": 0,
                        "reviews_per_candidate": 0,
                    },
                    source_url=suggestions.source_url,
                    retrieved_at=suggestions.retrieved_at,
                    notes=(
                        "Category choices come from the store; no fixed category vocabulary or inferred translations are used.",
                    ),
                )
            filters = filters.model_copy(
                update={"category_id": next(iter(category_ids))}
            )
        # Do not locally discard search cards by default-offer price: details may
        # expose a cheaper available offer; only details decide eligibility.
        page = await self.shop.search_products(request.query, request.page, filters)
        cards = list({card.id: card for card in page.products}.values())[
            : request.candidate_limit
        ]
        excluded = {}
        candidates = []
        for card in cards:
            try:
                product = await self.shop.get_product_details(card.id)
                price = _available_price(product)
                if (
                    price is None
                    or price > request.budget_toman
                    or price > filters.max_price_toman
                ):
                    excluded[card.id] = "Unavailable, price unknown, or over budget"
                    continue
                if (
                    filters.min_price_toman is not None
                    and price < filters.min_price_toman
                ):
                    excluded[card.id] = "Below the requested price range"
                    continue
                if filters.brand_id and product.brand_id != str(filters.brand_id):
                    excluded[card.id] = "Brand filter could not be verified"
                    continue
                if product.category_id != str(filters.category_id):
                    excluded[card.id] = (
                        "Product type could not be verified against the resolved category"
                    )
                    continue
                missing = [
                    feature
                    for feature in request.required_features
                    if not _feature_matches(product, feature)
                ]
                if missing:
                    excluded[card.id] = "Required features unverified: " + ", ".join(
                        missing
                    )
                    continue
                evidence = None
                tradeoffs = ["Shipping cost is unknown."]
                try:
                    evidence = await self._review_sample(product, request.max_reviews)
                except ShoppingError as exc:
                    if exc.code == "rate_limited" or exc.status_code in _ACCESS_DENIED:
                        raise
                    tradeoffs.append(f"Review sample unavailable ({exc.code}).")
                count = product.rating_count
                # Bayesian shrinkage: 20 prior ratings at 3/5, never trust sparse averages alone.
                rating = product.rating_stars if product.rating_stars is not None else 3
                score = (rating * count + 3 * 20) / (count + 20)
                score += min(log1p(count) / 20, 0.3)
                if evidence and evidence.usable_reviews:
                    buyer_fraction = (
                        evidence.verified_buyer_reviews / evidence.usable_reviews
                    )
                    recurring = sum(
                        theme.mentions
                        for theme in evidence.negatives
                        if theme.mentions >= 2
                    )
                    score += 0.15 * buyer_fraction - min(
                        0.5, recurring / evidence.usable_reviews
                    )
                else:
                    score -= 0.2
                value = score / price
                reasons = [
                    f"Available offer: {price:,} toman within budget.",
                    f"Review score uses {count} ratings with a 20-rating prior at 3/5.",
                ]
                if request.required_features:
                    reasons.append(
                        "Required features verified in specifications: "
                        + ", ".join(request.required_features)
                    )
                if count < 20 or not evidence or evidence.verified_buyer_reviews < 5:
                    tradeoffs.append(
                        "Buyer evidence is too thin for a confident winner."
                    )
                if evidence and evidence.negatives:
                    tradeoffs.append(
                        "Sample negatives: "
                        + ", ".join(theme.text for theme in evidence.negatives[:3])
                    )
                if (
                    product.cheapest_available_offer
                    and product.default_offer
                    and product.cheapest_available_offer.variant_id
                    != product.default_offer.variant_id
                ):
                    tradeoffs.append(
                        "Cheapest offer differs from the default variant; inspect seller, color, size and warranty."
                    )
                candidates.append(
                    MatchCandidate(
                        product=product,
                        review_evidence=evidence,
                        review_score=round(score, 4),
                        value_score=value,
                        reasons=tuple(reasons),
                        tradeoffs=tuple(tradeoffs),
                    )
                )
            except ShoppingError as exc:
                if exc.code == "rate_limited" or exc.status_code in _ACCESS_DENIED:
                    raise
                excluded[card.id] = f"Could not verify details ({exc.code})"
        best_value = (
            max(candidates, key=lambda item: item.value_score) if candidates else None
        )
        best_reviewed = (
            max(candidates, key=lambda item: item.review_score) if candidates else None
        )
        candidates.sort(
            key=lambda item: (
                item.review_score
                if request.priorities and request.priorities[0] == "reviews"
                else item.value_score
            ),
            reverse=True,
        )
        confident = bool(
            best_reviewed
            and best_reviewed.product.rating_count >= 20
            and best_reviewed.review_evidence
            and best_reviewed.review_evidence.verified_buyer_reviews >= 5
        )
        explanation = "No verified eligible products in the bounded search sample. Try a clearer product_type or fewer required features."
        if candidates:
            explanation = "Best value maximizes evidence-adjusted review score per toman; best reviewed maximizes the review score independent of price."
            explanation += (
                " The picks differ because of price."
                if best_value.product.id != best_reviewed.product.id
                else " Both criteria select the same product."
            )
            if not confident:
                explanation += " Evidence is too thin to declare a confident winner."
        shortlist = candidates[:4]
        for pick in (best_value, best_reviewed):
            if pick is not None and pick not in shortlist:
                shortlist[-1] = pick
        return BestMatch(
            candidates=tuple(shortlist),
            category_options=category_options,
            category_source_url=category_source_url,
            best_value_id=best_value.product.id if best_value else None,
            best_reviewed_id=best_reviewed.product.id if best_reviewed else None,
            confident_winner=confident,
            explanation=explanation,
            candidates_examined=len(cards),
            excluded=excluded,
            limits={
                "category_lookups": category_lookups,
                "search_pages": 1,
                "candidate_details": request.candidate_limit,
                "review_pages_per_candidate": min(3, (request.max_reviews + 19) // 20),
                "reviews_per_candidate": request.max_reviews,
            },
            source_url=page.source_url or "https://www.digikala.com/search/",
            retrieved_at=page.retrieved_at or datetime.now(UTC),
            notes=(
                "Ranking is a transparent heuristic, not a complete catalog search. Features use exact normalized specification phrases. Product type is verified by a caller-selected or dynamically resolved store category ID.",
            ),
        )
