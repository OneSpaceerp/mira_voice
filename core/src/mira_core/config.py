"""Settings, read from the environment (in production: /opt/mira/.env via docker compose)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class Settings(BaseSettings):
    """All Mira Core settings. Names match the keys install.sh writes to /opt/mira/.env."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    environment: Literal["production", "development", "test"] = Field(
        default="production", validation_alias="MIRA_ENV"
    )

    # PostgreSQL (the database runs on the same host, loopback only)
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_user: str = "mira"
    postgres_password: SecretStr = SecretStr("")
    postgres_db: str = "mira"
    # Full URL override (tests, external database). Takes precedence over POSTGRES_*.
    database_url: SecretStr | None = Field(default=None, validation_alias="MIRA_DATABASE_URL")

    # Auth
    jwt_secret: SecretStr = Field(validation_alias="MIRA_JWT_SECRET")
    jwt_access_minutes: int = Field(
        default=30, ge=5, le=24 * 60, validation_alias="MIRA_JWT_ACCESS_MINUTES"
    )

    # Asterisk (same host, loopback only)
    ari_url: str = Field(default="http://127.0.0.1:8088/ari", validation_alias="MIRA_ARI_URL")
    ari_user: str = "mira-core"
    ari_password: SecretStr = SecretStr("")
    # Password of the read-only PostgreSQL role "asterisk" (realtime views)
    asterisk_db_password: SecretStr = SecretStr("")
    # Shared volume: Mira Core writes the dialplan, Asterisk reads it (generated/extensions_mira.conf)
    asterisk_generated_dir: str = Field(
        default="/var/lib/mira/asterisk", validation_alias="MIRA_ASTERISK_GENERATED_DIR"
    )
    # Group shared with Asterisk ("mira-config", 2701): generated files are 0640 because the
    # trunk file holds carrier passwords. None = leave the group as is (tests, development).
    asterisk_config_gid: int | None = Field(
        default=None, validation_alias="MIRA_ASTERISK_CONFIG_GID"
    )

    # Prompt recordings (task 1.4): shared volume, Asterisk reads it as sounds/mira/
    prompts_dir: str = Field(default="/var/lib/mira/prompts", validation_alias="MIRA_PROMPTS_DIR")
    # Data dips (flow http nodes) may reach private LAN addresses (ERPNext on the LAN).
    # Mira Cloud sets false: tenants must never reach the provider's internal network.
    flow_http_allow_private: bool = Field(
        default=True, validation_alias="MIRA_FLOW_HTTP_ALLOW_PRIVATE"
    )

    # Kamailio (SIP edge): generated carrier list + JSON-RPC on loopback to reload it
    kamailio_generated_dir: str = Field(
        default="/var/lib/mira/kamailio", validation_alias="MIRA_KAMAILIO_GENERATED_DIR"
    )
    kamailio_rpc_url: str = Field(
        default="http://127.0.0.1:8095/RPC", validation_alias="MIRA_KAMAILIO_RPC_URL"
    )
    kamailio_rpc_token: SecretStr = SecretStr("")

    # Key(s) for secrets Mira must read back (carrier passwords): Fernet, comma-separated, newest first
    data_key: SecretStr = Field(default=SecretStr(""), validation_alias="MIRA_DATA_KEY")

    # Live state (active calls) and event fan-out: Valkey (Redis protocol), loopback only (task 1.3)
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: SecretStr = SecretStr("")
    # Full URL override (tests). Takes precedence over REDIS_*.
    redis_url_override: SecretStr | None = Field(default=None, validation_alias="MIRA_REDIS_URL")
    # Stasis application name Mira Core subscribes to (all events, subscribeAll)
    ari_app: str = Field(default="mira", validation_alias="MIRA_ARI_APP")

    @property
    def redis_url(self) -> str:
        if self.redis_url_override is not None:
            return self.redis_url_override.get_secret_value()
        password = self.redis_password.get_secret_value()
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/0"

    @property
    def ari_events_url(self) -> str:
        """WebSocket URL of ARI's event stream (same host and path prefix as ari_url)."""
        base = self.ari_url.rstrip("/")
        scheme = "wss" if base.startswith("https") else "ws"
        return scheme + base[base.index(":") :] + "/events"

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_strong(cls, v: SecretStr) -> SecretStr:
        # HS256 needs at least 32 bytes of key (RFC 7518 §3.2); install.sh generates 64 hex chars.
        if len(v.get_secret_value()) < 32:
            raise ValueError("MIRA_JWT_SECRET must be at least 32 characters")
        return v

    @property
    def sqlalchemy_url(self) -> URL:
        """psycopg 3 URL; the same URL works for the async app and the sync Alembic runner."""
        if self.database_url is not None:
            url = make_url(self.database_url.get_secret_value())
            return url.set(drivername="postgresql+psycopg")
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
