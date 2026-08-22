"""Configuración por entorno.

Spec §12.8 (entornos dev/staging/prod) · §12.4 (seguridad).

Todos los secretos vienen de variables de entorno (Render/Vercel), nunca del
repositorio.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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


ListaDeTexto = Annotated[list[str], NoDecode]
"""Lista que se escribe **separada por comas** en una variable de entorno.

`NoDecode` no es decoración: sin él, pydantic-settings intenta un
`json.loads()` sobre el valor **antes** de que corra ningún validador, porque
el campo es de tipo complejo. Con `CORS_ORIGENES=https://mi-web.vercel.app` eso
levanta `SettingsError` y **el proceso no arranca** — que es exactamente lo que
pasó la primera vez que se configuró CORS en Render:

    SettingsError: error parsing value for field "cors_origenes"
                   from source "EnvSettingsSource"

El `field_validator(mode="before")` que parte por comas existía desde la Fase 6
y nunca llegaba a ejecutarse por env. Funcionaba al construir `Config(...)` en
una prueba —ahí no hay fuente de entorno— y por eso la suite decía que sí.

Con `NoDecode`, la cadena llega cruda al validador y él decide cómo leerla.
"""


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
    jwt_algoritmos: ListaDeTexto = ["ES256", "RS256", "HS256"]
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

    # --- Supabase -------------------------------------------------------
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = Field(
        default="",
        description=(
            "Llave de servicio del proyecto. **Solo el backend**: nunca llega "
            "al cliente (§10.7), porque salta RLS por completo. La usa el "
            "adaptador de la Admin API para crear la cuenta de un usuario "
            "nuevo (§5.1) y nada más. Sin ella, el alta responde 503 y el "
            "resto del sistema funciona igual."
        ),
    )

    # --- Jobs (Arq + Redis) ---------------------------------------------
    redis_url: str = ""

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

    # --- Expo Push (§12.2) ----------------------------------------------
    #
    # Expo acepta envíos **sin** token de acceso; el `EXPO_ACCESS_TOKEN` solo
    # hace falta si en el proyecto de Expo se activó "enhanced security". Por
    # eso el default es vacío y no un valor de mentira: en la mayoría de los
    # despliegues no se necesita, y exigirlo haría fallar el push por una
    # variable que nadie tenía que poner.
    expo_access_token: str = ""

    # --- Versión mínima del cliente móvil (§12.12) -----------------------
    #
    # Estas cuatro se cambian **sin desplegar código**, que es justo el punto:
    # el día que un cambio de contrato deje de tolerar a los clientes viejos,
    # mover `MOVIL_VERSION_MINIMA` en Render surte efecto en el siguiente
    # arranque de cada app. Un build nuevo tardaría días en llegar por Play,
    # y llegaría tarde precisamente a quien ya no puede usar la app.
    #
    # El default de `minima` es `0.0.0` a propósito: **no bloquear a nadie**.
    # Un entorno recién levantado no debe dejar fuera a los clientes por
    # olvido de configurar; el bloqueo tiene que ser una decisión explícita.
    movil_version_minima: str = Field(
        default="0.0.0",
        description="Por debajo de esta versión la API responde 426 y la app se bloquea (§12.12).",
    )
    movil_version_recomendada: str = Field(
        default="1.0.0",
        description="Última publicada en la tienda; por debajo la app solo sugiere actualizar.",
    )
    movil_url_tienda: str = Field(
        default="https://play.google.com/store/apps/details?id=com.obractrl.app",
        description="Destino del botón 'Actualizar' (§12.13).",
    )
    movil_mensaje_actualizacion: str = Field(
        default=(
            "Actualiza ObraCtrl para seguir capturando avances. Lo que ya "
            "capturaste sigue guardado en el teléfono."
        ),
        description="Texto que la app muestra tal cual; permite explicar el motivo sin publicar.",
    )

    # --- Evidencias (Cloudflare R2) -------------------------------------
    r2_endpoint: str = ""
    r2_bucket: str = "obractrl-evidencias"
    r2_access_key: str = ""
    r2_secret_key: str = ""

    # --- CORS: orígenes de Vercel por entorno (§12.8) -------------------
    cors_origenes: ListaDeTexto = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- Observabilidad --------------------------------------------------
    sentry_dsn: str = ""

    @field_validator("cors_origenes", "jwt_algoritmos", mode="before")
    @classmethod
    def _separar_lista(cls, v: object) -> object:
        """Lee una lista escrita como texto en una variable de entorno.

        Se aceptan las dos formas que un operador puede escribir, porque las
        dos son razonables y equivocarse cuesta un despliegue caído:

            CORS_ORIGENES=https://a.com,https://b.com
            CORS_ORIGENES=["https://a.com","https://b.com"]

        La segunda es la convención de pydantic-settings y alguien que la
        conozca la va a usar; la primera es la que documenta `OPERACION.md` y
        la que se escribe sin pensar. Un JSON mal formado **no** se descarta en
        silencio: se parte por comas, que para `["https://a.com"]` deja un
        valor visiblemente raro en `/health` en vez de una lista vacía que
        rechaza a todo el mundo sin decir por qué.
        """
        if not isinstance(v, str):
            return v

        texto = v.strip()
        if texto.startswith("["):
            try:
                cargado = json.loads(texto)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(cargado, list):
                    return [str(x).strip() for x in cargado if str(x).strip()]

        return [parte.strip() for parte in texto.split(",") if parte.strip()]

    @property
    def es_produccion(self) -> bool:
        return self.entorno == "prod"


@lru_cache
def obtener_config() -> Config:
    return Config()
