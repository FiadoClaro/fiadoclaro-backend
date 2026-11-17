"""Configuración central. Todo se lee de variables de entorno (archivo .env)."""
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "FiadoClaro API"
    API_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/fiadoclaro"

    JWT_SECRET: str = "cambia-esta-clave-larga-en-produccion-0123456789"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480

    # Zona horaria del negocio: decide si una compra cae antes o después de la hora de corte.
    TIMEZONE: str = "America/Lima"

    # Usuario administrador del sistema que crea el script de semilla.
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "Admin123*"

    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.TIMEZONE)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
