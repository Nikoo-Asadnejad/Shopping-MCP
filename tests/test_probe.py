import asyncio
import json

import httpx
import pytest

from shopping_mcp.infrastructure.shops.digikala.probe import (
    _redirect_diagnostics,
    compact,
    probe,
)


def test_fixture_sanitization():
    assert compact(
        {
            "data": {
                "comments": [
                    {
                        "id": 1,
                        "body": "feedback",
                        "user_name": "private",
                        "profile": {"id": 2},
                    }
                ]
            }
        }
    ) == {"data": {"comments": [{"id": 1, "body": "feedback"}]}}


def test_probe_stops_on_denied_access(monkeypatch, tmp_path):
    calls = []
    original = httpx.AsyncClient

    def handler(request):
        calls.append(request)
        return httpx.Response(403)

    monkeypatch.setattr(
        "shopping_mcp.infrastructure.shops.digikala.probe.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    result = asyncio.run(probe(tmp_path, "test host"))
    assert not result["passed"]
    assert len(calls) == 1
    assert result["endpoints"]["search"]["http_status"] == 403
    assert result["endpoints"]["details"]["attempted"] is False
    assert json.loads((tmp_path / "access-report.json").read_text()) == result


@pytest.mark.parametrize(
    "location,expected,same_url",
    [
        (
            "https://api.digikala.com/v1/search/?q=laptop&page=1",
            "https://api.digikala.com/v1/search/",
            True,
        ),
        (
            "/challenge/?token=private#private",
            "https://api.digikala.com/challenge/",
            False,
        ),
        (
            "https://user:private@other.example/check?token=private#private",
            "https://other.example/check",
            False,
        ),
    ],
)
def test_probe_records_safe_redirect_destination(
    monkeypatch, tmp_path, location, expected, same_url
):
    original = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            307,
            headers={
                "location": location,
                "content-type": "text/html",
                "server": "test-edge",
                "set-cookie": "private-session=private",
            },
        )

    monkeypatch.setattr(
        "shopping_mcp.infrastructure.shops.digikala.probe.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    report = asyncio.run(probe(tmp_path, "test host"))
    search = report["endpoints"]["search"]
    assert search["redirect_location"] == expected
    assert search["redirect_same_url"] is same_url
    assert search["redirect_query_redacted"]
    assert search["content_type"] == "text/html"
    assert search["server"] == "test-edge"
    assert not report["passed"]
    assert len(requests) == 1  # Never follow the redirect or continue the probe.
    saved = (tmp_path / "access-report.json").read_text()
    assert "private" not in saved
    assert "set-cookie" not in saved


@pytest.mark.parametrize(
    "location", ["https://example.com:invalid/", "javascript:private"]
)
def test_invalid_redirect_diagnostics_do_not_expose_raw_header(location):
    response = httpx.Response(
        307,
        request=httpx.Request("GET", "https://api.digikala.com/v1/search/"),
        headers={"location": location},
    )
    assert _redirect_diagnostics(response) == {
        "redirect_location": "<invalid or unsupported URL>"
    }


def test_probe_validates_all_families_with_production_mappers(
    monkeypatch, tmp_path, payloads
):
    original = httpx.AsyncClient

    def handler(request):
        path = request.url.path
        if path == "/v1/search/":
            name = "search"
        elif path == "/v1/autocomplete/":
            name = "autocomplete"
        elif "comments" in path:
            name = "comments"
        elif "tabular-recommendation" in path:
            name = "recommendations"
        else:
            name = "details_123"
        return httpx.Response(200, json=payloads[name])

    monkeypatch.setattr(
        "shopping_mcp.infrastructure.shops.digikala.probe.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    report = asyncio.run(probe(tmp_path, "test", product="123"))
    assert report["passed"]
    assert len(report["endpoints"]) == 5
    assert all(record["schema_valid"] for record in report["endpoints"].values())
    assert all("elapsed_ms" in record for record in report["endpoints"].values())


def test_probe_rejects_http_200_with_changed_schema(monkeypatch, tmp_path):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        "shopping_mcp.infrastructure.shops.digikala.probe.httpx.AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"status": 200, "data": {}})
            ),
            **kwargs,
        ),
    )
    report = asyncio.run(probe(tmp_path, "test"))
    assert not report["passed"]
    assert not any(record["schema_valid"] for record in report["endpoints"].values())
