# Shopping MCP

Shopping MCP is a planned collection of read-only Model Context Protocol (MCP) tools for Iranian online stores. Phase 1 focuses on [Digikala](https://www.digikala.com/); later phases will add other stores so an assistant can compare products across them.

The goal is to help people find a product that fits their needs and budget, understand what buyers liked and disliked, and compare current offers without hiding missing or uncertain information.

> **Project status:** Early implementation. The shared shop contract and Digikala API adapter exist, but there is no runnable MCP server or hosted endpoint yet. The remaining sequence is in the [plan](docs/PLAN.md).

## Goals

- Search products in Persian or English and return compact results with direct store links.
- Show product specifications, variants, seller offers, availability, and prices in toman.
- Summarize buyer reviews with recurring positives, negatives, and the amount of evidence examined.
- Compare 2–4 products side by side, highlighting meaningful differences and missing data.
- Recommend the best fit for a budget and required features, explaining both value and review quality.
- Expose the same operations to local MCP clients and a hosted MCP endpoint. Support a mobile ChatGPT experience through the integration route that works for the intended account.
- Add more stores later without mixing store-specific API details into shopping decisions.

Phase 1 is read-only. Account access, carts, checkout, payments, and a historical price database are outside its scope.

## Planned tools

| Tool | Shopper question it answers |
| --- | --- |
| `search_products` | “What products match this query and budget?” |
| `get_product_details` | “What are this product's specifications and current offers?” |
| `compare_products` | “How do these products differ?” |
| `summarize_reviews` | “What do buyers consistently like or dislike?” |
| `find_best_match` | “Which available option best fits my budget and requirements?” |
| `suggest_searches` | “What should I search for?” |

Results will include source links and retrieval times. Recommendations will distinguish the best-value option from the best-reviewed option when they differ, and explain when the review evidence is too limited for a confident pick.

## Tech stack

| Technology | Role |
| --- | --- |
| Python | Server and shopping logic. |
| [uv](https://docs.astral.sh/uv/) | Dependency management and development commands. |
| [Pydantic](https://docs.pydantic.dev/) | Validation and typed input/output models. |
| [FastMCP](https://gofastmcp.com/) | MCP tools and local/remote transports. |
| [FastAPI](https://fastapi.tiangolo.com/) | A small HTTP API for health checks and GPT Actions if needed. |
| [HTTPX](https://www.python-httpx.org/) | Shared async connections to store APIs. |

The first version will be one Python package and one service. `infrastructure/shops/base.py` defines the common shop operations; each store implements its API access under `infrastructure/shops/<store>/`. Shopping decisions and transport adapters stay separate. The base class covers search, details, and reviews; store-specific capabilities can be added without forcing them on every shop.

## How to use

### Today

Install [uv](https://docs.astral.sh/uv/), then set up the development environment and run the adapter tests:

```bash
uv sync
uv run pytest
```

Read the [implementation plan](docs/PLAN.md) for the remaining scope and deployment approach. There is no MCP server command yet because the transport layer has not been implemented.

### After phase 1 is implemented

Connect a supported agent to the local MCP server or the hosted Streamable HTTP endpoint, then ask questions such as:

- “Find an in-stock laptop under 40 million toman for office work.”
- “Summarize the buyer reviews of this Digikala product. What problems recur?”
- “Compare these three phones and show the important differences.”
- “Find the best-reviewed option within my budget, and explain any trade-offs.”

The release will include exact setup instructions for Cursor, Claude, and ChatGPT once each integration has been tested. Any Custom GPT Action will use the same shopping logic through a small HTTP API; its availability on mobile will be verified before documenting it as a supported path.

## Repository layout

Current files:

```text
.
├── README.md
├── pyproject.toml
├── src/shopping_mcp/
│   ├── domain/
│   │   ├── product/               # Product aggregate and read projections
│   │   │   ├── product_details.py
│   │   │   ├── product_summary.py
│   │   │   ├── offer.py
│   │   │   ├── specification.py
│   │   │   └── search_page.py
│   │   └── review/                # Review aggregate and read projection
│   │       ├── review.py
│   │       └── review_page.py
│   └── infrastructure/
│       └── shops/
│           ├── base.py            # Abstract Shop contract
│           └── digikala/
│               └── api.py         # Digikala read-only API adapter
├── tests/                          # Adapter behavior checks
└── docs/
    └── PLAN.md                    # Remaining phases and acceptance checks
```

Later phases will add:

```text
src/shopping_mcp/
├── application/        # Search, comparison, review, and ranking operations
└── interfaces/         # MCP tools and minimal FastAPI routes
```

Digikala API research is kept in a local file excluded from Git. The service will rely on undocumented read-only web endpoints that may change, so deployment requires access checks, bounded request rates, and clear handling of unavailable data.

## Roadmap

1. **Digikala:** Complete the shopping operations and expose the six planned tools using the existing API adapter.
2. **Remote access:** Host the MCP endpoint and validate supported client connections and mobile usage.
3. **More shopping signals:** Add related products, deeper seller analysis, deals, or price snapshots where evidence and usage justify them.
4. **More stores:** Introduce a store adapter when implementing the second store, then validate cross-store product matching.

See [docs/PLAN.md](docs/PLAN.md) for the detailed milestones and quality checks.

## Disclaimer

Shopping MCP is an independent project and is not affiliated with Digikala. Product prices, stock, and offers can change; shoppers should verify them on the linked store page before purchasing.
