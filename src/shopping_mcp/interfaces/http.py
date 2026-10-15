"""Small HTTP shell around the same MCP application operations."""

import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastmcp.server.auth import StaticTokenVerifier
from starlette.types import ASGIApp, Receive, Scope, Send

from shopping_mcp.application.service import ShoppingService
from shopping_mcp.infrastructure.shops.digikala.health import DigikalaHealthCheck

from .mcp import create_server

_PRIVACY = """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Shopping MCP — Privacy</title>
<main><h1>Shopping MCP</h1>
<p>This independent, unofficial service is not affiliated with Digikala.
It provides read-only product information; it cannot log in, buy, or pay.</p>
<h2>Privacy</h2>
<p>Search terms, product IDs and filters needed to answer your request are sent
to Digikala. Do not include personal or sensitive information in shopping queries.
Your MCP client and hosting provider have their own privacy policies.</p>
<p>The application reuses successful store responses from memory for up to 30 seconds
(at most 128 entries). Expired entries are cleared on the next cache lookup;
eviction or restart also removes them.
It has no shopper database, cookies, analytics or persistent query history.
Application tool logs contain the operation name, outcome and duration;
they exclude tool arguments, query text, review bodies and authorization headers.
The host may retain its own connection and deployment logs.</p>
<h2>Product information</h2>
<p>Prices are in toman. Stock, seller offers and prices can change. Shipping cost
is unknown unless explicitly supplied. Review evidence is a bounded sample,
not a guarantee. Verify information on the linked Digikala product page.</p>
<p lang="fa" dir="rtl">این سرویس مستقل و غیررسمی است و به دیجی‌کالا وابسته نیست.
قیمت‌ها به تومان هستند. پیش از خرید، قیمت و موجودی را در لینک دیجی‌کالا بررسی کنید.
اطلاعات شخصی یا حساس را در درخواست‌ها وارد نکنید.</p></main></html>"""


class RequestSizeLimit:
    """Bound MCP request bodies, including chunked requests, before parsing."""

    def __init__(self, app: ASGIApp, max_bytes: int = 16_384):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                await JSONResponse(
                    {"code": "invalid_input", "message": "Request body is too large"},
                    status_code=413,
                )(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body)}
            return await receive()

        await self.app(scope, replay, send)


def create_http_app(
    service: ShoppingService | None = None, *, token: str | None = None
) -> FastAPI:
    """Stateless MCP sessions survive process restarts by reconnecting normally.

    A configured bearer token protects every MCP request via FastMCP. Public
    health/privacy routes stay available without credentials. No client tokens
    are forwarded to the store.
    """
    token = token if token is not None else os.getenv("SHOPPING_MCP_TOKEN")
    if token is not None and (not token.strip() or len(token) < 32):
        raise ValueError("SHOPPING_MCP_TOKEN must contain at least 32 characters")
    auth = (
        StaticTokenVerifier(
            tokens={
                token: {"client_id": "shopping-client", "scopes": ["shopping:read"]}
            },
            required_scopes=["shopping:read"],
        )
        if token
        else None
    )
    hosts = [
        host.strip()
        for host in os.getenv("SHOPPING_MCP_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    ]
    if render_host := os.getenv("RENDER_EXTERNAL_HOSTNAME"):
        hosts.append(render_host)
    mcp_app = create_server(service, auth=auth).http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
        host_origin_protection=True,
        allowed_hosts=hosts or None,
    )
    # Mounted applications do not run their own lifespan; propagate it explicitly.
    app = FastAPI(
        title="Shopping MCP",
        lifespan=mcp_app.lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(RequestSizeLimit)
    digikala_health = DigikalaHealthCheck()

    @app.get("/health")
    async def health():
        # Liveness only: do not turn health polling into upstream traffic.
        return {"status": "ok", "service": "shopping-mcp", "upstream": "not_checked"}

    @app.get("/health/digikala")
    async def upstream_health():
        report = await digikala_health.check()
        return JSONResponse(
            report,
            status_code=200 if report["status"] == "ok" else 503,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/", response_class=HTMLResponse)
    @app.get("/privacy", response_class=HTMLResponse)
    async def privacy():
        return _PRIVACY

    app.mount("/", mcp_app)
    return app
