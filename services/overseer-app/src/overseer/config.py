from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class OverseerSettings(BaseSettings):
    model_config = {"env_file": "/opt/Valkyrie/.env", "env_file_encoding": "utf-8"}

    # Anthropic
    anthropic_api_key: str = Field(alias="ANTHROPIC_API_KEY")

    # OpenRouter (for non-Anthropic model routing)
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    anthropic_misc_key: str = Field(default="", alias="ANTHROPIC_MISC_KEY")
    anthropic_admin_api_key: str = Field(default="", alias="ANTHROPIC_ADMIN_API_KEY")

    # Discord
    discord_bot_token: str = Field(alias="DISCORD_BOT_TOKEN")
    discord_server_id: int = Field(alias="DISCORD_SERVER_ID")
    discord_channel_id: int = Field(alias="DISCORD_CHANNEL_ID")

    # FMP
    fmp_api_key: str = Field(alias="FMP_API_KEY")
    fmp_local_api_key: str = Field(alias="FMP_LOCAL_API_KEY")
    fmp_host: str = Field(default="<LAN_IP>", alias="FMP_HOST")
    fmp_port: int = Field(default=8000, alias="FMP_PORT")

    # Twitter / Data Collection
    twitter_host: str = Field(default="<LAN_IP>", alias="TWITTER_HOST")
    twitter_port: int = Field(default=8082, alias="TWITTER_PORT")
    data_collection_host: str = Field(default="<LAN_IP>", alias="DATA_COLLECTION_HOST")

    # IBKR
    ibkr_host: str = Field(default="<LAN_IP>", alias="IBKR_HOST")

    # Database
    db_host: str = Field(default="localhost", alias="OVERSEER_DB_HOST")
    db_port: int = Field(default=5432, alias="OVERSEER_DB_PORT")
    db_name: str = Field(default="overseer", alias="OVERSEER_DB_NAME")
    db_user: str = Field(default="postgres", alias="OVERSEER_DB_USER")
    db_password: str = Field(default="", alias="OVERSEER_DB_PASSWORD")

    # SSH
    ssh_key_path: str = Field(default="/opt/Valkyrie/valhalla_key", alias="SSH_KEY_PATH")

    # Trading
    trading_mode: str = Field(default="paper", alias="TRADING_MODE")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def db_dsn(self) -> str:
        password_part = f":{self.db_password}" if self.db_password else ""
        return f"postgresql://{self.db_user}{password_part}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def fmp_base_url(self) -> str:
        return f"http://{self.fmp_host}:{self.fmp_port}"

    @property
    def twitter_base_url(self) -> str:
        return f"http://{self.twitter_host}:{self.twitter_port}"


def get_settings() -> OverseerSettings:
    return OverseerSettings()
