# Local live captures — 2026-10-15

These five fixtures were captured by the production `shopping-probe` from the development host, with one paced request per endpoint family and no retries. The [report](access-report.json) records source URLs, UTC time, timing, HTTP/body status and production-mapper validation. All five families passed.

The location label is operator supplied and unverified; this is not Render Frankfurt or phone evidence. Responses are historical snapshots, not current prices. The allowlist sanitizer removes commenter names/profiles and limits list lengths to 20, so fixtures are bounded extracts of the successful responses. Review bodies are public upstream content. Synthetic fixtures under `tests/fixtures` retain their separate provenance and are never production fallbacks.

`tests/test_recorded_responses.py` replays these captures through the production adapter without network access. `implementation-check.json` in the parent directory summarizes code/transport verification; the previous `live-check` directory remains historical evidence.
