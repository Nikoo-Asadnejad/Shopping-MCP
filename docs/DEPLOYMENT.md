# Deployment and operations

The implementation is ready for deployment testing. No public service, intended mobile account, hosted-use permission or phone latency has been verified. [Phase 0](PHASE_0.md) records those acceptance gates. Phases 3–4 remain future work; the Actions fallback is intentionally conditional.

## Local verification

```bash
uv sync --locked
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run shopping-mcp --transport http --host 127.0.0.1 --port 8000
```

`/mcp` is Streamable HTTP, `/health` is liveness, and `/privacy` is the public privacy/unofficial-service notice. The root page serves the same notice. Polling `/health` never calls Digikala and does not certify upstream availability. `GET /health/digikala` separately checks `https://api.digikala.com/v1/search/?q=laptop&page=1`: HTTP 200 means the search response passed adapter validation; HTTP 503 means access failed, timed out, or returned an incompatible response. The JSON includes the upstream HTTP/body status, check time, duration and sanitized redirect diagnostics. It does not certify the other endpoint families. Results, including failures, are cached for 30 seconds per process and concurrent checks are coalesced. Checks have a 12-second overall deadline and no transient retries. A 307 that sets `digicdn_cookie` and points to the exact same HTTPS URL on `api.digikala.com` permits one paced repeat with the client cookie jar. Other redirects, denial and rate limits remain terminal. `cookie_redirect_followed` reports whether this exchange occurred; HTTP/body status describes the final response. Stdio uses `uv run shopping-mcp` and exposes the same tools and application behavior.

HTTP is stateless and uses JSON tool responses. FastMCP owns protocol handling; its lifespan is propagated into FastAPI so startup and shutdown manage one shared HTTPX client for tools and upstream health, including its in-memory cookie jar and shared pacing/concurrency limits. HTTPX applies cookie expiry; shutdown discards the jar. Cookie values and response bodies are not included in health diagnostics or application logs. Clients reconnect after process restart; no session database is needed.

## Render prototype

Use the repository's [Blueprint](../render.yaml) on the actual Render account. It selects the planned Free Frankfurt prototype, installs the locked environment, and starts HTTP on Render's assigned port independently of Digikala availability. The startup probe has been removed; use `/health/digikala` for an on-demand search check and the manual CLI probe for all five endpoint families. `/health` is the configured health-check path. See [Render's Blueprint reference](https://render.com/docs/blueprint-spec).

The first actual service was manually created in Oregon, despite the command’s `render/frankfurt` label. Its diagnostic deployment returned a self-redirect from DigiCDN Edge and failed the access gate; see [captured evidence](evidence/render-oregon-redirect.json). That evidence predates the bounded cookie-handshake fix; it alone does not establish a permanent Render/IP block. [Local verification](evidence/local-cookie-handshake.json) now shows health and a live MCP search succeeding with cookie handling. Render verification must use the updated deployment.

For the existing manually created service, set **Settings → Build & Deploy → Start Command** to the following command; changing the Blueprint does not update this service's saved command:

```bash
uv run --no-sync shopping-mcp --transport http --host 0.0.0.0 --port $PORT
```

Keep Render's health-check path at `/health`. A Digikala outage must not cause a restart loop: `/health/digikala` returns 503 for diagnostics while the MCP service remains running and reports upstream tool errors normally. Both health endpoints are public and accept no caller-selected upstream URL or query.

Save the deployment ID, actual region and manual access report before accepting that host. Probe fixtures under `/tmp/digikala-probe` are ephemeral. Investigate upstream failures in the report; do not bypass upstream blocks. A successful local probe proves only local access.

Render's `RENDER_EXTERNAL_HOSTNAME` is automatically allowed by the MCP Host guard. For a custom domain or another host, set `SHOPPING_MCP_ALLOWED_HOSTS` to comma-separated hostnames. Browser origins are checked; configure additional trusted origins with FastMCP's `FASTMCP_HTTP_ALLOWED_ORIGINS` JSON array only when required by the client. The server enables no permissive CORS policy.

For private prototype access, set `SHOPPING_MCP_TOKEN` to a random secret of at least 32 characters in the host's environment, then configure bearer headers in a compatible client. An unset variable permits anonymous read-only use; an empty/short secret stops startup. Authentication is verified on MCP requests through FastMCP with a read-only scope. Health/privacy remain public. This shared-token mode provides no OAuth login or account management; verify support in the selected client. Keep tokens out of repository files and logs. `.env` is ignored and is not loaded automatically.

The current service is configured to auto-deploy on commit. Earlier diagnostics required a manual deploy when it was configured to wait for nonexistent CI checks; see [Render deploy behavior](https://render.com/docs/deploys).

## Resource and privacy behavior

- Run one process/worker: rate limits and caches are process-local. At most 30 tool calls per rolling minute and four concurrent calls are admitted; overload returns `rate_limited` before store access. Each tool has a 60-second execution limit.
- The store client allows three concurrent requests, one start per second, 5-second connect and 10-second request timeouts, and one retry for transient network/502/503/504 failures. Each request attempt can complete one same-URL DigiCDN cookie redirect through the same pacing/concurrency limits. Automatic redirects remain disabled; changed URL, host, scheme, missing cookie or a second redirect fails. Other denial and rate limits are not retried.
- Successful compact snapshots are reused for 30 seconds, at most 128 entries. Retrieval timestamps reflect the original fetch. Expired entries are removed on the next lookup; eviction/restart also clears data. Errors are never cached. There is no persistent shopping/query database.
- HTTP POST bodies are bounded to 16 KiB, including chunked requests. Operation input/result/candidate/review bounds apply inside the service as well.
- The CLI disables access logs and records tool name, outcome and elapsed time on stderr. Application metadata logs omit arguments, queries, review bodies and bearer credentials. Keep HTTPX and proxy body/header logging disabled; hosting providers and MCP clients have their own retention policies.

## Acceptance on the deployed service

Use [MCP Inspector](CLIENT_SETUP.md) and the intended remote client to discover all six tools, search in Persian, inspect a real ID/URL, compare 2–4 products, summarize reviews and rank a budget fit. Check invalid IDs and simulated outage responses locally rather than generating hostile upstream traffic. Confirm `/privacy`, bearer rejection if configured, and liveness without an upstream request.

Run the opt-in probe deliberately for upstream schema checks; do not run it on every health poll or commit. On the intended phone in Iran, record network/app/account context, typical latency and cold-start latency after the host has been idle. Reconnect after a deployment/restart. Save those results before marking remote/mobile acceptance complete.
