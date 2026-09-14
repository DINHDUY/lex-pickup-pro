from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./lex_pickup.db"
    database_provider: Literal["sql", "cosmos"] = "sql"
    cosmos_endpoint: str = ""
    cosmos_database: str = "lex_pickup"
    cosmos_container: str = "club_data"
    cosmos_club_id: str = Field(default="lex-pickup", pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    cosmos_auth_mode: Literal["managed_identity", "default_credential", "emulator"] = "managed_identity"
    cosmos_key: SecretStr = SecretStr("")
    cosmos_managed_identity_client_id: str | None = None
    cosmos_consistency_level: Literal["Strong"] = "Strong"
    cosmos_emulator: bool = False
    cosmos_max_documents: int = Field(default=10000, ge=100, le=100000)
    cosmos_max_snapshot_bytes: int = Field(default=32_000_000, ge=2_000_000, le=128_000_000)
    storage_retry_attempts: int = Field(default=4, ge=1, le=8)
    jwt_secret: str = "local-development-secret-change-before-deployment"
    cookie_secure: bool = False
    session_cookie_name: str = Field(default="lex_session", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    frontend_url: str = "http://localhost:5173"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    club_invite_code: str = "LEX2026"
    registration_enabled: bool = True
    demo_enabled: bool = False
    facebook_auth_enabled: bool = False
    facebook_app_id: str = ""
    facebook_app_secret: str = ""
    facebook_redirect_uri: str = "https://localhost:5173/login"
    reminder_webhook_url: str = ""
    reminder_webhook_secret: str = ""

    @model_validator(mode="after")
    def production_safety(self):
        self.cosmos_managed_identity_client_id = self.cosmos_managed_identity_client_id or None
        if self.database_provider == "cosmos":
            if not self.cosmos_endpoint or not self.cosmos_database or not self.cosmos_container:
                raise ValueError("Cosmos requires endpoint, database and container settings")
            if self.cosmos_emulator:
                from urllib.parse import urlparse

                host = urlparse(self.cosmos_endpoint).hostname
                if self.app_env == "production" or host not in ("localhost", "127.0.0.1", "cosmos-emulator"):
                    raise ValueError("Emulator access is restricted to local development")
                if self.cosmos_auth_mode != "emulator" or not self.cosmos_key.get_secret_value():
                    raise ValueError("Emulator mode requires its local key")
            elif not self.cosmos_endpoint.startswith("https://") or self.cosmos_auth_mode == "emulator":
                raise ValueError("Azure Cosmos requires HTTPS and Entra credentials")
        if self.app_env == "production":
            if len(self.jwt_secret) < 32 or self.jwt_secret.startswith("local-development"):
                raise ValueError("Production requires a unique JWT_SECRET of at least 32 characters")
            if not self.cookie_secure or not self.frontend_url.startswith("https://"):
                raise ValueError("Production requires COOKIE_SECURE=true and HTTPS FRONTEND_URL")
            if self.demo_enabled:
                raise ValueError("Production requires DEMO_ENABLED=false")
            if self.registration_enabled and self.club_invite_code == "LEX2026":
                raise ValueError(
                    "Production requires a unique CLUB_INVITE_CODE when REGISTRATION_ENABLED=true; "
                    "replace LEX2026 or set REGISTRATION_ENABLED=false"
                )
            if "*" in self.cors_origins:
                raise ValueError("Production CORS origins must be explicit")
        if self.facebook_auth_enabled:
            if not self.facebook_app_id or not self.facebook_app_secret:
                raise ValueError("Facebook auth enabled requires FACEBOOK_APP_ID and FACEBOOK_APP_SECRET")
            if self.facebook_redirect_uri.startswith("http://"):
                raise ValueError("Facebook auth requires an HTTPS redirect URI")
        return self


@lru_cache
def get_settings():
    return Settings()
