"""Validate a product reference without following caller-supplied URLs."""

import re
from urllib.parse import urlsplit


def product_id(value: str | int) -> str:
    if isinstance(value, bool):
        raise ValueError("use a positive product ID or a Digikala product URL")
    text = (
        str(value)
        .strip()
        .translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    )
    if len(text) > 500:
        raise ValueError("product reference is too long")
    if text.startswith("https://"):
        url = urlsplit(text)
        if (
            url.hostname not in {"digikala.com", "www.digikala.com"}
            or url.username
            or url.password
            or url.port not in {None, 443}
        ):
            raise ValueError("use an https Digikala product URL")
        match = re.fullmatch(r"/product/dkp-([0-9]{1,12})(?:/[^?]*)?", url.path)
        if not match:
            raise ValueError("URL must contain /product/dkp-ID/")
        text = match[1]
    if not re.fullmatch(r"[0-9]{1,12}", text) or int(text) <= 0:
        raise ValueError("use a positive product ID or a Digikala product URL")
    return str(int(text))
