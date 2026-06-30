# Database Migrations

Migration files live in `src/database/migrations/` so they ship inside the Python
package (pip installs and Docker). This directory keeps migration documentation for
developers working from a git checkout.

## CLI Commands

```bash
# Human-readable status
price-scout db migrate status

# JSON output (automation)
price-scout db migrate status --json

# Exit-code check (Docker/CI: 0=ok, 1=pending, 2=error)
price-scout db migrate check

# Apply pending migrations
price-scout db migrate apply
```

## Naming Convention

Migrations must follow this format:

```
{version}_{description}.py

Examples:
0001_add_offer_selection_strategy.py
0002_add_index_on_snapshots.py
0003_create_notifications_table.py
```

**Version**: 4-digit zero-padded number (0001, 0002, etc.)
**Description**: Snake_case description of what the migration does

## Migration File Structure

Each migration file must have an `up()` function and optionally a `down()` function:

```python
"""
Migration: Add offer_selection_strategy column
Version: 0001
"""

def up(conn):
    """Apply migration."""
    conn.execute("""
        ALTER TABLE tracked_pages
        ADD COLUMN offer_selection_strategy VARCHAR(50)
    """)

def down(conn):
    """Rollback migration (optional)."""
    conn.execute("""
        ALTER TABLE tracked_pages
        DROP COLUMN offer_selection_strategy
    """)

def check_applied(conn):
    """Check if migration already applied (optional).

    Useful for backwards compatibility - if this function exists and returns True,
    the migration will be skipped but recorded as applied.
    """
    result = conn.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'tracked_pages'
        AND column_name = 'offer_selection_strategy'
    """).fetchone()
    return result is not None
```

## Running Migrations

**Apply all pending migrations**:

```bash
scout db migrate
```

**Dry-run (show what would be applied)**:

```bash
scout db migrate --dry-run
```

**Check migration status**:

```bash
scout db migrate status
```

**Rollback last migration**:

```bash
scout db migrate rollback
```

## Migration Tracking

Migrations are tracked in the `schema_migrations` table:

```sql
SELECT * FROM schema_migrations ORDER BY version;

| version | name                           | applied_at          | checksum                                         | execution_time_ms |
|---------|--------------------------------|---------------------|--------------------------------------------------|-------------------|
| 0001    | add_offer_selection_strategy   | 2025-11-22 10:30:00 | a1b2c3d4e5f6...                                  | 45                |
| 0002    | add_index_on_snapshots         | 2025-11-22 10:31:00 | f6e5d4c3b2a1...                                  | 120               |
```

## Best Practices

1. **Never modify applied migrations** - Create a new migration instead
1. **Always provide down() for production migrations** - Enables rollback
1. **Test migrations locally first** - Use --dry-run before applying
1. **Keep migrations small** - One logical change per migration
1. **Include check_applied() for backwards compatibility** - Helps with existing databases
1. **Add comments** - Explain why the migration is needed

## Checksum Verification

The migration runner calculates a SHA256 checksum of each migration file. If you modify an already-applied migration, you'll see a warning:

```
Migration 0001_add_offer_selection_strategy has been modified since it was applied!
  Applied checksum:  a1b2c3d4e5f6...
  Current checksum:  f6e5d4c3b2a1...
```

**Do not modify applied migrations!** Create a new migration instead.

## Creating a New Migration

1. **Determine next version number**:

   ```bash
   ls src/database/migrations/ | grep -E "^[0-9]{4}_" | tail -1
   # If last is 0001_*, use 0002
   ```

1. **Create migration file**:

   ```bash
   touch src/database/migrations/0002_your_description.py
   ```

1. **Write migration logic**:

   ```python
   def up(conn):
       # Your migration code here
       pass

   def down(conn):
       # Your rollback code here
       pass
   ```

1. **Test with dry-run**:

   ```bash
   scout db migrate --dry-run
   ```

1. **Apply migration**:

   ```bash
   scout db migrate
   ```

## Troubleshooting

**Migration fails**: Check logs for specific error. Rollback if needed:

```bash
scout db migrate rollback
```

**Checksum mismatch**: Don't modify applied migrations! Create a new migration to fix issues.

**Database locked**: Stop all Price Scout processes before running migrations.

## See Also

- Main migration guide: `docs/MIGRATIONS.md`
- Database models: `src/database/models.py`
- Migration runner: `src/database/migration_runner.py`
