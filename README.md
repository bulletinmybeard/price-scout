# Price Scout

<p align="center">
    <em>Never overpay again. Track prices across online retailers.</em>
</p>

[![PyPI version](https://badge.fury.io/py/price-scout.svg)](https://pypi.org/project/price-scout/)
[![Python Versions](https://img.shields.io/pypi/pyversions/price-scout.svg)](https://pypi.org/project/price-scout/)
[![Docker Pulls](https://img.shields.io/docker/pulls/bulletinmybeard/price-scout)](https://hub.docker.com/r/bulletinmybeard/price-scout)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/bulletinmybeard/price-scout/actions/workflows/ci.yml/badge.svg)](https://github.com/bulletinmybeard/price-scout/actions/workflows/ci.yml)
[![Docker Publish](https://github.com/bulletinmybeard/price-scout/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/bulletinmybeard/price-scout/actions/workflows/docker-publish.yml)

**Quick Navigation**: [Features](#key-features) | [Quick Start](#quick-start) | [Usage Examples](#usage-examples) | [CLI Reference](#cli-commands) | [Contributing](#contributing)

## What is Price Scout?

**Price Scout** is a self-hosted price tracker with local data storage. Track product prices across online retailers with all data stored locally (no cloud, no accounts) in a fast DuckDB database with built-in analytics.

**Perfect for**: Weekly grocery tracking, product comparison, finding deals, and price history analysis.

## Key Features

**Local Analytics** - DuckDB Web UI for price trends and history visualization
**Local Data Storage** - All data stored locally, no accounts, no cloud services
**Auto-Detection** - Automatically detects retailer from URL
**Product Groups** - Compare same product across multiple stores
**Basket Comparison** - Compare total costs across multiple product groups
**Price Tracking** - Historical data with automated change detection
**Configurable** - YAML-based provider configs, easily extensible
**Docker Ready** - One-command setup with virtual display for headless rendering
**Works with major retailers** - Supermarkets, electronics, and more

## Quick Start

### Docker (Recommended)

The **easiest way** to use Price Scout with full features:

```bash
# 1. Pull and run the container
docker run -d \
  --name price-scout \
  -p 4213:4214 \
  -v price-scout-data:/app/data \
  bulletinmybeard/price-scout:latest

# 2. Scout your first product
docker exec -it price-scout price-scout track --url "PRODUCT_URL"

# 3. Access the web interface (optional)
# Open http://localhost:4213 in your browser
```

**That's it!** You're now ready to scout and monitor prices.

**Example Output:**

```
✓ Tracked: Example Product Name (500g)
  Price: €9.99
  Provider: store-a

Data saved to database.
```

**Upgrading from a previous version?**

<details>
<summary>Migration instructions (v1.2.0+)</summary>

Database migrations are only needed when upgrading to v1.2.0 or later with an existing database.

**Check your version:**

```bash
price-scout --version
```

**Docker users:** Migrations run automatically on container startup. No action needed.

**Local/PyPI users:**

```bash
# Check migration status
scout db migrate status

# Apply pending migrations (backup first!)
cp ~/.price-scout/database.duckdb ~/.price-scout/database.duckdb.backup
scout db migrate apply
```

See [CHANGELOG.md](CHANGELOG.md) for breaking changes. Full migration guide: [docs/MIGRATIONS.md](.claude/MIGRATIONS.md).

</details>

### pip (Alternative)

For automation, CI/CD, or lightweight scripting:

```bash
# 1. Install with pipx (recommended)
pipx install price-scout

# 2. Install browser support
playwright install firefox

# 3. Scout your first product
price-scout track --url "PRODUCT_URL"
```

### When to Use Docker vs pip

| Feature                  | Docker  | pip         |
| :----------------------- | :------ | :---------- |
| All retailers supported  | ✅ Yes  | ⚠️ Most     |
| DuckDB Web UI included   | ✅ Yes  | ❌ No       |
| Headless browser support | ✅ Full | ⚠️ Limited  |
| Setup complexity         | 🟢 Easy | 🟡 Moderate |
| Installation size        | ~2 GB   | ~500 MB     |

**Recommendation**: Use Docker for full features and better compatibility.

<details>
<summary><b>Advanced Docker Configuration</b></summary>

For **development** or **custom configurations**:

```bash
# Create local directories
mkdir -p data config provider_configs

# Download example configuration (optional)
curl -o config/config.yaml https://raw.githubusercontent.com/bulletinmybeard/price-scout/master/config.example.yaml

# Run with custom mounts
docker run -d \
  --name price-scout \
  -p 4213:4214 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/config/config.yaml:/app/config.yaml" \
  -v "$(pwd)/provider_configs:/app/provider_configs" \
  bulletinmybeard/price-scout:latest
```

**Volume Mount Options:**

| Mount                   | Purpose                        | Required?                      |
| ----------------------- | ------------------------------ | ------------------------------ |
| `/app/data`             | Database and Parquet files     | **Yes** (for data persistence) |
| `/app/config.yaml`      | Custom configuration override  | No (auto-creates default)      |
| `/app/provider_configs` | Custom provider configurations | No (uses built-in providers)   |

</details>

## Usage Examples

### Track Your Weekly Groceries

**Use case**: Track your regular grocery items and see which store offers the best price.

```bash
# Track items across stores
price-scout track --url "RETAILER_A_MILK_URL" --group "Weekly Groceries"
price-scout track --url "RETAILER_B_BREAD_URL" --group "Weekly Groceries"
price-scout track --url "RETAILER_C_COFFEE_URL" --group "Weekly Groceries"

# Or track multiple URLs at once
price-scout track \
  --url "RETAILER_A_MILK_URL" \
  --url "RETAILER_B_MILK_URL" \
  --url "RETAILER_C_MILK_URL" \
  --group "Weekly Groceries"

# Compare prices in the group
price-scout groups compare "Weekly Groceries"

# Check price history
price-scout history "PRODUCT_URL"
```

**Example Group Comparison Output:**

```
Weekly Groceries - Price Comparison
┌──────────────┬───────────┬───────┬────────┐
│ Product      │ Store     │ Price │ Change │
├──────────────┼───────────┼───────┼────────┤
│ Milk 1L      │ Store A   │ €1.29 │ ↓ €0.10│
│ Milk 1L      │ Store B   │ €1.39 │ → €0.00│
│ Milk 1L      │ Store C   │ €2.49 │ ↑ €0.20│
└──────────────┴───────────┴───────┴────────┘

Best Deal: Store A (€1.29 for Milk 1L)
```

**Smart shopping**: See price trends over weeks. Buy when prices dip, not at peak.

### Compare Product Variants

**Use case**: Which coffee brand offers the best value per gram?

```bash
price-scout track --url "RETAILER_A_COFFEE_500G_URL" --group "Coffee"
price-scout track --url "RETAILER_B_COFFEE_250G_URL" --group "Coffee"
price-scout groups compare "Coffee"
```

**Result**: See price per unit (€/kg, €/liter) to compare apples-to-apples across different package sizes.

## CLI Commands

### Common Workflows

```bash
# Quick price check (without saving to database)
price-scout track --url "URL" --check

# Track and add to group in one command
price-scout track --url "URL" --group "Group Name"

# Track from a file (one URL per line, # comments are being ignored)
price-scout track --url-file weekly_groceries_products.txt
price-scout track -F weekly_groceries_products.txt --group "Weekly Groceries"

# Refresh all tracked products (creates new snapshots)
price-scout refresh
```

**URL File Argument**: The `--url-file` option searches for files in:

- Current directory
- Data directory (`./data/` local, `/app/data/` Docker, `~/.price-scout/data/` global)
- User directory (`~/.price-scout/`)

### Basic Commands

```bash
# Track a product
price-scout track --url "URL"
price-scout track --url "URL" --group "Group Name"

# Refresh prices (update all tracked products)
price-scout refresh
```

### Product Groups

```bash
# Sync groups from config.yaml to database
price-scout groups sync

# List all groups
price-scout groups list

# Compare prices within a group
price-scout groups compare "Group Name"

# Compare basket costs across multiple groups
price-scout compare groups --name "Coffee" --name "Milk" --name "Bread"
```

### Database Management

```bash
# Initialize database
price-scout db init

# Show database info
price-scout db info

# Reset database (caution!)
price-scout db reset
```

## Tips & Tricks

### ZSH/Bash Function for Docker Users

If you're using Docker, create a shell function to run Price Scout commands more conveniently:

**Setup** (add to `~/.zshrc` or `~/.bashrc`):

```bash
# Price Scout wrapper function
scout() {
    if ! docker ps --format '{{.Names}}' | grep -q 'price-scout'; then
        echo "Error: price-scout container is not running"
        return 1
    fi
    docker exec -it price-scout price-scout "$@"
}
```

**Usage**:

```bash
# Instead of: docker exec -it price-scout price-scout track "URL"
scout track "URL"

# Instead of: docker exec -it price-scout price-scout groups compare "Group"
scout groups compare "Group"
```

### Automated Price Monitoring

Schedule regular price updates with cron:

```bash
# Add to crontab (run every day at 8 AM)
0 8 * * * docker exec price-scout price-scout refresh
```

### Handling Multi-Offer Products

Many retailers offer different product options and prices, commonly to find for **refurbished items** or **product editions**:

**Example for a refurbished product)**:

- Refurbished "Excellent" condition: €509.99
- Refurbished "Very Good" condition: €495.99
- Refurbished "Good" condition: €491.99

#### How Price Scout Handles This

Price Scout uses an **offer selection strategy** to determine which price to track:

- `first` (default) - Select the first price from multi-offer products
- `cheapest` - Select the lowest price regardless of its availability
- `cheapest_available` - Select the lowest price that's in stock

**Configuration Example**:

```yaml
extraction:
  json_ld:
    offer_selection_strategy: "first"  # or "cheapest" or "cheapest_available"
```

#### Strategy Locking

Once a product is tracked and the first snapshot created, the strategy for this product will be locked to the `offer_selection_strategy` at the time to prevent inaccurate "price changes" over time.

**Example of what strategy locking prevents**:

- Day 1: Track with `cheapest` strategy → €491.99 (Good condition)
- Day 2: Config changed to `first` → €509.99 (Excellent condition)
- Without locking: Database shows 3.7% "price increase" but nothing actually changed!

**To change the strategy for a tracked product**:

1. Delete all snapshots for the product URL
1. Delete the `tracked_pages` entry
1. Re-track the product URL (new strategy will be locked)

#### Best Practices

**For new products (single offer)**: No action needed - works automatically

**For refurbished with multiple offers**:

- Use `first` strategy (default) for most reliable tracking
- Or use `cheapest_available` if you want best deals
- Understand you're tracking a price point, not a specific condition

**For condition-specific tracking**:

- Track each condition as a separate product
- Use different product names (e.g., "PS5 (Refurbished - Good)")

#### Note: Schema.org Limitations

Unfortunately, Schema.org doesn't have a standard for refurbished condition grades (Excellent/Good/Fair). Most retailers mark all offers as generic `"RefurbishedCondition"` without specifying the grade in structured data.

The condition grades you see in the UI aren't in the JSON-LD data that Price Scout extracts. This is a limitation of the standardized format, not the tool.

## Platform Compatibility

Price Scout works on most operating systems:

| Platform                   | Docker  | pip     | Notes                    |
| -------------------------- | ------- | ------- | ------------------------ |
| Linux (Ubuntu 20.04+)      | ✅ Full | ✅ Full | Recommended for servers  |
| macOS (12+)                | ✅ Full | ✅ Full | Apple Silicon supported  |
| Windows (10/11 + WSL2)     | ✅ Full | ✅ Full | Docker recommended       |
| ARM64 (Raspberry Pi, etc.) | ✅ Full | ✅ Full | Multi-arch Docker images |

**Technical Note**: Docker provides virtual display support (Xvfb) for maximum compatibility.

## Contributing

We welcome contributions! Price Scout is built to be **extensible**—adding new retailers is straightforward.

### Adding a New Retailer

Most retailers can be added with just a YAML configuration file:

```yaml
# provider_configs/new-retailer.yaml
name: "new_retailer"
country: "XX"
base_url: "https://www.retailer.example"
extraction:
  priority: ["json-ld"]  # Most sites support JSON-LD Schema.org
```

No Python code required for standard retailers. See `provider_configs/` directory for examples.

### Development Setup

**Using Docker Compose** (recommended for development):

```bash
# Clone the repository
git clone https://github.com/bulletinmybeard/price-scout.git
cd price-scout

# Copy example configuration
cp config.example.yaml config.yaml

# Start with docker-compose (includes all volume mounts!)
docker compose up -d

# Your code changes are immediately reflected
docker exec -it price-scout price-scout --version
```

**Using Poetry** (local development):

```bash
# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Install Firefox support
playwright install firefox

# Run Price Scout
poetry run price-scout --help
```

### Ways to Contribute

- **Add new retailers** - Create YAML configs for stores you use
- **Report bugs** - Open GitHub Issues with reproduction steps
- **Suggest features** - Share your ideas for improvements
- **Improve documentation** - Help others get started
- **Write tests** - Increase code coverage (current: 37%)

## Architecture

### Technical Stack

- **Browser Automation**: Playwright with Firefox (best compatibility)
- **Database**: DuckDB (columnar analytics database, 100x faster than SQLite for analytics)
- **Extraction**: JSON-LD (Schema.org structured data) with PyLD library
- **CLI Framework**: Click with rich formatting
- **Data Validation**: Pydantic2 with strict type checking
- **Docker**: Multi-arch support (AMD64 + ARM64) with Xvfb for virtual display

### Key Design Decisions

**Why DuckDB?**

- Optimized for analytics queries (price trends, comparisons)
- Columnar storage = fast aggregations
- Exports to Parquet for zero-copy reads
- Built-in Web UI for data exploration

**Why JSON-LD Extraction?**

- Standardized format (Schema.org)
- Better compatibility across retailers
- Self-documenting data structure

**Why Docker-First?**

- Consistent environment across platforms
- Includes Xvfb for headless browser rendering
- DuckDB Web UI included out-of-the-box
- No dependency management hassles

## Acknowledgments

Price Scout uses these excellent open-source projects:

- [Playwright](https://playwright.dev/) - Browser automation
- [DuckDB](https://duckdb.org/) - Analytics database
- [Click](https://click.palletsprojects.com/) - CLI framework
- [Pydantic](https://docs.pydantic.dev/) - Data validation
- [PyLD](https://github.com/digitalbazaar/pyld) - JSON-LD processing
- [Chalkbox](https://pypi.org/project/chalkbox/) - GUI framework

## License

MIT License - see [LICENSE](LICENSE) file for details.

**Summary**: Free for personal and commercial use. Attribution appreciated but not required.
