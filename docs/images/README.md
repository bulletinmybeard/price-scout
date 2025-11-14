# Images for README

## TODO: Add DuckDB Web UI Screenshot

To complete the README polish, add a screenshot of the DuckDB Web UI showing:

1. **Access the DuckDB Web UI**:

   ```bash
   # Start the Docker container
   docker run -d --name price-scout -p 4213:4214 -v price-scout-data:/app/data bulletinmybeard/price-scout:latest

   # Track some products first to have data
   docker exec -it price-scout price-scout track --url "PRODUCT_URL_1"
   docker exec -it price-scout price-scout track --url "PRODUCT_URL_2"

   # Open browser to http://localhost:4213
   ```

1. **Screenshot Requirements**:

   - Show the product list or price history query
   - Capture a clean, professional view of the UI
   - Recommended size: 1200px wide, optimize to \<500KB
   - Format: PNG or JPG
   - Save as: `docs/images/duckdb-ui-screenshot.png`

1. **Add to README** (after Quick Start section):

   ```markdown
   ### DuckDB Web UI (Docker Only)

   ![DuckDB Web UI](docs/images/duckdb-ui-screenshot.png)
   *Built-in analytics interface for price history and trend analysis*
   ```

## Alternative: Use Placeholder

If a real screenshot is not available yet, you can use a placeholder:

```markdown
### DuckDB Web UI (Docker Only)

The Docker installation includes DuckDB's built-in Web UI accessible at `http://localhost:4213`.

**Features:**
- Query tracked products with SQL
- Visualize price history with charts
- Export data to CSV/Parquet
- Real-time analytics on price trends

Run any SQL query against your price data:
\`\`\`sql
SELECT product_name, price, timestamp
FROM page_snapshots
WHERE provider = 'store_a'
ORDER BY timestamp DESC;
\`\`\`
```
