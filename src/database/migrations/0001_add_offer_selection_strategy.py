"""
Migration: Add offer_selection_strategy column to tracked_pages table
Version: 0001
Created: 2025-11-22

This migration adds support for locking offer selection strategy per product to prevent
price history corruption when config changes.

Context:
- Some products (offers or refurbished items) have multiple offers with different prices
- offer_selection_strategy determines which offer to track (first, cheapest, cheapest_available)
- Strategy must be locked after first snapshot to prevent unwanted price changes
"""


def up(conn):
    """Apply migration: Add offer_selection_strategy column."""
    # Check if column already exists (backwards compatibility)
    result = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'tracked_pages'
        AND column_name = 'offer_selection_strategy'
        """
    ).fetchone()

    if result:
        # Column already exists - skip addition
        return

    # Add the column with default value
    conn.execute(
        """
        ALTER TABLE tracked_pages
        ADD COLUMN offer_selection_strategy VARCHAR(50) DEFAULT 'first'
        """
    )


def down(conn):
    """Rollback migration: Remove offer_selection_strategy column."""
    conn.execute(
        """
        ALTER TABLE tracked_pages
        DROP COLUMN offer_selection_strategy
        """
    )


def check_applied(conn):
    """Check if migration already applied."""
    result = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'tracked_pages'
        AND column_name = 'offer_selection_strategy'
        """
    ).fetchone()

    return result is not None
