import json

from chalkbox.logging.bridge import get_logger
from pyld import jsonld

logger = get_logger(__name__)


def _custom_document_loader(url, options=None):
    """Custom document loader that provides local schema.org context."""
    if options is None:
        options = {}

    if url in ("https://schema.org", "https://schema.org/", "http://schema.org"):
        return {
            "contextUrl": None,
            "documentUrl": url,
            "document": {"@context": {"@vocab": "https://schema.org/"}},
        }

    raise jsonld.JsonLdError(
        f"Could not load document for URL: {url}",
        "jsonld.LoadDocumentError",
        {"url": url},
        code="loading document failed",
    )


jsonld.set_document_loader(_custom_document_loader)


# JSON-LD Frame for extracting product info
PRODUCT_FRAME = {
    "@context": "https://schema.org",
    "@type": "Product",
    "name": {},
    "url": {},  # Canonical product URL
    "offers": {
        "@type": "Offer",
        "price": {},
        "priceCurrency": {},
        "availability": {},
        "priceSpecification": {"@type": "PriceSpecification", "@explicit": True, "price": {}},
    },
    "brand": {},
    "description": {},
    "image": {},
    "sku": {},
    "gtin": {},
    "gtin13": {},
    "weight": {},
}


# JSON-LD Frame for extracting ProductGroup with variants
PRODUCT_GROUP_FRAME = {
    "@context": "https://schema.org",
    "@type": "ProductGroup",
    "name": {},
    "hasVariant": {
        "@type": "Product",
        "name": {},
        "offers": {"@type": "Offer", "price": {}, "priceCurrency": {}, "availability": {}},
    },
    "variesBy": {},
}


class JSONLDExtractor:
    """Standards-based JSON-LD extractor using PyLD library."""

    def __init__(self):
        """Initialize the JSON-LD extractor."""
        self.product_frame = PRODUCT_FRAME
        self.product_group_frame = PRODUCT_GROUP_FRAME

    def _extract_with_frame(
        self, json_ld_data: dict | list, frame: dict, expected_type: str, type_name: str = "entity"
    ) -> dict | None:
        """Generic method to extract JSON-LD data using a specific frame."""
        try:
            if isinstance(json_ld_data, dict):
                json_ld_data = [json_ld_data]

            # Expand JSON-LD (normalize to canonical form)
            expanded = jsonld.expand(json_ld_data)

            if not expanded:
                logger.warning(f"JSON-LD expansion returned empty result for {type_name}")
                return None

            # Compact with schema.org context
            compacted = jsonld.compact(expanded, "https://schema.org")

            # Apply frame to extract desired structure
            framed = jsonld.frame(compacted, frame)

            # Extract result from @graph or direct result
            # Try @graph array first!
            graph = framed.get("@graph", [])
            if graph and len(graph) > 0:
                result = graph[0]
                self._log_extraction_success(result, expected_type, type_name)
                return result

            # Try direct result if @type matches
            if framed.get("@type") == expected_type:
                self._log_extraction_success(framed, expected_type, type_name)
                return framed

            logger.warning(f"No {type_name} found in framed result")
            return None

        except jsonld.JsonLdError as e:
            logger.error(f"PyLD framing error for {type_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in PyLD {type_name} extraction: {e}")
            return None

    @staticmethod
    def _log_extraction_success(result: dict, expected_type: str, type_name: str):
        """Log successful extraction with appropriate details based on type."""
        name = result.get("name", "N/A")

        if expected_type == "ProductGroup":
            variants = result.get("hasVariant", [])
            variant_count = len(variants) if isinstance(variants, list) else 1
            logger.debug(
                f"✓ Extracted {type_name} via PyLD framing: {name} ({variant_count} variants)"
            )
        else:
            logger.debug(f"✓ Extracted {type_name} via PyLD framing: {name}")

    def extract_product(self, json_ld_data: dict | list) -> dict | None:
        """Extract Product from JSON-LD data."""
        return self._extract_with_frame(
            json_ld_data, frame=self.product_frame, expected_type="Product", type_name="Product"
        )

    def extract_product_group(self, json_ld_data: dict | list) -> dict | None:
        """Extract ProductGroup with variants from JSON-LD data."""
        return self._extract_with_frame(
            json_ld_data,
            frame=self.product_group_frame,
            expected_type="ProductGroup",
            type_name="ProductGroup",
        )

    @staticmethod
    def select_best_variant(product_group: dict, strategy: str = "first_complete") -> dict | None:
        """Select the best variant from a ProductGroup."""
        variants = product_group.get("hasVariant", [])

        if not variants:
            logger.warning("ProductGroup has no variants")
            return None

        if not isinstance(variants, list):
            variants = [variants]

        if strategy == "first":
            return variants[0]

        elif strategy == "first_complete":
            for variant in variants:
                has_name = variant.get("name") and not variant.get("name", "").endswith("…")
                has_offers = variant.get("offers") is not None

                if has_name and has_offers:
                    logger.debug(f"Selected first complete variant: {variant.get('name')}")
                    return variant

            logger.warning("No complete variants found, using first variant")
            return variants[0]

        elif strategy == "cheapest":
            cheapest = None
            cheapest_price = float("inf")

            for variant in variants:
                offers = variant.get("offers")
                if not offers:
                    continue

                if isinstance(offers, list):
                    offers = offers[0] if offers else {}

                price_str = offers.get("price", "")
                try:
                    price = float(str(price_str).replace(",", "."))
                    if price < cheapest_price:
                        cheapest_price = price
                        cheapest = variant
                except (ValueError, TypeError):
                    continue

            if cheapest:
                logger.debug(
                    f"Selected cheapest variant: {cheapest.get('name')} at {cheapest_price}"
                )
                return cheapest

            logger.warning("Could not determine cheapest, using first variant")
            return variants[0]

        else:
            logger.warning(f"Unknown strategy '{strategy}', using first variant")
            return variants[0]

    def extract_from_html(self, html: str) -> dict | None:
        """Extract and parse JSON-LD from HTML content."""
        from bs4 import BeautifulSoup

        try:
            soup = BeautifulSoup(html, "lxml")
            script_tags = soup.find_all("script", {"type": "application/ld+json"})

            if not script_tags:
                logger.warning("No JSON-LD script tags found in HTML")
                return None

            logger.debug(f"Found {len(script_tags)} JSON-LD script tags")

            for idx, script_tag in enumerate(script_tags):
                try:
                    if not script_tag.string:
                        continue
                    json_ld_data = json.loads(script_tag.string)

                    product = self.extract_product(json_ld_data)
                    if product:
                        return product

                    product_group = self.extract_product_group(json_ld_data)
                    if product_group:
                        variant = self.select_best_variant(product_group, strategy="first_complete")
                        return variant

                except json.JSONDecodeError as e:
                    logger.warning(f"Script tag {idx} is not valid JSON: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Error processing script tag {idx}: {e}")
                    continue

            logger.warning("No Product or ProductGroup found in any script tag")
            return None

        except Exception as e:
            logger.error(f"Error extracting JSON-LD from HTML: {e}")
            return None


def create_extractor() -> JSONLDExtractor:
    """Factory function to create a new JSONLDExtractor instance."""
    return JSONLDExtractor()
