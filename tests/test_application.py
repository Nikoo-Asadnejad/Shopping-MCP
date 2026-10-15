import asyncio
from copy import deepcopy

import pytest
from pydantic import ValidationError

from shopping_mcp.application.inputs import (
    CompareInput,
    MatchInput,
    ProductInput,
    ReviewInput,
    SearchInput,
)
from shopping_mcp.domain.product.search_filters import SearchFilters
from shopping_mcp.domain.text import contains


def run_service(factory, operation, request, overrides=None):
    async def run():
        service, client, calls = factory(overrides)
        async with client:
            result = await getattr(service, operation)(request)
        return result, calls

    return asyncio.run(run())


@pytest.mark.parametrize(
    "reference", ["123", "۱۲۳", "https://www.digikala.com/product/dkp-123/name/?a=1"]
)
def test_product_reference(reference):
    assert ProductInput(product=reference).product == "123"


@pytest.mark.parametrize(
    "reference",
    [
        "../123",
        "0",
        True,
        "https://evil.test/product/dkp-123/",
        "https://www.digikala.com@evil.test/product/dkp-123/",
        "https://www.digikala.com:444/product/dkp-123/",
        "http://digikala.com/product/dkp-123/",
        "1234567890123",
    ],
)
def test_bad_reference(reference):
    with pytest.raises(ValidationError):
        ProductInput(product=reference)


def test_comparison_normalizes_only_within_same_category(service_factory, payloads):
    records = deepcopy(payloads)
    records["details_456"]["data"]["product"]["specifications"][0]["attributes"][1][
        "values"
    ] = ["۲۵۶ گیگابایت"]
    result, calls = run_service(
        service_factory,
        "compare_products",
        CompareInput(products=["123", "456"]),
        records,
    )
    assert len(calls) == 2
    assert len(result.differences) == 1
    assert result.differences[0].name == "رم"
    assert (
        result.products[0].default_offer.variant_id
        != result.products[0].cheapest_available_offer.variant_id
    )
    assert result.products[0].cheapest_available_offer.color == "نقره ای"
    records["details_456"]["data"]["product"]["category"] = {
        "id": 99,
        "title_fa": "کیف لپ تاپ",
    }
    result, _ = run_service(
        service_factory,
        "compare_products",
        CompareInput(products=["123", "456"]),
        records,
    )
    assert not result.differences
    assert "Category match" in result.notes[-1]


def test_missing_specs_are_explicit(service_factory, payloads):
    data = deepcopy(payloads["details_456"])
    data["data"]["product"]["specifications"] = []
    result, _ = run_service(
        service_factory,
        "compare_products",
        CompareInput(products=["123", "456"]),
        {"details_456": data},
    )
    assert result.differences[0].values_by_product["456"] is None


def test_reviews_filter_questions_and_attribute_themes(service_factory):
    result, calls = run_service(
        service_factory, "summarize_reviews", ReviewInput(product="123", max_reviews=40)
    )
    assert len(calls) == 3  # Details plus first and last review pages.
    assert result.examined == 7  # Duplicate review IDs across pages are counted once.
    assert result.usable_reviews == 5
    assert result.verified_buyer_reviews == 4
    assert result.unrated_reviews == 3
    assert result.positives[0].mentions == 3
    assert result.positives[0].review_ids == ("2", "3", "6")
    assert result.negatives[0].mentions == 2
    assert result.conflicting_themes == ("کیفیت",)
    assert result.upstream_overview == "خلاصه دیجی کالا"
    assert all(review.id not in {"1", "7"} for review in result.examples)
    assert all(review.source_url for review in result.examples)
    assert "not a random" in result.coverage_notes[0]


def test_no_reviews(service_factory):
    empty = {
        "status": 200,
        "data": {"pager": {"total_pages": 0, "total_items": 0}, "comments": []},
    }
    result, _ = run_service(
        service_factory,
        "summarize_reviews",
        ReviewInput(product="123"),
        {"comments": empty},
    )
    assert result.examined == result.usable_reviews == 0
    assert not result.positives and not result.negatives
    assert any("Too few" in note for note in result.coverage_notes)


def test_ranking_budget_type_features_and_sparse_averages(service_factory, payloads):
    result, calls = run_service(
        service_factory,
        "find_best_match",
        MatchInput(query="laptop", budget_toman=2000, candidate_limit=4),
    )
    assert result.best_value_id == "123"
    assert result.best_reviewed_id == "789"
    assert result.candidates[0].product.id == "123"
    assert "999" in result.excluded
    assert (
        next(
            item for item in result.candidates if item.product.id == "456"
        ).review_score
        < next(
            item for item in result.candidates if item.product.id == "789"
        ).review_score
    )
    assert not result.confident_winner  # Only four verified-buyer experiences.
    assert len(calls) <= 1 + 1 + 4 + 4
    required, _ = run_service(
        service_factory,
        "find_best_match",
        MatchInput(
            query="laptop", budget_toman=2000, required_features=["۱۶ گیگابایت"]
        ),
    )
    assert {item.product.id for item in required.candidates} == {"456", "789"}
    assert contains("18 گیگابایت", "8 گیگابایت") is False
    accessory = deepcopy(payloads["details_123"])
    accessory["data"]["product"]["category"] = {
        "id": 99,
        "title_fa": "کیف و لوازم جانبی",
    }
    filtered, _ = run_service(
        service_factory,
        "find_best_match",
        MatchInput(query="laptop", budget_toman=2000),
        {"details_123": accessory},
    )
    assert "type" in filtered.excluded["123"]


def test_unavailable_unknown_and_cheapest_offer_budget(service_factory, payloads):
    data = deepcopy(payloads["details_123"])
    data["data"]["product"]["default_variant"]["price"]["selling_price"] = 25000
    data["data"]["product"]["variants"][0]["price"]["selling_price"] = 25000
    result, _ = run_service(
        service_factory,
        "find_best_match",
        MatchInput(query="laptop", budget_toman=1000),
        {"details_123": data},
    )
    assert (
        result.best_value_id == "123"
    )  # Cheaper available variant, not default offer.
    data["data"]["product"]["status"] = "out_of_stock"
    result, _ = run_service(
        service_factory,
        "find_best_match",
        MatchInput(query="laptop", budget_toman=1000),
        {"details_123": data},
    )
    assert not result.candidates


def test_search_rechecks_filters_and_bounds_cards(service_factory):
    result, calls = run_service(
        service_factory,
        "search_products",
        SearchInput(
            query="laptop",
            filters=SearchFilters(
                max_price_toman=1600, brand_id=7, available_only=True
            ),
        ),
    )
    assert [item.id for item in result.products] == ["123", "789"]
    assert calls[0].url.params["price[max]"] == "16000"
    assert calls[0].url.params["brands[0]"] == "7"
    assert calls[0].url.params["has_selling_stock"] == "1"
    assert result.source_url and result.retrieved_at


@pytest.mark.parametrize(
    "make_request",
    [
        lambda: CompareInput(products=["123", "123"]),
        lambda: CompareInput(products=["123"]),
        lambda: SearchInput(query=" "),
        lambda: SearchInput(query="x", page=101),
        lambda: SearchFilters(min_price_toman=10, max_price_toman=1),
        lambda: MatchInput(query="x", budget_toman=10, required_features=[" "]),
    ],
)
def test_invalid_operation_inputs(make_request):
    with pytest.raises(ValidationError):
        make_request()


def test_review_sampling_caps_upstream_pages(service_factory, payloads):
    data = deepcopy(payloads["comments"])
    data["data"]["pager"] = {"total_pages": 400, "total_items": 8000}
    result, calls = run_service(
        service_factory,
        "summarize_reviews",
        ReviewInput(product="123", max_reviews=60),
        {"comments": data},
    )
    pages = [
        int(call.url.params["page"]) for call in calls if "comments" in call.url.path
    ]
    assert pages == [1, 50, 100]
    assert result.total_reviews == 8000
    assert "pages [1, 50, 100]" in result.coverage_notes[0]


def test_zero_max_price_does_not_expand_budget(service_factory):
    result, _ = run_service(
        service_factory,
        "find_best_match",
        MatchInput(
            query="laptop", budget_toman=2000, filters=SearchFilters(max_price_toman=0)
        ),
    )
    assert not result.candidates


def test_rated_solicitation_is_not_product_experience():
    from shopping_mcp.application.reviews import is_experience
    from shopping_mcp.domain.review import Review

    assert not is_experience(
        Review(id="1", body="لطفا موجود کنید", rating_stars=5, is_buyer=True)
    )


def test_cheapest_offer_is_selected_before_display_cap(service_factory, payloads):
    data = deepcopy(payloads["details_123"])
    product = data["data"]["product"]
    template = product["variants"][0]
    product["variants"] = [dict(template, id=1000 + index) for index in range(25)]
    product["variants"][-1]["price"] = {"selling_price": 100}
    details, _ = run_service(
        service_factory,
        "get_product_details",
        ProductInput(product="123"),
        {"details_123": data},
    )
    assert len(details.offers) == 20
    assert details.cheapest_available_offer.variant_id == "1024"
    assert details.cheapest_available_offer.price_toman == 10
    assert details.cheapest_available_offer in details.offers


def test_default_offer_is_preserved_without_variants(service_factory, payloads):
    data = deepcopy(payloads["details_123"])
    data["data"]["product"]["variants"] = []
    details, _ = run_service(
        service_factory,
        "get_product_details",
        ProductInput(product="123"),
        {"details_123": data},
    )
    assert details.cheapest_available_offer == details.default_offer
    assert details.cheapest_available_offer in details.offers


@pytest.mark.parametrize(
    "query,title,category_id",
    [
        ("washing machine", "ماشین لباسشویی", 101),
        ("coffee", "قهوه", 102),
        ("running shoes", "کفش ورزشی", 103),
        ("book", "کتاب", 104),
        ("garden tools", "ابزار باغبانی", 105),
    ],
)
def test_ranking_resolves_any_store_category(
    service_factory, payloads, query, title, category_id
):
    records = deepcopy(payloads)
    records["autocomplete"]["data"]["categories"] = [
        {"keyword": query, "category": {"id": category_id, "title_fa": title}}
    ]
    product = records["details_123"]["data"]["product"]
    product["title_fa"] = title + " نمونه"
    product["category"] = {"id": category_id, "title_fa": title}
    records["search"]["data"]["products"] = [product]
    result, calls = run_service(
        service_factory,
        "find_best_match",
        MatchInput(query=query, budget_toman=2000),
        records,
    )
    assert result.best_value_id == "123"
    assert result.category_options[0].id == category_id
    assert result.category_options[0].title == title
    assert result.category_source_url
    assert calls[0].url.params["q"] == query
    assert calls[1].url.params["category_id"] == str(category_id)
    assert result.limits["category_lookups"] == 1


def test_ambiguous_categories_return_choices_before_detail_fetches(
    service_factory, payloads
):
    data = deepcopy(payloads["autocomplete"])
    data["data"]["categories"] = [
        {"category": {"id": 20, "title_fa": "قهوه"}},
        {"category": {"id": 30, "title_fa": "قهوه ساز"}},
    ]
    result, calls = run_service(
        service_factory,
        "find_best_match",
        MatchInput(query="coffee", budget_toman=2000),
        {"autocomplete": data},
    )
    assert not result.candidates
    assert {item.id for item in result.category_options} == {20, 30}
    assert result.candidates_examined == 0
    assert len(calls) == 1
    assert "select a category ID" in result.explanation


def test_unresolved_category_does_not_infer_type_from_product_titles(
    service_factory, payloads
):
    data = deepcopy(payloads["autocomplete"])
    data["data"]["categories"] = []
    result, calls = run_service(
        service_factory,
        "find_best_match",
        MatchInput(query="something", budget_toman=2000),
        {"autocomplete": data},
    )
    assert not result.candidates
    assert len(calls) == 1
    assert "filters.category_id" in result.explanation


def test_explicit_category_skips_lookup_and_accepts_any_category(
    service_factory, payloads
):
    records = deepcopy(payloads)
    product = records["details_123"]["data"]["product"]
    product["category"] = {"id": 500, "title_fa": "یک دسته جدید"}
    records["search"]["data"]["products"] = [product]
    result, calls = run_service(
        service_factory,
        "find_best_match",
        MatchInput(
            query="any product",
            budget_toman=2000,
            filters=SearchFilters(category_id=500),
        ),
        records,
    )
    assert result.best_value_id == "123"
    assert result.limits["category_lookups"] == 0
    assert not any("autocomplete" in call.url.path for call in calls)
    assert calls[0].url.params["category_id"] == "500"


def test_product_type_refines_dynamic_lookup(service_factory):
    result, calls = run_service(
        service_factory,
        "find_best_match",
        MatchInput(
            query="office equipment", product_type="a specific type", budget_toman=2000
        ),
    )
    assert result.candidates
    assert calls[0].url.params["q"] == "a specific type"
    assert calls[1].url.params["q"] == "office equipment"


def test_out_of_stock_product_has_no_available_offers(service_factory, payloads):
    data = deepcopy(payloads["details_123"])
    data["data"]["product"]["status"] = "out_of_stock"
    result, _ = run_service(
        service_factory,
        "get_product_details",
        ProductInput(product="123"),
        {"details_123": data},
    )
    assert not result.available
    assert result.cheapest_available_offer is None
    assert not result.default_offer.available
    assert all(not offer.available for offer in result.offers)


def test_zero_product_rating_is_not_replaced_by_prior(service_factory, payloads):
    data = deepcopy(payloads["details_123"])
    data["data"]["product"]["rating"] = {"count": 100, "rate": 0}
    result, _ = run_service(
        service_factory,
        "find_best_match",
        MatchInput(query="laptop", budget_toman=2000),
        {"details_123": data},
    )
    candidate = next(item for item in result.candidates if item.product.id == "123")
    assert candidate.review_score < 1


@pytest.mark.parametrize("status", [303, 403, 429])
def test_ranking_stops_after_denial_or_rate_limit(payloads, status):
    import httpx

    from shopping_mcp.application.service import ShoppingService
    from shopping_mcp.domain.errors import ShoppingError
    from shopping_mcp.infrastructure.shops.digikala import DigikalaShop

    async def run():
        calls = []

        def handler(request):
            calls.append(request)
            if request.url.path == "/v1/search/":
                return httpx.Response(200, json=payloads["search"])
            if request.url.path == "/v1/autocomplete/":
                return httpx.Response(200, json=payloads["autocomplete"])
            return httpx.Response(status)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            shop = DigikalaShop(client, request_interval=0)
            service = ShoppingService(shop, shop.get_search_suggestions)
            with pytest.raises(ShoppingError) as error:
                await service.find_best_match(
                    MatchInput(query="laptop", budget_toman=2000)
                )
            assert error.value.status_code == status
            assert len(calls) == 3

    asyncio.run(run())


def test_review_summary_preserves_cached_evidence_time(service_factory):
    async def run():
        service, client, calls = service_factory()
        async with client:
            first = await service.summarize_reviews(ReviewInput(product="123"))
            count = len(calls)
            second = await service.summarize_reviews(ReviewInput(product="123"))
            assert second.retrieved_at == first.retrieved_at
            assert len(calls) == count

    asyncio.run(run())
