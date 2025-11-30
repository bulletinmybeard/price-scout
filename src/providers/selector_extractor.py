import re
from typing import Any

from chalkbox.logging.bridge import get_logger
from playwright.async_api import Page

logger = get_logger(__name__)


class SelectorConfig:
    """Configuration for a single selector extraction rule."""

    def __init__(
        self,
        selector: str,
        selector_type: str = "css",
        attribute: str | None = None,
        check_exists: bool = False,
        check_not_disabled: bool = False,
        check_visible: bool = False,
        multiple: bool = False,
        wait_for: bool = False,
        wait_timeout: int = 5000,
        text_mode: str = "text_content",
        regex_extract: str | None = None,
        regex_replace: dict | None = None,
    ):
        self.selector = selector
        self.selector_type = selector_type.lower()
        self.attribute = attribute
        self.check_exists = check_exists
        self.check_not_disabled = check_not_disabled
        self.check_visible = check_visible
        self.multiple = multiple
        self.wait_for = wait_for
        self.wait_timeout = wait_timeout
        self.text_mode = text_mode.lower()
        self.regex_extract = regex_extract
        self.regex_replace = regex_replace

        if self.selector_type not in ("css", "xpath"):
            raise ValueError(
                f"Invalid selector_type: {self.selector_type}. Must be 'css' or 'xpath'"
            )

        if self.text_mode not in ("text_content", "inner_text"):
            raise ValueError(
                f"Invalid text_mode: {self.text_mode}. Must be 'text_content' or 'inner_text'"
            )

    def __repr__(self) -> str:
        """String representation for debugging."""
        parts = [f"type={self.selector_type}", f"selector='{self.selector}'"]
        if self.attribute:
            parts.append(f"attribute='{self.attribute}'")
        if self.check_exists:
            parts.append("check_exists=True")
        if self.check_not_disabled:
            parts.append("check_not_disabled=True")
        if self.check_visible:
            parts.append("check_visible=True")
        if self.multiple:
            parts.append("multiple=True")
        if self.wait_for:
            parts.append(f"wait_for=True, timeout={self.wait_timeout}ms")
        if self.text_mode != "text_content":
            parts.append(f"text_mode='{self.text_mode}'")
        if self.regex_extract:
            parts.append(f"regex_extract='{self.regex_extract}'")
        if self.regex_replace:
            parts.append(f"regex_replace={self.regex_replace}")
        return f"SelectorConfig({', '.join(parts)})"


class SelectorExtractor:
    """Extract data from web pages using CSS selectors and XPath expressions."""

    def __init__(self):
        pass

    async def extract_field(
        self,
        page: Page,
        field_name: str,
        selectors: list[SelectorConfig],
    ) -> Any:
        """Extract a field value using multiple selectors with fallback."""
        if not selectors:
            logger.warning(f"No selectors provided for field '{field_name}'")
            return None

        for _idx, selector_config in enumerate(selectors, 1):
            try:
                result = await self._extract_with_selector(page, selector_config)

                if result is not None:
                    return result

            except Exception as e:
                logger.debug(f"Selector extraction failed: {e}")
                continue

        return None

    async def _extract_with_selector(
        self,
        page: Page,
        config: SelectorConfig,
    ) -> Any:
        if config.wait_for:
            try:
                await self._wait_for_selector(page, config)
            except Exception:
                return None

        if config.multiple:
            elements = await self._find_elements(page, config)
            if not elements:
                return None
        else:
            element = await self._find_element(page, config)
            if element is None:
                return None
            elements = [element]

        results: list[Any] = []
        for element in elements:
            if config.check_exists:
                if config.check_visible:
                    is_visible = await element.is_visible()
                    if not is_visible:
                        results.append(False)
                        continue

                if config.check_not_disabled:
                    is_disabled = await element.get_attribute("disabled")
                    results.append(is_disabled is None)
                else:
                    results.append(True)
                continue

            if config.attribute:
                value = await element.get_attribute(config.attribute)
                if value:
                    results.append(value.strip())
            else:
                # Text content extraction (based on text_mode)
                if config.text_mode == "inner_text":
                    value = await element.inner_text()
                else:  # text_content (default)
                    value = await element.text_content()

                if value:
                    value = value.strip()
                    # Apply regex extraction if configured
                    value = self._apply_regex_processing(value, config)
                    if value:
                        results.append(value)

        if not results:
            return None

        if config.multiple:
            return results
        elif config.check_exists:
            # For boolean checks, return single value
            return results[0] if results else False
        else:
            # Return first non-empty value
            return results[0]

    @staticmethod
    async def _wait_for_selector(page: Page, config: SelectorConfig) -> None:
        if config.selector_type == "css":
            await page.wait_for_selector(config.selector, timeout=config.wait_timeout)
        elif config.selector_type == "xpath":
            await page.wait_for_selector(f"xpath={config.selector}", timeout=config.wait_timeout)
        else:
            raise ValueError(f"Unknown selector type: {config.selector_type}")

    @staticmethod
    def _apply_regex_processing(value: str, config: SelectorConfig) -> str:
        if config.regex_extract:
            try:
                match = re.search(config.regex_extract, value)
                if match:
                    # Return first group if exists, otherwise full match
                    value = match.group(1) if match.groups() else match.group(0)
                else:
                    return ""
            except re.error as e:
                logger.warning(f"Invalid regex extract pattern '{config.regex_extract}': {e}")
                return value

        if config.regex_replace:
            try:
                pattern = config.regex_replace.get("pattern", "")
                replacement = config.regex_replace.get("replacement", "")
                if pattern:
                    value = re.sub(pattern, replacement, value)
            except re.error as e:
                logger.warning(
                    f"Invalid regex replace pattern '{config.regex_replace.get('pattern')}': {e}"
                )

        return value

    @staticmethod
    async def _find_element(page: Page, config: SelectorConfig):
        if config.selector_type == "css":
            return await page.query_selector(config.selector)
        elif config.selector_type == "xpath":
            elements = await page.query_selector_all(f"xpath={config.selector}")
            return elements[0] if elements else None
        else:
            raise ValueError(f"Unknown selector type: {config.selector_type}")

    @staticmethod
    async def _find_elements(page: Page, config: SelectorConfig):
        if config.selector_type == "css":
            return await page.query_selector_all(config.selector)
        elif config.selector_type == "xpath":
            return await page.query_selector_all(f"xpath={config.selector}")
        else:
            raise ValueError(f"Unknown selector type: {config.selector_type}")

    async def extract_all_fields(
        self,
        page: Page,
        field_selectors: dict[str, list[SelectorConfig]],
    ) -> dict[str, Any]:
        results: dict[str, Any] = {}

        for field_name, selectors in field_selectors.items():
            value = await self.extract_field(page, field_name, selectors)
            if value is not None:
                results[field_name] = value

        return results

    @staticmethod
    def parse_selector_config(config_data: dict[str, Any] | str) -> SelectorConfig:
        if isinstance(config_data, str):
            # Simple string = CSS selector extracting text
            return SelectorConfig(selector=config_data, selector_type="css")

        selector = config_data.get("selector")
        if not selector:
            raise ValueError("Selector config must have 'selector' field")

        return SelectorConfig(
            selector=selector,
            selector_type=config_data.get("type", "css"),
            attribute=config_data.get("attribute"),
            check_exists=config_data.get("check_exists", False),
            check_not_disabled=config_data.get("check_not_disabled", False),
            check_visible=config_data.get("check_visible", False),
            multiple=config_data.get("multiple", False),
            wait_for=config_data.get("wait_for", False),
            wait_timeout=config_data.get("wait_timeout", 5000),
            text_mode=config_data.get("text_mode", "text_content"),
            regex_extract=config_data.get("regex_extract"),
            regex_replace=config_data.get("regex_replace"),
        )

    @staticmethod
    def parse_field_selectors(
        extraction_config: dict[str, Any],
    ) -> dict[str, list[SelectorConfig]]:
        """Parse extraction configuration from provider YAML.

        Example YAML:
            extraction:
              css_selectors:
                name:
                  - "h1.product-title"
                  - selector: "//h1"
                    type: "xpath"
                price:
                  - selector: ".price-current"
                    type: "css"
                image:
                  - selector: "img.product-image"
                    attribute: "src"
        """
        css_config = extraction_config.get("css_selectors", {})
        field_selectors: dict[str, list[SelectorConfig]] = {}

        for field_name, selector_list in css_config.items():
            if not isinstance(selector_list, list):
                selector_list = [selector_list]

            configs = []
            for selector_data in selector_list:
                try:
                    config = SelectorExtractor.parse_selector_config(selector_data)
                    configs.append(config)
                except Exception as e:
                    logger.warning(
                        f"Failed to parse selector for field '{field_name}': {e}. "
                        f"Selector data: {selector_data}"
                    )
                    continue

            if configs:
                field_selectors[field_name] = configs

        logger.debug(f"Parsed selectors for {len(field_selectors)} fields")
        return field_selectors


def create_extractor() -> SelectorExtractor:
    return SelectorExtractor()
