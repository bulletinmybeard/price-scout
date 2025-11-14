from chalkbox.logging.bridge import get_logger

from src.database.db_manager import DatabaseManager

logger = get_logger(__name__)


def main():
    """Initialize the DuckDB database."""

    print("=" * 80)
    print("[DB] INITIALIZING DUCKDB DATABASE")
    print("=" * 80)

    db_path = "./data/price_scout.duckdb"
    db = DatabaseManager(db_path, read_only=False)

    print(f"\n  Database path: {db_path}")

    print("\n[LIST] Creating tables...")
    db.create_tables()

    print("\n✓ Database initialized successfully!")
    print("\n[TIP] Access methods:")
    print("   1. Python:  from src.database.db_manager import DatabaseManager")
    print("   2. CLI:     duckdb price_scout.duckdb")

    print("\n[STATS] Tables created:")
    with db.get_connection() as conn:
        tables = conn.execute("SHOW TABLES").fetchall()
        for table in tables:
            print(f"   - {table[0]}")

            count = conn.execute(f"SELECT COUNT(*) FROM {table[0]}").fetchone()[0]  # noqa: S608
            print(f"     Records: {count}")

    print("\n" + "=" * 80)
    print("✓ Ready to use!")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
