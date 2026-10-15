"""Run deliberately with SHOPPING_MCP_LIVE=1 uv run pytest -m live."""

import asyncio
import os

import pytest

from shopping_mcp.infrastructure.shops.digikala.probe import probe


@pytest.mark.live
@pytest.mark.skipif(
    os.getenv("SHOPPING_MCP_LIVE") != "1", reason="live traffic is opt-in"
)
def test_live_endpoint_access_and_mapping(tmp_path):
    report = asyncio.run(probe(tmp_path, "opt-in test; host location unverified"))
    assert report["passed"], report
