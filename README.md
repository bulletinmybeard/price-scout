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

# Refresh all tracked products (creates ne snapshots)
price-scout refresh
```

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
