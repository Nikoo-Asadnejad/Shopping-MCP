import asyncio
from copy import deepcopy

import httpx
import pytest

from shopping_mcp.domain.errors import ShoppingError
from shopping_mcp.domain.product.search_filters import SearchFilters
from shopping_mcp.infrastructure.shops.digikala import DigikalaShop


def test_cached_snapshot_keeps_timestamp_and_expires(payloads, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(
        "shopping_mcp.infrastructure.shops.digikala.api.monotonic", lambda: now[0]
    )

    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=payloads["search"])

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            shop = DigikalaShop(client, request_interval=0)
            first = await shop.search_products("laptop")
            second = await shop.search_products("laptop")
            assert second == first
            assert second.retrieved_at == first.retrieved_at
            assert len(calls) == 1
            await shop.search_products(
                "laptop", filters=SearchFilters(max_price_toman=10)
            )
            await shop.search_products("laptop", page=2)
            assert len(calls) == 3
            now[0] += 31
            await shop.search_products("laptop")
            assert len(calls) == 4

    asyncio.run(run())


def test_cache_eviction_and_failed_response_not_cached(payloads):
    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            if request.url.params["q"] == "bad":
                return httpx.Response(429)
            return httpx.Response(200, json=payloads["autocomplete"])

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            shop = DigikalaShop(client, request_interval=0, cache_size=1)
            for query in ("laptop", "phone", "laptop"):
                await shop.get_search_suggestions(query)
            assert len(calls) == 3
            for _ in range(2):
                with pytest.raises(ShoppingError, match="rate limited"):
                    await shop.get_search_suggestions("bad")
            assert len(calls) == 5

    asyncio.run(run())


def test_invalid_mapped_data_is_never_cached(payloads):
    bad = deepcopy(payloads["comments"])
    bad["data"]["comments"][0]["is_buyer"] = "false"

    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(
                200, json=bad if len(calls) == 1 else payloads["comments"]
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            shop = DigikalaShop(client, request_interval=0)
            with pytest.raises(ShoppingError) as error:
                await shop.get_reviews("123")
            assert error.value.code == "upstream_changed"
            result = await shop.get_reviews("123")
            assert result.reviews
            assert len(calls) == 2

    asyncio.run(run())


def test_cached_read_cannot_bypass_page_validation(payloads):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=payloads["search"])
            )
        ) as client:
            shop = DigikalaShop(client, request_interval=0)
            await shop.search_products("laptop", 1)
            for invalid_page in (True, 1.0):
                with pytest.raises(ValueError, match="page must be an integer"):
                    await shop.search_products("laptop", invalid_page)

    asyncio.run(run())
