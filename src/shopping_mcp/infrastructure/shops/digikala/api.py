"""Read-only access to Digikala's undocumented web API."""

from datetime import datetime, timezone
from typing import Any

import httpx

from shopping_mcp.domain.product import (
    Offer,
    ProductDetails,
    ProductSummary,
    SearchPage,
    Specification,
)
from shopping_mcp.domain.review import Review, ReviewPage
from shopping_mcp.infrastructure.shops.base import Shop

_API_URL = "https://api.digikala.com"
_PRODUCT_URL = "https://www.digikala.com"
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class ShopApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class DigikalaShop(Shop):
    """Map Digikala API responses to store-neutral models.

    The caller owns the shared AsyncClient and closes it at application shutdown.
    """

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "digikala"

    async def search_products(self, query: str, page: int = 1) -> SearchPage:
        if not query.strip() or len(query) > 200:
            raise ValueError("query must contain 1 to 200 characters")
        self._validate_page(page)
        data = await self._get("/v1/search/", params={"q": query.strip(), "page": page})
        products = self._require_list(data, "products")
        pager = self._require_dict(data, "pager")
        retrieved_at = datetime.now(timezone.utc)
        return SearchPage(
            page=page,
            total_pages=int(pager.get("total_pages") or 0),
            total_items=int(pager.get("total_items") or 0),
            products=tuple(self._product(item, retrieved_at) for item in products),
        )

    async def get_product_details(self, product_id: int | str) -> ProductDetails:
        digikala_id = self._validate_product_id(product_id)
        data = await self._get(f"/v2/product/{digikala_id}/")
        product = self._require_dict(data, "product")
        summary = self._product(product, datetime.now(timezone.utc))
        specifications = tuple(
            Specification(
                group=group.get("title") or "",
                name=attribute.get("title") or "",
                values=tuple(attribute.get("values") or ()),
            )
            for group in product.get("specifications") or ()
            for attribute in group.get("attributes") or ()
        )
        offers = tuple(self._offer(variant) for variant in product.get("variants") or ())
        overview = product.get("comments_overview") or {}
        return ProductDetails(
            **summary.model_dump(),
            specifications=specifications,
            offers=offers,
            buyer_overview=overview.get("overview"),
            buyer_advantages=tuple(overview.get("advantages") or ()),
            buyer_disadvantages=tuple(overview.get("disadvantages") or ()),
        )

    async def get_reviews(self, product_id: int | str, page: int = 1) -> ReviewPage:
        digikala_id = self._validate_product_id(product_id)
        self._validate_page(page)
        data = await self._get(f"/v1/product/{digikala_id}/comments/", params={"page": page})
        comments = self._require_list(data, "comments")
        pager = self._require_dict(data, "pager")
        return ReviewPage(
            page=page,
            total_pages=int(pager.get("total_pages") or 0),
            total_items=int(pager.get("total_items") or 0),
            reviews=tuple(
                Review(
                    id=str(item["id"]),
                    body=item.get("body") or "",
                    rating_stars=item.get("rate") or None,
                    is_buyer=bool(item.get("is_buyer")),
                    advantages=tuple(item.get("advantages") or ()),
                    disadvantages=tuple(item.get("disadvantages") or ()),
                )
                for item in comments
            ),
        )

    async def suggest_searches(self, query: str) -> tuple[str, ...]:
        if not query.strip() or len(query) > 200:
            raise ValueError("query must contain 1 to 200 characters")
        data = await self._get("/v1/autocomplete/", params={"q": query.strip()})
        return tuple(
            item["keyword"]
            for item in self._require_list(data, "auto_complete")
            if isinstance(item, dict) and item.get("keyword")
        )

    async def get_recommendations(self, product_id: int | str) -> tuple[ProductSummary, ...]:
        digikala_id = self._validate_product_id(product_id)
        data = await self._get(f"/v1/product/{digikala_id}/tabular-recommendation/")
        recommendations = self._require_dict(data, "data")
        retrieved_at = datetime.now(timezone.utc)
        return tuple(
            self._product(item, retrieved_at)
            for item in self._require_list(recommendations, "products")
        )

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = await self._client.get(
                f"{_API_URL}{path}", params=params, timeout=_TIMEOUT
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ShopApiError("Digikala request failed", exc.response.status_code) from exc
        except httpx.RequestError as exc:
            raise ShopApiError("Digikala is unavailable") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ShopApiError("Digikala returned invalid JSON") from exc
        if not isinstance(payload, dict) or payload.get("status") != 200:
            status = payload.get("status") if isinstance(payload, dict) else None
            status = status if isinstance(status, int) else None
            raise ShopApiError("Digikala returned an unexpected response", status)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ShopApiError("Digikala response is missing data")
        return data

    @staticmethod
    def _product(product: dict[str, Any], retrieved_at: datetime) -> ProductSummary:
        variant = product.get("default_variant") or {}
        rating = product.get("rating") or {}
        count = int(rating.get("count") or 0)
        uri = (product.get("url") or {}).get("uri")
        if not isinstance(uri, str) or not uri.startswith("/product/"):
            raise ShopApiError("Digikala product URL is missing or invalid")
        price = DigikalaShop._price_toman((variant.get("price") or {}).get("selling_price"))
        if "id" not in product:
            raise ShopApiError("Digikala product ID is missing")
        rate = rating.get("rate")
        if count and rate is None:
            raise ShopApiError("Digikala product rating is missing")
        return ProductSummary(
            shop="digikala",
            id=str(product["id"]),
            title=product.get("title_fa") or "",
            url=f"{_PRODUCT_URL}{uri}",
            available=product.get("status") == "marketable" and price is not None,
            price_toman=price,
            rating_stars=round(float(rate) / 20, 1) if count else None,
            rating_count=count,
            retrieved_at=retrieved_at,
        )

    @staticmethod
    def _offer(variant: dict[str, Any]) -> Offer:
        if "id" not in variant:
            raise ShopApiError("Digikala variant ID is missing")
        seller = variant.get("seller") or {}
        color = variant.get("color") or {}
        warranty = variant.get("warranty") or {}
        return Offer(
            variant_id=str(variant["id"]),
            seller=seller.get("title"),
            price_toman=DigikalaShop._price_toman(
                (variant.get("price") or {}).get("selling_price")
            ),
            available=variant.get("status") == "marketable",
            color=color.get("title"),
            warranty=warranty.get("title_fa"),
        )

    @staticmethod
    def _price_toman(price_rial: int | None) -> int | None:
        if price_rial is None:
            return None
        if not isinstance(price_rial, int) or isinstance(price_rial, bool) or price_rial < 0:
            raise ShopApiError("Digikala price is invalid")
        toman, remainder = divmod(price_rial, 10)
        if remainder:
            raise ShopApiError("Digikala price cannot be represented as whole toman")
        return toman

    @staticmethod
    def _require_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
        value = data.get(key)
        if not isinstance(value, dict):
            raise ShopApiError(f"Digikala response is missing {key}")
        return value

    @staticmethod
    def _require_list(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
        value = data.get(key)
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise ShopApiError(f"Digikala response is missing {key}")
        return value

    @staticmethod
    def _validate_product_id(product_id: int | str) -> int:
        if isinstance(product_id, bool):
            raise ValueError("product_id must be a positive Digikala ID")
        if isinstance(product_id, str):
            if not product_id.isascii() or not product_id.isdecimal():
                raise ValueError("product_id must be a positive Digikala ID")
            product_id = int(product_id)
        if not isinstance(product_id, int) or product_id <= 0:
            raise ValueError("product_id must be a positive Digikala ID")
        return product_id

    @staticmethod
    def _validate_page(page: int) -> None:
        if not isinstance(page, int) or isinstance(page, bool) or page <= 0:
            raise ValueError("page must be a positive integer")
