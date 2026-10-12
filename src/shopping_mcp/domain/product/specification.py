"""A product specification and its displayed values."""

from pydantic import BaseModel, ConfigDict


class Specification(BaseModel):
    model_config = ConfigDict(frozen=True)

    group: str
    name: str
    values: tuple[str, ...]
