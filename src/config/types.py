from typing import Literal

# Playwright's valid `wait_until` values for page navigation
# See: https://playwright.dev/python/docs/api/class-page#page-goto
PlaywrightWaitUntil = Literal["commit", "domcontentloaded", "load", "networkidle"]
