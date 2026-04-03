"""
config.py — Environment-driven settings for ProspectAI
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    # ── Anthropic ──────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    claude_model: str = "claude-3-5-sonnet-20241022"

    # ── LinkedIn session ───────────────────────────────────────────────────
    # Path to a JSON file containing exported LinkedIn cookies.
    # See README for how to export these from your browser.
    linkedin_cookies_path: Path = Path("linkedin_cookies.json")
    # Optional: direct li_at cookie value (alternative to cookies file)
    linkedin_li_at: str = ""

    # ── Scraper behaviour ──────────────────────────────────────────────────
    # Whether to run the browser in headless mode (True = invisible)
    playwright_headless: bool = True
    # Min/max delay (seconds) between page actions — mimics human behaviour
    scrape_delay_min: float = 1.5
    scrape_delay_max: float = 4.0
    # Max concurrent browser contexts (keep low to avoid LinkedIn bans)
    max_browser_contexts: int = 1

    # ── Email enrichment ───────────────────────────────────────────────────
    # Optional: Hunter.io API key for verified email lookup
    hunter_api_key: str = ""
    # Optional: Apollo.io API key
    apollo_api_key: str = ""
    # Whether to attempt SMTP verification of guessed emails (slow, use cautiously)
    smtp_verify: bool = False

    # ── Email sending ──────────────────────────────────────────────────────
    # Currently supports SendGrid. Add others as needed.
    sendgrid_api_key: str = ""
    from_email: str = ""
    from_name: str = "SDR Agent"

    # ── App ────────────────────────────────────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
