import asyncio
from typing import Any

from bs4 import BeautifulSoup
from chalkbox.logging.bridge import get_logger
from playwright.async_api import Page

from src.config.models import ProviderConfig
from src.providers.base_product import BaseProduct
from src.providers.field_mapper import FieldMapper
from src.providers.transformations import Transformations
from src.scrapers.async_base_provider import AsyncBaseProvider
from src.utils.datetime_utils import now_in_configured_tz

logger = get_logger(__name__)


class ConfigurableProvider(AsyncBaseProvider):
    """Generic provider that loads configuration from Pydantic ProviderConfig model."""

    def __init__(self, config: ProviderConfig, headless: bool = True):
        """Initialize provider with Pydantic ProviderConfig model."""
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

                product = await self._extract_from_json_ld(html_content, url, page)
                if product:
                    product.extraction_method = "json-ld"
                    if attempt > 0:
                        logger.info(
                            f"Successfully extracted product after {attempt + 1} attempts: {url}"
                        )
                    await page.close()
                    return product

                if attempt < max_retries:
                    logger.debug(f"Retry {attempt + 1}/{max_retries} for {url} (extraction failed)")
                    await self._save_screenshot(
                        page, f"{self.name}_extraction_failed", attempt=attempt
                    )
                    await page.close()
                    delay = retry_delay * (2**attempt)
                    await asyncio.sleep(delay)
                    continue

                logger.debug(f"JSON-LD extraction failed after {max_retries + 1} attempts: {url}")
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
        """Extract product from JSON-LD structured data."""
        json_ld_config = self.provider_config.extraction.get("json_ld", {})

        use_pyld = json_ld_config.get("use_pyld", False)
        if use_pyld:
            logger.debug("Using PyLD library for JSON-LD extraction")
            from src.providers.jsonld_extractor import create_extractor

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
            offers = offers[0]

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

        from src.utils.product_parser import parse_product_details

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

    @staticmethod
    def _apply_field_transformation(value: Any, transformation: Any) -> Any:
        """Apply transformation to a field value."""
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
