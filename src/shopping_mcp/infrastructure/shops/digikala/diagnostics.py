"""Safe HTTP diagnostics shared by manual probes and upstream health checks."""

import httpx


def redirect_diagnostics(response: httpx.Response) -> dict:
    location = response.headers.get("location")
    if not location:
        return {}
    try:
        target = response.url.join(location)
        if target.scheme not in {"http", "https"}:
            raise ValueError("unsupported redirect scheme")
        destination = target.copy_with(
            username=None, password=None, query=None, fragment=None
        )
    except (httpx.InvalidURL, ValueError):
        return {"redirect_location": "<invalid or unsupported URL>"}
    return {
        "redirect_location": str(destination),
        "redirect_query_redacted": bool(target.query),
        "redirect_same_url": target == response.url,
    }
