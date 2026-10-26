"""Evidencias en Cloudflare R2: firma de URLs de subida.

Spec §12.2 ("Evidencias — **Cloudflare R2** (o S3): backend emite **presigned
URLs**; el móvil sube fotos en segundo plano") · §12.2 diagrama (`API
-->|presigned URL| R2`, `M -->|upload directo| R2`) · §12.4 (seguridad).

**El archivo nunca pasa por el backend.** Este módulo solo firma: calcula una
URL con la firma SigV4 embebida y la devuelve; el cliente hace el `PUT`
directo contra R2. Por eso el endpoint no recibe `multipart` ni abre un stream
—si el binario viajara por la API, un lote de fotos de campo saturaría el
único worker de Render (§12.8) para nada.

Qué sale y qué no en la URL firmada (§12.4):

- **Sale** el `AccessKeyId`, dentro de `X-Amz-Credential`. Es inevitable y es
  correcto: SigV4 exige decirle a R2 con qué llave verificar la firma, igual
  que un JWT dice su `kid`. Un `AccessKeyId` sin su secreto no abre nada.
- **No sale nunca** `r2_secret_key`. La firma es un HMAC derivado del secreto;
  de ella no se puede volver al secreto. Que el secreto no aparezca en la URL
  ni en un log es lo que `tests/integracion/test_evidencias_presigned.py`
  verifica explícitamente.

La URL además nace acotada: caduca (`expira_en`) y vale solo para **esa** clave
y ese verbo. Quien la reciba no puede subir a otra ruta ni leer nada.

`boto3` es síncrono, pero `generate_presigned_url` **no hace red**: es puro
cómputo local de la firma sobre credenciales que ya están en memoria. Por eso
se puede llamar desde una corrutina sin mandarlo a un hilo — no bloquea el
event loop más que una llamada a `hmac`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID, uuid4

import boto3
from botocore.config import Config as ConfigBoto

from obractrl.infrastructure.config import Config, obtener_config

__all__ = [
    "AlmacenamientoNoConfigurado",
    "SubidaFirmada",
    "clave_de_evidencia",
    "firmar_subida",
]

EXPIRACION_POR_DEFECTO = timedelta(minutes=15)
"""Ventana de la URL firmada. Alcanza de sobra para una foto desde campo y
deja la credencial temporal inútil en cuanto vence (§12.4)."""

_NO_SEGURO = re.compile(r"[^A-Za-z0-9._-]+")


class AlmacenamientoNoConfigurado(RuntimeError):
    """Faltan credenciales de R2 en el entorno (§12.8).

    Es un fallo **de despliegue**, no del cliente: la API está arriba pero no
    puede firmar nada. Se distingue a propósito de un error genérico para que
    el borde responda un 503 legible en vez de un 500 opaco —el mismo criterio
    con el que `/health` reporta `jwks_url` sin exponer secretos (`main.py`).
    """


@dataclass(frozen=True, slots=True)
class SubidaFirmada:
    """Lo que el cliente necesita para subir y para referenciar después.

    `clave` es lo que se guarda en `revision_fisica.fotos`,
    `incidencia.evidencias` o `expediente_doc.url` (§7.8, §7.9): la URL firmada
    caduca, la clave no.
    """

    url: str
    clave: str
    metodo: str
    content_type: str
    expira_en_segundos: int
    expira_en: datetime


def _saneado(nombre: str) -> str:
    """Nombre de archivo reducido a ASCII seguro para una clave de objeto.

    Las fotos de campo llegan con nombres de teléfono (`IMG_20260814 (1).jpg`,
    acentos, a veces una ruta entera). Sin sanear, un `../` en el nombre
    cambiaría el prefijo de la clave y sacaría el objeto del espacio de su
    organización — que es justo lo que el prefijo por `org_id` evita.
    """
    plano = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    limpio = _NO_SEGURO.sub("-", plano).strip("-.")
    return limpio[:120] or "evidencia"


def clave_de_evidencia(
    *, org_id: UUID, nombre_archivo: str, obra_id: UUID | None = None
) -> str:
    """Clave del objeto en el bucket, derivada **en el servidor** (§12.4).

    El cliente propone el nombre, no la ruta: el prefijo sale de `org_id` —que
    viene del token, nunca de la petición (`adapters/api/dependencias.py`)— y
    de un UUID nuevo. Así dos organizaciones no pueden colisionar ni pisarse
    objetos aunque manden el mismo nombre, que es el aislamiento del §12.4
    llevado al bucket: R2 no tiene RLS que lo imponga por debajo.
    """
    ambito = f"obras/{obra_id}/" if obra_id else ""
    return f"{org_id}/{ambito}{uuid4()}/{_saneado(nombre_archivo)}"


@lru_cache(maxsize=2)
def _cliente(endpoint: str, access_key: str, secret_key: str) -> object:
    """Cliente S3 apuntado a R2, cacheado: crearlo es caro y no tiene estado
    por petición. R2 no tiene regiones, `auto` es lo que espera su endpoint.

    Se cachea por credenciales y no por el objeto `Config` —que no es
    hashable— así que una rotación de llaves entra sola con la config nueva,
    sin reiniciar el proceso.
    """
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=ConfigBoto(signature_version="s3v4"),
    )


def _exigir_configuracion(cfg: Config) -> None:
    """Falla con `AlmacenamientoNoConfigurado` si falta cualquier credencial."""
    faltantes = [
        nombre
        for nombre, valor in (
            ("R2_ENDPOINT", cfg.r2_endpoint),
            ("R2_BUCKET", cfg.r2_bucket),
            ("R2_ACCESS_KEY", cfg.r2_access_key),
            ("R2_SECRET_KEY", cfg.r2_secret_key),
        )
        if not valor
    ]
    if faltantes:
        # Se nombran las variables que faltan, nunca su valor: quien opera el
        # despliegue necesita saber cuál poner, y el nombre no es secreto.
        raise AlmacenamientoNoConfigurado(
            "El almacenamiento de evidencias no está configurado en este "
            f"entorno; faltan: {', '.join(faltantes)} (§12.8)."
        )


def firmar_subida(
    *,
    clave: str,
    content_type: str,
    cfg: Config | None = None,
    expira_en: timedelta = EXPIRACION_POR_DEFECTO,
) -> SubidaFirmada:
    """URL firmada para un `PUT` directo a R2 (§12.2).

    Levanta `AlmacenamientoNoConfigurado` si falta cualquier credencial: sin
    ella `boto3` firmaría igual y el fallo aparecería recién en el `PUT` del
    cliente, como un 403 de R2 imposible de diagnosticar desde el móvil.
    """
    cfg = cfg or obtener_config()
    _exigir_configuracion(cfg)

    segundos = int(expira_en.total_seconds())
    cliente = _cliente(cfg.r2_endpoint, cfg.r2_access_key, cfg.r2_secret_key)
    url = cliente.generate_presigned_url(  # type: ignore[attr-defined]
        "put_object",
        Params={
            "Bucket": cfg.r2_bucket,
            "Key": clave,
            "ContentType": content_type,
        },
        ExpiresIn=segundos,
        HttpMethod="PUT",
    )
    return SubidaFirmada(
        url=url,
        clave=clave,
        metodo="PUT",
        content_type=content_type,
        expira_en_segundos=segundos,
        # Instante absoluto además de la ventana: la cola del móvil puede
        # quedarse días sin red (§12.2), y con solo "900 segundos" no sabría
        # si la URL que guardó sigue sirviendo. En UTC, como toda marca de
        # tiempo del sistema (§3.1).
        expira_en=datetime.now(UTC) + expira_en,
    )


@dataclass(frozen=True, slots=True)
class DescargaFirmada:
    """URL firmada para leer un objeto; caduca, la clave no."""

    url: str
    expira_en_segundos: int
    expira_en: datetime


def firmar_descarga(
    *,
    clave: str,
    cfg: Config | None = None,
    expira_en: timedelta = EXPIRACION_POR_DEFECTO,
) -> DescargaFirmada:
    """URL firmada para un `GET` directo a R2.

    Es el par de `firmar_subida`: quien la pide ya probó que ve el objeto que
    lo referencia (RLS sobre la fila), pero R2 no tiene RLS, así que **quien
    llama** debe comprobar que la clave cuelga del prefijo de su organización
    antes de firmar — la clave que guarda una fila la escribió un cliente.
    """
    cfg = cfg or obtener_config()
    _exigir_configuracion(cfg)

    segundos = int(expira_en.total_seconds())
    cliente = _cliente(cfg.r2_endpoint, cfg.r2_access_key, cfg.r2_secret_key)
    url = cliente.generate_presigned_url(  # type: ignore[attr-defined]
        "get_object",
        Params={"Bucket": cfg.r2_bucket, "Key": clave},
        ExpiresIn=segundos,
        HttpMethod="GET",
    )
    return DescargaFirmada(
        url=url,
        expira_en_segundos=segundos,
        expira_en=datetime.now(UTC) + expira_en,
    )
