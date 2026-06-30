"""
Migration: Add promotion_starts_at column to page_snapshots table
Version: 0002
Created: 2025-11-30

This migration adds support for tracking promotion start dates

Context:
- JSON-LD schema.org offers can include validFrom and priceValidUntil dates
- promotion_ends_at already exists for priceValidUntil
- promotion_starts_at tracks when the promotion begins (validFrom)
- Together they enable displaying promotion date ranges in the comparison table
"""


def up(conn):
    """Apply migration: Add promotion_starts_at column."""
    result = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'page_snapshots'
        AND column_name = 'promotion_starts_at'
        """
    ).fetchone()

    if result:
        return

    conn.execute(
        """
        ALTER TABLE page_snapshots
        ADD COLUMN promotion_starts_at TIMESTAMP
        """
    )


def down(conn):
    """Rollback migration: Remove promotion_starts_at column."""
    conn.execute(
        """
        ALTER TABLE page_snapshots
        DROP COLUMN promotion_starts_at
        """
    )


def check_applied(conn):
    """Check if migration already applied."""
    result = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'page_snapshots'
        AND column_name = 'promotion_starts_at'
        """
    ).fetchone()

    return result is not None
