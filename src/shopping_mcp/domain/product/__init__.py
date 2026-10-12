"""Product aggregate and its read projections."""

from .offer import Offer
from .product_details import ProductDetails
from .product_summary import ProductSummary
from .search_page import SearchPage
from .specification import Specification

__all__ = ["Offer", "ProductDetails", "ProductSummary", "SearchPage", "Specification"]
