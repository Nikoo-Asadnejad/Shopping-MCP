import json
from pathlib import Path

import httpx
import pytest

from shopping_mcp.application.service import ShoppingService
from shopping_mcp.infrastructure.shops.digikala import DigikalaShop

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def payloads():
    return {path.stem: json.loads(path.read_text()) for path in FIXTURES.glob("*.json")}


@pytest.fixture
def service_factory(payloads):
    def create(overrides=None):
        records = dict(payloads)
        records.update(overrides or {})
        requests = []

        def handler(request):
            requests.append(request)
            path = request.url.path
            if path == "/v1/search/":
                key = "search"
            elif path == "/v1/autocomplete/":
                key = "autocomplete"
            elif "comments" in path:
                key = "comments"
            elif "tabular-recommendation" in path:
                key = "recommendations"
            else:
                key = "details_" + path.strip("/").split("/")[-1]
            data = records.get(key, records.get("details"))
            return httpx.Response(200, json=data)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        shop = DigikalaShop(client, request_interval=0)
        return (
            ShoppingService(shop, shop.get_search_suggestions),
            client,
            requests,
        )

    return create
