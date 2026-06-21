# config.py
"""
Central configuration loader. Reads config.yaml and provides
typed access to all settings. CLI arguments override yaml values.
"""
import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.yaml"


@dataclass
class ModelConfig:
    backend: str = "anthropic"
    model: Optional[str] = None
    vision_model: Optional[str] = None
    extraction_model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    def client_kwargs(self) -> Dict[str, Any]:
        """Return backend-appropriate kwargs for model client creation."""
        kwargs: Dict[str, Any] = {}

        if self.backend == "anthropic" and self.api_key:
            kwargs["api_key"] = self.api_key

        if self.backend in {"ollama", "llamacpp"} and self.base_url:
            kwargs["base_url"] = self.base_url

        return kwargs


@dataclass
class GmailConfig:
    query: str = "from:substack.com"
    max_results: int = 50
    credentials_path: str = "credentials.json"
    token_path: str = "token.json"
    sender_whitelist: List[str] = field(default_factory=lambda: ["substack.com"])


@dataclass
class PipelineConfig:
    batch_size: int = 10
    max_batches: Optional[int] = None
    rate_limit_delay: float = 1.0


@dataclass
class ImageConfig:
    directory: str = "images"
    download_timeout: int = 10


@dataclass
class OutputConfig:
    newsletter_data: str = "newsletter_data.json"
    ticker_history: str = "ticker_history.json"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: Optional[str] = "pipeline.log"


@dataclass
class DiscordConfig:
    enabled: bool = True
    webhook_url: Optional[str] = None
    notify_on_error: bool = True
    notify_on_warning: bool = False
    notify_on_start: bool = False
    notify_on_complete: bool = False


@dataclass
class AppConfig:
    model: ModelConfig = field(default_factory=ModelConfig)
    gmail: GmailConfig = field(default_factory=GmailConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    images: ImageConfig = field(default_factory=ImageConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    database_path: str = "newsletters.db"


def load_config(config_path: str = None, cli_overrides: dict = None) -> AppConfig:
    """Load config.yaml, apply environment variable overrides, then CLI overrides."""
    env_path = Path('.env')
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    path = Path(config_path) if config_path else CONFIG_PATH

    raw = {}
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    else:
        logger.warning(f"Config file not found at {path}, using defaults")

    cfg = AppConfig()

    # --- Model section ---
    model_raw = raw.get("model", {})
    cfg.model.backend = model_raw.get("backend", "anthropic")

    backend_settings = model_raw.get(cfg.model.backend, {})
    cfg.model.model = backend_settings.get("model")
    cfg.model.vision_model = backend_settings.get("vision_model")
    cfg.model.extraction_model = backend_settings.get("extraction_model")
    cfg.model.api_key = backend_settings.get("api_key")
    cfg.model.base_url = backend_settings.get("base_url")

    # Environment variable fallback for API key
    if cfg.model.backend == "anthropic" and not cfg.model.api_key:
        cfg.model.api_key = os.environ.get("ANTHROPIC_API_KEY")

    # --- Database ---
    cfg.database_path = raw.get("database", {}).get("path", "newsletters.db")

    # --- Gmail ---
    gmail_raw = raw.get("gmail", {})
    cfg.gmail.query = gmail_raw.get("query", "from:substack.com")
    cfg.gmail.max_results = gmail_raw.get("max_results", 50)
    cfg.gmail.credentials_path = gmail_raw.get("credentials_path", "credentials.json")
    cfg.gmail.token_path = gmail_raw.get("token_path", "token.json")
    cfg.gmail.sender_whitelist = gmail_raw.get("sender_whitelist", ["substack.com"])

    # --- Images ---
    images_raw = raw.get("images", {})
    cfg.images.directory = images_raw.get("directory", "images")
    cfg.images.download_timeout = images_raw.get("download_timeout", 10)

    # --- Pipeline ---
    pipeline_raw = raw.get("pipeline", {})
    cfg.pipeline.batch_size = pipeline_raw.get("batch_size", 10)
    cfg.pipeline.max_batches = pipeline_raw.get("max_batches")
    cfg.pipeline.rate_limit_delay = pipeline_raw.get("rate_limit_delay", 1.0)

    # --- Output ---
    output_raw = raw.get("output", {})
    cfg.output.newsletter_data = output_raw.get("newsletter_data", "newsletter_data.json")
    cfg.output.ticker_history = output_raw.get("ticker_history", "ticker_history.json")

    # --- Logging ---
    logging_raw = raw.get("logging", {})
    cfg.logging.level = logging_raw.get("level", "INFO")
    cfg.logging.file = logging_raw.get("file", "pipeline.log")

    # --- Discord ---
    discord_raw = raw.get("discord", {})
    cfg.discord.enabled = discord_raw.get("enabled", True)
    cfg.discord.webhook_url = discord_raw.get("webhook_url")
    cfg.discord.notify_on_error = discord_raw.get("notify_on_error", True)
    cfg.discord.notify_on_warning = discord_raw.get("notify_on_warning", False)
    cfg.discord.notify_on_start = discord_raw.get("notify_on_start", False)
    cfg.discord.notify_on_complete = discord_raw.get("notify_on_complete", False)

    # Environment variable fallback for Discord webhook
    if not cfg.discord.webhook_url:
        cfg.discord.webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")

    # --- CLI overrides (applied last, highest priority) ---
    if cli_overrides:
        if cli_overrides.get("model"):
            cfg.model.model = cli_overrides["model"]
        if cli_overrides.get("batch_size") is not None:
            cfg.pipeline.batch_size = cli_overrides["batch_size"]
        if cli_overrides.get("max_batches") is not None:
            cfg.pipeline.max_batches = cli_overrides["max_batches"]
        if cli_overrides.get("db"):
            cfg.database_path = cli_overrides["db"]

    return cfg
