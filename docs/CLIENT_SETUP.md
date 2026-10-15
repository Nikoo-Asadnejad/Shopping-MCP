# Local MCP setup and checks

Requires Python 3.12+ and uv. Install the locked environment:

```bash
uv sync --locked
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

## Client-launched stdio

```bash
uv run shopping-mcp
```

For a client using `mcpServers` configuration (e.g. a local Cursor/Claude configuration), use absolute paths and let the client launch the server:

```json
{
  "mcpServers": {
    "shopping": {
      "command": "/absolute/path/to/uv",
      "args": ["--directory", "/absolute/path/to/Shopping-MCP", "run", "shopping-mcp"]
    }
  }
}
```

The stdio protocol uses stdout; service logs go to stderr. Client configuration locations vary by client. Discovery/calls were verified with the FastMCP client; specific GUI-client configuration and ChatGPT mobile acceptance remain pending.

## Streamable HTTP

```bash
uv run shopping-mcp --transport http --host 127.0.0.1 --port 8000
```

Connect to `http://127.0.0.1:8000/mcp`. FastMCP is mounted in a minimal FastAPI app with its lifespan propagated; one shared HTTPX client is opened at startup and closed at shutdown. HTTP uses stateless sessions and JSON responses, so reconnecting after restart requires no saved session state. There is no legacy HTTP+SSE endpoint. Public HTTPS hosting and ChatGPT account/device validation remain phase-0/phase-2 gates; local HTTP transport support does not imply public deployment acceptance. `GET /health` is a liveness check without an upstream request. `GET /health/digikala` checks the fixed Digikala search endpoint and returns 200 when its response passes validation or 503 on failure, including upstream HTTP/body status and safe redirect diagnostics. Results are cached for 30 seconds; it does not check details/reviews or gate startup. `/privacy` (also `/`) explains data use and the unofficial service. Actions routes remain conditional on needing the fallback.

## MCP Inspector

[Inspector](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector) requires Node 22.19+:

```bash
npx @modelcontextprotocol/inspector --cli uv run shopping-mcp --method tools/list
npx @modelcontextprotocol/inspector --cli uv run shopping-mcp --method tools/call --tool-name suggest_searches --tool-arg query=laptop
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8000/mcp --transport http --method tools/list
```

Calls to the production server make real upstream requests. For a repeatable offline transport check, replace `uv run shopping-mcp` with `.venv/bin/python tests/mcp_fixture_server.py`; for offline HTTP, launch that fixture server with `--port 8765`. Synthetic data is for tests only and is never a fallback in the production server.

## Operation limits and interpretation

- Search: page 1–100, at most 20 cards; `filters` supports min/max price in toman, numeric brand/category IDs and availability. Filters are sent upstream and rechecked locally; missing/unverified filtered fields are excluded. Totals describe upstream pagination, not the locally filtered card count. Live filter semantics are pending verification.
- Details: ID or HTTPS Digikala product URL; source, time, description, at most 60 specs and 20 variant offers. Default and cheapest available offers retain separate seller/color/size/warranty context. Prices come from rial divided by 10; missing or zero price is unknown. Shipping is unknown.
- Compare: 2–4 distinct products, same-category specification-name alignment with conservative Persian/digit normalization. Missing values remain null; unrelated categories are not aligned.
- Reviews: 1–60 comments, at most 3 pages across the available first 100 pages. Deduplicate/interleave pages; state the actual sample and its nonrandom coverage. Only explicit pros/cons from experience comments become attributed themes. Questions/non-experience comments are excluded, rate zero is unrated, buyers are counted separately, and Digikala's overview stays upstream content. Body-only feedback is available as attributed examples, not inferred themes.
- Best match: at most 1 category lookup plus 1 search page, at most 8 details, at most 40 reviews/2 pages per eligible candidate, top 4 including both picks. Strict budget, availability, category product-type and required-specification checks precede ranking. Categories are resolved dynamically from Digikala autocomplete IDs; there is no fixed product-type list. A unique category scopes the search, or `filters.category_id` selects any store category directly and skips lookup. Ambiguous or unresolved queries return category choices/clarification before fetching details. `product_type` can refine the category lookup; the explicit category ID is authoritative when supplied. Use `required_features` such as `"16 گیگابایت"`. Phrase matching is conservative; no semantic feature inference or currency guessing. Priorities are `value` or `reviews`.
- Suggestions: at most 10 suggestions and 10 category hints containing ID, title and matched keywords, with source/time. Nested autocomplete category records are grouped by category identity.

All six MCP handlers have a 60-second execution limit. A process admits at most 30 tool calls per rolling minute and four concurrent tool calls; excess calls return an MCP `rate_limited` tool error before upstream work. HTTP POST bodies are capped at 16 KiB, including chunked bodies. Successful mapped snapshots are reused for 30 seconds in a 128-entry in-memory cache; original retrieval times are retained, expired entries are cleared on the next lookup, and errors are never cached. These limits and caches are process-local; run one worker for this prototype. Upstream concurrency is 3, starts are spaced by one second, connect timeout is 5 seconds and request timeout is 10 seconds. Exactly one retry is allowed for network errors or 502/503/504; denial, redirects and 429 are never retried. Best-match stops on denial/rate limits rather than continuing across candidates. Error codes: `invalid_input`, `not_found`, `unavailable`, `rate_limited`, `upstream_changed`; tool failures use MCP `isError`.

Review ranking is a documented heuristic: shrink product average toward a 3/5 prior with 20 ratings, add at most 0.3 for count, add up to 0.15 for verified-buyer share, and subtract up to 0.5 for recurring sampled negatives (or 0.2 when no usable sample). Value divides that score by the cheapest available offer in toman. Fewer than 20 product ratings or five sampled verified buyers prevents a confident best-reviewed winner. Those thresholds describe evidence sufficiency, not calibrated statistical confidence. Every recommendation includes evidence and trade-offs so the client can explain the picks.

## Verification record

Historical checks are in [validation evidence](evidence/validation.json). Current checks are in [implementation evidence](evidence/implementation-check.json): 90 offline tests passed (one opt-in live test skipped), with successful FastMCP-client discovery/calls in process, over stdio and over loopback Streamable HTTP. Lint, formatting and locked dependency checks passed. On 2026-10-15, official Inspector 2.11.0 with Node 24.19.0 passed stdio discovery and, in both legacy and modern protocol modes, strict HTTP discovery, all six HTTP fixture calls and invalid-input tool-error checks after a server restart. The expected Inspector exit code for `isError: true` is 5. See [current verification](evidence/implementation-check.json); earlier installation failures remain in the historical report. Actual Render/client-phone acceptance remains pending.

## Optional bearer access and host validation

Set `SHOPPING_MCP_TOKEN` to a randomly generated secret of at least 32 characters to protect MCP requests. An absent variable allows anonymous access; an empty or short value fails startup. Clients must send `Authorization: Bearer <secret>` on each MCP request. Public health/privacy routes need no token. The server verifies the token through FastMCP, grants only `shopping:read`, and never forwards it to Digikala. This is a shared-token prototype mode, not an OAuth login implementation; use a client that supports bearer headers and verify compatibility with the intended account before enabling it for ChatGPT.

For example, pass headers to the FastMCP client using an environment variable:

```python
import os
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

transport = StreamableHttpTransport(
    "https://your-service.example/mcp",
    headers={"Authorization": f"Bearer {os.environ['SHOPPING_MCP_TOKEN']}"},
)
# Use `async with Client(transport) as client:` in your async application.
```

HTTP validates Host and Origin headers. Localhost is accepted by default. Render's `RENDER_EXTERNAL_HOSTNAME` is added automatically; for another host or custom domains set comma-separated `SHOPPING_MCP_ALLOWED_HOSTS`. Additional browser origins can use FastMCP's `FASTMCP_HTTP_ALLOWED_ORIGINS` JSON-array setting. No permissive CORS policy is enabled.

The CLI disables HTTP access logs and writes tool name, outcome and duration to stderr. Do not enable HTTPX debug/request logging or log request bodies/authorization headers on the reverse proxy. External hosting/client retention is outside the application's control.

## Opt-in schema smoke check

```bash
SHOPPING_MCP_LIVE=1 uv run pytest -m live
uv run shopping-probe --location your-provider/actual-region --output /tmp/shopping-probe
```

Each run makes at most five requests with no retries, tests the production mappers, records timing, and stops on denial, redirect or rate limit. An HTTP 200 containing a changed schema fails the gate. `--product ID` deliberately selects a replacement probe product if the default observed example disappears. Inspect saved evidence before retrying. The [2026-10-15 local run](evidence/implementation-live/access-report.json) passed all five families; it is not Render-region evidence.

See [deployment steps](DEPLOYMENT.md) and the [Persian client guide](CLIENT_SETUP_FA.md).
