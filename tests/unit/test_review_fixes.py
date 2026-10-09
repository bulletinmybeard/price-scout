from datetime import datetime
from types import SimpleNamespace

from click.testing import CliRunner

from src import __version__
from src.cli.cli import cli
from src.cli.commands.history import history
from src.cli.helpers import detect_provider_from_url
from src.config.models import ExtractionMethod, ProviderConfig
from src.database.db_manager import DatabaseManager


def _provider(name: str, base_url: str) -> ProviderConfig:
    return ProviderConfig(name=name, country="NL", base_url=base_url)


def test_longest_base_url_wins() -> None:
    broad = _provider("amazon", "https://www.amazon.nl")
    specific = _provider("amazon_kosta", "https://www.amazon.nl/shops/kosta")
    factory = SimpleNamespace(config={"amazon": broad, "amazon_kosta": specific})

    name, config = detect_provider_from_url("https://www.amazon.nl/shops/kosta/dp/X", factory)
    assert name == "amazon_kosta"
    assert config is specific

    name, config = detect_provider_from_url("https://www.amazon.nl/dp/X", factory)
    assert name == "amazon"
    assert config is broad


def test_extraction_method_aliases() -> None:
    assert ExtractionMethod.normalize("json-ld") is ExtractionMethod.JSON_LD
    assert ExtractionMethod.normalize("selectors") is ExtractionMethod.SELECTORS
    assert ExtractionMethod.normalize("css") is ExtractionMethod.SELECTORS
    assert ExtractionMethod.normalize("xpath") is ExtractionMethod.SELECTORS
    assert ExtractionMethod.normalize("html") is None


def test_cli_version_matches_package() -> None:
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
    assert "1.2.0b1" in result.output


def test_history_command_prints_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        DatabaseManager, "export_snapshots_to_parquet", lambda self, force=False: None
    )
    db_path = tmp_path / "history.duckdb"
    manager = DatabaseManager(str(db_path), read_only=False)
    manager.create_tables()
    url = "https://test.com/product"
    manager.add_snapshot(
        {
            "url": url,
            "provider": "test_provider",
            "name": "Test Product",
            "current_price": 9.99,
            "currency": "EUR",
            "availability": True,
            "scraped_at": datetime.now(),
        }
    )
    manager.close()

    monkeypatch.setattr(
        "src.cli.commands.history.get_db_url",
        lambda config_path=None: str(db_path),
    )

    result = CliRunner().invoke(history, [url, "--days", "30"])
    assert result.exit_code == 0
    assert "Test Product" in result.output
    assert "9.99" in result.output


def test_history_command_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        DatabaseManager, "export_snapshots_to_parquet", lambda self, force=False: None
    )
    db_path = tmp_path / "empty.duckdb"
    manager = DatabaseManager(str(db_path), read_only=False)
    manager.create_tables()
    manager.close()

    monkeypatch.setattr(
        "src.cli.commands.history.get_db_url",
        lambda config_path=None: str(db_path),
    )

    result = CliRunner().invoke(history, ["https://test.com/missing"])
    assert result.exit_code == 0
    assert "No price history" in result.output
