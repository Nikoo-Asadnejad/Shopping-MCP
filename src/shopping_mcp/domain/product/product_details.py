"""Full product snapshot, the root of the product aggregate."""

from .offer import Offer
from .product_summary import ProductSummary
from .specification import Specification


class ProductDetails(ProductSummary):
    coverage_notes: tuple[str, ...] = (
        "Description/specifications/offers are bounded snapshots. Shipping cost is unknown; unavailable fields are null or empty.",
    )
    description: str | None = None
    default_offer: Offer | None = None
    cheapest_available_offer: Offer | None = None
    specifications: tuple[Specification, ...] = ()
    offers: tuple[Offer, ...] = ()
    buyer_overview: str | None = None
    buyer_advantages: tuple[str, ...] = ()
    buyer_disadvantages: tuple[str, ...] = ()
