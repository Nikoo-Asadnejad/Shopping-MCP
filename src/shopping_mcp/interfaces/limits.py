"""Bound tool traffic and log operational metadata without shopper inputs."""

import json
import logging
from collections import deque
from time import monotonic

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

logger = logging.getLogger("shopping_mcp.tools")


class ToolLimits(Middleware):
    """Process-wide limits, independent of client-controlled identities."""

    def __init__(self, calls_per_minute: int = 30, max_concurrent: int = 4):
        if calls_per_minute < 1 or max_concurrent < 1:
            raise ValueError("tool limits must be positive")
        self._calls_per_minute = calls_per_minute
        self._max_concurrent = max_concurrent
        self._starts: deque[float] = deque()
        self._active = 0

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        started = monotonic()
        while self._starts and self._starts[0] <= started - 60:
            self._starts.popleft()
        # No await between checking and reserving capacity on the event loop.
        if (
            len(self._starts) >= self._calls_per_minute
            or self._active >= self._max_concurrent
        ):
            raise ToolError(
                json.dumps(
                    {"code": "rate_limited", "message": "Server busy; try again later"}
                )
            )
        self._starts.append(started)
        self._active += 1
        outcome = "error"
        try:
            result = await call_next(context)
            outcome = "ok"
            return result
        finally:
            self._active -= 1
            logger.info(
                "tool=%s outcome=%s duration_ms=%d",
                context.message.name,
                outcome,
                round((monotonic() - started) * 1000),
            )
