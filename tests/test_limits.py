import asyncio
import logging
from types import SimpleNamespace

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from shopping_mcp.interfaces.limits import ToolLimits
from shopping_mcp.interfaces.mcp import create_server


def test_limit_returns_tool_error_before_upstream_call(service_factory):
    async def run():
        service, upstream, calls = service_factory()
        server = create_server(service, limits=ToolLimits(calls_per_minute=1))
        async with upstream, Client(server) as client:
            await client.call_tool("suggest_searches", {"query": "laptop"})
            result = await client.call_tool(
                "suggest_searches", {"query": "phone"}, raise_on_error=False
            )
            assert result.is_error
            assert "rate_limited" in result.content[0].text
            assert len(calls) == 1

    asyncio.run(run())


def test_concurrency_limit_releases_capacity_after_cancellation():
    async def run():
        middleware = ToolLimits(max_concurrent=1)
        entered = asyncio.Event()
        release = asyncio.Event()
        context = SimpleNamespace(message=SimpleNamespace(name="search_products"))

        async def slow(_):
            entered.set()
            await release.wait()

        task = asyncio.create_task(middleware.on_call_tool(context, slow))
        await entered.wait()
        with pytest.raises(ToolError, match="rate_limited"):
            await middleware.on_call_tool(context, slow)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        await middleware.on_call_tool(context, slow)

    asyncio.run(run())


def test_logs_exclude_shopper_arguments(service_factory, caplog):
    caplog.set_level(logging.INFO, logger="shopping_mcp.tools")

    async def run():
        service, upstream, _ = service_factory()
        async with upstream, Client(create_server(service)) as client:
            await client.call_tool("suggest_searches", {"query": "private-query-text"})

    asyncio.run(run())
    logs = " ".join(
        record.message
        for record in caplog.records
        if record.name == "shopping_mcp.tools"
    )
    assert "tool=suggest_searches outcome=ok duration_ms=" in logs
    assert "private-query-text" not in logs
