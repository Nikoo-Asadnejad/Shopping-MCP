"""The common operations required from a shopping site."""

from abc import ABC, abstractmethod

from shopping_mcp.domain.product import ProductDetails, SearchPage
from shopping_mcp.domain.product.search_filters import SearchFilters
from shopping_mcp.domain.review import ReviewPage


class Shop(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier for the store."""

    @abstractmethod
    async def search_products(
        self, query: str, page: int = 1, filters: SearchFilters | None = None
    ) -> SearchPage:
        """Find products by query."""

    @abstractmethod
    async def get_product_details(self, product_id: str) -> ProductDetails:
        """Get current product details and offers."""

    @abstractmethod
    async def get_reviews(self, product_id: str, page: int = 1) -> ReviewPage:
        """Get one page of product comments for review analysis."""
