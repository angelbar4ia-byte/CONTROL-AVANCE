"""Configuración por entorno.

Spec §12.8 (entornos dev/staging/prod) · §12.4 (seguridad).

Todos los secretos vienen de variables de entorno (Render/Vercel), nunca del
repositorio.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Config", "obtener_config"]


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    entorno: str = Field(default="dev", description="dev | staging | prod")
    debug: bool = False

    # --- Base de datos (Supabase) ---------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/obractrl",
        description="Conexión a Postgres. El backend NO usa la service key.",
    )
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # --- Auth (JWT del proveedor administrado) --------------------------
    jwt_secret: str = Field(default="cambiar-en-produccion")
    jwt_algoritmo: str = "HS256"
    jwt_audiencia: str = "authenticated"

    # --- Supabase (solo para la ruta directa del front) -----------------
    supabase_url: str = ""
    supabase_anon_key: str = ""

    # --- Jobs (Arq + Redis) ---------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # --- Evidencias (Cloudflare R2) -------------------------------------
    r2_endpoint: str = ""
    r2_bucket: str = "obractrl-evidencias"
    r2_access_key: str = ""
    r2_secret_key: str = ""

    # --- CORS: orígenes de Vercel por entorno (§12.8) -------------------
    cors_origenes: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- Observabilidad --------------------------------------------------
    sentry_dsn: str = ""

    @field_validator("cors_origenes", mode="before")
    @classmethod
    def _separar_origenes(cls, v: object) -> object:
        """Permite `CORS_ORIGENES=https://a.com,https://b.com`."""
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def es_produccion(self) -> bool:
        return self.entorno == "prod"


@lru_cache
def obtener_config() -> Config:
    return Config()
