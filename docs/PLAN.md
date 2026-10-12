# Shopping MCP implementation plan

Research snapshot: 2026-10-12. Detailed Digikala API observations are kept in a local file excluded from Git; source links for the main decisions appear below.

## Goal and boundaries

Build a reliable, read-only shopping assistant for Iranian stores. In phase 1, a user should be able to ask in Persian or English for products, inspect a product, summarize buyer reviews, compare a short list, and find the best fit for a budget and stated needs using current Digikala data. Every result should show its source URL, price unit, and retrieval time. The assistant should state when price, stock, delivery cost, review evidence, or a specification is unavailable.

The project should support local MCP clients and a remotely hosted Streamable HTTP MCP endpoint. A small HTTP API will expose the same application operations to a Custom GPT Action if that route proves usable on mobile. No account login, cart, checkout, payment, or price history database is in phase 1.

**Transport decision:** Streamable HTTP at `/mcp` is the hosted MCP transport. FastMCP will handle protocol details; `stdio` is an optional local transport for clients that launch the server themselves. We will not add a legacy HTTP+SSE endpoint. Both transports call the same application operations and return the same structured results.

## Product scope and milestones

### Phase 0 — prove access and client fit

1. Confirm that Digikala's read-only web endpoints remain accessible from the chosen deployment region. Record status codes and representative response fixtures for search, autocomplete, details, comments, and recommendations. Do not assume local access implies cloud access.
2. Confirm which ChatGPT route works on mobile: a Custom GPT with Actions, or a ChatGPT plugin/MCP connection if available in the intended account and app. Test with the actual account and device before choosing the final delivery path.
3. Check Digikala's current terms and access limits for the intended hosted usage. Keep traffic low and stop or adapt if access is denied or terms disallow the intended use.

**Exit:** one realistic request works from the candidate host, and the chosen user-facing route is demonstrated on mobile.

### Phase 1 — Digikala vertical slice

Implement six shopper-facing operations:

| Operation | Inputs | Output |
| --- | --- | --- |
| `search_products` | query, page, optional price range, brand/category and availability filters | Compact cards with ID, title, price in toman, rating, stock, seller if known, URL, retrieval time, and pagination. |
| `get_product_details` | product ID or Digikala product URL | Description, grouped specifications, variants, seller offers, price, rating, and source URL. |
| `compare_products` | 2–4 product IDs/URLs | Side-by-side price, stock, rating, seller/variant context, and only meaningful specification differences; missing values remain explicit. |
| `summarize_reviews` | product ID/URL, bounded review count | Buyer feedback themes, recurring positives and negatives, rating/count context, examples or links, and the number of reviews examined. |
| `find_best_match` | query, budget in toman, required features, optional priorities | A small ranked shortlist with best value and best reviewed choices, prices, review evidence, trade-offs, and reasons for each recommendation. |
| `suggest_searches` | partial query | Digikala suggestions and relevant categories. |

Comparison is computed from verified product details; it does not need a dedicated Digikala compare endpoint. Match specification names within the same category, normalize Persian digits and text conservatively, and never present different capacities/colors as identical variants. Show the cheapest *available* offer separately from the default offer. Treat shipping cost as unknown unless Digikala gives a concrete amount.

Review summaries should use Digikala's product-level buyer overview when present and a bounded, representative sample from the comments endpoint. Label Digikala's summary as upstream content and any new synthesis as our summary. Distinguish verified buyers from other commenters; treat a `rate` of zero as unrated, not a zero-star review; ignore questions or non-experience comments when identifying product strengths and weaknesses. Report sample size, total review count, coverage limits, and conflicting opinions. Do not invent review themes or quote comments without attribution.

Best-match ranking should first enforce the requested budget, availability, product type, and required features. Then compare the eligible shortlist on price/value and review quality, considering rating together with review count, verified-buyer evidence, and recurring negative themes. Avoid a high average from a handful of ratings outranking strong evidence automatically. Explain why the best-value and best-reviewed picks differ, show their current offers, and say when the evidence is too thin for a confident winner. Keep the candidate and review fetch limits explicit so a search cannot trigger an unbounded number of upstream calls.

Use one async Digikala client with connection reuse, short timeouts, bounded concurrency, a modest per-host request rate, and one retry only for transient failures. Validate inputs with Pydantic, map upstream data into small internal models, and return concise structured errors for not found, unavailable, rate limited, and upstream changed. Do not leak raw large API responses into agent context.

**Exit:** MCP Inspector and a local client can execute the six tools; representative searches, review summaries, comparisons, and ranked picks match the linked Digikala evidence; invalid IDs and upstream failures yield understandable errors; tests cover parsing, review filtering, and ranking with recorded fixtures.

### Phase 2 — remote access and mobile experience

1. Expose the same FastMCP tools over Streamable HTTP at `/mcp`. Provide local `stdio` instructions where useful for Cursor and Claude development workflows.
2. Add a minimal FastAPI surface (`/health` and the few read-only JSON routes needed for GPT Actions). Mount FastMCP in that app and share application services; do not duplicate parsing or business rules. FastMCP's [HTTP/FastAPI guidance](https://gofastmcp.com/deployment/http) documents the ASGI/lifespan integration.
3. Publish an OpenAPI schema for those routes, a simple Persian Custom GPT instruction set, and a short mobile onboarding guide. Test end-to-end in the mobile ChatGPT app. OpenAI's [GPT Actions documentation](https://developers.openai.com/api/docs/actions/introduction) describes the REST integration; its [plugin documentation](https://developers.openai.com/plugins/build/mcp-server) describes a separate MCP route. Availability and mobile behavior must be checked for the intended account.
4. Deploy from a GitHub repository to a Python-capable HTTPS host. GitHub Pages cannot run Python server code ([GitHub docs](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site)). Render Free is a prototype candidate, but it sleeps after 15 idle minutes and can take about a minute to wake; that may be too slow for mobile use ([Render docs](https://render.com/docs/free)). Choose the actual host after testing upstream access, cold starts, latency, and current free limits.
5. Add a privacy page, a clear unofficial-service notice, request logging without personal queries, basic health checks, and a small smoke check for upstream schema drift.

**Exit:** MCP Inspector and a remote client can discover and call tools through Streamable HTTP at `/mcp`; a remote client can search, summarize reviews, and recommend a budget fit; the chosen ChatGPT mobile path works; the endpoint survives restart and handles a Digikala outage cleanly.

### Phase 3 — better shopping decisions

Add only after phase 1 usage shows value: similar products, deeper seller-offer analysis, buyer questions, deals, and price snapshots. Each new tool needs a verified data source, a specific user question it answers, bounded calls, and an explicit confidence/coverage note. Avoid claiming a price trend from a single current response.

### Phase 4 — additional stores

Add a second store through a narrow store client interface and shared shopper models (`ProductDetails`, `ProductSummary`, `Offer`, `Specification`). Keep store-specific API fields, currency handling, and availability semantics inside each adapter. Cross-store matching must use stable identifiers or explicit evidence; otherwise label candidates as possible matches. Expose cross-store comparison only once matching quality is tested.

## Code shape

```text
src/shopping_mcp/
  domain/
    product/             # product aggregate and search projection; one model per file
    review/              # review aggregate and page projection; one model per file
  infrastructure/
    shops/
      base.py             # abstract Shop contract for common operations
      digikala/           # Digikala API calls and response mapping
  application/            # search, comparison, review summary, and ranking use cases
  interfaces/             # FastMCP tools and minimal FastAPI routes
tests/             # recorded response parsing and comparison cases
docs/              # API observations, client setup, deployment notes
```

Start as one Python package and one deployed service. `uv` manages dependencies and runs tests; Pydantic validates public inputs and outputs; FastMCP provides MCP transports; FastAPI is only for health and GPT Actions. The `Shop` abstract class defines search, details, and reviews; Digikala-specific suggestions and recommendations remain in its adapter. Extend the contract only when another store needs the same operation.

## Quality checks

- Verify toman/rial conversion (Digikala prices observed in rial), missing price and out-of-stock states, variant and seller selection, Persian text/digits, and category-specific specification matching.
- Test mixed comment quality: unrated questions, non-buyers, sparse review samples, conflicting opinions, and products with no usable comments. Check that rankings honor budget and required features and explain review-count effects.
- Use fixture-based tests for API mapping, review summaries, comparison, and ranking; run a small opt-in live smoke suite against real endpoints. Do not run live tests on every commit or at a high frequency.
- Check tool discovery, valid calls, invalid inputs, and error responses over Streamable HTTP with MCP Inspector and one intended remote client; check FastAPI's OpenAPI schema against a real Custom GPT Action in Preview when available.
- Measure typical and cold-start latency from the chosen host and phone. Preserve a direct Digikala link so the shopper can verify current price and buy there.

## Key risks and decisions

| Risk | Response |
| --- | --- |
| Undocumented Digikala endpoints change or block cloud IPs | Isolate the client, keep fixtures and a live smoke check, handle 403/429 and schema drift, and prove deployment-region access before hosting. |
| A free host is slow or suspends external-API traffic | Use free hosting for a prototype; decide on a reliable host from measured mobile latency and usage limits. |
| Existing Digikala MCP servers already cover many features | Differentiate through transparent, evidence-backed reviews and recommendations, a tested mobile route, and future cross-store architecture; do not copy tool lists for their own sake. |
| Seller offers and product variants make comparisons misleading | Report offer/variant identity and availability, compare like-for-like where possible, and mark uncertain matches. |
| Review summaries or rankings overstate weak evidence | Show sample size, buyer status, rating count, source and missing data; avoid a single confident winner when evidence is thin. |
| Public hosted endpoint gets abused | Use input limits, bounded result sizes, cache short-lived reads, apply rate limits, and add access control if needed. |

## Initial backlog order

1. Finish the dependency lockfile and expand fixtures for the five verified Digikala endpoint families.
2. Complete the shared client and response mapping for required fields and error cases.
3. Implement the six application operations on the shop adapter.
4. Expose local MCP tools and test them with Inspector.
5. Add the Streamable HTTP endpoint at `/mcp` and minimal JSON/OpenAPI routes.
6. Validate deployment and the mobile ChatGPT path, then document setup.
