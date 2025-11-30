import asyncio
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup
from chalkbox.logging.bridge import get_logger
from playwright.async_api import Page

from src.cli.helpers import get_db_url
from src.config.models import ProviderConfig
from src.database.db_manager import DatabaseManager
from src.providers.base_product import BaseProduct
from src.providers.field_mapper import FieldMapper
from src.providers.jsonld_extractor import create_extractor
from src.providers.selector_extractor import SelectorExtractor
from src.providers.transformations import Transformations
from src.scrapers.async_base_provider import AsyncBaseProvider
from src.utils.datetime_utils import now_in_configured_tz
from src.utils.product_parser import parse_product_details

logger = get_logger(__name__)


class ConfigurableProvider(AsyncBaseProvider):
    """Generic provider that loads configuration from Pydantic ProviderConfig model."""

    def __init__(self, config: ProviderConfig, headless: bool = True):
        super().__init__(headless=headless)
        self.provider_config = config
        self._name = config.name
        self._country = config.country
        self._base_url = config.base_url

    @property
    def name(self) -> str:
        return self._name

    @property
    def country(self) -> str:
        return self._country

    @property
    def base_url(self) -> str:
        return self._base_url

    async def search_product(self, query: str) -> list[dict[str, Any]]:
        """Search not yet implemented for config-based providers."""
        raise NotImplementedError(f"Search not yet implemented for {self.name}")

    async def get_product_details(self, url: str) -> BaseProduct | None:
        logger.debug(f"Fetching {self.name} product: {url}")

        max_retries = self.config.scraping.max_retries
        retry_delay = self.config.scraping.request_delay_seconds

        wait_strategy = self.provider_config.wait_strategy
        wait_delay = self.provider_config.wait_delay

        for attempt in range(max_retries + 1):
            page = None
            try:
                page = await self.fetch_page(url, wait_until=wait_strategy.value)
                if not page:
                    if attempt < max_retries:
                        logger.debug(f"Retry {attempt + 1}/{max_retries} for {url} (fetch failed)")
                        delay = retry_delay * (2**attempt)
                        await asyncio.sleep(delay)
                        continue
                    logger.debug(f"Failed to fetch page after {max_retries + 1} attempts: {url}")
                    return None

                await asyncio.sleep(wait_delay)

                html_content = await self.get_page_content(page)

                if await self._is_white_page(html_content, page):
                    await self._save_screenshot(page, f"{self.name}_white_page", attempt=attempt)
                    if attempt < max_retries:
                        logger.debug(
                            f"Retry {attempt + 1}/{max_retries} for {url} (white page detected)"
                        )
                        await page.close()
                        delay = retry_delay * (2**attempt)
                        await asyncio.sleep(delay)
                        continue
                    logger.debug(f"White page detected after {max_retries + 1} attempts: {url}")
                    await page.close()
                    return None

                priority = self.provider_config.extraction.get("priority", ["json-ld"])
                logger.debug(f"Extraction priority: {priority}")

                product = None
                for method in priority:
                    if method == "json-ld":
                        product = await self._extract_from_json_ld(html_content, url, page)
                        if product:
                            product.extraction_method = "json-ld"
                            logger.debug("✓ Product extracted via JSON-LD")
                            break
                        logger.debug("JSON-LD extraction failed, trying next method")
                    elif method == "selectors":
                        product = await self._extract_from_selectors(html_content, url, page)
                        if product:
                            product.extraction_method = "selectors"
                            logger.debug("✓ Product extracted via selectors")
                            break
                        logger.debug("Selector extraction failed, trying next method")
                    else:
                        logger.warning(f"Unknown extraction method '{method}', skipping")

                if product:
                    if attempt > 0:
                        logger.info(
                            f"Successfully extracted product after {attempt + 1} attempts: {url}"
                        )
                    await page.close()
                    return product

                if attempt < max_retries:
                    logger.debug(
                        f"Retry {attempt + 1}/{max_retries} for {url} (all extraction methods failed)"
                    )
                    await self._save_screenshot(
                        page, f"{self.name}_extraction_failed", attempt=attempt
                    )
                    await page.close()
                    delay = retry_delay * (2**attempt)
                    await asyncio.sleep(delay)
                    continue

                logger.debug(
                    f"All extraction methods failed after {max_retries + 1} attempts: {url}"
                )
                await self._save_screenshot(page, f"{self.name}_extraction_failed", attempt=attempt)
                await page.close()
                return None

            except Exception as e:
                logger.debug(f"Attempt {attempt + 1}/{max_retries + 1} failed for {url}: {e}")
                if page:
                    await self._save_screenshot(page, f"{self.name}_exception", attempt=attempt)
                    await page.close()

                if attempt < max_retries:
                    delay = retry_delay * (2**attempt)
                    await asyncio.sleep(delay)
                    continue

                return None

        return None

    async def _extract_from_json_ld(
        self, html_content: str, url: str, page: Page
    ) -> BaseProduct | None:
        json_ld_config = self.provider_config.extraction.get("json_ld", {})

        use_pyld = json_ld_config.get("use_pyld", False)
        if use_pyld:
            logger.debug("Using PyLD library for JSON-LD extraction")

            extractor = create_extractor()
            json_ld = extractor.extract_from_html(html_content)

            if json_ld:
                logger.debug("✓ Extracting product data from JSON-LD (via PyLD)")
            else:
                logger.warning("PyLD extraction failed, falling back to manual parsing")
                json_ld = None
        else:
            wrapper_config = json_ld_config.get("wrapper")
            json_ld = self.extract_json_ld(html_content, wrapper_config=wrapper_config)

        if not json_ld:
            logger.debug("JSON-LD not found")
            return None

        if not use_pyld:
            logger.debug("✓ Extracting product data from JSON-LD")

        json_ld_config = self.provider_config.extraction.get("json_ld", {})
        if json_ld_config.get("use_variant_data") and json_ld.get("@type") == "ProductGroup":
            variants = json_ld.get("hasVariant", [])
            variant_index = json_ld_config.get("variant_index", 0)
            if variants and len(variants) > variant_index:
                logger.debug(
                    f"ProductGroup detected, extracting from variant [{variant_index}]: "
                    f"{variants[variant_index].get('name', 'unnamed')}"
                )
                json_ld = variants[variant_index]
            else:
                logger.warning("ProductGroup has no variants, using root data")

        original_url = url
        canonical_url = json_ld.get("url")
        url_was_canonicalized = False

        if canonical_url:
            canonical_url_normalized = canonical_url.rstrip("/")
            user_url_normalized = url.rstrip("/")

            if canonical_url_normalized != user_url_normalized:
                logger.debug("Canonical URL differs from provided URL:")
                logger.debug(f"  Provided:  {url}")
                logger.debug(f"  Canonical: {canonical_url}")
                url = canonical_url
                url_was_canonicalized = True
            else:
                logger.debug(f"URL matches canonical URL: {canonical_url}")
        else:
            logger.debug("No canonical URL found in JSON-LD, using provided URL")

        transformations = self.provider_config.transformations

        raw_name = json_ld.get("name", "")
        name = self._apply_field_transformation(raw_name, transformations.get("name"))

        brand_data = json_ld.get("brand", {})
        if isinstance(brand_data, dict):
            brand = brand_data.get("name", "")
        elif isinstance(brand_data, str):
            brand = brand_data
        else:
            brand = ""

        category_raw = json_ld.get("category", "")
        category = self._apply_field_transformation(category_raw, transformations.get("category"))
        if isinstance(category, str):
            category = [category] if category else []

        json_ld_config = self.provider_config.extraction.get("json_ld", {})
        field_mappings = json_ld_config.get("field_mappings", {})

        offers_path = field_mappings.get("offers", "offers")
        offers = FieldMapper.get_value(json_ld, offers_path, default={})
        if isinstance(offers, list) and offers:
            # Check database for locked offer_selection_strategy
            # This prevents price history corruption when config changes after first snapshot
            locked_strategy = None
            try:
                db = DatabaseManager(get_db_url(), read_only=True)
                tracked_page = db.get_tracked_page(url)
                if tracked_page and tracked_page.get("offer_selection_strategy"):
                    locked_strategy = tracked_page["offer_selection_strategy"]
                    config_strategy = json_ld_config.get("offer_selection_strategy", "first")

                    if locked_strategy != config_strategy:
                        logger.warning(
                            f"⚠ Using locked offer strategy '{locked_strategy}' for this product "
                            f"(config has '{config_strategy}' but strategy locked from first snapshot)"
                        )
                        logger.warning(
                            f"  To change strategy: Delete all snapshots for {url[:60]}... and re-track"
                        )
            except Exception as e:
                logger.debug(f"Could not check for locked offer strategy: {e}")

            # Use locked strategy if available, otherwise fall back to config (default: first)
            strategy = locked_strategy or json_ld_config.get("offer_selection_strategy", "first")
            offers = self._select_best_offer(offers, strategy)

            # Update json_ld with selected offer so field extraction works correctly
            # This handles nested paths like "object.offers" by updating the parent dict
            if "." in offers_path:
                # Nested path - update the parent object
                parts = offers_path.split(".")
                parent = json_ld
                for part in parts[:-1]:
                    parent = parent.get(part, {})
                if parent:
                    parent[parts[-1]] = offers
            else:
                # Direct path - update json_ld directly
                json_ld[offers_path] = offers

        price_paths = field_mappings.get("price", ["offers.price", "offers.lowPrice"])
        current_price_raw = FieldMapper.get_value(json_ld, price_paths)
        current_price = None
        if current_price_raw:
            try:
                current_price = float(current_price_raw)
            except (ValueError, TypeError):
                logger.warning(f"Failed to parse current price: {current_price_raw}")

        original_price_paths = field_mappings.get(
            "original_price", ["offers.highPrice", "offers.priceSpecification.price"]
        )
        original_price_raw = FieldMapper.get_value(json_ld, original_price_paths)
        original_price = None
        if original_price_raw:
            try:
                original_price = float(original_price_raw)
            except (ValueError, TypeError):
                logger.warning(f"Failed to parse original price: {original_price_raw}")

        has_promotion = False
        discount_percentage = None
        if original_price and current_price and original_price > current_price:
            has_promotion = True
            discount_percentage = ((original_price - current_price) / original_price) * 100
            logger.debug(
                f"Promotion detected: {original_price} → {current_price} "
                f"({discount_percentage:.1f}% off)"
            )

        promotion_starts_at = None
        promotion_ends_at = None
        if isinstance(offers, dict):
            price_valid_until = offers.get("priceValidUntil")
            valid_from = offers.get("validFrom")

            invalid_values = ("undefined", "null", "")
            if valid_from and valid_from not in invalid_values:
                try:
                    promotion_starts_at = datetime.fromisoformat(valid_from)
                except (ValueError, TypeError):
                    logger.debug(f"Could not parse validFrom: {valid_from}")
            if price_valid_until and price_valid_until not in invalid_values:
                try:
                    promotion_ends_at = datetime.fromisoformat(price_valid_until)
                except (ValueError, TypeError):
                    logger.debug(f"Could not parse priceValidUntil: {price_valid_until}")

            if promotion_starts_at or promotion_ends_at:
                has_promotion = True
                logger.debug(
                    f"Time-limited promotion: {promotion_starts_at} - {promotion_ends_at}"
                )

        currency_path = field_mappings.get("currency", "offers.priceCurrency")
        currency = FieldMapper.get_value(json_ld, currency_path, default="EUR")

        price_per_unit = None
        if isinstance(offers, dict):
            price_spec = offers.get("priceSpecification", {})
            if price_spec and transformations.get("price_per_unit"):
                price_per_unit = Transformations.parse_price_specification(price_spec, currency)

        availability = False
        if isinstance(offers, dict):
            availability_url = offers.get("availability", "")
            if availability_url:
                availability = Transformations.parse_schema_availability(availability_url)
            else:
                json_ld_config = self.provider_config.extraction.get("json_ld", {})
                use_default = json_ld_config.get("default_availability_when_missing", False)

                if use_default:
                    offer_count = offers.get("offerCount", 0)
                    has_offer_count = offer_count > 0

                    has_price = (
                        offers.get("lowPrice") is not None
                        or offers.get("price") is not None
                        or current_price is not None
                    )

                    availability = has_price or has_offer_count
                    logger.debug(
                        f"Using availability fallback: has_price={has_price}, "
                        f"offer_count={offer_count}, available={availability}"
                    )

        field_mappings = json_ld_config.get("field_mappings", {})
        if "image" in field_mappings:
            image = FieldMapper.get_value(json_ld, field_mappings["image"], default="")
            images = [image] if image else []
        else:
            image_data = json_ld.get("image", "")
            if isinstance(image_data, dict):
                image = image_data.get("url", "")
                images = [image] if image else []
            elif isinstance(image_data, list):
                processed_images = []
                for img in image_data:
                    if isinstance(img, dict):
                        url = img.get("url", "")
                        if url:
                            processed_images.append(url)
                    elif isinstance(img, str):
                        processed_images.append(img)
                image = processed_images[0] if processed_images else ""
                images = processed_images
            else:
                image = image_data if isinstance(image_data, str) else ""
                images = [image] if image else []

        if "weight_value" in field_mappings and "weight_unit" in field_mappings:
            weight_value = FieldMapper.get_value(
                json_ld, field_mappings["weight_value"], default=""
            )
            weight_unit = FieldMapper.get_value(json_ld, field_mappings["weight_unit"], default="")
            weight = (
                f"{weight_value} {weight_unit}" if weight_value and weight_unit else weight_value
            )
        else:
            weight_data = json_ld.get("weight", "")
            if isinstance(weight_data, dict):
                value = weight_data.get("value", "")
                unit = weight_data.get("unitText", "")
                weight = f"{value} {unit}" if value and unit else value if value else ""
            else:
                weight = weight_data if isinstance(weight_data, str) else ""

        sku = json_ld.get("sku", "")
        gtin = json_ld.get("gtin13") or json_ld.get("gtin", "")
        description = json_ld.get("description", "")

        detected_language = self.provider_config.language

        if not detected_language:
            detected_language = await self.extract_language(page)

        product_details = parse_product_details(
            name=name,
            weight=weight,
            volume=json_ld.get("volume", ""),
            language=detected_language,
            country=self.provider_config.country,
        )

        if detected_language:
            logger.debug(
                f"Using language '{detected_language}' for variant extraction "
                f"(provider override: {self.provider_config.language is not None})"
            )

        if url_was_canonicalized:
            json_ld["_canonicalization"] = {
                "original_url": original_url,
                "canonical_url": url,
                "was_canonicalized": True,
            }

        return BaseProduct(
            name=name,
            url=url,
            current_price=current_price,
            original_price=original_price,
            currency=currency,
            price_per_unit=price_per_unit,
            has_promotion=has_promotion,
            discount_percentage=discount_percentage,
            promotion_starts_at=promotion_starts_at,
            promotion_ends_at=promotion_ends_at,
            sku=sku,
            gtin=gtin,
            brand=brand,
            category=category if isinstance(category, list) else [category] if category else [],
            availability=availability,
            description=description,
            weight=weight,
            amount_value=product_details.get("amount_value"),
            amount_unit=product_details.get("amount_unit"),
            pack_quantity=product_details.get("pack_quantity", 1),
            variant_color=product_details.get("variant_color"),
            variant_flavor=product_details.get("variant_flavor"),
            variant_type=product_details.get("variant_type"),
            image=image,
            images=images,
            provider=self.name,
            extracted_at=now_in_configured_tz(),
            raw_data=json_ld,
        )

    async def _extract_from_selectors(
        self, html_content: str, url: str, page: Page
    ) -> BaseProduct | None:
        extractor = SelectorExtractor()

        field_selectors = extractor.parse_field_selectors(self.provider_config.extraction)

        if not field_selectors:
            logger.debug("No CSS/XPath selectors configured")
            return None

        logger.debug(f"Extracting product using selectors for {len(field_selectors)} fields")

        extracted_data = await extractor.extract_all_fields(page, field_selectors)

        is_marketplace_only_detected = extracted_data.get("is_marketplace_only", False)

        if not extracted_data:
            logger.debug("No data extracted via selectors")
            return None

        if not extracted_data.get("name") and not is_marketplace_only_detected:
            logger.debug("No name extracted and not marketplace-only")
            return None

        logger.debug(f"✓ Extracted {len(extracted_data)} fields via selectors")

        transformations = self.provider_config.transformations
        for field_name, transformation in transformations.items():
            if field_name in extracted_data:
                extracted_data[field_name] = self._apply_field_transformation(
                    extracted_data[field_name], transformation
                )

        current_price = None
        if "price" in extracted_data:
            try:
                price_str = str(extracted_data["price"]).replace(",", ".").strip()
                # Remove currency symbols
                for symbol in ["€", "$", "£", "¥"]:
                    price_str = price_str.replace(symbol, "").strip()
                current_price = float(price_str) if price_str else None
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse price '{extracted_data['price']}': {e}")

        original_price = None
        if "original_price" in extracted_data:
            try:
                price_str = str(extracted_data["original_price"]).replace(",", ".").strip()
                for symbol in ["€", "$", "£", "¥"]:
                    price_str = price_str.replace(symbol, "").strip()
                original_price = float(price_str) if price_str else None
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Failed to parse original_price '{extracted_data['original_price']}': {e}"
                )

        has_promotion = False
        discount_percentage = None
        if original_price and current_price and original_price > current_price:
            has_promotion = True
            discount_percentage = ((original_price - current_price) / original_price) * 100
            logger.debug(
                f"Promotion detected: {original_price} → {current_price} "
                f"({discount_percentage:.1f}% off)"
            )

        category = extracted_data.get("category", [])
        if isinstance(category, str):
            category = [category] if category else []

        image = extracted_data.get("image", "")
        images = extracted_data.get("images", [])
        if isinstance(image, str) and image:
            images = images if images else [image]
        elif isinstance(image, list):
            images = image
            image = image[0] if image else ""

        availability = extracted_data.get("availability", False)
        if isinstance(availability, bool):
            pass  # Already boolean
        elif isinstance(availability, str):
            # Convert string to boolean
            availability = availability.lower() in ("true", "yes", "available", "in stock")

        is_marketplace_only = extracted_data.get("is_marketplace_only", False)
        if isinstance(is_marketplace_only, bool):
            pass
        elif is_marketplace_only is not None:
            # check_exists returns True if element found, False otherwise
            is_marketplace_only = bool(is_marketplace_only)
        else:
            is_marketplace_only = False

        detected_language = self.provider_config.language
        if not detected_language:
            detected_language = await self.extract_language(page)

        product_details = parse_product_details(
            name=extracted_data.get("name", ""),
            weight=extracted_data.get("weight", ""),
            volume=extracted_data.get("volume", ""),
            language=detected_language,
            country=self.provider_config.country,
        )

        return BaseProduct(
            name=extracted_data.get("name", ""),
            url=url,
            current_price=current_price,
            original_price=original_price,
            currency=extracted_data.get("currency", "EUR"),
            price_per_unit=extracted_data.get("price_per_unit"),
            has_promotion=has_promotion,
            discount_percentage=discount_percentage,
            sku=extracted_data.get("sku", ""),
            gtin=extracted_data.get("gtin", ""),
            brand=extracted_data.get("brand", ""),
            category=category,
            availability=availability,
            is_marketplace_only=is_marketplace_only,
            description=extracted_data.get("description", ""),
            weight=extracted_data.get("weight", ""),
            amount_value=product_details.get("amount_value"),
            amount_unit=product_details.get("amount_unit"),
            pack_quantity=product_details.get("pack_quantity", 1),
            variant_color=product_details.get("variant_color"),
            variant_flavor=product_details.get("variant_flavor"),
            variant_type=product_details.get("variant_type"),
            image=image,
            images=images,
            provider=self.name,
            extracted_at=now_in_configured_tz(),
            raw_data=extracted_data,
        )

    @staticmethod
    def _select_best_offer(offers: list[dict[str, Any]], strategy: str = "first") -> dict[str, Any]:
        """Select best offer from array based on strategy.

        Examples:
            >>> offers = [
            ...     {"price": 509.99, "availability": "InStock"},
            ...     {"price": 495.99, "availability": "OutOfStock"},
            ...     {"price": 491.99, "availability": "InStock"},
            ... ]
            >>> _select_best_offer(offers, "cheapest")
            {"price": 491.99, "availability": "InStock"}
            >>> _select_best_offer(offers, "cheapest_available")
            {"price": 491.99, "availability": "InStock"}
        """
        if not offers:
            return {}

        if strategy == "first":
            return offers[0]

        elif strategy == "cheapest":
            # Find cheapest offer with valid price
            valid_offers = [o for o in offers if o.get("price") is not None]
            if not valid_offers:
                logger.debug("No offers with valid prices, falling back to first")
                return offers[0]

            try:
                cheapest = min(valid_offers, key=lambda o: float(o["price"]))
                logger.debug(
                    f"Selected cheapest offer: €{cheapest['price']} from {len(offers)} offers"
                )
                return cheapest
            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"Failed to select cheapest offer: {e}, using first")
                return offers[0]

        elif strategy == "cheapest_available":
            # Find cheapest in-stock offer
            in_stock_offers = [
                o
                for o in offers
                if "InStock" in str(o.get("availability", "")) and o.get("price") is not None
            ]

            if in_stock_offers:
                try:
                    cheapest_available = min(in_stock_offers, key=lambda o: float(o["price"]))
                    logger.debug(
                        f"Selected cheapest available offer: €{cheapest_available['price']} "
                        f"from {len(in_stock_offers)} in-stock offers"
                    )
                    return cheapest_available
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Failed to select cheapest available offer: {e}, using first")
                    return offers[0]

            logger.debug("No in-stock offers found, falling back to cheapest overall")
            # Fallback to cheapest regardless of availability
            return ConfigurableProvider._select_best_offer(offers, "cheapest")

        else:
            logger.warning(
                f"Unknown offer selection strategy '{strategy}', using 'first' as fallback"
            )
            return offers[0]

    @staticmethod
    def _apply_field_transformation(value: Any, transformation: Any) -> Any:
        if not transformation:
            return value

        return Transformations.apply_transformation(value, transformation)

    @staticmethod
    async def _is_white_page(html_content: str, page: Page) -> bool:
        """
        Detect if the page is likely blocked/empty.

        A "white page" is detected if 2 or more of these conditions are true:
        - Content length < 1000 bytes
        - Visible text content < 100 characters
        - No JSON-LD script tags found
        - Blocking keywords present ("Access Denied", "Blocked", etc.)
        """
        indicators = 0

        if len(html_content) < 1000:
            logger.debug("White page indicator: content length < 1000 bytes")
            indicators += 1

        try:
            soup = BeautifulSoup(html_content, "lxml")
            visible_text = soup.get_text(strip=True)
            if len(visible_text) < 100:
                logger.debug("White page indicator: visible text < 100 characters")
                indicators += 1
        except Exception as e:
            logger.debug(f"Could not extract visible text: {e}")

        if '<script type="application/ld+json">' not in html_content:
            logger.debug("White page indicator: no JSON-LD script tags")
            indicators += 1

        try:
            soup = BeautifulSoup(html_content, "lxml")
            for script_or_style in soup(["script", "style"]):
                script_or_style.decompose()
            visible_text = soup.get_text(separator=" ", strip=True).lower()

            blocking_keywords = [
                "access denied",
                "forbidden",
                "not authorized",
                "bot detection",
                "captcha",
                "please verify",
                "permission to access",
            ]

            for keyword in blocking_keywords:
                if keyword in visible_text:
                    logger.debug(
                        f"White page indicator: blocking keyword '{keyword}' found in visible text"
                    )
                    indicators += 1
                    break
        except Exception as e:
            logger.debug(f"Could not check blocking keywords: {e}")

        is_white = indicators >= 2
        if is_white:
            logger.debug(
                f"White page detected ({indicators}/4 indicators): likely blocked or empty"
            )
        return is_white
