"""On-demand search availability, independent of application liveness."""

import asyncio
from datetime import UTC, datetime
from time import monotonic

import httpx

from shopping_mcp.domain.errors import ShoppingError

from . import mapping
from .api import DigikalaShop
from .diagnostics import redirect_diagnostics

SEARCH_HEALTH_URL = "https://api.digikala.com/v1/search/?q=laptop&page=1"


class DigikalaHealthCheck:
    """Coalesce concurrent checks and retain successes and failures for 30 seconds."""

    def __init__(self, shop: DigikalaShop):
        self._shop = shop
        self._lock = asyncio.Lock()
        self._report: dict | None = None
        self._expires = 0.0

    async def check(self) -> dict:
        async with self._lock:
            if self._report is not None and monotonic() < self._expires:
                return self._report
            report = {
                "status": "unavailable",
                "endpoint": SEARCH_HEALTH_URL,
                "checked_at": datetime.now(UTC).isoformat(),
                "http_status": None,
                "body_status": None,
            }
            started = monotonic()
            try:
                # Share the tool client's cookie jar and traffic limits. No
                # transient retries; only the bounded same-URL cookie handshake.
                async with asyncio.timeout(12):
                    shop = self._shop
                    response = await shop._paced_get(
                        "/v1/search/", {"q": "laptop", "page": 1}
                    )
                    report["http_status"] = response.status_code
                    report["cookie_redirect_followed"] = bool(response.history)
                    report["content_type"] = response.headers.get("content-type", "")[
                        :200
                    ]
                    report["server"] = response.headers.get("server", "")[:100]
                    report.update(redirect_diagnostics(response))
                    shop._check_status(response.status_code)
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise mapping.changed("invalid JSON") from exc
                    if not isinstance(payload, dict):
                        raise mapping.changed("missing response envelope")
                    body_status = payload.get("status")
                    report["body_status"] = (
                        body_status if isinstance(body_status, int) else None
                    )
                    if report["body_status"] != 200:
                        if isinstance(report["body_status"], int):
                            shop._check_status(report["body_status"])
                        raise mapping.changed("unexpected body status")
                    shop._parse(
                        lambda: mapping.search_page(
                            mapping.require_dict(payload, "data"),
                            1,
                            SEARCH_HEALTH_URL,
                            datetime.now(UTC),
                        )
                    )
                    report["status"] = "ok"
            except ShoppingError as exc:
                report.update(code=exc.code, message=str(exc))
            except (httpx.RequestError, TimeoutError):
                report.update(
                    code="unavailable", message="Network unavailable or timed out"
                )
            report["elapsed_ms"] = round((monotonic() - started) * 1000)
            self._report = report
            self._expires = monotonic() + 30
            return report
