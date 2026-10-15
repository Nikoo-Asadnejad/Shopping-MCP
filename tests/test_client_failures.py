import asyncio

import httpx
import pytest

from shopping_mcp.domain.errors import ShoppingError
from shopping_mcp.infrastructure.shops.digikala import DigikalaShop


@pytest.mark.parametrize(
    "status,code,retries",
    [
        (404, "not_found", 1),
        (403, "unavailable", 1),
        (429, "rate_limited", 1),
        (307, "unavailable", 1),
        (503, "unavailable", 2),
    ],
)
def test_status_mapping_and_retry_bound(status, code, retries):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ShoppingError) as error:
                await DigikalaShop(client, request_interval=0).get_product_details(
                    "123"
                )
            assert error.value.code == code

    asyncio.run(run())
    assert len(calls) == retries


def test_transient_failure_recovers_once():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(200, json={"status": 200, "data": {"auto_complete": []}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert (
                await DigikalaShop(client, request_interval=0).suggest_searches(
                    "laptop"
                )
                == ()
            )

    asyncio.run(run())
    assert len(calls) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"status": 200, "data": {"product": []}},
        {
            "status": 200,
            "data": {
                "product": {
                    "id": 123,
                    "title_fa": "x",
                    "url": {"uri": "/product/dkp-123/"},
                    "rating": {"count": 1, "rate": 200},
                }
            },
        },
        {
            "status": 200,
            "data": {
                "product": {
                    "id": 123,
                    "title_fa": "x",
                    "url": {"uri": "/product/dkp-123/"},
                    "default_variant": {"price": {"selling_price": 123}},
                }
            },
        },
    ],
)
def test_schema_drift_yields_safe_error(payload):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as client:
            with pytest.raises(ShoppingError) as error:
                await DigikalaShop(client, request_interval=0).get_product_details(
                    "123"
                )
            assert error.value.code == "upstream_changed"

    asyncio.run(run())


def test_rate_and_concurrency_limits(payloads):
    async def run():
        starts = []
        active = peak = 0

        async def handler(request):
            nonlocal active, peak
            starts.append(asyncio.get_running_loop().time())
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.03)
            active -= 1
            return httpx.Response(200, json=payloads["autocomplete"])

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            shop = DigikalaShop(client, request_interval=0.01, concurrency=2)
            await asyncio.gather(*(shop.suggest_searches("laptop") for _ in range(5)))
        assert peak <= 2
        assert all(b - a >= 0.009 for a, b in zip(starts, starts[1:]))

    asyncio.run(run())


def test_mismatched_product_id_is_schema_drift(payloads):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=payloads["details_456"])
            )
        ) as client:
            with pytest.raises(ShoppingError) as error:
                await DigikalaShop(client, request_interval=0).get_product_details(
                    "123"
                )
            assert error.value.code == "upstream_changed"

    asyncio.run(run())
