# Access and client validation

Updated 2026-10-15. Intended users are in Iran. The selected delivery route is a ChatGPT MCP connection packaged as a plugin; a Custom GPT Action is a fallback only.

## Hosting decision

Render Free is the prototype host. [Render's regions](https://render.com/docs/regions) do not include Iran. Frankfurt is the provisional service region, not a claim of Iranian hosting or measured best latency. Test both Digikala access from that service and phone access from Iran. Render Free [sleeps after 15 idle minutes and can take about a minute to restart](https://render.com/docs/free); measure that delay in the actual mobile flow.

`render.yaml` prepares a Free Python web service in Frankfurt. It runs an access probe before starting the MCP server; a failed probe stops startup rather than serving misleading data. The initial manually created service is in Oregon and has not passed startup access validation. The probe report is printed to the deployment log because Render Free's filesystem is ephemeral. Save the report and successful sanitized fixtures externally before treating access as proven.

## Evidence and remaining gates

- Latest local check: **all five endpoint families returned HTTP/body 200 and passed representative adapter parsing checks**. Successful sanitized responses and timings are saved in the [live access report](evidence/implementation-live/access-report.json). An earlier search request returned HTTP 307 ([historical evidence](evidence/local-access.json)); live access can vary. No redirects or retries were used in the successful check.
- Candidate Render host: **failed the initial access gate** on 2026-10-15. Render MCP confirms service `srv-db8c5htg1s2s739ptp70` is Free in **Oregon**, despite the operator-supplied `render/frankfurt` probe label. Deployment `dep-db8c5i5g1s2s739ptqk0` built successfully but search returned HTTP 307; the probe exited 1 before server startup. The initial report did not capture the redirect destination. Follow-up deployment `dep-db8cdkqvcj2c73905dug` of commit `dd79a01` captured HTTP 307 from `DigiCDN Edge`, content type `text/html`, and a redirect to the exact original URL. Render restarted the failed process once with the same result. This is consistent with an edge access filter or challenge, but the exact reason is unconfirmed. See [saved Render diagnostics](evidence/render-oregon-redirect.json). No usable hosted Digikala data has been established.
- Mobile MCP/plugin connection: **pending**, requires the intended ChatGPT account and phone in Iran. Documentation does not prove account availability.
- Five successful local live fixture families: **captured** under `docs/evidence/implementation-live/` (2026-10-15); earlier evidence remains under `docs/evidence/live-check/`, with source URLs and retrieval time. The original synthetic fixtures remain explicitly labeled. Successful capture on the actual Render candidate is still pending.
- Hosted-usage terms/access review: **unresolved**. The [current terms page](https://www.digikala.com/page/terms/) includes a noncommercial-use/source-attribution notice, but its dynamically displayed sections were not fully available in the fetched page. It does not establish permission for this third-party hosted API usage or publish API quotas. [robots.txt](https://www.digikala.com/robots.txt) is a crawler signal, not an API license. Resolve intended hosted use with the full terms/access policy before public launch.

## Reproduce a low-volume access check

Run from the actual candidate host (or use the startup probe in the Render blueprint):

```bash
uv run shopping-probe --location render/frankfurt --output /tmp/digikala-probe
```

The probe makes one request per endpoint family (search, autocomplete, details, comments, recommendations), starts requests at most once per second, validates the production mappers and captures status codes, timing and UTC retrieval time, and saves compact parser-relevant successful JSON. It excludes commenter names/profiles. It stops on HTTP/body denial, redirect, or rate limit. It never solves challenges, follows redirects, or changes region/proxy to bypass a denial. HTTP 200 with incompatible product/review data also fails the gate. Exit code 1 means the five-family gate failed; inspect `access-report.json` before retrying. Product ID `20176433` is an observed example and may disappear; a moved/missing product must be documented and a current accessible example chosen deliberately.

The location label is operator supplied. Attach Render's actual service region and deployment identifier to the saved report; the label alone is not independent location evidence. Redirect reports include the resolved destination with user information, query values and fragments removed, plus whether it matches the original URL. Redirects are never followed. Review any captured comments before committing fixtures.

## Prove the mobile route

OpenAI documents [MCP servers for plugins](https://developers.openai.com/plugins/build/mcp-server) and [connecting and testing a plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt). Configure the public HTTPS `/mcp` URL through the MCP/plugin route available in the actual account. A tools-only plugin can use this server; optional UI is outside phase 1. Do not document account/mobile support as verified until it works on the intended phone.

On that phone, run a Persian search, inspect an ID and a store URL, compare two products, summarize reviews, and request a budget match. Check source links, toman units, retrieval time, buyer/sample counts and unavailable-data messages. Repeat a request after at least 15 idle minutes and record cold-start latency. Save account route, app version, phone OS, network/location, time, result and latency. Avoid saving account tokens or personal queries in logs.

**Phase 0 exit remains open** until a realistic request succeeds on the candidate host, the terms/access gate is resolved, and the chosen MCP/plugin route is demonstrated on mobile.
