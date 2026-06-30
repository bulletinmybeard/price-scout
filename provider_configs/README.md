# Provider Configuration Guide

This guide shows you how to create a provider configuration file for a new retailer.

## Quick Start

Most retailers can be added with a simple YAML config. Here's a minimal example:

```yaml
name: "my_store"
country: "XX"
base_url: "https://www.mystore.example"

extraction:
  priority: ["json-ld"]
```

That's it! Save as `my_store.yaml` and test with:

```bash
price-scout --provider-config my_store.yaml track --url "PRODUCT_URL"
```

## Configuration Structure

### Required Fields

| Field                 | Description                                  | Example                   |
| --------------------- | -------------------------------------------- | ------------------------- |
| `name`                | Provider identifier (lowercase, underscores) | `"jumbo"`                 |
| `country`             | Two-letter country code                      | `"NL"`, `"US"`            |
| `base_url`            | Retailer's website URL                       | `"https://www.jumbo.com"` |
| `extraction.priority` | Extraction methods to try                    | `["json-ld"]`             |

### Optional Fields

| Field                                                  | Description                    | Default              |
| ------------------------------------------------------ | ------------------------------ | -------------------- |
| `wait_strategy`                                        | Page load strategy             | `"domcontentloaded"` |
| `wait_delay`                                           | Extra wait time (seconds)      | `0`                  |
| `extraction.json_ld.field_mappings`                    | Map nested JSON-LD fields      | Auto-detected        |
| `extraction.json_ld.default_availability_when_missing` | Fallback availability          | `false`              |
| `extraction.json_ld.offer_selection_strategy`          | Multi-offer selection strategy | `"first"`            |
| `transformations`                                      | Post-process extracted data    | None                 |

## Field Mappings

Use field mappings to handle nested JSON-LD structures or provide defaults:

```yaml
extraction:
  json_ld:
    field_mappings:
      # Multiple fallback paths
      price: ["offers.price", "offers.lowPrice"]

      # With default value
      currency: ["offers.priceCurrency", {"default": "EUR"}]

      # Complex nested structure
      manufacturer: ["manufacturer.name", "brand.name", {"default": "Unknown"}]
```

**Path syntax**: Use dots for nested objects (e.g., `offers.price` accesses `data["offers"]["price"]`)

**Fallback order**: Tries each path left-to-right, uses first non-None value

**Defaults**: Use `{"default": "value"}` as last item to provide fallback

## Multi-Offer Products (e.g., refurbished items)

Some products have multiple offers with different prices (common for refurbished items). Configure which offer to track:

```yaml
extraction:
  json_ld:
    offer_selection_strategy: "first"  # Options: "first", "cheapest", "cheapest_available"
```

**Strategies**:

- `first` (default) - Most reliable, tracks first offer in array
- `cheapest` - Lowest price regardless of availability
- `cheapest_available` - Lowest price that's in stock

**Important: Strategy Locking**

Once a product is tracked, the strategy is **locked in the database** to prevent fake price changes. If you change the strategy in the config later, Price Scout will warn you but continue using the locked strategy.

**Example**: Refurbished products

```yaml
# Store-A often has 3 refurbished condition tiers
name: "storae-a"
extraction:
  json_ld:
    offer_selection_strategy: "first"  # Track "Excellent" condition (highest price)
```

**To change strategy for a tracked product**:

1. Delete all snapshots for that URL
1. Delete the tracked_pages entry
1. Re-track the URL (new strategy will be locked)

See README.md section "Handling Multi-Offer Products" for detailed explanation and best practices.

## CSS/XPath Selectors

For sites without JSON-LD or when you need precise control, use CSS or XPath selectors:

```yaml
extraction:
  priority: ["selectors"]  # or ["json-ld", "selectors"] for fallback

  css_selectors:
    # Basic CSS selector
    name:
      - selector: "#productTitle"

    # Multiple fallbacks (first match wins)
    price:
      - selector: "span.a-price span.a-offscreen"
      - selector: "#priceblock_ourprice"
      - selector: ".product-price"

    # With regex extraction and replacement
    price:
      - selector: "span.price"
        regex_extract: '€?\s*([\d.,]+)'  # Extract "14,44" from "€ 14,44"
        regex_replace:
          pattern: ','                     # Convert European comma to period
          replacement: '.'                 # Result: "14.44"

    # XPath for complex queries
    brand:
      - selector: "//th[contains(text(), 'Brand')]/following-sibling::td"
        type: "xpath"

    # Extract attribute value
    image:
      - selector: "#mainImage"
        attribute: "src"                   # Get src attribute value

    # Wait for dynamic content
    price:
      - selector: "span.dynamic-price"
        wait_for: true                     # Wait for element to appear
        wait_timeout: 5000                 # Max 5 seconds

    # Check element state (for availability)
    availability:
      - selector: "#add-to-cart-button"
        check_exists: true                 # Element exists in DOM
        check_visible: true                # Element is visible
        check_not_disabled: true           # Element is not disabled

    # Extract multiple elements (array)
    images:
      - selector: "img.product-image"
        attribute: "src"
        multiple: true                     # Returns array of all matches

    # Text extraction modes
    description:
      - selector: "#product-description"
        text_mode: "inner_text"           # Only visible text (default)
      - selector: "#product-description"
        text_mode: "text_content"         # All text including hidden
      - selector: "#product-description"
        text_mode: "full_html"            # Full HTML content
```

### CSS Selector Features

| Feature                  | Description                       | Example                         |
| ------------------------ | --------------------------------- | ------------------------------- |
| **Multiple Fallbacks**   | Try selectors in order            | `price: [sel1, sel2, sel3]`     |
| **Regex Extract**        | Extract pattern from text         | `regex_extract: '([\d.,]+)'`    |
| **Regex Replace**        | Replace pattern in extracted text | `pattern: ',' replacement: '.'` |
| **XPath Support**        | Use XPath instead of CSS          | `type: "xpath"`                 |
| **Attribute Extraction** | Get attribute value               | `attribute: "src"`              |
| **Wait for Element**     | Wait for dynamic content          | `wait_for: true`                |
| **State Checking**       | Check visibility/disabled state   | `check_visible: true`           |
| **Multiple Elements**    | Extract array of elements         | `multiple: true`                |
| **Text Modes**           | Control text extraction           | `text_mode: "inner_text"`       |

### When to Use CSS vs JSON-LD

**Use JSON-LD** (preferred):

- Site has Schema.org structured data
- More reliable, less likely to break
- Self-documenting data structure

**Use CSS Selectors**:

- No JSON-LD available
- Need precise control over extraction
- Site has non-standard data structure

**Hybrid Approach** (both):

```yaml
extraction:
  priority: ["json-ld", "selectors"]  # Try JSON-LD first, fallback to selectors
```

## Transformations

Apply transformations to extracted data:

### Available Types

**`split`** - Split string into list

```yaml
transformations:
  category:
    type: "split"
    delimiter: ","
```

**`regex_replace`** - Find and replace with regex

```yaml
transformations:
  description:
    type: "regex_replace"
    pattern: "\\s+"
    replacement: " "
```

**`price_specification`** - Extract price from PriceSpecification object

```yaml
transformations:
  current_price:
    type: "price_specification"
    price_type: "https://schema.org/SalePrice"
```

**`multiply`** - Multiply numeric value

```yaml
transformations:
  current_price:
    type: "multiply"
    factor: 100
```

## Browser Settings

Control page loading behavior:

```yaml
wait_strategy: "domcontentloaded"  # Options: load, domcontentloaded, networkidle
wait_delay: 2  # Additional wait time in seconds after page load
```

## Testing Your Config

### 1. Test with a product URL

```bash
price-scout --provider-config your_store.yaml track --url "PRODUCT_URL"
```

### 2. Enable debug logging

```bash
price-scout --debug --provider-config your_store.yaml track --url "PRODUCT_URL"
```

### 3. Check extracted data

Look for:

- Product name extracted correctly
- Price is numeric (not string with currency symbol)
- Availability detected (if product is in stock)

## Common Issues

**"No JSON-LD found"**

- Check if the website uses JSON-LD (view page source, search for `application/ld+json`)
- Some sites need JavaScript to render - use `wait_strategy: "networkidle"`

**Wrong field values**

- Add field_mappings to specify correct paths
- Use browser DevTools to inspect JSON-LD structure

**Missing fields**

- Provide defaults using `{"default": "value"}` in field_mappings
- Check if field exists in JSON-LD at all

## Next Steps

1. **Find JSON-LD structure**: View product page source, locate `<script type="application/ld+json">`
1. **Identify fields**: Match Schema.org fields to our model (name, price, currency, etc.)
1. **Create config**: Start minimal, add field_mappings/transformations as needed
1. **Test**: Use `--provider-config` flag to test before committing

For detailed field mapping examples and advanced features, see `.claude/CLAUDE.md` section "Provider Configuration Schema".
