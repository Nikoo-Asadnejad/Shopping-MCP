"""Translate undocumented response fields into small store-neutral snapshots."""

from datetime import datetime
from typing import Any

from shopping_mcp.domain.errors import ShoppingError
from shopping_mcp.domain.product import (
    Offer,
    ProductDetails,
    ProductSummary,
    SearchPage,
    Specification,
)
from shopping_mcp.domain.product.category_suggestion import CategorySuggestion
from shopping_mcp.domain.product.search_suggestions import SearchSuggestions
from shopping_mcp.domain.review import Review, ReviewPage


def changed(message: str) -> ShoppingError:
    return ShoppingError(f"Digikala response changed: {message}", "upstream_changed")


def require_dict(data: dict, key: str) -> dict:
    value = data.get(key)
    if not isinstance(value, dict):
        raise changed(f"missing {key}")
    return value


def require_list(data: dict, key: str) -> list[dict]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise changed(f"missing {key}")
    return value


def text_items(value: Any, limit: int = 15) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise changed("invalid text list")
    return tuple(item[:500] for item in value[:limit] if item.strip())


def search_page(data: dict, page: int, source: str, now: datetime) -> SearchPage:
    products = require_list(data, "products")
    pager = require_dict(data, "pager")
    return SearchPage(
        page=page,
        total_pages=int(pager.get("total_pages") or 0),
        total_items=int(pager.get("total_items") or 0),
        products=tuple(product(item, now) for item in products[:20]),
        source_url=source,
        retrieved_at=now,
    )


def review_page(data: dict, identifier: str, page: int, now: datetime) -> ReviewPage:
    comments = require_list(data, "comments")
    pager = require_dict(data, "pager")
    return ReviewPage(
        page=page,
        total_pages=int(pager.get("total_pages") or 0),
        total_items=int(pager.get("total_items") or 0),
        retrieved_at=now,
        reviews=tuple(
            Review(
                id=str(item["id"]),
                body=(item.get("body") or "")[:2000],
                title=(item.get("title") or "")[:200],
                rating_stars=item.get("rate") if item.get("rate") != 0 else None,
                is_buyer=item.get("is_buyer", False),
                advantages=text_items(item.get("advantages")),
                disadvantages=text_items(item.get("disadvantages")),
                source_url=f"https://www.digikala.com/product/dkp-{identifier}/#comments",
            )
            for item in comments[:20]
        ),
    )


def search_suggestions(data: dict, source: str, now: datetime) -> SearchSuggestions:
    return SearchSuggestions(
        suggestions=tuple(
            item["keyword"][:200]
            for item in require_list(data, "auto_complete")
            if item.get("keyword")
        )[:10],
        categories=category_suggestions(data),
        source_url=source,
        retrieved_at=now,
    )


def recommendations(data: dict, now: datetime) -> tuple[ProductSummary, ...]:
    return tuple(
        product(item, now)
        for item in require_list(require_dict(data, "data"), "products")[:20]
    )


def price_toman(price_rial: int | None) -> int | None:
    if price_rial is None:
        return None
    if (
        not isinstance(price_rial, int)
        or isinstance(price_rial, bool)
        or price_rial < 0
    ):
        raise changed("invalid price")
    toman, remainder = divmod(price_rial, 10)
    if remainder:
        raise changed("price cannot be represented as whole toman")
    return toman if toman > 0 else None


def product(data: dict[str, Any], retrieved_at: datetime) -> ProductSummary:
    variant = data.get("default_variant") or {}
    rating = data.get("rating") or {}
    count = int(rating.get("count") or 0)
    uri = (data.get("url") or {}).get("uri")
    if (
        not isinstance(uri, str)
        or not uri.startswith(f"/product/dkp-{data.get('id')}/")
        or uri.startswith("//")
    ):
        raise changed("product URL is missing or invalid")
    if not data.get("id") or not data.get("title_fa"):
        raise changed("product ID or title missing")
    rate = rating.get("rate")
    if count and rate is None:
        raise changed("product rating missing")
    price = price_toman((variant.get("price") or {}).get("selling_price"))
    category = data.get("category") or {}
    brand = data.get("brand") or {}
    return ProductSummary(
        shop="digikala",
        id=str(data["id"]),
        title=data["title_fa"][:500],
        title_en=(data.get("title_en") or "")[:500] or None,
        url=f"https://www.digikala.com{uri}",
        available=data.get("status") == "marketable"
        and price is not None
        and variant.get("status", "marketable") == "marketable",
        price_toman=price,
        rating_stars=round(float(rate) / 20, 1) if count else None,
        rating_count=count,
        retrieved_at=retrieved_at,
        seller=(variant.get("seller") or {}).get("title"),
        default_variant_id=str(variant["id"]) if variant.get("id") else None,
        category_id=str(category["id"]) if category.get("id") else None,
        category=category.get("title_fa") or category.get("title_en"),
        brand_id=str(brand["id"]) if brand.get("id") else None,
    )


def offer(data: dict) -> Offer:
    if not data.get("id"):
        raise changed("variant ID missing")
    price = price_toman((data.get("price") or {}).get("selling_price"))
    return Offer(
        variant_id=str(data["id"]),
        seller=(data.get("seller") or {}).get("title"),
        price_toman=price,
        available=data.get("status") == "marketable" and price is not None,
        color=(data.get("color") or {}).get("title"),
        size=(data.get("size") or {}).get("title"),
        warranty=(data.get("warranty") or {}).get("title_fa"),
    )


def details(data: dict, retrieved_at: datetime) -> ProductDetails:
    summary = product(data, retrieved_at)
    specs = tuple(
        Specification(
            group=group.get("title") or "",
            name=attribute["title"],
            values=tuple(
                str(value)[:500] for value in (attribute.get("values") or ())[:8]
            ),
        )
        for group in (data.get("specifications") or ())[:30]
        for attribute in (group.get("attributes") or ())[:50]
    )
    specs = specs[:60]
    variants = data.get("variants") or ()
    offers = tuple(offer(variant) for variant in variants)
    default = data.get("default_variant") or {}
    default_offer = offer(default) if default.get("id") else None
    if data.get("status") != "marketable":
        offers = tuple(item.model_copy(update={"available": False}) for item in offers)
        if default_offer:
            default_offer = default_offer.model_copy(update={"available": False})
    all_offers = offers + ((default_offer,) if default_offer else ())
    available = [
        item for item in all_offers if item.available and item.price_toman is not None
    ]
    cheapest = min(available, key=lambda item: item.price_toman) if available else None
    overview = data.get("comments_overview") or {}
    description = data.get("review") or {}
    fields = summary.model_dump()
    fields["available"] = data.get("status") == "marketable" and bool(
        cheapest or summary.available
    )
    displayed_offers = list(offers[:20])
    if cheapest and cheapest not in displayed_offers:
        if len(displayed_offers) == 20:
            displayed_offers[-1] = cheapest
        else:
            displayed_offers.append(cheapest)
    return ProductDetails(
        **fields,
        coverage_notes=(
            f"Showing {len(displayed_offers)} selected offers from {len(offers)} returned variants plus the default offer and at most 60 specifications; cheapest available offer is selected from all returned variants. Shipping cost is unknown.",
        ),
        description=(description.get("description") or "")[:4000] or None,
        specifications=specs,
        offers=tuple(displayed_offers),
        default_offer=default_offer,
        cheapest_available_offer=cheapest,
        buyer_overview=(overview.get("overview") or "")[:3000] or None,
        buyer_advantages=text_items(overview.get("advantages")),
        buyer_disadvantages=text_items(overview.get("disadvantages")),
    )


def category_suggestions(data: dict) -> tuple[CategorySuggestion, ...]:
    groups = {}
    for item in (
        require_list(data, "categories")[:50]
        if data.get("categories") is not None
        else ()
    ):
        category = item.get("category", item)
        if not isinstance(category, dict):
            raise changed("invalid autocomplete category")
        identifier = category.get("id")
        title = (
            category.get("title_fa")
            or category.get("title_en")
            or category.get("title")
        )
        if identifier is None or not title:
            continue  # A hint without identity cannot verify product type.
        suggestion = CategorySuggestion(id=identifier, title=title[:200])
        entry = groups.setdefault(
            suggestion.id, {"category": suggestion, "keywords": []}
        )
        keyword = item.get("keyword")
        if (
            isinstance(keyword, str)
            and keyword.strip()
            and keyword not in entry["keywords"]
        ):
            entry["keywords"].append(keyword[:200])
    return tuple(
        entry["category"].model_copy(update={"keywords": tuple(entry["keywords"][:10])})
        for entry in groups.values()
    )[:10]
