# Changelog

All notable changes to Price Scout will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [unreleased]

## [1.2.0b1] - 2026-07-01

### Added

- **`price-scout db migrate check`**: Exit-code based migration check for automation (Docker, CI)
  - Exit `0` = up to date, `1` = pending migrations, `2` = error
- **`price-scout db migrate status --json`**: Machine-readable migration status output
- **Packaged migrations**: Migration files ship inside the Python wheel at `src/database/migrations/`
  - Fixes pip/PyPI installs where `scripts/migrations/` was not available
- **Empty group cleanup**: Deleting a tracked product now removes product groups that become empty
- **Migration tests**: Unit tests for `MigrationRunner`, `migration_checker`, and `delete_tracked_page`

### Changed

- **BREAKING**: Basket comparison command moved from `scout groups basket` to `scout compare groups`

  - Improved command structure with extensibility for future compare subcommands
  - Example: `scout compare groups --name "Coffee" --name "Milk"` (replaces `scout groups basket --groups "Coffee,Milk"`)
  - See migration guide below for details

- **BREAKING**: Changed `--groups` comma-separated list to repeatable `--name` flag

  - Better UX for long group names (no escaping needed)
  - Shell-friendly with familiar pattern (like docker `-v`)
  - Short flag alias: `-n`
  - Example: `scout compare groups -n "SONY PlayStation 5" -n "Weekend Groceries"`

- **BREAKING**: Removed `--include-unavailable` flag - unavailable products always shown

  - Unavailable products now appear in all output sections with clear status markers
  - Unavailable products excluded from price calculations (total cost, category subtotals)
  - "Unavailable" column added to Provider Totals table
  - Products marked with "OUT" status in Product Breakdown
  - More transparent and accurate cost calculations

- **Docker migrations**: Startup script uses `db migrate check` exit codes instead of parsing CLI text

- **Dependencies**: Updated Python packages to latest compatible versions

  - Updated `beautifulsoup4` from 4.12.2 to 4.14.2
  - Updated `chalkbox` from 2.1.1 to 2.2.0
  - Updated `click` from 8.1.7 to 8.3.1
  - Updated `pydantic` from 2.12.4 to 2.12.5
  - Updated `PyYAML` from 6.0.1 to 6.0.3
  - Updated `requests` from 2.31.0 to 2.32.5
  - Updated `selectolax` from 0.4.0 to 0.4.2

### Migration Guide

**Old command:**

```bash
scout groups basket --groups "Group1,Group2,Group3"
```

**New command:**

```bash
scout compare groups --name "Group1" --name "Group2" --name "Group3"
```

**What changed:**

1. Command moved: `groups basket` → `compare groups`
1. Argument changed: `--groups "A,B"` → `--name "A" --name "B"`
1. Unavailable products now always shown (removed `--include-unavailable` flag)

## [0.9.0b1] - 2025-11-22

### Changed

- **Multi-Offer Strategy Locking**: Price history integrity for products

  - Prevents fake price changes when config changes
  - Strategy locked in database after first snapshot
  - Three strategies: `first` (default), `cheapest`, `cheapest_available`
  - Warns when locked strategy differs from config
  - Database migration script included
  - Comprehensive documentation in code and README
  - 100% backwards compatible (existing products unaffected)

- **Formal Migration System**: Laravel-style database migrations

  - Numbered migration files (0001\_*, 0002\_*, etc.) in `src/database/migrations/` (shipped in the Python package)
  - Version tracking in `schema_migrations` table
  - CLI commands: `scout db migrate apply/status/rollback`
  - Checksum verification (SHA256) to detect modified migrations
  - Dry-run support for testing migrations safely
  - Rollback support with `down()` functions
  - Backwards compatibility via `check_applied()` functions
  - Detailed documentation in `docs/MIGRATIONS.md`

- **Docker Auto-Migration**: Zero-config database migrations

  - Automatic migration application on container startup
  - Timestamped backups before each migration run
  - Fail-safe container startup (aborts if migrations fail)
  - Colored output for clear status visibility
  - Manual override available via CLI commands
  - Backup management with cleanup instructions
  - Full logging of migration process

- **CSS/XPath Selector Extraction**: Fallback for sites without JSON-LD

  - Full CSS selector support with advanced features
  - XPath selector support for complex DOM queries
  - Multiple selector fallbacks per field (first match wins)
  - Regex extraction and replacement per selector
  - Text mode control (inner_text, text_content, full_html)
  - Attribute extraction (src, href, data-\*, etc.)
  - Wait-for-selector with configurable timeout
  - Visibility and disabled state checking
  - Multiple element extraction (arrays)
  - Amazon.nl provider implementation with 30+ selectors
  - Comprehensive inline documentation and examples

### Database Migration Required

**For existing installations**, database schema updates are required for new features.

#### Migration Methods

**Docker installations** (AUTOMATIC):

- Migrations run automatically on container startup
- Automatic backup created before applying migrations
- No manual action required
- Check container logs for migration status

**Local/PyPI installations** (MANUAL):

```bash
# Check migration status
scout db migrate status

# Apply pending migrations
scout db migrate apply
```

#### What Migrations Do

**Migration 001: Add offer_selection_strategy column**

- Adds `offer_selection_strategy` column to `tracked_pages` table
- Enables multi-offer strategy locking feature
- Existing products remain unaffected (NULL values use config-based selection)

#### Backwards Compatibility

- All migrations are **100% safe** - no data loss or price history corruption
- Existing tracked products continue using config-based strategy selection (defaults to "first")
- Fresh installs include all schema changes automatically (no migration needed)
- Idempotent: Safe to run multiple times

#### Skip Migrations If

- Fresh install (v0.8.5b1 or later)
- No existing tracked products in database
- Docker installation (auto-applies on startup)

See `docs/MIGRATIONS.md` for comprehensive migration guide, backup procedures, and rollback instructions.

## [0.8.5b1] - 2025-11-13

### Beta Release - Pre-v1.0 Polish & Refinements

Final beta release with proper parsing, configuration improvements, and UX enhancements.

### Added

- **Product Parser System**: Structured amount/unit extraction

  - Extract numeric values and units from product names ("500 g", "1.5 l")
  - UN/CEFACT code normalization (KGM→kg, LTR→l, GRM→g, MLT→ml)
  - Multi-pack detection ("6 x 330ml" → pack=6, amount=330, unit=ml)
  - Range handling ("100-200g" takes first value)
  - Variant detection (colors, flavors, types like organic/bio/zero)
  - 6 structured database fields for analytics-ready data
  - 62 tests, 94% coverage

- **Language Detection System**: Intelligent language-specific variant extraction

  - Auto-detects page language from HTML (`<html lang="nl-NL">`)
  - Provider-level language overrides for edge cases
  - 50+ country-to-language mappings as fallback
  - 5-10x performance improvement (searches ~14 variants vs 72)
  - 28 comprehensive tests, 100% backward compatible

- **Fuzzy Group Matching**: Typo prevention for product groups

  - Runs BEFORE tracking to ask once for all URLs
  - Shows top 3 similar groups when similarity > 80%
  - Interactive "Did you mean...?" prompts
  - Example: "Weekly Groceriess" → suggests "Weekly Groceries (~85% match)"
  - Slug-based matching (case-insensitive, normalized)
  - Uses stdlib `difflib.SequenceMatcher` (no new dependencies)

- **Flexible Product Grouping**: CLI-based group assignment

  - `--group` flag for track command - assign groups on-the-fly
  - Creates groups automatically if they don't exist
  - Groups now optional - track without groups, organize later
  - Automatic config-based association as fallback
  - Priority: `--group` flag > config.yaml > no group

- **Provider Config Variants**: Testing and comparison support

  - `--provider-config` flag to override default configs
  - Variant naming: `provider.variant.yaml` (e.g., `store-a.minimal.yaml`)
  - Automatic variant skipping during normal loading
  - Useful for testing and debugging

- **Debug Logging Mode**: Clean, user-friendly debug output

  - `--debug` flag enables detailed logging
  - Clean format without timestamps/paths for readability
  - Separate from normal user output
  - Useful for troubleshooting issues

- **Currency Symbol Display**: Enhanced price formatting

  - Displays proper currency symbols (€, $, £, etc.)
  - 37+ currency symbols supported
  - Fallback to currency code if symbol unavailable
  - Integrated into all price display output

### Changed

- **Configuration System**: ConfigDict → Pydantic2 models

  - Type-safe configuration with proper validation
  - Better error messages for invalid configs
  - Eliminates runtime configuration errors

- **Default Browser**: Chromium → Firefox

  - Better TLS fingerprinting for broad compatibility
  - Recommended for reliable price scouting

- **Groups Command**: Manual sync now optional

  - Automatic association eliminates most manual sync needs
  - `groups sync` still useful for bulk operations
  - Simpler workflow

- **Test Coverage**: Increased to 37% (379 tests, 100% passing)

  - Product parser: 62 tests, 94% coverage
  - Language detection: 28 tests, 100% coverage
  - Fuzzy matching: 27 tests, 100% coverage
  - All critical paths well-tested

### Fixed

- **Database Connection Conflicts**: Fixed parallel tracking errors

  - Each thread creates own database connection
  - Prevents DuckDB "Cannot attach database" errors
  - Affects multi-URL tracking workflows

- **JSON Serialization**: Fixed decimal/datetime handling

  - Proper serialization of Decimal types for prices
  - Datetime objects correctly formatted
  - Prevents JSON encoding errors

- **Foreign Key Handling**: Improved relationship management

  - Better cascade deletion for product groups
  - Database integrity maintained

### Technical Details

- Python 3.12+
- New utilities: `product_parser.py`, `slug.py`, `fuzzy_matcher.py`
- Pydantic2 for configuration validation
- Enhanced Parquet exports with structured fields

## [0.5.0] - 2025-06-20

Release with Docker support and advanced anti-fingerprinting.

### Added

- **Docker Support**: Containerization

  - Unified container (CLI + DuckDB Web UI)
  - Supervisord process management
  - Xvfb virtual display for headed browser mode
  - Volume mounts for persistent data
  - `docker-compose.yml` configuration

- **DuckDB Web UI**: Analytics visualization interface

  - Integrated web interface on port 4213
  - Real-time query interface
  - Read-only replica pattern for concurrent access
  - Event-driven DB sync with inotify
  - Automatic Parquet export for UI queries

- **Xvfb Virtual Display**: Headless server support

  - Enables headed Firefox in Docker
  - Bypasses advanced bot detection
  - Works on Linux servers without display
  - Configured via `DISPLAY=:99` environment

- **Warm-up Navigation**: Improved success rate

  - Homepage → product page navigation pattern
  - Better cookie/session establishment
  - Reduces bot detection triggers
  - Configurable per provider

### Changed

- **Default Browser Mode**: Headless → Headed (in Docker)

  - Significantly better bypass success
  - Virtual display makes it transparent

- **Screenshot Configuration**: Always → Error-only

  - Reduces disk usage
  - Still captures failures for debugging
  - Configurable via `save_screenshots: true`

### Technical Details

- Docker: Multi-stage build with Playwright browsers
- Xvfb: Virtual display server for headed mode
- Supervisord: Process management in container
- DuckDB UI: Port 4213, read-only replica access
- Anti-fingerprinting: 18 techniques implemented

## [0.4.0] - 2025-03-10

### Analytics Database & Structured Data Extraction

Major architectural upgrade with DuckDB analytics database and JSON-LD extraction.

### Added

- **DuckDB Database**: Columnar analytics database replacing SQLite

  - Optimized for analytics queries
  - Better performance for price history analysis
  - Parquet export support
  - Migration script from SQLite

- **JSON-LD Extraction System**: Schema.org structured data parsing

  - `JSONLDExtractor` class - Standards-based extraction
  - PyLD library integration
  - Priority: JSON-LD → CSS selectors (fallback)
  - Automatic detection in HTML script tags

- **PyLD Pipeline**: Robust JSON-LD processing

  - Normalize → Expand → Compact → Frame → Extract
  - Handles nested Schema.org structures
  - Multiple fallback paths for fields
  - Default values when data missing

- **Product Groups Feature**: Compare same product across retailers

  - `product_groups` table - Group definitions
  - `product_group_pages` - Many-to-many relationships
  - Group sync from config.yaml
  - Price comparison across group members

- **Field Mappings System**: Declarative data extraction

  - YAML-based field path definitions
  - Multiple fallback paths per field
  - Default values support
  - Transformations (split, regex, price parsing)

### Changed

- **Database Engine**: SQLite → DuckDB

  - Backward compatible migration
  - Same schema, better performance
  - Analytics-ready columnar storage

- **Primary Extraction Method**: CSS selectors → JSON-LD

  - More reliable (standards-based)
  - CSS selectors kept as fallback

### Technical Details

- New dependencies: `duckdb = "^1.4.1"`, `pyld = "^2.0.4"`
- Database: DuckDB with Parquet export
- Extraction: JSON-LD primary, CSS fallback
- Migration: Automated SQLite → DuckDB script

## [0.3.0] - 2024-12-01

### Configuration System & Provider Architecture

Introducing YAML-based configuration and modular provider architecture.

### Added

- **YAML Configuration System**: App configuration

  - `config.yaml` for user settings
  - Database path, browser settings, wait strategies
  - Replaces hardcoded configuration values
  - Example file: `config.yaml.example`

- **Provider System Architecture**: Modular provider design

  - `ProviderFactory` - Auto-loads provider configs
  - `ConfigurableProvider` - Generic YAML-based provider
  - Separation of extraction logic from code
  - Foundation for multi-retailer support

- **Provider Configs Directory**: YAML-based provider definitions

  - `provider_configs/` directory structure
  - CSS selectors moved from code to YAML
  - Wait strategies and delays per provider

- **Two-Level Configuration**: Flexible config priority

  - `provider_configs/*.yaml` - System defaults
  - `config.yaml` providers section - User overrides
  - Individual YAML files take precedence

### Changed

- **Provider Loading**: Hardcoded → YAML-based

  - No code changes needed to add new retailers
  - Provider-specific logic refactored
  - Simplified retailer onboarding

- **Configuration Management**: Centralized settings

### Technical Details

- New dependency: `PyYAML = "^6.0.1"`
- Config file: `config.yaml`
- Provider configs: `provider_configs/*.yaml`

## [0.2.0] - 2024-10-05

### Browser Automation & JavaScript Support

Introducing browser automation to handle JavaScript-rendered pages.

### Added

- **Playwright Integration**: Browser automation replacing simple HTTP requests

  - Handles JavaScript-rendered pages
  - Supports dynamic content loading
  - Async/await architecture for better performance

- **Firefox Browser Support**: Initial browser implementation

  - Headed mode for debugging
  - Screenshot capture on errors
  - Better compatibility with retailers

- **AsyncBaseProvider**: Foundation for async scraping

  - Replaces synchronous HTTP fetching
  - Non-blocking page loads
  - Context manager pattern for browser lifecycle

- **Basic Anti-Fingerprinting**: Initial bot detection bypass

  - Hides `navigator.webdriver` flag
  - Custom user agent strings
  - Basic browser fingerprint masking

- **Screenshot System**: Automatic error capture

  - Saves screenshots when extraction fails
  - Helps debug JavaScript rendering and scraping issues
  - Stored in local `screenshots/` directory

### Changed

- **Scraping Architecture**: Moved from requests → Playwright
  - BeautifulSoup4 still used for HTML parsing
  - Browser automation handles page loading
  - Async/await replaces synchronous requests

### Fixed

- JavaScript detection
- Dynamic price loading no longer causes extraction failures
- Timeout handling for slow-loading pages

### Technical Details

- Python 3.12+
- New dependency: `playwright = "1.55.0"`
- Browser: Firefox (headed mode)
- Async architecture with asyncio
- Screenshot storage: `./screenshots/`

## [0.1.0] - 2024-08-23

### Initial Prototype

First working version of the Python Price Tracker.

### Added

- **Basic CLI Interface**

  - Click framework for command-line interface
  - `track` command to add product URLs
  - `list` command to view tracked products
  - Simple text-based output

- **HTTP-based Scraping**

  - Requests library for fetching web pages
  - BeautifulSoup4 for HTML parsing
  - Manual CSS selector configuration in code
  - Basic price extraction from HTML

- **SQLite Database**

  - Product tracking table (URLs, names, providers)
  - Price history table (timestamps, prices)
  - Basic schema with SQLAlchemy ORM
  - Local file-based storage

### Limitations

- Only works with simple HTML sites (no JavaScript)
- CSS selectors hardcoded per retailer
- No error handling for failed requests
- No browser automation
- Single-threaded (one product at a time)
- Manual provider configuration required

### Technical Details

- Python 3.12+
- Dependencies: click, requests, beautifulsoup4, sqlalchemy, lxml
- Database: SQLite (local file)
- No configuration file yet (hardcoded values)
