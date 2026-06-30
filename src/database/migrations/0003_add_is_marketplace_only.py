"""
Migration: Add is_marketplace_only column to page_snapshots table
Version: 0003
Created: 2025-11-30

This migration adds support for tracking marketplace-only products.

Context:
- These products have only third-party marketplace sellers
- Products stored with is_marketplace_only=TRUE and price=NULL
- Displayed as "Marketplace" in the Promotion column (linked to product page)
"""


def up(conn):
    """Apply migration: Add is_marketplace_only column."""
    result = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'page_snapshots'
        AND column_name = 'is_marketplace_only'
        """
    ).fetchone()

    if result:
        return

    conn.execute(
        """
        ALTER TABLE page_snapshots
        ADD COLUMN is_marketplace_only BOOLEAN DEFAULT FALSE
        """
    )


def down(conn):
    """Rollback migration: Remove is_marketplace_only column."""
    conn.execute(
        """
        ALTER TABLE page_snapshots
        DROP COLUMN is_marketplace_only
        """
    )


def check_applied(conn):
    """Check if migration already applied."""
    result = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'page_snapshots'
        AND column_name = 'is_marketplace_only'
        """
    ).fetchone()

    return result is not None
