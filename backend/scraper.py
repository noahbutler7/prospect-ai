"""
scraper.py — LinkedIn Playwright scraping engine for ProspectAI

Strategy:
  1. Load a real LinkedIn session via cookies (exported from your browser).
  2. For each target account, navigate to the company's /people page.
  3. Scroll and extract profile cards (name, title, LinkedIn URL).
  4. Optionally visit individual profiles for activity signals.
  5. Yield RawProfile objects for the ICP matcher to score.

Anti-detection measures applied:
  - Randomised delays between every action
  - Human-like scroll behaviour
  - Realistic viewport and user-agent
  - playwright-stealth patches (WebGL, permissions, navigator overrides)
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator, Optional
from urllib.parse import quote_plus

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    async_playwright,
)

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Raw profile (pre-enrichment / pre-ICP-scoring) ──────────────────────────

@dataclass
class RawProfile:
    first_name: str
    last_name: str
    full_name: str
    title: str
    company: str
    company_domain: str
    linkedin_url: str
    linkedin_urn: Optional[str] = None
    headline: Optional[str] = None
    profile_picture_url: Optional[str] = None
    recent_post: Optional[str] = None          # First visible post snippet
    connection_degree: Optional[str] = None    # "1st", "2nd", "3rd"
    raw_signals: list[str] = field(default_factory=list)


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _human_delay(min_s: float | None = None, max_s: float | None = None) -> None:
    lo = min_s if min_s is not None else settings.scrape_delay_min
    hi = max_s if max_s is not None else settings.scrape_delay_max
    await asyncio.sleep(random.uniform(lo, hi))


async def _smooth_scroll(page: Page, distance: int = 800) -> None:
    """Scroll in small increments to mimic human behaviour."""
    step = random.randint(80, 160)
    scrolled = 0
    while scrolled < distance:
        await page.evaluate(f"window.scrollBy(0, {step})")
        await asyncio.sleep(random.uniform(0.05, 0.15))
        scrolled += step


def _infer_slug(company_name: str) -> str:
    """Best-guess LinkedIn company slug from a name."""
    slug = company_name.lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug


def _parse_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split()
    if len(parts) == 0:
        return ("", "")
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], " ".join(parts[1:]))


# ─── Session management ───────────────────────────────────────────────────────

async def _load_cookies(context: BrowserContext) -> bool:
    """
    Load LinkedIn cookies from disk.
    Returns True if cookies were loaded successfully.

    How to export cookies:
      1. Log into LinkedIn in Chrome/Firefox.
      2. Install the 'EditThisCookie' or 'Cookie-Editor' extension.
      3. Export all cookies for linkedin.com as JSON.
      4. Save to the path set in LINKEDIN_COOKIES_PATH (.env).
    """
    path = settings.linkedin_cookies_path
    li_at = settings.linkedin_li_at

    # Option A: Full cookies file
    if path.exists():
        raw = json.loads(path.read_text())
        # Normalize to Playwright's cookie format
        cookies = []
        for c in raw:
            cookie = {
                "name": c.get("name", c.get("Name", "")),
                "value": c.get("value", c.get("Value", "")),
                "domain": c.get("domain", c.get("Domain", ".linkedin.com")),
                "path": c.get("path", c.get("Path", "/")),
                "httpOnly": c.get("httpOnly", c.get("HttpOnly", False)),
                "secure": c.get("secure", c.get("Secure", True)),
            }
            if "expirationDate" in c:
                cookie["expires"] = int(c["expirationDate"])
            cookies.append(cookie)
        await context.add_cookies(cookies)
        logger.info(f"Loaded {len(cookies)} LinkedIn cookies from {path}")
        return True

    # Option B: Just the li_at session token
    if li_at:
        await context.add_cookies([{
            "name": "li_at",
            "value": li_at,
            "domain": ".linkedin.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
        }])
        logger.info("Loaded LinkedIn session from li_at env var")
        return True

    logger.warning("No LinkedIn session found. Set LINKEDIN_COOKIES_PATH or LINKEDIN_LI_AT.")
    return False


# ─── Stealth patches ──────────────────────────────────────────────────────────

STEALTH_SCRIPT = """
// Mask automation fingerprints
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
const origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (params) =>
  params.name === 'notifications'
    ? Promise.resolve({ state: Notification.permission })
    : origQuery(params);
"""


# ─── Profile extraction ───────────────────────────────────────────────────────

async def _extract_profile_cards(
    page: Page,
    company: str,
    domain: str,
    max_results: int,
) -> list[RawProfile]:
    """
    Extract prospect cards from LinkedIn's company /people page.
    LinkedIn renders them as <li> elements inside a search results list.
    """
    profiles: list[RawProfile] = []

    # Scroll through the page to load all visible cards
    for _ in range(6):
        await _smooth_scroll(page, random.randint(600, 1000))
        await _human_delay(0.8, 1.5)
        if len(profiles) >= max_results:
            break

    # Each employee card on /company/X/people/ uses consistent selectors
    cards = await page.query_selector_all("li.org-people-profile-card__profile-card-spacing")

    if not cards:
        # Fallback: search results page
        cards = await page.query_selector_all("li.reusable-search__result-container")

    logger.info(f"Found {len(cards)} raw cards for {company}")

    for card in cards:
        if len(profiles) >= max_results:
            break
        try:
            profile = await _parse_card(card, company, domain)
            if profile:
                profiles.append(profile)
        except Exception as e:
            logger.debug(f"Card parse error: {e}")
            continue

    return profiles


async def _parse_card(card, company: str, domain: str) -> Optional[RawProfile]:
    """Parse a single LinkedIn profile card element."""
    # Name
    name_el = await card.query_selector("span.org-people-profile-card__profile-title, .actor-name, .entity-result__title-text a span[aria-hidden='true']")
    if not name_el:
        name_el = await card.query_selector("span[aria-hidden='true']")
    if not name_el:
        return None

    full_name = (await name_el.inner_text()).strip()
    if not full_name or full_name.lower() == "linkedin member":
        return None

    first_name, last_name = _parse_name(full_name)

    # Title / headline
    title_el = await card.query_selector(
        ".org-people-profile-card__profile-position, "
        ".entity-result__primary-subtitle, "
        ".subline-level-1"
    )
    title = (await title_el.inner_text()).strip() if title_el else ""

    # LinkedIn URL
    link_el = await card.query_selector("a[href*='/in/']")
    linkedin_url = ""
    if link_el:
        href = await link_el.get_attribute("href")
        if href:
            # Strip query params and trailing slashes
            match = re.search(r"(https?://[^/]*linkedin\.com/in/[^/?#]+)", href)
            if match:
                linkedin_url = match.group(1)
            elif href.startswith("/in/"):
                linkedin_url = f"https://www.linkedin.com{href.split('?')[0]}"

    # Profile picture
    img_el = await card.query_selector("img.presence-entity__image, img.EntityPhoto-circle-3, img[data-delayed-url]")
    picture_url = None
    if img_el:
        picture_url = await img_el.get_attribute("src") or await img_el.get_attribute("data-delayed-url")

    return RawProfile(
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        title=title,
        company=company,
        company_domain=domain,
        linkedin_url=linkedin_url,
        headline=title,
        profile_picture_url=picture_url,
    )


async def _enrich_profile_from_page(page: Page, profile: RawProfile) -> None:
    """
    Visit the individual profile page to extract:
    - Recent activity / posts (for buying signals)
    - Full headline
    """
    if not profile.linkedin_url:
        return

    try:
        await page.goto(profile.linkedin_url, wait_until="domcontentloaded", timeout=15_000)
        await _human_delay(1.0, 2.5)

        # Headline
        headline_el = await page.query_selector(".text-body-medium.break-words")
        if headline_el:
            profile.headline = (await headline_el.inner_text()).strip()

        # Recent activity — navigate to activity tab
        activity_url = profile.linkedin_url.rstrip("/") + "/recent-activity/all/"
        await page.goto(activity_url, wait_until="domcontentloaded", timeout=12_000)
        await _human_delay(1.0, 2.0)

        post_els = await page.query_selector_all(".feed-shared-update-v2__description span[dir='ltr']")
        if post_els:
            first_post = (await post_els[0].inner_text()).strip()
            profile.recent_post = first_post[:500]  # cap length
            profile.raw_signals.append(f'Recent post: "{first_post[:120]}..."')

    except Exception as e:
        logger.debug(f"Profile enrichment failed for {profile.full_name}: {e}")


# ─── Main scraper interface ───────────────────────────────────────────────────

class LinkedInScraper:
    """
    Async context manager that manages a single Playwright browser session
    and exposes scrape_account() as an async generator of RawProfile objects.

    Usage:
        async with LinkedInScraper() as scraper:
            async for profile in scraper.scrape_account(account, max_results=25):
                process(profile)
    """

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self) -> "LinkedInScraper":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=settings.playwright_headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
            ],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        # Inject stealth patches on every new page
        await self._context.add_init_script(STEALTH_SCRIPT)
        # Load LinkedIn session cookies
        await _load_cookies(self._context)
        return self

    async def __aexit__(self, *_) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def verify_session(self) -> bool:
        """Return True if our LinkedIn session is still valid."""
        page = await self._context.new_page()
        try:
            await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=15_000)
            # If we're redirected to login, session is dead
            is_authenticated = "feed" in page.url
            return is_authenticated
        except Exception:
            return False
        finally:
            await page.close()

    async def scrape_account(
        self,
        company_name: str,
        company_domain: str,
        linkedin_slug: Optional[str] = None,
        max_results: int = 25,
        visit_profiles: bool = False,
    ) -> AsyncGenerator[RawProfile, None]:
        """
        Scrape LinkedIn profiles from a company's people page.
        Yields RawProfile objects one at a time.

        Args:
            company_name:    Human-readable company name.
            company_domain:  Email domain e.g. 'salesforce.com'.
            linkedin_slug:   LinkedIn company URL slug. Inferred if not given.
            max_results:     Max profiles to return.
            visit_profiles:  Whether to visit each profile page for activity signals.
                             Slower but gives much better signal quality.
        """
        slug = linkedin_slug or _infer_slug(company_name)
        page = await self._context.new_page()

        try:
            # ── Navigate to company people page ───────────────────────────
            people_url = f"https://www.linkedin.com/company/{slug}/people/"
            logger.info(f"Scraping {company_name} → {people_url}")
            await page.goto(people_url, wait_until="domcontentloaded", timeout=20_000)
            await _human_delay(2.0, 3.5)

            # Check for auth wall
            if "authwall" in page.url or "login" in page.url:
                logger.error("LinkedIn auth wall hit — session may be expired")
                return

            # Check if company page exists
            if await page.query_selector(".not-found-404"):
                logger.warning(f"Company not found: {slug}. Trying search fallback.")
                await self._search_fallback(page, company_name)
                await _human_delay(2.0, 3.0)

            # ── Extract cards ──────────────────────────────────────────────
            profiles = await _extract_profile_cards(page, company_name, company_domain, max_results)
            logger.info(f"Extracted {len(profiles)} profiles from {company_name}")

            for profile in profiles:
                if visit_profiles and profile.linkedin_url:
                    await _enrich_profile_from_page(page, profile)
                    await _human_delay()
                yield profile
                await _human_delay(0.2, 0.6)  # Small yield gap

        except Exception as e:
            logger.error(f"Scrape failed for {company_name}: {e}", exc_info=True)
        finally:
            await page.close()

    async def _search_fallback(self, page: Page, company_name: str) -> None:
        """
        If the company /people page doesn't exist, fall back to LinkedIn
        people search filtered by current company.
        """
        query = quote_plus(company_name)
        search_url = (
            f"https://www.linkedin.com/search/results/people/"
            f"?keywords={query}&origin=SWITCH_SEARCH_VERTICAL"
        )
        await page.goto(search_url, wait_until="domcontentloaded", timeout=20_000)
