"""One paced async client for Digikala's read-only, undocumented web API."""

import asyncio
from collections import OrderedDict
from datetime import UTC, datetime
from functools import wraps
from time import monotonic
from typing import Any

import httpx
from pydantic import ValidationError

from shopping_mcp.domain.errors import ShoppingError
from shopping_mcp.domain.product import ProductDetails, ProductSummary, SearchPage
from shopping_mcp.domain.product.reference import product_id as parse_product_id
from shopping_mcp.domain.product.search_filters import SearchFilters
from shopping_mcp.domain.product.search_suggestions import SearchSuggestions
from shopping_mcp.domain.review import ReviewPage
from shopping_mcp.infrastructure.shops.base import Shop

from . import mapping

ShopApiError = ShoppingError  # Backward-compatible import for adapter users.
_API_URL = "https://api.digikala.com"
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _cached_read(operation):
    """Cache only successfully mapped, bounded snapshots, retaining freshness."""

    @wraps(operation)
    async def read(self, *args, **kwargs):
        now = monotonic()
        for key, (expires, _) in list(self._cache.items()):
            if expires <= now:
                del self._cache[key]
        # bool/float compare equal to integers in Python; keep their types in
        # the key so a hit cannot bypass the operation's input validation.
        key = (
            operation.__name__,
            tuple((type(value), value) for value in args),
            tuple((name, type(value), value) for name, value in sorted(kwargs.items())),
        )
        try:
            hash(key)
        except TypeError:
            return await operation(self, *args, **kwargs)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key][1]
        result = await operation(self, *args, **kwargs)
        if self._cache_ttl:
            self._cache[key] = (monotonic() + self._cache_ttl, result)
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return result

    return read


class DigikalaShop(Shop):
    """Caller owns the shared client and closes it at service shutdown.

    Default: at most 3 concurrent requests, one start per second, and one retry
    for network failures or 502/503/504. Complete a same-URL CDN cookie
    handshake once per attempt; no retries for denial or rate limits.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        request_interval: float = 1.0,
        concurrency: int = 3,
        cache_ttl: float = 30.0,
        cache_size: int = 128,
    ):
        if request_interval < 0 or concurrency < 1 or cache_ttl < 0 or cache_size < 1:
            raise ValueError("invalid request limits")
        self._client = client
        self._interval = request_interval
        self._semaphore = asyncio.Semaphore(concurrency)
        self._pace_lock = asyncio.Lock()
        self._next_request = 0.0
        self._cache_ttl = cache_ttl
        self._cache_size = cache_size
        self._cache: OrderedDict[tuple, tuple[float, Any]] = OrderedDict()

    @property
    def name(self) -> str:
        return "digikala"

    @_cached_read
    async def search_products(
        self, query: str, page: int = 1, filters: SearchFilters | None = None
    ) -> SearchPage:
        self._validate_query(query)
        self._validate_page(page)
        filters = filters or SearchFilters()
        params: dict[str, Any] = {"q": query.strip(), "page": page}
        if filters.min_price_toman is not None:
            params["price[min]"] = filters.min_price_toman * 10
        if filters.max_price_toman is not None:
            params["price[max]"] = filters.max_price_toman * 10
        if filters.brand_id:
            params["brands[0]"] = filters.brand_id
        if filters.category_id:
            params["category_id"] = filters.category_id
        if filters.available_only:
            params["has_selling_stock"] = 1
        data = await self._get("/v1/search/", params)

        return self._parse(
            lambda: mapping.search_page(
                data,
                page,
                str(httpx.URL(f"{_API_URL}/v1/search/", params=params)),
                datetime.now(UTC),
            )
        )

    @_cached_read
    async def get_product_details(self, product_id: int | str) -> ProductDetails:
        identifier = parse_product_id(product_id)
        data = await self._get(f"/v2/product/{identifier}/")
        details = self._parse(
            lambda: mapping.details(
                mapping.require_dict(data, "product"), datetime.now(UTC)
            )
        )
        if details.id != identifier:
            raise mapping.changed("returned product ID does not match the request")
        return details

    @_cached_read
    async def get_reviews(self, product_id: int | str, page: int = 1) -> ReviewPage:
        identifier = parse_product_id(product_id)
        self._validate_page(page)
        data = await self._get(f"/v1/product/{identifier}/comments/", {"page": page})

        return self._parse(
            lambda: mapping.review_page(data, identifier, page, datetime.now(UTC))
        )

    @_cached_read
    async def get_search_suggestions(self, query: str) -> SearchSuggestions:
        self._validate_query(query)
        query = query.strip()
        data = await self._get("/v1/autocomplete/", {"q": query})

        return self._parse(
            lambda: mapping.search_suggestions(
                data,
                str(httpx.URL(f"{_API_URL}/v1/autocomplete/", params={"q": query})),
                datetime.now(UTC),
            )
        )

    async def suggest_searches(self, query: str) -> tuple[str, ...]:
        return (await self.get_search_suggestions(query)).suggestions

    @_cached_read
    async def get_recommendations(
        self, product_id: int | str
    ) -> tuple[ProductSummary, ...]:
        identifier = parse_product_id(product_id)
        data = await self._get(f"/v1/product/{identifier}/tabular-recommendation/")

        return self._parse(lambda: mapping.recommendations(data, datetime.now(UTC)))

    @staticmethod
    def _parse(parser):
        try:
            return parser()
        except (
            ValidationError,
            TypeError,
            ValueError,
            KeyError,
            AttributeError,
        ) as exc:
            raise mapping.changed("invalid field shape or value") from exc

    async def _paced_get(self, path: str, params: dict | None) -> httpx.Response:
        response = await self._request_once(path, params)
        if self._is_cookie_handshake(response):
            initial = response
            response = await self._request_once(path, params)
            response.history = [initial]
        return response

    @staticmethod
    def _is_cookie_handshake(response: httpx.Response) -> bool:
        if response.status_code != 307 or not any(
            cookie.name == "digicdn_cookie" and cookie.value
            for cookie in response.cookies.jar
        ):
            return False
        location = response.headers.get("location")
        if not location:
            return False
        try:
            destination = response.url.join(location)
        except (httpx.InvalidURL, ValueError):
            return False
        return (
            destination == response.url
            and destination.scheme == "https"
            and destination.host == "api.digikala.com"
            and not destination.username
            and not destination.password
        )

    async def _request_once(self, path: str, params: dict | None) -> httpx.Response:
        async with self._semaphore:
            async with self._pace_lock:
                await asyncio.sleep(max(0, self._next_request - monotonic()))
                self._next_request = monotonic() + self._interval
            try:
                return await self._client.get(
                    f"{_API_URL}{path}",
                    params=params,
                    timeout=_TIMEOUT,
                    follow_redirects=False,
                )
            except httpx.InvalidURL as exc:
                # HTTPX prepares a redirect request even when following is off.
                raise ShoppingError("Digikala returned an invalid redirect") from exc
            except httpx.RemoteProtocolError as exc:
                if isinstance(exc.__context__, httpx.InvalidURL):
                    raise ShoppingError(
                        "Digikala returned an invalid redirect"
                    ) from exc
                raise

    async def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = None
        for attempt in range(2):
            try:
                response = await self._paced_get(path, params)
            except httpx.RequestError as exc:
                if attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                raise ShoppingError(
                    "Digikala is unavailable; try again later", "unavailable"
                ) from exc
            if response.status_code in {502, 503, 504} and attempt == 0:
                await asyncio.sleep(0.25)
                continue
            break
        self._check_status(response.status_code)
        try:
            payload = response.json()
        except ValueError as exc:
            raise mapping.changed("invalid JSON") from exc
        if not isinstance(payload, dict):
            raise mapping.changed("missing response envelope")
        status = payload.get("status")
        if status != 200:
            if isinstance(status, int):
                self._check_status(status)
            raise mapping.changed("unexpected body status")
        return mapping.require_dict(payload, "data")

    @staticmethod
    def _check_status(status: int):
        if status == 200:
            return
        if status == 404:
            raise ShoppingError("Product or endpoint not found", "not_found", status)
        if status == 429:
            raise ShoppingError(
                "Digikala rate limited this request; wait before trying again",
                "rate_limited",
                status,
            )
        if status in {301, 302, 303, 307, 308, 401, 403}:
            raise ShoppingError(
                "Digikala denied or redirected access; check the source page",
                "unavailable",
                status,
            )
        raise ShoppingError(
            "Digikala is unavailable; try again later", "unavailable", status
        )

    @staticmethod
    def _validate_query(query: str):
        if not isinstance(query, str) or not query.strip() or len(query) > 200:
            raise ValueError("query must contain 1 to 200 characters")

    @staticmethod
    def _validate_page(page: int):
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 100:
            raise ValueError("page must be an integer from 1 to 100")
