from collections.abc import Generator
import contextlib
from pathlib import Path
import tempfile
from unittest.mock import MagicMock

import pytest
import yaml

from src.database.db_manager import DatabaseManager


@pytest.fixture
def migrations_dir(tmp_path: Path) -> Path:
    """Temporary migration directory for migration runner tests."""
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()
    (migration_dir / "0001_test_migration.py").write_text(
        """
def up(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS migration_test (id INTEGER)")

def down(conn):
    conn.execute("DROP TABLE IF EXISTS migration_test")

def check_applied(conn):
    result = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_name = 'migration_test'"
    ).fetchone()
    return result is not None
"""
    )
    return migration_dir


@pytest.fixture
def db_manager() -> Generator[DatabaseManager, None, None]:
    """Create a test database manager with temporary DuckDB file."""
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as tmp_file:
        tmp_path = tmp_file.name
    Path(tmp_path).unlink()  # Delete the empty file so DuckDB can create it fresh

    manager = DatabaseManager(db_path=tmp_path, read_only=False)
    manager.create_tables()
    yield manager

    with contextlib.suppress(FileNotFoundError):
        Path(tmp_path).unlink()


@pytest.fixture
def temp_config_file():
    """Create a temporary config file with product groups."""
    config_data = {
        "database": {"url": ":memory:"},  # Required field for AppConfig
        "product_groups": [
            {
                "name": "Coffee - Douwe Egberts",
                "description": "Track coffee prices across stores",
                "pages": [
                    "https://www.webshop-a/products/coffee-500g",
                    "https://www.store-b.example/producten/product/coffee-500g",
                ],
            },
            {
                "name": "Dog Food - Royal Canin",
                "description": "Track dog food prices",
                "pages": [
                    {"url": "https://www.webshop-a/products/dog-food-4kg", "provider": "store_a"},
                    {
                        "url": "https://www.store-b.example/producten/product/dog-food-4kg",
                        "provider": "store_b",
                    },
                ],
            },
            {
                "name": "Weekly Groceries",
                "description": "Weekly grocery items",
                "pages": [
                    {"url": "https://www.webshop-a/products/milk-1l", "provider": "store_a"},
                ],
            },
        ],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config_data, f)
        config_path = Path(f.name)

    yield config_path

    with contextlib.suppress(FileNotFoundError):
        config_path.unlink()


@pytest.fixture
def temp_config_dir() -> Generator[tuple[Path, Path], None, None]:
    """Create temporary directory with config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        config_path = tmpdir_path / "config.yaml"
        config_data = {
            "database": {
                "path": ":memory:",
                "export_to_parquet": False,
            },
            "providers": {
                "test_provider": {
                    "name": "test_provider",
                    "country": "NL",
                    "base_url": "https://www.example.com",
                },
            },
        }

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        provider_configs_dir = tmpdir_path / "provider_configs"
        provider_configs_dir.mkdir()

        yield config_path, provider_configs_dir


@pytest.fixture
def mock_db_manager():
    """Create a mock database manager."""
    db = MagicMock(spec=DatabaseManager)
    db.create_group.return_value = 1  # Return group_id
    db.get_tracked_page.return_value = {"id": 1, "url": "test-url"}
    return db


@pytest.fixture
def mock_tracker():
    """Create mock tracker for CLI testing."""
    tracker = MagicMock()
    mock_product = MagicMock()
    mock_product.current_price = 9.99
    mock_product.name = "Test Product"
    tracker.track_product_url.return_value = (mock_product, {"snapshot_id": 1})
    return tracker


@pytest.fixture
def mock_factory():
    """Create mock provider factory."""
    factory = MagicMock()
    return factory


@pytest.fixture
def sample_groups():
    """Sample product groups for testing fuzzy matching."""
    return [
        {"group_id": 1, "name": "Dog Food", "slug": "dog-food"},
        {"group_id": 2, "name": "Dog Food Premium", "slug": "dog-food-premium"},
        {"group_id": 3, "name": "Cat Litter", "slug": "cat-litter"},
        {"group_id": 4, "name": "Weekly Groceries", "slug": "weekly-groceries"},
        {"group_id": 5, "name": "Coffee Beans", "slug": "coffee-beans"},
    ]
