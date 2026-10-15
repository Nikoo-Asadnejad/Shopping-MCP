import asyncio

import httpx
import pytest

from shopping_mcp.infrastructure.shops.digikala import DigikalaShop
from shopping_mcp.infrastructure.shops.digikala.health import DigikalaHealthCheck
from shopping_mcp.interfaces.http import create_http_app


@pytest.mark.parametrize(
    "status,payload,expected_code",
    [
        (307, None, "unavailable"),
        (403, None, "unavailable"),
        (429, None, "rate_limited"),
        (503, None, "unavailable"),
        (200, {"status": 403}, "unavailable"),
        (200, {"status": 200, "data": {}}, "upstream_changed"),
        (200, None, "upstream_changed"),
        (200, [], "upstream_changed"),
        (200, {"status": {"private": "value"}}, "upstream_changed"),
    ],
)
def test_upstream_failure_does_not_prevent_startup_or_discovery(
    monkeypatch, service_factory, status, payload, expected_code
):
    async def run():
        service, upstream, tool_calls = service_factory()
        original = httpx.AsyncClient
        checks = []

        def handler(request):
            checks.append(request)
            return httpx.Response(
                status,
                json=payload,
                headers={
                    "location": "/v1/search/?q=laptop&page=1#private",
                    "set-cookie": "private-session=secret",
                }
                if status == 307
                else {},
            )

        monkeypatch.setattr(
            "shopping_mcp.interfaces.http.httpx.AsyncClient",
            lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
        )
        app = create_http_app(service)
        async with upstream, app.router.lifespan_context(app):
            async with original(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost"
            ) as client:
                assert not checks  # Startup makes no upstream requests.
                assert (await client.get("/health")).status_code == 200
                assert not checks
                listing = await client.post(
                    "/mcp",
                    headers={"Accept": "application/json, text/event-stream"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                )
                assert listing.status_code == 200
                assert len(listing.json()["result"]["tools"]) == 6
                assert not checks
                response = await client.get("/health/digikala")
                report = response.json()
                assert response.status_code == 503
                assert response.headers["cache-control"] == "no-store"
                assert report["status"] == "unavailable"
                assert report["http_status"] == status
                assert report["code"] == expected_code
                assert report["endpoint"] == str(checks[0].url)
                assert report["checked_at"] and report["elapsed_ms"] >= 0
                assert "private" not in response.text and "secret" not in response.text
                if status == 307:
                    assert (
                        report["redirect_location"]
                        == "https://api.digikala.com/v1/search/"
                    )
                    assert report["redirect_query_redacted"]
                assert (await client.get("/health")).status_code == 200
                assert (await client.get("/health/digikala")).json() == report
                assert len(checks) == 1  # No redirects, retries or repeated polling.
                assert not tool_calls

    asyncio.run(run())


def test_upstream_success_is_coalesced_cached_and_refreshed(monkeypatch, payloads):
    async def run():
        original = httpx.AsyncClient
        calls = []
        now = 100.0

        async def handler(request):
            calls.append(request)
            await asyncio.sleep(0)
            return httpx.Response(200, json=payloads["search"])

        monkeypatch.setattr(
            "shopping_mcp.interfaces.http.httpx.AsyncClient",
            lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
        )
        monkeypatch.setattr(
            "shopping_mcp.infrastructure.shops.digikala.health.monotonic", lambda: now
        )
        async with httpx.AsyncClient() as upstream:
            checker = DigikalaHealthCheck(DigikalaShop(upstream, request_interval=0))
            reports = await asyncio.gather(*(checker.check() for _ in range(5)))
            assert len(calls) == 1
            assert all(report == reports[0] for report in reports)
            assert reports[0]["status"] == "ok"
            assert reports[0]["http_status"] == reports[0]["body_status"] == 200
            assert "products" not in reports[0]
            now += 31
            assert (await checker.check())["status"] == "ok"
            assert len(calls) == 2

    asyncio.run(run())


@pytest.mark.parametrize(
    "error", [httpx.ReadTimeout("private"), TimeoutError("private")]
)
def test_network_failure_is_bounded_and_cached(monkeypatch, error):
    async def run():
        original = httpx.AsyncClient
        calls = []

        def handler(request):
            calls.append(request)
            raise error

        monkeypatch.setattr(
            "shopping_mcp.interfaces.http.httpx.AsyncClient",
            lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
        )
        async with httpx.AsyncClient() as upstream:
            checker = DigikalaHealthCheck(DigikalaShop(upstream, request_interval=0))
            report = await checker.check()
            assert report["status"] == "unavailable"
            assert report["http_status"] is None
            assert report["code"] == "unavailable"
            assert "private" not in str(report)
            assert await checker.check() == report
            assert len(calls) == 1

    asyncio.run(run())
