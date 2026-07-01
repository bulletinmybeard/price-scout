
from src.database.db_manager import DatabaseManager
from src.price_tracker.persistence import persist_scrape_result
from src.providers.base_product import BaseProduct


def _product(**kwargs) -> BaseProduct:
    defaults = {
        "name": "Test Coffee",
        "url": "https://example.com/coffee",
        "current_price": 4.99,
        "currency": "EUR",
        "offer_selection_strategy": "cheapest",
    }
    defaults.update(kwargs)
    return BaseProduct(**defaults)


def test_persist_scrape_result_locks_strategy_on_first_snapshot(db_manager: DatabaseManager):
    product = _product()

    persist_scrape_result(db_manager, product, "store_a", auto_associate_groups=False)

    page = db_manager.get_tracked_page(product.url)
    assert page is not None
    assert page["offer_selection_strategy"] == "cheapest"
    assert page["last_price"] == 4.99
    assert page["last_checked"] is not None
    assert db_manager.get_snapshot_count(product.url) == 1


def test_persist_scrape_result_updates_last_checked_on_refresh(db_manager: DatabaseManager):
    product = _product(current_price=4.99)
    persist_scrape_result(db_manager, product, "store_a", auto_associate_groups=False)

    first_checked = db_manager.get_tracked_page(product.url)["last_checked"]

    refreshed = _product(current_price=3.99)
    persist_scrape_result(db_manager, refreshed, "store_a", auto_associate_groups=False)

    page = db_manager.get_tracked_page(product.url)
    assert page["last_price"] == 3.99
    assert page["last_checked"] >= first_checked
    assert page["offer_selection_strategy"] == "cheapest"
    assert db_manager.get_snapshot_count(product.url) == 2


def test_persist_scrape_result_associates_group(db_manager: DatabaseManager):
    product = _product(url="https://example.com/tea")

    persist_scrape_result(
        db_manager,
        product,
        "store_a",
        group_name="Tea",
        auto_associate_groups=False,
    )

    group = db_manager.get_group_by_name("Tea")
    assert group is not None
    pages = db_manager.get_group_pages("Tea")
    assert len(pages) == 1


def test_persist_scrape_result_group_creation_failure_still_persists(db_manager: DatabaseManager):
    product = _product(url="https://example.com/fail-group")
    original_create_group = db_manager.create_group

    def _fail_create_group(**_kwargs):
        raise Exception("Database error")

    db_manager.create_group = _fail_create_group  # type: ignore[method-assign]

    result = persist_scrape_result(
        db_manager,
        product,
        "store_a",
        group_name="Broken Group",
        auto_associate_groups=False,
    )

    db_manager.create_group = original_create_group  # type: ignore[method-assign]

    assert result["snapshot_id"] is not None
    assert db_manager.get_snapshot_count(product.url) == 1
    assert db_manager.get_group_by_name("Broken Group") is None


def test_associate_tracked_page_with_group_handles_missing_page(db_manager: DatabaseManager):
    from src.price_tracker.group_helpers import associate_tracked_page_with_group

    associated = associate_tracked_page_with_group(
        "https://example.com/never-tracked",
        "Orphan Group",
        db_manager,
    )

    assert associated is False
    assert db_manager.get_group_by_name("Orphan Group") is not None
    assert db_manager.get_group_pages("Orphan Group") == []
