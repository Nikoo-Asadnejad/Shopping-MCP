"""Small, safe errors shared by application and store adapters."""

from typing import Literal

ErrorCode = Literal[
    "invalid_input", "not_found", "unavailable", "rate_limited", "upstream_changed"
]


class ShoppingError(Exception):
    def __init__(
        self,
        message: str,
        code: ErrorCode = "unavailable",
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
