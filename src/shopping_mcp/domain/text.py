"""Conservative normalization for matching, never for displayed source text."""

import re
import unicodedata

_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك", "01234567890123456789یک")


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).translate(_TRANSLATION).casefold()
    return " ".join(value.replace("\u200c", " ").split())


def contains(text: str, phrase: str) -> bool:
    return (
        re.search(
            r"(?<!\w)" + re.escape(normalize(phrase)) + r"(?!\w)", normalize(text)
        )
        is not None
    )
