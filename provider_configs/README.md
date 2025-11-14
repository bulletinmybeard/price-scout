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

| Field                                                  | Description                 | Default              |
| ------------------------------------------------------ | --------------------------- | -------------------- |
| `wait_strategy`                                        | Page load strategy          | `"domcontentloaded"` |
| `wait_delay`                                           | Extra wait time (seconds)   | `0`                  |
| `extraction.json_ld.field_mappings`                    | Map nested JSON-LD fields   | Auto-detected        |
| `extraction.json_ld.default_availability_when_missing` | Fallback availability       | `false`              |
| `transformations`                                      | Post-process extracted data | None                 |

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

## Examples

**Simple config**: `jumbo.yaml` - Basic setup with minimal transformations

**Complex config**: `albert-heijn.yaml` - Advanced transformations and field mappings

**Field mappings reference**: `config-field_mappings.yaml` - Comprehensive field mapping examples

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
