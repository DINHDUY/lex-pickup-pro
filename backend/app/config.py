from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./lex_pickup.db"
    jwt_secret: str = "local-development-secret-change-before-deployment"
    cookie_secure: bool = False
    session_cookie_name: str = Field(default="lex_session", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    frontend_url: str = "http://localhost:5173"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    club_invite_code: str = "LEX2026"
    registration_enabled: bool = True
    demo_enabled: bool = False
    reminder_webhook_url: str = ""
    reminder_webhook_secret: str = ""

    @model_validator(mode="after")
    def production_safety(self):
        if self.app_env == "production":
            if len(self.jwt_secret) < 32 or self.jwt_secret.startswith("local-development"):
                raise ValueError("Production requires a unique JWT_SECRET of at least 32 characters")
            if not self.cookie_secure or not self.frontend_url.startswith("https://"):
                raise ValueError("Production requires COOKIE_SECURE=true and HTTPS FRONTEND_URL")
            if self.demo_enabled or (self.registration_enabled and self.club_invite_code == "LEX2026"):
                raise ValueError("Disable demo mode and replace the default invitation code in production")
            if "*" in self.cors_origins:
                raise ValueError("Production CORS origins must be explicit")
        return self


@lru_cache
def get_settings():
    return Settings()
