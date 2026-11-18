"""Application settings, loaded from the environment / ``.env`` (constitution III.4).

Secrets (JWT key, DB password, portal token) only ever live in server-side env
config — never in code, never in the repository.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str
    APP_DB_USER: str = "helixa_app"
    APP_DB_PASSWORD: str = ""

    # Auth / sessions
    JWT_SECRET: str
    ACCESS_TTL_MIN: int = 15
    REFRESH_IDLE_H: int = 12
    REFRESH_ABSOLUTE_D: int = 7

    # Reports
    REPORTS_ROOT: str = "/data/reports"
    REPORT_MAX_BYTES: int = 52428800
    REPORT_ALLOWED_TYPES: str = "application/pdf"

    # Portal (optional until Spec 2 integration is live)
    PORTAL_BASE_URL: str | None = None
    PORTAL_TOKEN: str | None = None
    PORTAL_MAX_ATTEMPTS: int = 5
    PORTAL_RETRY_BACKOFF_SEC: int = 60

    @property
    def report_allowed_types(self) -> frozenset[str]:
        return frozenset(t.strip() for t in self.REPORT_ALLOWED_TYPES.split(",") if t.strip())


_settings: Settings | None = None


def get_settings() -> Settings:
    """Cached settings accessor; instantiate fresh in tests via ``Settings()``."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_cached_settings() -> None:
    """Forget the cached instance so the next get_settings() re-reads the env."""
    global _settings
    _settings = None
