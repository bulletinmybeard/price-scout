from src.database.db_manager import DatabaseManager


def test_delete_tracked_page_removes_empty_groups(db_manager: DatabaseManager):
    group_id = db_manager.create_group("Coffee", "Test group")
    page_id = db_manager.add_tracked_page(
        {
            "url": "https://example.com/coffee",
            "provider": "store_a",
        }
    )
    db_manager.add_page_to_group(page_id, group_id)

    result = db_manager.delete_tracked_page("https://example.com/coffee")

    assert result["deleted_empty_groups"] == ["Coffee"]
    assert db_manager.get_group_by_name("Coffee") is None


def test_delete_tracked_page_keeps_group_with_remaining_pages(db_manager: DatabaseManager):
    group_id = db_manager.create_group("Coffee", "Test group")

    page_one = db_manager.add_tracked_page(
        {
            "url": "https://example.com/coffee-a",
            "provider": "store_a",
        }
    )
    page_two = db_manager.add_tracked_page(
        {
            "url": "https://example.com/coffee-b",
            "provider": "store_b",
        }
    )
    db_manager.add_page_to_group(page_one, group_id)
    db_manager.add_page_to_group(page_two, group_id)

    result = db_manager.delete_tracked_page("https://example.com/coffee-a")

    assert result["deleted_empty_groups"] == []
    assert db_manager.get_group_by_name("Coffee") is not None
