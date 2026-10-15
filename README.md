# Shopping MCP

Shopping MCP provides a collection of read-only Model Context Protocol (MCP) tools for Iranian online stores. Phase 1 focuses on [Digikala](https://www.digikala.com/); later phases will add other stores so an assistant can compare products across them.

The goal is to help people find a product that fits their needs and budget, understand what buyers liked and disliked, and compare current offers without hiding missing or uncertain information.

> **Project status:** The six phase-1 tools are implemented with local stdio and Streamable HTTP support, a FastAPI health/privacy surface, bounded caching, traffic limits and optional bearer access. Phase-0 live acceptance is pending: the latest local check succeeded for all five Digikala endpoint families, after an earlier redirect; Render access, hosted-usage terms and ChatGPT mobile MCP/plugin support remain unverified. See the [plan](docs/PLAN.md) and [access checklist](docs/PHASE_0.md).

## Goals

- Search products in Persian or English and return compact results with direct store links.
- Show product specifications, variants, seller offers, availability, and prices in toman.
- Summarize buyer reviews with recurring positives, negatives, and the amount of evidence examined.
- Compare 2–4 products side by side, highlighting meaningful differences and missing data.
- Recommend the best fit for a budget and required features, explaining both value and review quality.
- Expose the same operations to local MCP clients and a hosted MCP endpoint. Support a mobile ChatGPT experience through the integration route that works for the intended account.
- Add more stores later without mixing store-specific API details into shopping decisions.

Phase 1 is read-only. Account access, carts, checkout, payments, and a historical price database are outside its scope.

## Tools

| Tool | Shopper question it answers |
| --- | --- |
| `search_products` | “What products match this query and budget?” |
| `get_product_details` | “What are this product's specifications and current offers?” |
| `compare_products` | “How do these products differ?” |
| `summarize_reviews` | “What do buyers consistently like or dislike?” |
| `find_best_match` | “Which available option best fits my budget and requirements?” |
| `suggest_searches` | “What should I search for?” |

Results include source links and retrieval times. Recommendations distinguish the best-value option from the best-reviewed option when they differ, and explain when the review evidence is too limited for a confident pick.

Product results also include an optional `image_url`. Assistants are instructed to show a numbered list of up to five products by default, each with a linked title, inline image when available, a separate bold price in toman, availability, and a star rating with its rating count. Search always requests in-stock products and locally excludes unavailable products and products without a positive price, even if a caller sets `available_only` to false. Pagination totals describe upstream results and can exceed the number of eligible products returned. Missing images are omitted and missing ratings are labeled explicitly. Image rendering depends on the connected chat client.

The server instructs assistants to handle shopping requests exclusively through its Digikala tools, without web search or external browsing, including when results are empty or upstream access fails. These instructions guide the client model; disabling other search tools must be configured in the client if strict enforcement is required.

## Tech stack

| Technology | Role |
| --- | --- |
| Python | Server and shopping logic. |
| [uv](https://docs.astral.sh/uv/) | Dependency management and development commands. |
| [Pydantic](https://docs.pydantic.dev/) | Validation and typed input/output models. |
| [FastMCP](https://gofastmcp.com/) | MCP tools and local/remote transports. |
| [FastAPI](https://fastapi.tiangolo.com/) | Health/privacy HTTP surface; Actions fallback remains conditional. |
| [HTTPX](https://www.python-httpx.org/) | Shared async connections to store APIs. |

The first version will be one Python package and one service. `infrastructure/shops/base.py` defines the common shop operations; each store implements its API access under `infrastructure/shops/<store>/`. Shopping decisions and transport adapters stay separate. The base class covers search, details, and reviews; store-specific capabilities can be added without forcing them on every shop.

## How to use

Install [uv](https://docs.astral.sh/uv/) and run:

```bash
uv sync --locked
uv run pytest
uv run shopping-mcp
```

For local HTTP:

```bash
uv run shopping-mcp --transport http --host 127.0.0.1 --port 8000
```

The MCP endpoint is `/mcp`; `/health` provides liveness, `/health/digikala` checks Digikala search availability on demand (200 or 503, cached for 30 seconds), and `/privacy` explains data use. Both transports share the same six operations and structured results. See [client configuration, Inspector commands and limits](docs/CLIENT_SETUP.md), [deployment](docs/DEPLOYMENT.md) and the [Persian guide](docs/CLIENT_SETUP_FA.md). The server returns clear tool errors when upstream access is unavailable; it never substitutes test data for live products.

The intended mobile route is a ChatGPT MCP connection/plugin for users in Iran. Render Free is the prototype host, with Frankfurt provisionally selected because Render does not offer an Iran region. The [Render blueprint](render.yaml) starts the server independently of Digikala availability; upstream access is checked separately. Hosted/mobile acceptance remains pending; see [phase-0 evidence and acceptance steps](docs/PHASE_0.md).

## Repository layout

```text
src/shopping_mcp/
├── domain/                  # Product/review models and conservative text/reference rules
├── infrastructure/shops/    # Shared Shop contract and Digikala client/mapping/probe
├── application/             # Inputs/results, comparison, review synthesis and ranking
└── interfaces/              # FastMCP tools, HTTP shell, traffic limits and transports
tests/                       # Synthetic field-shape fixtures and application/protocol tests
docs/                        # Plan, client setup and access evidence
render.yaml                  # Render Free prototype configuration
```

Digikala's undocumented read-only endpoints may change or deny access. Prices are converted from rial to toman, variants remain distinct, shipping is unknown, and all tools expose provenance/freshness. Review summaries use attributed explicit evidence and preserve coverage limits. Search supports all Digikala categories. Rankings resolve category IDs dynamically from store suggestions or an explicit category filter, then enforce budget, availability, product type and required specifications before considering price/value and review quality.

## Verification

Run `uv run pytest`, `uv run ruff check src tests` and `uv run ruff format --check src tests`. Current verification covers all six tools over authenticated HTTP, subprocess stdio, mapping/review/ranking behavior, cache freshness and expiry, request limits and upstream failures. Official Inspector discovery and HTTP calls passed; the opt-in five-family live schema check also passed locally on 2026-10-15. See [saved verification](docs/evidence/implementation-check.json). Render and phone acceptance remain pending.

## Roadmap

1. **Digikala:** Validate the implemented six tools against successful live fixtures and linked store evidence.
2. **Remote access:** Host the MCP endpoint and validate supported client connections and mobile usage.
3. **More shopping signals:** Add related products, deeper seller analysis, deals, or price snapshots where evidence and usage justify them.
4. **More stores:** Introduce a store adapter when implementing the second store, then validate cross-store product matching.

See [docs/PLAN.md](docs/PLAN.md) for the detailed milestones and quality checks.

## Disclaimer

Shopping MCP is an independent project and is not affiliated with Digikala. Product prices, stock, and offers can change; shoppers should verify them on the linked store page before purchasing.
