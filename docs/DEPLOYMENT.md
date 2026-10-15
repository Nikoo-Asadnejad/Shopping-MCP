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

`/mcp` is Streamable HTTP, `/health` is liveness, and `/privacy` is the public privacy/unofficial-service notice. The root page serves the same notice. Health polling never calls Digikala and does not certify upstream availability. Stdio uses `uv run shopping-mcp` and exposes the same tools and application behavior.

HTTP is stateless and uses JSON tool responses. FastMCP owns protocol handling; its lifespan is propagated into FastAPI so startup and shutdown manage one shared HTTPX client. Clients reconnect after process restart; no session database is needed.

## Render prototype

Use the repository's [Blueprint](../render.yaml) on the actual Render account. It selects the planned Free Frankfurt prototype, installs the locked environment, runs `shopping-probe`, and starts HTTP on Render's assigned port only after all five endpoint families pass status and schema checks. `/health` is the configured health-check path. See [Render's Blueprint reference](https://render.com/docs/blueprint-spec).

The first actual service was manually created in Oregon, despite the command’s `render/frankfurt` label. Its diagnostic deployment returned a self-redirect from DigiCDN Edge and failed the access gate; see [captured evidence](evidence/render-oregon-redirect.json). A successful deployment or Digikala access from Render is not claimed.

Save the deployment ID, actual region and startup access report before accepting that host. Probe fixtures under `/tmp/digikala-probe` are ephemeral. A denial, redirect, rate limit or changed schema fails startup. Investigate the report; do not bypass upstream blocks. A successful local probe proves only local access.

Render's `RENDER_EXTERNAL_HOSTNAME` is automatically allowed by the MCP Host guard. For a custom domain or another host, set `SHOPPING_MCP_ALLOWED_HOSTS` to comma-separated hostnames. Browser origins are checked; configure additional trusted origins with FastMCP's `FASTMCP_HTTP_ALLOWED_ORIGINS` JSON array only when required by the client. The server enables no permissive CORS policy.

For private prototype access, set `SHOPPING_MCP_TOKEN` to a random secret of at least 32 characters in the host's environment, then configure bearer headers in a compatible client. An unset variable permits anonymous read-only use; an empty/short secret stops startup. Authentication is verified on MCP requests through FastMCP with a read-only scope. Health/privacy remain public. This shared-token mode provides no OAuth login or account management; verify support in the selected client. Keep tokens out of repository files and logs. `.env` is ignored and is not loaded automatically.

The current service waits for CI checks to pass before auto-deploying, but the repository has no CI checks. The diagnostic deployment was triggered manually after local tests passed. Configure CI or deliberately select On Commit if automatic deployment is desired; see [Render deploy behavior](https://render.com/docs/deploys).

## Resource and privacy behavior

- Run one process/worker: rate limits and caches are process-local. At most 30 tool calls per rolling minute and four concurrent calls are admitted; overload returns `rate_limited` before store access. Each tool has a 60-second execution limit.
- The store client allows three concurrent requests, one start per second, 5-second connect and 10-second request timeouts, and one retry for transient network/502/503/504 failures. Denial, redirects and rate limits are not retried.
- Successful compact snapshots are reused for 30 seconds, at most 128 entries. Retrieval timestamps reflect the original fetch. Expired entries are removed on the next lookup; eviction/restart also clears data. Errors are never cached. There is no persistent shopping/query database.
- HTTP POST bodies are bounded to 16 KiB, including chunked requests. Operation input/result/candidate/review bounds apply inside the service as well.
- The CLI disables access logs and records tool name, outcome and elapsed time on stderr. Application metadata logs omit arguments, queries, review bodies and bearer credentials. Keep HTTPX and proxy body/header logging disabled; hosting providers and MCP clients have their own retention policies.

## Acceptance on the deployed service

Use [MCP Inspector](CLIENT_SETUP.md) and the intended remote client to discover all six tools, search in Persian, inspect a real ID/URL, compare 2–4 products, summarize reviews and rank a budget fit. Check invalid IDs and simulated outage responses locally rather than generating hostile upstream traffic. Confirm `/privacy`, bearer rejection if configured, and liveness without an upstream request.

Run the opt-in probe deliberately for upstream schema checks; do not run it on every health poll or commit. On the intended phone in Iran, record network/app/account context, typical latency and cold-start latency after the host has been idle. Reconnect after a deployment/restart. Save those results before marking remote/mobile acceptance complete.
