import asyncio
import json

import httpx

from shopping_mcp.infrastructure.shops.digikala.probe import compact, probe


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
