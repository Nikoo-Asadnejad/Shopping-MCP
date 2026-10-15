import asyncio

import httpx
from fastmcp import Client

from shopping_mcp.application.service import ShoppingService
from shopping_mcp.infrastructure.shops.digikala import DigikalaShop
from shopping_mcp.interfaces.mcp import create_server


def test_discovery_and_all_six_tools(service_factory, payloads):
    image_url = "https://dkstatics-public.digikala.com/digikala-products/sample.jpg"
    payloads["search"]["data"]["products"][0]["images"] = {"main": {"url": [image_url]}}
    payloads["details_123"]["data"]["product"]["images"] = {
        "main": {"url": [image_url]}
    }

    async def run():
        service, upstream, _ = service_factory()
        async with upstream, Client(create_server(service)) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools} == {
                "search_products",
                "get_product_details",
                "compare_products",
                "summarize_reviews",
                "find_best_match",
                "suggest_searches",
            }
            assert all(tool.output_schema for tool in tools)
            assert all(tool.annotations.read_only_hint for tool in tools)
            calls = [
                (
                    "search_products",
                    {"query": "laptop", "filters": {"available_only": False}},
                ),
                ("get_product_details", {"product": "123"}),
                ("compare_products", {"products": ["123", "456"]}),
                ("summarize_reviews", {"product": "123", "max_reviews": 20}),
                ("find_best_match", {"query": "laptop", "budget_toman": 2000}),
                ("suggest_searches", {"query": "lap"}),
            ]
            for name, arguments in calls:
                result = await client.call_tool(name, arguments)
                assert not result.is_error, (name, result)
                assert result.structured_content is not None
                if name == "search_products":
                    item = result.structured_content["products"][0]
                    assert item["image_url"] == image_url
                    assert item["url"] == "https://www.digikala.com/product/dkp-123/"
                    assert item["rating_stars"] == 4.0
                    assert item["rating_count"] == 100
                    assert item["price_toman"] == 1000
                    assert item["price_unit"] == "toman"
                    assert all(
                        product["available"] and product["price_toman"] > 0
                        for product in result.structured_content["products"]
                    )
                elif name == "get_product_details":
                    assert result.structured_content["image_url"] == image_url
            for name, arguments in [
                ("get_product_details", {"product": "../123"}),
                ("search_products", {"query": "", "page": 0}),
                ("compare_products", {"products": ["123", "123"]}),
                ("search_products", {"query": "laptop", "page": True}),
                ("search_products", {"query": "laptop", "page": "1"}),
            ]:
                result = await client.call_tool(name, arguments, raise_on_error=False)
                assert result.is_error

    asyncio.run(run())


def test_shared_client_is_closed_with_server_lifespan(monkeypatch, payloads):
    original = httpx.AsyncClient
    clients = []

    def create_client(**kwargs):
        client = original(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=payloads["autocomplete"])
            ),
            **kwargs,
        )
        clients.append(client)
        return client

    monkeypatch.setattr("shopping_mcp.interfaces.mcp.httpx.AsyncClient", create_client)

    async def run():
        async with Client(create_server()) as client:
            for _ in range(2):
                await client.call_tool("suggest_searches", {"query": "laptop"})
            assert len(clients) == 1
            assert not clients[0].is_closed
        assert clients[0].is_closed

    asyncio.run(run())


def test_upstream_errors_are_tool_errors():
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(429))
        ) as upstream:
            shop = DigikalaShop(upstream, request_interval=0)
            service = ShoppingService(shop, shop.get_search_suggestions)
            async with Client(create_server(service)) as client:
                result = await client.call_tool(
                    "get_product_details", {"product": "123"}, raise_on_error=False
                )
                assert result.is_error
                assert "rate_limited" in result.content[0].text

    asyncio.run(run())


def test_subprocess_stdio_transport():
    import sys
    from pathlib import Path

    from fastmcp.client.transports import StdioTransport

    async def run():
        transport = StdioTransport(
            command=sys.executable,
            args=[str(Path(__file__).parent / "mcp_fixture_server.py")],
        )
        async with Client(transport) as client:
            assert len(await client.list_tools()) == 6
            result = await client.call_tool("suggest_searches", {"query": "lap"})
            assert result.structured_content["categories"][0]["id"] == 18
            assert result.structured_content["categories"][0]["title"] == "لپ تاپ"
            invalid = await client.call_tool(
                "get_product_details", {"product": "../123"}, raise_on_error=False
            )
            assert invalid.is_error

    asyncio.run(run())
