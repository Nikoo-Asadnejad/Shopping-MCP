"""Subprocess transport test server. No upstream network calls."""

import argparse
import json
from pathlib import Path

import httpx

from shopping_mcp.application.service import ShoppingService
from shopping_mcp.infrastructure.shops.digikala import DigikalaShop
from shopping_mcp.interfaces.http import create_http_app
from shopping_mcp.interfaces.mcp import create_server


def handler(request):
    path = request.url.path
    if path == "/v1/search/":
        name = "search"
    elif path == "/v1/autocomplete/":
        name = "autocomplete"
    elif "comments" in path:
        name = "comments"
    else:
        name = "details_" + path.strip("/").split("/")[-1]
    return httpx.Response(
        200,
        json=json.loads(
            (Path(__file__).parent / "fixtures" / f"{name}.json").read_text()
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    shop = DigikalaShop(client, request_interval=0)
    service = ShoppingService(shop, shop.get_search_suggestions)
    if args.port:
        import uvicorn

        uvicorn.run(
            create_http_app(service),
            host="127.0.0.1",
            port=args.port,
            access_log=False,
        )
    else:
        create_server(service).run(transport="stdio", show_banner=False)
