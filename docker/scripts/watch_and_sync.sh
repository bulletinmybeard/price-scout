#!/bin/bash

set -euo pipefail

MASTER_DB="${1:-/data/price_scout.duckdb}"
PARQUET_FILE="${2:-/data/snapshots.parquet}"
INIT_SQL="${3:-/init_ui.sql}"
PID_FILE="/tmp/duckdb_ui.pid"
SOCAT_PID_FILE="/tmp/socat.pid"
LOG_PREFIX="[DuckDB UI]"

if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    RED='\033[0;31m'
    NC='\033[0m' # No Color
else
    GREEN=''
    YELLOW=''
    RED=''
    NC=''
fi

log_info() {
    echo -e "${GREEN}${LOG_PREFIX} [INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warn() {
    echo -e "${YELLOW}${LOG_PREFIX} [WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}${LOG_PREFIX} [ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

cleanup() {
    log_info "Shutting down..."

    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null 2>&1; then
            log_info "Stopping DuckDB UI (PID: $pid)"
            kill "$pid" 2>/dev/null || true
            sleep 1
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"
    fi

    if [ -f "$SOCAT_PID_FILE" ]; then
        local socat_pid
        socat_pid=$(cat "$SOCAT_PID_FILE")
        if ps -p "$socat_pid" > /dev/null 2>&1; then
            log_info "Stopping socat proxy (PID: $socat_pid)"
            kill "$socat_pid" 2>/dev/null || true
        fi
        rm -f "$SOCAT_PID_FILE"
    fi

    log_info "Cleanup complete"
    exit 0
}

trap cleanup SIGTERM SIGINT EXIT

start_socat_proxy() {
    log_info "Starting socat proxy: 0.0.0.0:4214 -> [::1]:4213"

    # Start socat in background
    # DuckDB UI binds to IPv6 [::1]:4213, so we proxy to 0.0.0.0:4214
    socat TCP-LISTEN:4214,fork,reuseaddr,bind=0.0.0.0 TCP:[::1]:4213 &
    local socat_pid=$!

    echo "$socat_pid" > "$SOCAT_PID_FILE"
    log_info "Socat proxy started (PID: $socat_pid)"

    return 0
}

start_duckdb_ui() {
    log_info "Starting DuckDB UI (reads from Parquet: $PARQUET_FILE)"

    # Use script command to create a pseudo-TTY for DuckDB
    # This is necessary for the UI to work properly
    # NOTE: Use :memory: database to avoid ANY file locking!!!
    # BROWSER= prevents DuckDB from trying to auto-open a browser (no GUI in Docker)
    if [ -f "$INIT_SQL" ]; then
        log_info "Using initialization SQL: $INIT_SQL"
        script -q -c "BROWSER= duckdb :memory: -init $INIT_SQL" /dev/null 2>&1 &
    else
        script -q -c "BROWSER= duckdb :memory: -ui" /dev/null 2>&1 &
    fi

    local duckdb_pid=$!
    echo "$duckdb_pid" > "$PID_FILE"
    log_info "DuckDB UI started (PID: $duckdb_pid)"

    return 0
}

wait_for_ui() {
    log_info "Waiting for DuckDB UI on port 4213..."

    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if nc -z localhost 4213 2>/dev/null; then
            log_info "DuckDB UI is ready on localhost:4213"
            return 0
        fi

        attempt=$((attempt + 1))
        sleep 1
    done

    log_error "DuckDB UI failed to start within ${max_attempts}s"
    return 1
}

initial_export() {
    PARQUET_DIR=$(dirname "$PARQUET_FILE")

    if [ -f "$MASTER_DB" ] && [ ! -f "$PARQUET_FILE" ]; then
        log_info "Performing initial Parquet export from master DB"

        # Export all tables to Parquet using DuckDB CLI
        # This matches the export logic in db_manager.py
        duckdb "$MASTER_DB" <<SQL
COPY (SELECT * FROM page_snapshots) TO '$PARQUET_DIR/snapshots.tmp.parquet' (FORMAT PARQUET);
COPY (SELECT * FROM tracked_pages) TO '$PARQUET_DIR/tracked_pages.tmp.parquet' (FORMAT PARQUET);
COPY (SELECT * FROM product_groups) TO '$PARQUET_DIR/product_groups.tmp.parquet' (FORMAT PARQUET);
COPY (SELECT * FROM page_groups) TO '$PARQUET_DIR/page_groups.tmp.parquet' (FORMAT PARQUET);
SQL

        for table in snapshots tracked_pages product_groups page_groups; do
            if [ -f "$PARQUET_DIR/${table}.tmp.parquet" ]; then
                mv "$PARQUET_DIR/${table}.tmp.parquet" "$PARQUET_DIR/${table}.parquet"
            fi
        done

        if [ -f "$PARQUET_FILE" ]; then
            log_info "Initial Parquet export complete:"
            log_info "  - snapshots.parquet: $(du -h "$PARQUET_DIR/snapshots.parquet" | cut -f1)"
            log_info "  - tracked_pages.parquet: $(du -h "$PARQUET_DIR/tracked_pages.parquet" | cut -f1)"
            log_info "  - product_groups.parquet: $(du -h "$PARQUET_DIR/product_groups.parquet" | cut -f1)"
            log_info "  - page_groups.parquet: $(du -h "$PARQUET_DIR/page_groups.parquet" | cut -f1)"
        else
            log_warn "Parquet files not created - will be created on first write"
        fi
    elif [ ! -f "$PARQUET_FILE" ]; then
        log_warn "Neither DB nor Parquet found - will be created on first write"
    else
        log_info "Parquet files exist ($(du -sh "$PARQUET_DIR"/*.parquet 2>/dev/null | wc -l | tr -d ' ') files)"
    fi
}

log_info "=== DuckDB UI for Parquet Data Source ==="
log_info "Parquet file: $PARQUET_FILE"
log_info "=========================================="

initial_export

start_duckdb_ui

if ! wait_for_ui; then
    log_error "Failed to start DuckDB UI"
    exit 1
fi

start_socat_proxy

log_info "Setup complete!"
log_info "  • DuckDB UI: http://localhost:4213"
log_info "  • External access: http://localhost:4214"
log_info ""
log_info "UI reads Parquet data (no file locking, always consistent)"
log_info "Data is automatically exported after each price tracker write"

# Keep script running (supervisord will manage this process!)
while true; do
    sleep 60

    # Health check - restart UI if it died
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        if ! ps -p "$pid" > /dev/null 2>&1; then
            log_warn "DuckDB UI process died, restarting..."
            start_duckdb_ui
            sleep 2
            wait_for_ui
        fi
    fi
done
