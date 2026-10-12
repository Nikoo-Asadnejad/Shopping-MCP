"""Full product snapshot, the root of the product aggregate."""

from .offer import Offer
from .product_summary import ProductSummary
from .specification import Specification


class ProductDetails(ProductSummary):
    specifications: tuple[Specification, ...] = ()
    offers: tuple[Offer, ...] = ()
    buyer_overview: str | None = None
    buyer_advantages: tuple[str, ...] = ()
    buyer_disadvantages: tuple[str, ...] = ()
