from abc import ABC, abstractmethod
import asyncio
import json
from pathlib import Path
from random import SystemRandom
from typing import Any, TypedDict
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup
from chalkbox.logging.bridge import get_logger
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from src.config.config_loader import load_typed_config
from src.config.types import PlaywrightWaitUntil
from src.utils.datetime_utils import now_in_configured_tz

_rng = SystemRandom()

logger = get_logger(__name__)


class UserAgentInfo(TypedDict):
    """User agent parsing results."""

    platform: str
    vendor: str
    browser: str
    has_chrome_object: bool


class AsyncBaseProvider(ABC):
    """Universal async base provider for web scraping retailer websites."""

    def __init__(self, headless: bool = True, config: Any | None = None):
        if config is None:
            self.config = load_typed_config()
        else:
            self.config = config

        self.headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._cached_user_agent: str | None = None  # Cache UA for session consistency

    def _clean_url(self, url: str) -> str:
        if not self.config.scraping.strip_query_params:
            return url

        parsed = urlparse(url)
        cleaned = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                "",  # params
                "",  # query - STRIPPED
                "",  # fragment - STRIPPED
            )
        )

        if cleaned != url:
            logger.debug(f"Cleaned URL for consistent tracking: {url} → {cleaned}")

        return cleaned

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def country(self) -> str:
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        pass

    @abstractmethod
    async def search_product(self, query: str) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    async def get_product_details(self, url: str) -> Any:
        pass

    async def init_browser(self) -> None:
        if self._playwright is None:
            self._playwright = await async_playwright().start()

        if self._browser is None:
            browser_type = self.config.scraping.browser_type.value
            logger.debug(f"Launching {browser_type} browser (headless={self.headless})")

            launch_args = []
            if self.headless:
                launch_args = [
                    # Hide automation signals
                    "--disable-blink-features=AutomationControlled",
                    # Performance and stability
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    # Hide headless indicators
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                    # Mimic real browser behavior
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                    # Additional stealth
                    "--disable-infobars",
                    "--window-position=0,0",
                    "--ignore-certificate-errors",
                    "--ignore-certificate-errors-spki-list",
                    "--disable-extensions",
                    # GPU acceleration (helps with fingerprinting)
                    "--enable-features=NetworkService,NetworkServiceInProcess",
                    "--disable-features=VizDisplayCompositor",
                ]

            if browser_type == "firefox":
                self._browser = await self._playwright.firefox.launch(
                    headless=self.headless, args=launch_args if self.headless else None
                )
            elif browser_type == "webkit":
                self._browser = await self._playwright.webkit.launch(
                    headless=self.headless, args=launch_args if self.headless else None
                )
            else:  # chromium (default)
                self._browser = await self._playwright.chromium.launch(
                    headless=self.headless, args=launch_args if self.headless else None
                )

        if self._context is None:
            context_options: dict[str, Any] = {
                "viewport": {
                    "width": self.config.scraping.viewport_width,
                    "height": self.config.scraping.viewport_height,
                },
                "locale": self.config.scraping.locale,
                "timezone_id": self.config.scraping.timezone,
                "user_agent": self._cached_user_agent or self._get_user_agent(),
                "extra_http_headers": {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Accept-Encoding": "gzip, deflate, br",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Cache-Control": "max-age=0",
                },
            }

            self._context = await self._browser.new_context(**context_options)

            # Cache the UA for this session
            if not self._cached_user_agent:
                self._cached_user_agent = context_options["user_agent"]

            if self.headless:
                # Parse UA to ensure consistency
                ua_info = self._parse_user_agent_info(self._cached_user_agent)

                # Build Chrome object script (only for Chrome/Chromium)
                chrome_object_script = ""
                if ua_info["has_chrome_object"]:
                    chrome_object_script = """
                    // Mock Chrome object (only for Chrome/Chromium UAs)
                    if (!window.chrome) {
                        window.chrome = {
                            runtime: {},
                            loadTimes: function() {},
                            csi: function() {},
                            app: {}
                        };
                    }
                    """

                stealth_script = f"""
                    // ==================================================================
                    // DYNAMIC ANTI-DETECTION SCRIPT
                    // Automatically matches User-Agent: {self._cached_user_agent[:50]}...
                    // ==================================================================

                    // Hide webdriver property
                    Object.defineProperty(navigator, 'webdriver', {{
                        get: () => undefined
                    }});

                    // Mock Chrome object (browser-specific)
                    {chrome_object_script}

                    // Mock plugins (browser-specific)
                    {self._get_plugins_script(ua_info["browser"])}

                    // Mock languages
                    Object.defineProperty(navigator, 'languages', {{
                        get: () => ['nl-NL', 'nl', 'en-US', 'en']
                    }});

                    // Override navigator.permissions
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({{ state: Notification.permission }}) :
                            originalQuery(parameters)
                    );

                    // Mock hardware concurrency
                    Object.defineProperty(navigator, 'hardwareConcurrency', {{
                        get: () => 8
                    }});

                    // Mock device memory
                    Object.defineProperty(navigator, 'deviceMemory', {{
                        get: () => 8
                    }});

                    // Mock platform (MUST match UA)
                    Object.defineProperty(navigator, 'platform', {{
                        get: () => '{ua_info["platform"]}'
                    }});

                    // Mock vendor (MUST match UA)
                    Object.defineProperty(navigator, 'vendor', {{
                        get: () => '{ua_info["vendor"]}'
                    }});

                    // Mock maxTouchPoints
                    Object.defineProperty(navigator, 'maxTouchPoints', {{
                        get: () => 0
                    }});

                    // 11. Override the Date object to use consistent timezone
                    const originalDate = Date;
                    const timezoneOffset = -60; // UTC+1 (Netherlands/Amsterdam)
                    Date = class extends originalDate {{
                        getTimezoneOffset() {{
                            return timezoneOffset;
                        }}
                    }};
                    Date.prototype = originalDate.prototype;

                    // Mock screen properties for realistic resolution
                    Object.defineProperty(screen, 'width', {{
                        get: () => 1920
                    }});
                    Object.defineProperty(screen, 'height', {{
                        get: () => 1080
                    }});
                    Object.defineProperty(screen, 'availWidth', {{
                        get: () => 1920
                    }});
                    Object.defineProperty(screen, 'availHeight', {{
                        get: () => 1040
                    }});
                    Object.defineProperty(screen, 'colorDepth', {{
                        get: () => 24
                    }});
                    Object.defineProperty(screen, 'pixelDepth', {{
                        get: () => 24
                    }});

                    // Mock WebGL vendor and renderer (platform-specific)
                    {self._get_webgl_script(ua_info["platform"])}

                    // Mock connection
                    Object.defineProperty(navigator, 'connection', {{
                        get: () => ({{
                            effectiveType: '4g',
                            rtt: 100,
                            downlink: 10,
                            saveData: false
                        }})
                    }});

                    // Add missing properties that real browsers have
                    window.outerWidth = 1920;
                    window.outerHeight = 1080;
                    window.screenX = 0;
                    window.screenY = 0;

                    // Mock battery API
                    navigator.getBattery = () => Promise.resolve({{
                        charging: true,
                        chargingTime: 0,
                        dischargingTime: Infinity,
                        level: 1
                    }});

                    // Override toString to hide proxy nature
                    const originalToString = Function.prototype.toString;
                    Function.prototype.toString = function() {{
                        if (this === navigator.permissions.query) {{
                            return 'function query() {{ [native code] }}';
                        }}
                        return originalToString.call(this);
                    }};

                    // Mock notification permission
                    Object.defineProperty(Notification, 'permission', {{
                        get: () => 'default'
                    }});
                """

                await self._context.add_init_script(stealth_script)
                logger.debug(
                    f"Dynamic stealth script injected (platform={ua_info['platform']}, "
                    f"vendor={ua_info['vendor']}, browser={ua_info['browser']})"
                )

            logger.debug("Browser context created")

    async def close_browser(self):
        if self._context:
            await self._context.close()
            self._context = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        logger.debug("Browser closed and resources cleaned up")

    async def create_page(self) -> Page:
        if self._context is None:
            await self.init_browser()

        if self._context is None:
            raise RuntimeError("Failed to initialize browser context")

        page = await self._context.new_page()
        return page

    async def fetch_page(
        self,
        url: str,
        wait_for_selector: str | None = None,
        timeout: int = 60000,
        wait_until: PlaywrightWaitUntil = "domcontentloaded",
        warm_up: bool = True,
    ) -> Page | None:
        """Fetch a web page using Playwright."""
        try:
            url = self._clean_url(url)

            page = await self.create_page()

            # WARM-UP NAVIGATION: Visit homepage first (only in headless mode!)
            # This establishes cookies, sessions, and makes the bot look like a real user
            logger.debug(
                f"Warm-up check: headless={self.headless}, warm_up={warm_up}, base_url={self.base_url}"
            )
            if self.headless and warm_up and self.base_url:
                try:
                    logger.debug(f"Warm-up: visiting homepage {self.base_url}")
                    await page.goto(self.base_url, wait_until="domcontentloaded", timeout=10000)

                    # Simulate brief homepage interaction
                    await asyncio.sleep(_rng.uniform(0.5, 1.5))

                    # Random scroll on homepage
                    await page.evaluate(f"window.scrollBy(0, {_rng.randint(100, 300)})")
                    await asyncio.sleep(_rng.uniform(0.3, 0.7))

                    logger.debug("Warm-up navigation complete")
                except Exception as e:
                    logger.warning(f"Warm-up navigation failed (non-critical): {e}")

            # Human-like pre-navigation delay (200-800ms)
            if self.headless:
                await asyncio.sleep(_rng.uniform(0.2, 0.8))

            # Navigate to the actual target URL
            # Set referer to make it look like we came from the homepage
            logger.debug(f"Navigating to: {url}")
            if self.headless and self.base_url:
                # Add referer header to look like we came from homepage
                await page.set_extra_http_headers({"Referer": self.base_url})

            await page.goto(url, wait_until=wait_until, timeout=timeout)

            # Simulate human-like mouse movements (only in headless mode for stealth)
            if self.headless:
                # Random small mouse movement to trigger event listeners
                await page.mouse.move(_rng.randint(100, 300), _rng.randint(100, 300))
                await asyncio.sleep(_rng.uniform(0.1, 0.3))

                # Scroll a bit (human behavior)
                await page.evaluate("window.scrollBy(0, 100)")
                await asyncio.sleep(_rng.uniform(0.2, 0.5))

            # Wait for specific selector if provided
            if wait_for_selector:
                logger.debug(f"Waiting for selector: {wait_for_selector}")
                await page.wait_for_selector(wait_for_selector, timeout=5000)

            # Rate limiting delay with slight randomization
            delay = self.config.scraping.request_delay_seconds
            if self.headless:
                # Add 0-50% random variation to delay
                delay = delay * _rng.uniform(1.0, 1.5)
            await asyncio.sleep(delay)

            return page

        except Exception as e:
            logger.error(f"Failed to fetch page {url}: {e}")
            if self.config.scraping.save_screenshots:
                await self._save_screenshot(page, f"error_{url.split('/')[-1]}")
            return None

    @staticmethod
    async def get_page_content(page: Page) -> str:
        return await page.content()

    async def extract_language(self, page: Page) -> str | None:
        """Extract page language from multiple sources.

        Tries to detect the page language in priority order:
        1. HTML lang attribute (<html lang="nl-NL">)
        2. Content-Language meta tag
        3. JSON-LD inLanguage field
        """
        try:
            # HTML lang attribute
            html_lang = await page.locator("html").get_attribute("lang")
            if html_lang:
                # Extract language code from formats like "nl-NL", "de", "en-US"
                lang_code = html_lang.split("-")[0].lower()
                if lang_code:
                    logger.debug(f"Detected language from HTML lang attribute: {lang_code}")
                    return lang_code

            # Content-Language meta tag
            content_lang = await page.locator('meta[http-equiv="Content-Language"]').get_attribute(
                "content"
            )
            if content_lang:
                lang_code = content_lang.split("-")[0].lower()
                if lang_code:
                    logger.debug(f"Detected language from Content-Language meta: {lang_code}")
                    return lang_code

            # JSON-LD inLanguage field
            html_content = await self.get_page_content(page)
            json_ld = self.extract_json_ld(html_content)
            if json_ld and isinstance(json_ld, dict):
                in_language = json_ld.get("inLanguage")
                if in_language:
                    if isinstance(in_language, str):
                        lang_code = in_language.split("-")[0].lower()
                        if lang_code:
                            logger.debug(f"Detected language from JSON-LD inLanguage: {lang_code}")
                            return lang_code
                    elif isinstance(in_language, dict):
                        lang_code = in_language.get("alternateName") or in_language.get("name", "")
                        if lang_code:
                            lang_code = lang_code.split("-")[0].lower()
                            logger.debug(
                                f"Detected language from JSON-LD inLanguage object: {lang_code}"
                            )
                            return lang_code

            logger.debug("Could not detect language from any source")
            return None

        except Exception as e:
            logger.debug(f"Language detection failed: {e}")
            return None

    @staticmethod
    def parse_html(html_content: str) -> BeautifulSoup:
        return BeautifulSoup(html_content, "lxml")

    @staticmethod
    def extract_json_ld(html: str, wrapper_config: dict | None = None) -> dict | None:
        """Extract JSON-LD structured data from HTML."""
        try:
            soup = BeautifulSoup(html, "lxml")

            json_ld_scripts = soup.find_all("script", {"type": "application/ld+json"})

            logger.debug(f"Found {len(json_ld_scripts)} JSON-LD script tags")

            for idx, script in enumerate(json_ld_scripts):
                if not script.string:
                    logger.debug(f"Script tag {idx} has no content")
                    continue

                try:
                    data = json.loads(script.string)
                    logger.debug(
                        f"Script tag {idx} parsed successfully, @type: {data.get('@type') if isinstance(data, dict) else 'array'}"
                    )

                    if wrapper_config and isinstance(data, dict):
                        wrapper_type = wrapper_config.get("type")
                        if data.get("@type") == wrapper_type:
                            product_path = wrapper_config.get("product_path", "object")
                            product_obj = data.get(product_path, {})

                            if isinstance(product_obj, dict) and product_obj.get("@type") in (
                                "Product",
                                "ProductGroup",
                            ):
                                logger.debug(f"Found Product unwrapped from {wrapper_type} wrapper")
                                return product_obj

                    if isinstance(data, list):
                        for item_idx, item in enumerate(data):
                            item_type = item.get("@type") if isinstance(item, dict) else None
                            if isinstance(item, dict) and item_type in ("Product", "ProductGroup"):
                                logger.debug(
                                    f"Found {item_type} JSON-LD schema in array item {item_idx}"
                                )
                                return item
                    elif isinstance(data, dict) and data.get("@type") in (
                        "Product",
                        "ProductGroup",
                    ):
                        data_type = data.get("@type")
                        logger.debug(f"Found {data_type} JSON-LD schema")
                        return data

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON-LD in script tag {idx}: {e}")
                    logger.debug(
                        f"Problematic JSON content (first 200 chars): {script.string[:200]}"
                    )
                    continue

            logger.warning("No Product JSON-LD found in any script tags")
            return None

        except Exception as e:
            logger.error(f"Error extracting JSON-LD: {e}")
            return None

    @staticmethod
    def normalize_json_ld_product(data: dict) -> dict:
        """Convert JSON-LD Product schema to normalized product dict."""
        product = {
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "image": data.get("image", ""),
            "sku": data.get("sku", ""),
            "gtin": data.get("gtin13") or data.get("gtin", ""),
        }

        category_raw = data.get("category", "")
        if isinstance(category_raw, str) and category_raw:
            product["category"] = [cat.strip() for cat in category_raw.split(",")]
        elif isinstance(category_raw, list):
            product["category"] = category_raw
        else:
            product["category"] = []

        product["url"] = data.get("url", "")

        brand = data.get("brand", {})
        if isinstance(brand, dict):
            product["brand"] = brand.get("name", "")
        elif isinstance(brand, str):
            product["brand"] = brand
        else:
            product["brand"] = ""

        offers = data.get("offers", {})
        if isinstance(offers, dict):
            product["current_price"] = offers.get("lowPrice") or offers.get("price")
            product["original_price"] = offers.get("highPrice")
            product["currency"] = offers.get("priceCurrency", "")

            if product.get("original_price") and product.get("current_price"):
                if float(product["original_price"]) > float(product["current_price"]):
                    product["has_promotion"] = True
                    orig = float(product["original_price"])
                    curr = float(product["current_price"])
                    product["discount_percentage"] = ((orig - curr) / orig) * 100
                else:
                    product["has_promotion"] = False
            else:
                product["has_promotion"] = False

        elif isinstance(offers, list) and offers:
            first_offer = offers[0]
            product["current_price"] = first_offer.get("lowPrice") or first_offer.get("price")
            product["original_price"] = first_offer.get("highPrice")
            product["currency"] = first_offer.get("priceCurrency", "")
            product["has_promotion"] = False

        product["availability"] = bool(offers)

        logger.debug(f"Normalized JSON-LD product: {product.get('name', 'Unknown')}")
        return product

    async def _save_screenshot(self, page: Page, filename: str, attempt: int = 0):
        """Save a JPEG screenshot for debugging (only if save_screenshots enabled)."""
        if not self.config.scraping.save_screenshots:
            return

        try:
            # Create screenshots directory if it doesn't exist
            screenshots_dir = Path(self.config.scraping.screenshots_dir)
            screenshots_dir.mkdir(parents=True, exist_ok=True)

            # Generate timestamped filename
            timestamp = now_in_configured_tz().strftime("%Y-%m-%d_%H-%M-%S")

            # Sanitize filename by removing special characters
            safe_filename = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in filename)

            if attempt > 0:
                jpeg_filename = f"error_{timestamp}_{safe_filename}_attempt_{attempt}.jpg"
            else:
                jpeg_filename = f"error_{timestamp}_{safe_filename}.jpg"

            filepath = screenshots_dir / jpeg_filename

            # Capture screenshot as JPEG with 80% quality
            await page.screenshot(path=str(filepath), type="jpeg", quality=80)
            logger.info(f"Screenshot saved: {filepath}")

        except Exception as e:
            # Don't fail the main error flow if screenshot fails
            logger.debug(f"Failed to save screenshot: {e}")

    def _get_user_agent(self) -> str:
        """Generate user agent based on configuration."""
        # Check if rotation is enabled
        if not self.config.scraping.user_agent_rotation:
            return (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )

        try:
            from fake_useragent import UserAgent

            ua = UserAgent()
            browser_type = self.config.scraping.browser_type.value

            if browser_type == "firefox":
                return ua.firefox
            elif browser_type == "webkit":
                return ua.safari
            else:  # chromium
                return ua.chrome

        except Exception as e:
            logger.warning(f"Failed to generate dynamic user-agent: {e}")
            logger.warning("Falling back to static user-agent")
            return (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )

    @staticmethod
    def _parse_user_agent_info(ua: str) -> UserAgentInfo:
        """Extract platform, vendor, and browser info from UA string."""
        ua_lower = ua.lower()

        if "windows" in ua_lower or "win64" in ua_lower or "win32" in ua_lower:
            platform = "Win32"
        elif "mac" in ua_lower or "darwin" in ua_lower or "macintosh" in ua_lower:
            platform = "MacIntel"
        elif "linux" in ua_lower:
            platform = "Linux armv7l" if "android" in ua_lower else "Linux x86_64"
        else:
            platform = "Win32"

        if "chrome" in ua_lower or "chromium" in ua_lower:
            vendor = "Google Inc."
        elif "safari" in ua_lower and "chrome" not in ua_lower:
            vendor = "Apple Computer, Inc."
        else:  # Firefox
            vendor = ""

        if "firefox" in ua_lower:
            browser = "firefox"
            has_chrome_object = False
        elif "safari" in ua_lower and "chrome" not in ua_lower:
            browser = "webkit"
            has_chrome_object = False
        else:  # Chrome/Chromium
            browser = "chromium"
            has_chrome_object = True

        return {
            "platform": platform,
            "vendor": vendor,
            "browser": browser,
            "has_chrome_object": has_chrome_object,
        }

    def _get_plugins_script(self, browser: str) -> str:
        """Generate browser-specific plugins array for anti-fingerprinting."""
        if browser == "chromium":
            return """
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {
                    0: {type: "application/pdf", suffixes: "pdf", description: "Portable Document Format"},
                    name: "Chrome PDF Plugin",
                    filename: "internal-pdf-viewer",
                    description: "Portable Document Format",
                    length: 1
                },
                {
                    0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
                    name: "Chrome PDF Viewer",
                    filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                    description: "Portable Document Format",
                    length: 1
                }
            ]
        });
        """
        elif browser == "firefox":
            return """
        Object.defineProperty(navigator, 'plugins', {
            get: () => []  // Firefox has empty plugins array by default
        });
        """
        else:  # webkit/safari
            return """
        Object.defineProperty(navigator, 'plugins', {
            get: () => []  // Safari has empty plugins array
        });
        """

    def _get_webgl_script(self, platform: str) -> str:
        """Generate platform-specific WebGL vendor/renderer for anti-fingerprinting."""
        if "Win" in platform:
            # Windows
            return """
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return 'Intel Inc.';
            }
            if (parameter === 37446) {
                return 'Intel(R) UHD Graphics 630';
            }
            return getParameter.call(this, parameter);
        };
        """
        elif "Mac" in platform:
            # macOS
            return """
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return 'Intel Inc.';
            }
            if (parameter === 37446) {
                return 'Intel Iris OpenGL Engine';
            }
            return getParameter.call(this, parameter);
        };
        """
        else:  # Linux
            return """
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) {
                return 'Intel Open Source Technology Center';
            }
            if (parameter === 37446) {
                return 'Mesa DRI Intel(R) UHD Graphics 630 (CFL GT2)';
            }
            return getParameter.call(this, parameter);
        };
        """

    async def __aenter__(self):
        await self.init_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_browser()

    def __repr__(self):
        return f"<{self.__class__.__name__}(name='{self.name}', country='{self.country}')>"
