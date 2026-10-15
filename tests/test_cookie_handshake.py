import asyncio
from time import monotonic, time

import httpx
import pytest

from shopping_mcp.domain.errors import ShoppingError
from shopping_mcp.infrastructure.shops.digikala import DigikalaShop
from shopping_mcp.interfaces.http import create_http_app


def challenge(request, **headers):
    return httpx.Response(
        307,
        headers={
            "location": str(request.url),
            "set-cookie": "digicdn_cookie=test-cookie; Path=/; Secure; HttpOnly",
            **headers,
        },
    )


def test_cookie_handshake_preserves_pacing_and_reuses_cookie_until_expiry(payloads):
    async def run():
        calls = []
        starts = []

        def handler(request):
            calls.append(request)
            starts.append(monotonic())
            if "digicdn_cookie=test-cookie" not in request.headers.get("cookie", ""):
                return challenge(request)
            return httpx.Response(200, json=payloads["search"])

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            shop = DigikalaShop(client, request_interval=0.01, cache_ttl=0)
            assert (await shop.search_products("laptop")).products
            assert len(calls) == 2
            assert calls[0].url == calls[1].url
            assert (await shop.search_products("phone")).products
            assert len(calls) == 3
            assert all(b - a >= 0.009 for a, b in zip(starts, starts[1:]))
            # HTTPX drops an expired cookie and accepts a fresh handshake.
            for cookie in client.cookies.jar:
                cookie.expires = int(time()) - 1
            assert (await shop.search_products("tablet")).products
            assert len(calls) == 5
            assert "cookie" not in calls[3].headers
            assert "digicdn_cookie=test-cookie" in calls[4].headers["cookie"]

    asyncio.run(run())


@pytest.mark.parametrize(
    "headers",
    [
        {"location": "https://other.example/v1/search/?q=laptop&page=1"},
        {"location": "http://api.digikala.com/v1/search/?q=laptop&page=1"},
        {"location": "/different/path/"},
        {"location": "/v1/search/?q=other&page=1"},
        {
            "location": "https://user:password@api.digikala.com/v1/search/?q=laptop&page=1"
        },
        {"location": ""},
        {"set-cookie": "unrelated=test-cookie; Path=/"},
        {"set-cookie": "digicdn_cookie=; Max-Age=0; Path=/"},
    ],
)
def test_other_redirects_are_terminal_even_with_automatic_redirects_enabled(headers):
    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            return challenge(request, **headers)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=True
        ) as client:
            with pytest.raises(ShoppingError) as error:
                await DigikalaShop(client, request_interval=0).search_products("laptop")
            assert error.value.status_code == 307
            assert len(calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "location", ["https://api.digikala.com:invalid/", "javascript:alert(1)"]
)
def test_invalid_redirect_location_is_a_terminal_safe_error(location):
    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            return challenge(request, location=location)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ShoppingError, match="invalid redirect"):
                await DigikalaShop(client, request_interval=0).search_products("laptop")
            assert len(calls) == 1

    asyncio.run(run())


@pytest.mark.parametrize("status", [301, 302, 303, 308, 401, 403, 429])
def test_only_307_can_start_the_cookie_handshake(status):
    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            response = challenge(request)
            response.status_code = status
            return response

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ShoppingError):
                await DigikalaShop(client, request_interval=0).search_products("laptop")
            assert len(calls) == 1

    asyncio.run(run())


def test_repeated_cookie_redirect_stops_after_one_repeat():
    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            return challenge(request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ShoppingError) as error:
                await DigikalaShop(client, request_interval=0).search_products("laptop")
            assert error.value.status_code == 307
            assert len(calls) == 2

    asyncio.run(run())


def test_http_health_and_tools_share_owned_client_and_close_it(monkeypatch, payloads):
    async def run():
        original = httpx.AsyncClient
        owned = []
        calls = []
        token = "test-token-for-shopping-mcp-1234567890"

        def handler(request):
            calls.append(request)
            assert "authorization" not in request.headers
            if "digicdn_cookie=test-cookie" not in request.headers.get("cookie", ""):
                return challenge(request)
            return httpx.Response(200, json=payloads["search"])

        def factory(**kwargs):
            client = original(transport=httpx.MockTransport(handler), **kwargs)
            owned.append(client)
            return client

        monkeypatch.setattr("shopping_mcp.interfaces.http.httpx.AsyncClient", factory)
        app = create_http_app(token=token)
        async with app.router.lifespan_context(app):
            assert len(owned) == 1
            assert not calls
            async with original(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost"
            ) as client:
                response = await client.get("/health/digikala")
                assert response.status_code == 200
                report = response.json()
                assert report["cookie_redirect_followed"]
                assert report["http_status"] == report["body_status"] == 200
                assert "test-cookie" not in response.text
                result = await client.post(
                    "/mcp",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Accept": "application/json, text/event-stream",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "search_products",
                            "arguments": {"query": "phone"},
                        },
                    },
                )
                assert result.status_code == 200
                assert not result.json()["result"].get("isError")
                assert (
                    len(calls) == 3
                )  # Health handshake, then a tool with the same cookie.
                assert (await client.get("/health/digikala")).json() == report
                assert (await client.get("/health")).status_code == 200
                assert len(calls) == 3
        assert owned[0].is_closed

    asyncio.run(run())
