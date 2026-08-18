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

# Sufijos que el Dashboard de Supabase muestra pegados a la URL del proyecto.
# La etiqueta que ve el usuario dice "API URL" y el valor viene con
# `/rest/v1/`, así que copiarlo tal cual es el camino natural —y dejaría el
# JWKS en `/rest/v1/auth/v1/...`, que no existe. Se normaliza en vez de
# exigir que el operador sepa recortarlo.
_SUFIJOS_DE_SERVICIO = ("/rest/v1", "/auth/v1", "/storage/v1", "/realtime/v1")


def _base_de_proyecto(url: str) -> str:
    """URL base del proyecto, sin sufijo de servicio ni barra final."""
    base = url.strip().rstrip("/")
    for sufijo in _SUFIJOS_DE_SERVICIO:
        if base.endswith(sufijo):
            return base[: -len(sufijo)].rstrip("/")
    return base


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
    #
    # Supabase firma con **llaves asimétricas** (ES256) y publica la parte
    # pública en el JWKS del proyecto. El backend verifica contra ese JWKS:
    # así el secreto no existe en las variables de Render y una rotación de
    # llaves no obliga a redesplegar (§12.4, §12.8).
    #
    # `jwt_secret` solo sigue existiendo para proyectos que aún emiten HS256
    # con secreto compartido; si `jwt_jwks_url` está puesta, se ignora.
    jwt_secret: str = Field(default="cambiar-en-produccion")
    jwt_algoritmos: list[str] = ["ES256", "RS256", "HS256"]
    jwt_audiencia: str = "authenticated"
    jwt_holgura_segundos: int = Field(
        default=60,
        description=(
            "Tolerancia de desfase de reloj al validar `iat`/`exp`. El token "
            "lo emite Supabase y lo valida otro host; unos segundos de "
            "diferencia bastan para que un token legítimo se vea prematuro."
        ),
    )
    jwt_jwks_url: str = Field(
        default="",
        description=(
            "JWKS del proyecto, p. ej. "
            "https://<ref>.supabase.co/auth/v1/.well-known/jwks.json. "
            "Si se deja vacío se deriva de `supabase_url`."
        ),
    )

    @property
    def jwks_url_efectiva(self) -> str:
        """JWKS explícito, o el derivado de `supabase_url`; '' si no hay ninguno."""
        if self.jwt_jwks_url:
            return self.jwt_jwks_url
        base = _base_de_proyecto(self.supabase_url)
        return f"{base}/auth/v1/.well-known/jwks.json" if base else ""

    # --- Supabase (solo para la ruta directa del front) -----------------
    supabase_url: str = ""
    supabase_anon_key: str = ""

    # --- Jobs (Arq + Redis) ---------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # --- Notificaciones (Resend, §12.2) ---------------------------------
    #
    # Sin llave el sistema **sigue funcionando**: `ClienteResend.enviar`
    # registra y devuelve `False` (§11.3 E.5, una notificación no puede
    # tumbar la validación de una estimación). Por eso el default es vacío y
    # no un valor de mentira.
    resend_api_key: str = ""
    resend_remitente: str = Field(
        default="",
        description=(
            'Remitente verificado en Resend, p. ej. "ObraCtrl '
            '<avisos@obractrl.mx>". Un dominio no verificado hace que Resend '
            "rechace el envío."
        ),
    )

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
