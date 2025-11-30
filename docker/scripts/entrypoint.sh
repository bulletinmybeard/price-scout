#!/bin/bash

set -e

echo "Price Scout Container"
echo "Version: 1.0.0"
echo "Price Scout + DuckDB UI"
echo ""

if [ -f "/app/config.yaml" ]; then
    echo "✓ Configuration found: /app/config.yaml"
else
    echo " No config.yaml found, using example"
    if [ -f "/app/config.yaml.example" ]; then
        cp /app/config.example.yaml /app/config.yaml
    fi
fi

if [ ! -f "/data/price_scout.duckdb" ]; then
    echo " Initializing DuckDB database..."
    python /init_duckdb.py || echo "  Database initialization failed (may already exist?!)"
else
    echo "✓ DuckDB database found: /data/price_scout.duckdb"
fi

echo ""

# Run database migrations with auto-backup
/run_migrations.sh || exit 1

echo ""
echo "Services starting..."
echo "  - Xvfb (Virtual Display): :99"
echo "  - DuckDB Web UI: http://localhost:4213"
echo "  - Price Tracker CLI: Available via 'docker exec'"
echo ""
echo "Usage:"
echo "  docker exec -it <container> price-scout track --url \"URL\""
echo "  docker exec -it <container> price-scout list"
echo "  docker exec -it <container> price-scout --help"
echo ""
echo "========================================"
echo ""

exec "$@"
