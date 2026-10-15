"""Opt-in access evidence; run on the actual candidate host, never in routine tests."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

import httpx

from shopping_mcp.domain.errors import ShoppingError
from shopping_mcp.domain.product.reference import product_id

from . import mapping
from .api import DigikalaShop
from .diagnostics import redirect_diagnostics


def _endpoints(identifier: str):
    return {
        "search": ("/v1/search/", {"q": "laptop", "page": 1}),
        "autocomplete": ("/v1/autocomplete/", {"q": "laptop"}),
        "details": (f"/v2/product/{identifier}/", None),
        "comments": (f"/v1/product/{identifier}/comments/", {"page": 1}),
        "recommendations": (f"/v1/product/{identifier}/tabular-recommendation/", None),
    }


def _validate(name: str, payload: dict, identifier: str, source: str):
    """Exercise production mappers without making additional network requests."""
    data = mapping.require_dict(payload, "data")
    now = datetime.now(UTC)
    if name == "search":
        return mapping.search_page(data, 1, source, now)
    if name == "autocomplete":
        return mapping.search_suggestions(data, source, now)
    if name == "details":
        result = mapping.details(mapping.require_dict(data, "product"), now)
        if result.id != identifier:
            raise mapping.changed("returned product ID does not match the request")
        return result
    if name == "comments":
        return mapping.review_page(data, identifier, 1, now)
    return mapping.recommendations(data, now)


# Preserve only parser-relevant public fields. Exclude commenter names and profiles.
_FIELDS = {
    "status",
    "data",
    "products",
    "product",
    "pager",
    "total_pages",
    "total_items",
    "auto_complete",
    "categories",
    "keyword",
    "id",
    "title",
    "title_fa",
    "title_en",
    "url",
    "uri",
    "rating",
    "rate",
    "count",
    "default_variant",
    "price",
    "selling_price",
    "seller",
    "color",
    "size",
    "warranty",
    "specifications",
    "attributes",
    "values",
    "variants",
    "comments_overview",
    "overview",
    "advantages",
    "disadvantages",
    "review",
    "description",
    "comments",
    "body",
    "is_buyer",
    "category",
    "brand",
}


def compact(value):
    if isinstance(value, dict):
        return {key: compact(item) for key, item in value.items() if key in _FIELDS}
    if isinstance(value, list):
        return [compact(item) for item in value[:20]]
    return value


async def probe(output: Path, location: str, product: str = "20176433"):
    identifier = product_id(product)
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "observed_at": datetime.now(UTC).isoformat(),
        "location_label": location,
        "location_verified": False,
        "note": "Location label is operator-supplied; this does not prove host/device access elsewhere.",
        "endpoints": {},
    }
    denied = False
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        shop = DigikalaShop(client)
        for name, (path, params) in _endpoints(identifier).items():
            if denied:
                report["endpoints"][name] = {
                    "attempted": False,
                    "reason": "Stopped after upstream denied or redirected access",
                }
                continue
            record = {
                "attempted": True,
                "url": str(httpx.URL(f"https://api.digikala.com{path}", params=params)),
                "http_status": None,
                "body_status": None,
            }
            started = monotonic()
            try:
                # No transient retries; complete only the bounded CDN cookie handshake.
                response = await shop._paced_get(path, params)
                record["http_status"] = response.status_code
                record["cookie_redirect_followed"] = bool(response.history)
                record["content_type"] = response.headers.get("content-type", "")[:200]
                record["server"] = response.headers.get("server", "")[:100]
                record.update(redirect_diagnostics(response))
                try:
                    payload = response.json()
                    record["body_status"] = (
                        payload.get("status") if isinstance(payload, dict) else None
                    )
                except ValueError:
                    payload = None
                denied = response.status_code in {
                    301,
                    302,
                    303,
                    307,
                    308,
                    401,
                    403,
                    429,
                } or (
                    isinstance(record["body_status"], int)
                    and record["body_status"]
                    in {301, 302, 303, 307, 308, 401, 403, 429}
                )
                if response.status_code == 200 and record["body_status"] == 200:
                    filename = f"{name}.json"
                    (output / filename).write_text(
                        json.dumps(compact(payload), ensure_ascii=False, indent=2)
                        + "\n"
                    )
                    record["fixture"] = filename
                    try:
                        DigikalaShop._parse(
                            lambda: _validate(name, payload, identifier, record["url"])
                        )
                        record["schema_valid"] = True
                    except ShoppingError as exc:
                        record["schema_valid"] = False
                        record["error"] = str(exc)
            except ShoppingError as exc:
                record["error"] = str(exc)
                denied = True
            except httpx.RequestError:
                record["error"] = "Network unavailable or timed out"
            record["elapsed_ms"] = round((monotonic() - started) * 1000)
            report["endpoints"][name] = record
    report["passed"] = all(
        record.get("fixture") and record.get("schema_valid")
        for record in report["endpoints"].values()
    )
    (output / "access-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--product", type=product_id, default="20176433")
    parser.add_argument(
        "--location",
        required=True,
        help="Actual provider/region or local location label",
    )
    args = parser.parse_args()
    report = asyncio.run(probe(args.output, args.location, args.product))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
