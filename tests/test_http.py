import asyncio

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from shopping_mcp.application.service import ShoppingService
from shopping_mcp.infrastructure.shops.digikala import DigikalaShop
from shopping_mcp.interfaces.http import create_http_app

TOKEN = "test-token-for-shopping-mcp-1234567890"


def transport_for(app, token=None):
    return StreamableHttpTransport(
        "http://localhost/mcp",
        headers={"Authorization": f"Bearer {token}"} if token else None,
        httpx_client_factory=lambda **kwargs: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), **kwargs
        ),
    )


def test_http_lifespan_discovery_and_six_tools(service_factory):
    async def run():
        service, upstream, calls = service_factory()
        app = create_http_app(service, token=TOKEN)
        async with upstream, app.router.lifespan_context(app):
            async with Client(transport_for(app, TOKEN)) as client:
                assert len(await client.list_tools()) == 6
                for name, arguments in [
                    ("search_products", {"query": "لپ تاپ"}),
                    ("get_product_details", {"product": "123"}),
                    ("compare_products", {"products": ["123", "456"]}),
                    ("summarize_reviews", {"product": "123"}),
                    ("find_best_match", {"query": "laptop", "budget_toman": 2000}),
                    ("suggest_searches", {"query": "lap"}),
                ]:
                    result = await client.call_tool(name, arguments)
                    assert not result.is_error, name
                    assert result.structured_content
                result = await client.call_tool(
                    "get_product_details", {"product": "../123"}, raise_on_error=False
                )
                assert result.is_error and "invalid_input" in result.content[0].text
        assert all("authorization" not in request.headers for request in calls)

    asyncio.run(run())


def test_auth_and_public_pages_make_no_upstream_calls(service_factory):
    async def run():
        service, upstream, calls = service_factory()
        app = create_http_app(service, token=TOKEN)
        async with upstream, app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost"
            ) as client:
                for path in ("/", "/privacy", "/health"):
                    assert (await client.get(path)).status_code == 200
                assert (await client.get("/health")).json()["upstream"] == "not_checked"
                assert "unofficial" in (await client.get("/privacy")).text
                for method in (client.get, client.post, client.delete):
                    for headers in ({}, {"Authorization": "Bearer incorrect"}):
                        response = await method("/mcp", headers=headers)
                        # JSON/stateless transport has no GET event stream.
                        assert response.status_code == (
                            405 if method == client.get else 401
                        )
                assert not calls

    asyncio.run(run())


def test_http_outage_is_a_tool_error():
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(403))
        ) as upstream:
            shop = DigikalaShop(upstream, request_interval=0)
            app = create_http_app(
                ShoppingService(shop, shop.get_search_suggestions), token=TOKEN
            )
            async with app.router.lifespan_context(app):
                async with Client(transport_for(app, TOKEN)) as client:
                    result = await client.call_tool(
                        "search_products", {"query": "laptop"}, raise_on_error=False
                    )
                    assert result.is_error
                    assert "unavailable" in result.content[0].text

    asyncio.run(run())


def test_request_size_limit_including_chunked_body(service_factory):
    async def run():
        service, upstream, calls = service_factory()
        app = create_http_app(service, token=TOKEN)

        async def chunks():
            for _ in range(3):
                yield b"x" * 8192

        async with (
            upstream,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost"
            ) as client,
        ):
            for content in (b"x" * 20_000, chunks()):
                response = await client.post("/mcp", content=content)
                assert response.status_code == 413
                assert not calls

    asyncio.run(run())


def test_reject_cross_origin_requests(service_factory):
    async def run():
        service, upstream, calls = service_factory()
        app = create_http_app(service, token=TOKEN)
        async with (
            upstream,
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost"
            ) as client,
        ):
            response = await client.post(
                "/mcp", headers={"Origin": "https://untrusted.example"}, json={}
            )
            assert response.status_code == 403
            assert not calls

    asyncio.run(run())


@pytest.mark.parametrize("token", ["", " ", "too-short"])
def test_reject_invalid_token_configuration(token):
    with pytest.raises(ValueError, match="SHOPPING_MCP_TOKEN"):
        create_http_app(token=token)
