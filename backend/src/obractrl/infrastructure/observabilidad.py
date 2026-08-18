"""Logs, id de petición y Sentry.

Spec §11.7 ("**logs separados**: bitácora de negocio vs log técnico") · §12.2
(Sentry) · §12.4 (no exponer secretos) · §12.8 (entornos).

Tres piezas que resuelven un solo problema: **poder reconstruir qué pasó**.

- `id_de_peticion()` — el hilo que cose una respuesta de error, sus líneas de
  log y su evento de Sentry. Sin él, un 500 en Render es una traza suelta que
  nadie puede cruzar con el reporte del usuario.
- `configurar_logging()` — un formato único que lleva ese id en cada línea.
- `iniciar_sentry()` — silencioso si no hay DSN, igual que `ClienteResend` sin
  API key: un entorno sin observabilidad configurada tiene que arrancar (§12.8).

**Por qué un `ContextVar` y no un parámetro.** El id lo necesita quien registra
—un repositorio, un caso de uso, el manejador de errores—, y hacerlo viajar por
firma obligaría a que `application` y `domain` conocieran un concepto de HTTP,
que es exactamente lo que el §12.11 prohíbe. `ContextVar` es de asyncio: cada
petición corre en su propio contexto, así que dos peticiones concurrentes no se
pisan el id.

Este módulo **no importa Starlette**: el middleware que lee la cabecera vive en
`adapters/api/middleware.py`, que es donde está el borde HTTP. Aquí solo queda
lo que también sirve fuera de una petición —el worker de jobs registra con el
mismo formato—.
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

from obractrl.infrastructure.config import Config

__all__ = [
    "FiltroDeIdDePeticion",
    "configurar_logging",
    "id_de_peticion",
    "iniciar_sentry",
    "nuevo_id_de_peticion",
    "poner_id_de_peticion",
]

_log = logging.getLogger(__name__)

SIN_PETICION = "-"
"""Lo que se registra fuera de una petición: el worker de jobs, el arranque."""

_ID_PETICION: ContextVar[str] = ContextVar("id_peticion", default=SIN_PETICION)


def id_de_peticion() -> str:
    """Id de la petición en curso, o `-` si no hay ninguna."""
    return _ID_PETICION.get()


def poner_id_de_peticion(valor: str) -> None:
    _ID_PETICION.set(valor)


def nuevo_id_de_peticion(entrante: str | None = None) -> str:
    """Toma el id que trae el cliente o genera uno.

    Se acepta el entrante para poder seguir una petición **a través** de los
    servicios: si el front ya trae un id de su propia traza, cortarlo aquí
    partiría el hilo justo donde más se necesita.

    Se acota a 64 caracteres y a un alfabeto seguro porque el valor va a
    parar a un log y a una cabecera de respuesta: un id con saltos de línea
    inyectaría renglones falsos en la bitácora (log forging), y uno de 8 KB
    la llenaría de basura. Si lo que llega no sirve, se genera uno nuevo en
    vez de rechazar la petición — el id es diagnóstico, no autenticación.
    """
    limpio = (entrante or "").strip()[:64]
    if limpio and all(c.isalnum() or c in "-_." for c in limpio):
        return limpio
    return uuid.uuid4().hex


class FiltroDeIdDePeticion(logging.Filter):
    """Pone `id_peticion` en cada registro para que el formato lo pueda usar.

    Es un `Filter` y no un `LoggerAdapter` porque tiene que aplicar a **todo**
    lo que se registre —incluido lo que emiten uvicorn, SQLAlchemy o una
    biblioteca de terceros—, no solo a los loggers propios.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.id_peticion = id_de_peticion()
        return True


FORMATO = "%(asctime)s %(levelname)-8s [%(id_peticion)s] %(name)s: %(message)s"


def configurar_logging(cfg: Config) -> None:
    """Deja un solo handler con el formato de la casa.

    Se **reemplazan** los handlers de la raíz en vez de agregar uno: uvicorn
    instala los suyos y sumarle otro duplica cada línea. Al reasignar, todo
    —el log de la app y el de uvicorn— sale con el mismo formato y el mismo
    id de petición.

    `sqlalchemy.engine` se deja en WARNING a propósito, incluso en debug: en
    INFO registra **cada sentencia con sus parámetros**, y esos parámetros son
    datos de la organización (§12.4). Quien necesite ver el SQL lo enciende a
    mano, que es una decisión consciente y no un default que se filtra a
    producción.
    """
    manejador = logging.StreamHandler(sys.stdout)
    manejador.setFormatter(logging.Formatter(FORMATO))
    manejador.addFilter(FiltroDeIdDePeticion())

    raiz = logging.getLogger()
    raiz.handlers = [manejador]
    raiz.setLevel(logging.DEBUG if cfg.debug else logging.INFO)

    for ruidoso in ("uvicorn.access", "uvicorn.error"):
        # Que no lleven handler propio: así heredan el de la raíz —formato e
        # id incluidos— en vez de escribir por su cuenta.
        logging.getLogger(ruidoso).handlers = []
        logging.getLogger(ruidoso).propagate = True

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def iniciar_sentry(cfg: Config) -> bool:
    """Arranca Sentry si hay DSN. Devuelve si quedó activo.

    **No levanta y no es obligatorio.** Sin DSN se registra y se sigue: mismo
    criterio que `ClienteResend` sin API key (§12.8). Un entorno de desarrollo
    —o un despliegue al que todavía no le pusieron la variable— tiene que
    arrancar igual.

    `send_default_pii=False` explícito: el default del SDK ya es ése, pero
    dejarlo escrito es lo que impide que un cambio de default mande correos y
    encabezados de usuarios a un tercero (§12.4).
    """
    if not cfg.sentry_dsn.strip():
        _log.info("Sentry no configurado en este entorno (falta SENTRY_DSN).")
        return False

    try:
        import sentry_sdk
    except ImportError:  # pragma: no cover - viene en las dependencias
        _log.warning("SENTRY_DSN está puesto pero `sentry-sdk` no está instalado.")
        return False

    sentry_sdk.init(
        dsn=cfg.sentry_dsn,
        environment=cfg.entorno,
        # Sin trazas de rendimiento por default: a la escala del §12.1 el
        # valor está en los errores, y el muestreo de transacciones es lo que
        # hace cara la factura sin que nadie lo mire.
        traces_sample_rate=0.0,
        send_default_pii=False,
    )
    _log.info("Sentry activo (entorno=%s).", cfg.entorno)
    return True
