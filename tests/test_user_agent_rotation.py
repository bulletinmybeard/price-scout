"""Tests for user-agent rotation functionality."""

from typing import Any
from unittest.mock import MagicMock, patch

from src.providers.base_product import BaseProduct
from src.scrapers.async_base_provider import AsyncBaseProvider


class ConcreteAsyncProvider(AsyncBaseProvider):
    """Concrete test implementation of AsyncBaseProvider."""

    def __init__(self, config: Any):
        """Initialize with mocked config."""
        # Mock the config attribute that AsyncBaseProvider expects
        self.config = config
        self._cached_user_agent: str | None = None

    @property
    def name(self) -> str:
        return "test_provider"

    @property
    def country(self) -> str:
        return "NL"

    @property
    def base_url(self) -> str:
        return "https://test.example.com"

    async def search_product(self, query: str) -> list[dict[str, Any]]:
        """Not implemented for tests."""
        raise NotImplementedError()

    async def get_product_details(self, url: str) -> BaseProduct | None:
        """Not implemented for tests."""
        raise NotImplementedError()


class TestUserAgentRotation:
    """Test dynamic user-agent generation."""

    def test_static_ua_when_rotation_disabled(self):
        """Verify static UA when user_agent_rotation: false."""
        config = MagicMock()
        config.scraping.user_agent_rotation = False

        provider = ConcreteAsyncProvider(config=config)
        ua = provider._get_user_agent()

        assert "Chrome/131.0.0.0" in ua
        assert "Windows NT 10.0" in ua

    def test_dynamic_ua_firefox_when_rotation_enabled(self):
        """Verify Firefox UA when browser_type=firefox."""
        config = MagicMock()
        config.scraping.user_agent_rotation = True
        config.scraping.browser_type.value = "firefox"

        provider = ConcreteAsyncProvider(config=config)
        ua = provider._get_user_agent()

        assert "Firefox" in ua
        assert "Gecko" in ua

    def test_dynamic_ua_chrome_when_rotation_enabled(self):
        """Verify Chrome UA when browser_type=chromium."""
        config = MagicMock()
        config.scraping.user_agent_rotation = True
        config.scraping.browser_type.value = "chromium"

        provider = ConcreteAsyncProvider(config=config)
        ua = provider._get_user_agent()

        assert ("Chrome" in ua or "CriOS" in ua)
        assert "Safari" in ua

    def test_dynamic_ua_safari_when_rotation_enabled(self):
        """Verify Safari UA when browser_type=webkit."""
        config = MagicMock()
        config.scraping.user_agent_rotation = True
        config.scraping.browser_type.value = "webkit"

        provider = ConcreteAsyncProvider(config=config)
        ua = provider._get_user_agent()

        assert "Safari" in ua
        # Safari UA shouldn't have "Chrome" in it
        assert "Chrome" not in ua

    def test_ua_parsing_windows_chrome(self):
        """Verify UA parsing for Windows Chrome."""
        config = MagicMock()
        provider = ConcreteAsyncProvider(config=config)

        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        info = provider._parse_user_agent_info(ua)

        assert info["platform"] == "Win32"
        assert info["vendor"] == "Google Inc."
        assert info["browser"] == "chromium"
        assert info["has_chrome_object"] is True

    def test_ua_parsing_firefox(self):
        """Verify UA parsing for Firefox."""
        config = MagicMock()
        provider = ConcreteAsyncProvider(config=config)

        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0"
        info = provider._parse_user_agent_info(ua)

        assert info["platform"] == "Win32"
        assert info["vendor"] == ""  # Firefox has empty vendor
        assert info["browser"] == "firefox"
        assert info["has_chrome_object"] is False

    def test_ua_parsing_mac_safari(self):
        """Verify UA parsing for Mac Safari."""
        config = MagicMock()
        provider = ConcreteAsyncProvider(config=config)

        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        info = provider._parse_user_agent_info(ua)

        assert info["platform"] == "MacIntel"
        assert info["vendor"] == "Apple Computer, Inc."
        assert info["browser"] == "webkit"
        assert info["has_chrome_object"] is False

    def test_ua_parsing_linux_chrome(self):
        """Verify UA parsing for Linux Chrome."""
        config = MagicMock()
        provider = ConcreteAsyncProvider(config=config)

        ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        info = provider._parse_user_agent_info(ua)

        assert info["platform"] == "Linux x86_64"
        assert info["vendor"] == "Google Inc."
        assert info["browser"] == "chromium"
        assert info["has_chrome_object"] is True

    def test_ua_parsing_android(self):
        """Verify UA parsing for Android."""
        config = MagicMock()
        provider = ConcreteAsyncProvider(config=config)

        ua = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Mobile Safari/537.36"
        info = provider._parse_user_agent_info(ua)

        assert info["platform"] == "Linux armv7l"
        assert info["vendor"] == "Google Inc."
        assert info["browser"] == "chromium"
        assert info["has_chrome_object"] is True

    def test_fallback_on_library_error(self):
        """Verify fallback to static UA on library errors."""
        config = MagicMock()
        config.scraping.user_agent_rotation = True
        config.scraping.browser_type.value = "firefox"

        provider = ConcreteAsyncProvider(config=config)

        with patch("fake_useragent.UserAgent", side_effect=Exception("Library error")):
            ua = provider._get_user_agent()

            # Should fallback to static UA
            assert "Chrome/131.0.0.0" in ua

    def test_plugins_script_chromium(self):
        """Verify Chrome plugins are generated for Chromium."""
        config = MagicMock()
        provider = ConcreteAsyncProvider(config=config)

        script = provider._get_plugins_script("chromium")

        assert "Chrome PDF Plugin" in script
        assert "Chrome PDF Viewer" in script

    def test_plugins_script_firefox(self):
        """Verify empty plugins array for Firefox."""
        config = MagicMock()
        provider = ConcreteAsyncProvider(config=config)

        script = provider._get_plugins_script("firefox")

        assert "[]" in script  # Empty array
        assert "Firefox has empty plugins array" in script

    def test_plugins_script_webkit(self):
        """Verify empty plugins array for Safari."""
        config = MagicMock()
        provider = ConcreteAsyncProvider(config=config)

        script = provider._get_plugins_script("webkit")

        assert "[]" in script  # Empty array
        assert "Safari has empty plugins array" in script

    def test_webgl_script_windows(self):
        """Verify Windows WebGL vendor/renderer."""
        config = MagicMock()
        provider = ConcreteAsyncProvider(config=config)

        script = provider._get_webgl_script("Win32")

        assert "Intel Inc." in script
        assert "Intel(R) UHD Graphics 630" in script

    def test_webgl_script_mac(self):
        """Verify Mac WebGL vendor/renderer."""
        config = MagicMock()
        provider = ConcreteAsyncProvider(config=config)

        script = provider._get_webgl_script("MacIntel")

        assert "Intel Inc." in script
        assert "Intel Iris OpenGL Engine" in script

    def test_webgl_script_linux(self):
        """Verify Linux WebGL vendor/renderer."""
        config = MagicMock()
        provider = ConcreteAsyncProvider(config=config)

        script = provider._get_webgl_script("Linux x86_64")

        assert "Intel Open Source Technology Center" in script
        assert "Mesa DRI Intel(R) UHD Graphics 630" in script


class TestUserAgentConsistency:
    """Test UA consistency across session."""

    def test_ua_cached_for_session(self):
        """Verify UA caching mechanism works correctly."""
        config = MagicMock()
        config.scraping.user_agent_rotation = True
        config.scraping.browser_type.value = "firefox"

        provider = ConcreteAsyncProvider(config=config)

        # Verify cache starts as None
        assert provider._cached_user_agent is None

        # Generate a UA
        ua1 = provider._get_user_agent()
        assert "Firefox" in ua1

        # Manually cache it (simulating what init_browser does)
        provider._cached_user_agent = ua1

        # Verify cache was set correctly
        assert provider._cached_user_agent == ua1
        assert "Firefox" in provider._cached_user_agent

    def test_parse_and_stealth_consistency(self):
        """Verify parsed UA info matches expected anti-fingerprinting values."""
        config = MagicMock()
        provider = ConcreteAsyncProvider(config=config)

        # Test Windows Chrome
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        info = provider._parse_user_agent_info(ua)

        plugins_script = provider._get_plugins_script(info["browser"])
        webgl_script = provider._get_webgl_script(info["platform"])

        # Verify consistency
        assert info["platform"] == "Win32"
        assert info["vendor"] == "Google Inc."
        assert "Chrome PDF" in plugins_script
        assert "Intel(R) UHD Graphics" in webgl_script

    def test_firefox_ua_no_chrome_object(self):
        """Verify Firefox UA doesn't get Chrome object."""
        config = MagicMock()
        provider = ConcreteAsyncProvider(config=config)

        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0"
        info = provider._parse_user_agent_info(ua)

        assert info["has_chrome_object"] is False
        assert info["vendor"] == ""  # Firefox has no vendor
        assert info["browser"] == "firefox"

    def test_safari_ua_apple_vendor(self):
        """Verify Safari UA gets correct vendor."""
        config = MagicMock()
        provider = ConcreteAsyncProvider(config=config)

        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        info = provider._parse_user_agent_info(ua)

        assert info["vendor"] == "Apple Computer, Inc."
        assert info["platform"] == "MacIntel"
        assert info["browser"] == "webkit"
        assert info["has_chrome_object"] is False
