#!/bin/bash

set -e

# Auto-migration config for Docker container startup
DB_PATH="${DB_PATH:-/data/price_scout.duckdb}"
BACKUP_DIR="/data"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/database.duckdb.backup-${TIMESTAMP}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo ""
echo "Database Migrations"
echo ""

if [ ! -f "$DB_PATH" ]; then
    echo -e "${YELLOW}Database not found: ${DB_PATH}${NC}"
    echo "Skipping migrations (database will be created on first use)"
    echo ""
    exit 0
fi

echo "Database: ${DB_PATH}"

echo "Creating backup..."
if cp "$DB_PATH" "$BACKUP_PATH"; then
    echo -e "${GREEN}✓ Backup created: ${BACKUP_PATH}${NC}"
else
    echo -e "${RED}✗ Failed to create backup${NC}"
    echo "Aborting migrations for safety"
    exit 1
fi

echo ""

echo "Checking migration status..."
if ! poetry run price-scout db migrate status 2>&1 | grep -q "Pending:"; then
    # No pending migrations or error occurred
    if poetry run price-scout db migrate status 2>&1 | grep -q "All migrations up to date"; then
        echo -e "${GREEN}✓ All migrations up to date${NC}"
        echo ""
        exit 0
    fi
fi

# Show pending migrations
poetry run price-scout db migrate status | grep -A 10 "Pending:" || true

echo ""
echo "Applying migrations..."

if poetry run price-scout db migrate apply 2>&1; then
    echo ""
    echo -e "${GREEN}✓ Migrations applied successfully${NC}"
    echo ""
    echo "Backup kept at: ${BACKUP_PATH}"
    echo "(You can safely delete old backups manually)"
else
    MIGRATION_EXIT_CODE=$?
    echo ""
    echo -e "${RED}✗ Migration failed!${NC}"
    echo ""
    echo "Container startup aborted!"
    echo ""
    echo "To rollback:"
    echo "  1. Stop container: docker stop price-scout"
    echo "  2. Restore backup: docker exec price-scout cp ${BACKUP_PATH} ${DB_PATH}"
    echo "  3. Check logs: docker logs price-scout"
    echo ""
    exit $MIGRATION_EXIT_CODE
fi

echo ""
exit 0
