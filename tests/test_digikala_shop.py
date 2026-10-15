import asyncio

import httpx
import pytest

from shopping_mcp.infrastructure.shops import Shop
from shopping_mcp.infrastructure.shops.digikala import DigikalaShop, ShopApiError


def _response(data: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(200, json={"status": status, "data": data})


def test_search_maps_current_offer_and_rating() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/search/"
        assert request.url.params["q"] == "لپ تاپ"
        assert request.url.params["page"] == "2"
        return _response(
            {
                "pager": {"total_pages": 3, "total_items": 42},
                "products": [
                    {
                        "id": 123,
                        "title_fa": "لپ تاپ نمونه",
                        "url": {"uri": "/product/dkp-123/"},
                        "status": "marketable",
                        "rating": {"rate": 80, "count": 20},
                        "default_variant": {"price": {"selling_price": 1250000}},
                    }
                ],
            }
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            shop = DigikalaShop(client)
            assert isinstance(shop, Shop)
            result = await shop.search_products("لپ تاپ", page=2)
            assert result.total_items == 42
            assert result.products[0].price_toman == 125000
            assert result.products[0].rating_stars == 4.0
            assert result.products[0].available is True

    asyncio.run(run())


def test_details_include_specs_offers_and_upstream_review_overview() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/product/123/"
        return _response(
            {
                "product": {
                    "id": 123,
                    "title_fa": "لپ تاپ نمونه",
                    "url": {"uri": "/product/dkp-123/"},
                    "status": "marketable",
                    "rating": {"rate": 80, "count": 20},
                    "default_variant": {"price": {"selling_price": 1250000}},
                    "specifications": [
                        {
                            "title": "حافظه",
                            "attributes": [{"title": "رم", "values": ["8 گیگابایت"]}],
                        }
                    ],
                    "variants": [
                        {
                            "id": 77,
                            "status": "marketable",
                            "price": {"selling_price": 1250000},
                            "seller": {"title": "فروشنده نمونه"},
                            "color": {"title": "مشکی"},
                            "warranty": {"title_fa": "گارانتی نمونه"},
                        }
                    ],
                    "comments_overview": {
                        "overview": "مناسب کار روزمره",
                        "advantages": ["سبک"],
                        "disadvantages": ["باتری ضعیف"],
                    },
                }
            }
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            details = await DigikalaShop(client).get_product_details(123)
            assert details.specifications[0].values == ("8 گیگابایت",)
            assert details.offers[0].seller == "فروشنده نمونه"
            assert details.buyer_advantages == ("سبک",)
            assert details.buyer_disadvantages == ("باتری ضعیف",)

    asyncio.run(run())


def test_comments_keep_buyer_status_and_treat_zero_rate_as_unrated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/product/123/comments/"
        return _response(
            {
                "pager": {"total_pages": 2, "total_items": 21},
                "comments": [
                    {
                        "id": 9,
                        "body": "آیا برای بازی مناسب است؟",
                        "rate": 0,
                        "is_buyer": False,
                    },
                    {
                        "id": 10,
                        "body": "برای کار روزمره خوب است",
                        "rate": 4,
                        "is_buyer": True,
                        "advantages": ["سبک"],
                    },
                ],
            }
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            page = await DigikalaShop(client).get_reviews(123)
            assert page.total_items == 21
            assert page.reviews[0].rating_stars is None
            assert page.reviews[0].is_buyer is False
            assert page.reviews[1].rating_stars == 4
            assert page.reviews[1].advantages == ("سبک",)

    asyncio.run(run())


def test_body_level_redirect_is_not_treated_as_product_data() -> None:
    async def run() -> None:
        transport = httpx.MockTransport(lambda _: _response({}, status=302))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(ShopApiError) as error:
                await DigikalaShop(client).get_product_details(123)
            assert error.value.status_code == 302

    asyncio.run(run())


def test_digikala_only_suggestions_and_recommendations() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/autocomplete/":
            return _response(
                {
                    "auto_complete": [
                        {"keyword": "لپ تاپ لنوو"},
                        {"keyword": "لپ تاپ ایسوس"},
                    ]
                }
            )
        assert request.url.path == "/v1/product/123/tabular-recommendation/"
        return _response(
            {
                "data": {
                    "products": [
                        {
                            "id": 456,
                            "title_fa": "مدل مشابه",
                            "url": {"uri": "/product/dkp-456/"},
                            "status": "out_of_stock",
                            "rating": {"count": 0},
                        }
                    ]
                }
            }
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            shop = DigikalaShop(client)
            assert await shop.suggest_searches("لپ تاپ") == (
                "لپ تاپ لنوو",
                "لپ تاپ ایسوس",
            )
            recommendations = await shop.get_recommendations("123")
            assert recommendations[0].id == "456"
            assert recommendations[0].available is False

    asyncio.run(run())


def test_invalid_product_id_is_rejected_before_request() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("invalid IDs must not reach Digikala")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError):
                await DigikalaShop(client).get_product_details("../123")

    asyncio.run(run())


def test_recorded_autocomplete_maps_nested_category_identity():
    import json
    from pathlib import Path

    from shopping_mcp.infrastructure.shops.digikala.mapping import category_suggestions

    payload = json.loads(
        (
            Path(__file__).parents[1] / "docs/evidence/live-check/autocomplete.json"
        ).read_text()
    )
    categories = category_suggestions(payload["data"])
    assert len(categories) == 1
    assert categories[0].id == 18
    assert categories[0].title == "لپ تاپ و الترابوک"
    assert len(categories[0].keywords) == 5
    assert "laptop gaming" in categories[0].keywords
