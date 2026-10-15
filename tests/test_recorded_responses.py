"""Production adapter checks against sanitized 2026-10-15 local captures."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from shopping_mcp.infrastructure.shops.digikala import DigikalaShop

CAPTURES = Path(__file__).parents[1] / "docs/evidence/implementation-live"


@pytest.mark.parametrize(
    "family", ["search", "autocomplete", "details", "comments", "recommendations"]
)
def test_recorded_response_mapping(family):
    payload = json.loads((CAPTURES / f"{family}.json").read_text())

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as client:
            shop = DigikalaShop(client, request_interval=0)
            if family == "search":
                result = await shop.search_products("laptop")
                assert result.products and result.source_url and result.retrieved_at
                assert all(item.price_unit == "toman" for item in result.products)
            elif family == "autocomplete":
                result = await shop.get_search_suggestions("laptop")
                assert result.suggestions and result.categories
                assert result.categories[0].id == 18
            elif family == "details":
                result = await shop.get_product_details("20176433")
                assert result.id == "20176433" and result.specifications
                assert result.default_offer.price_toman == 84_990_000
                assert result.rating_stars == 3.8 and result.rating_count == 57
                assert result.cheapest_available_offer.available
            elif family == "comments":
                result = await shop.get_reviews("20176433")
                assert result.reviews and result.retrieved_at
                assert all(item.source_url for item in result.reviews)
                assert all(item.rating_stars != 0 for item in result.reviews)
            else:
                result = await shop.get_recommendations("20176433")
                assert result and all(item.url and item.retrieved_at for item in result)

    asyncio.run(run())
