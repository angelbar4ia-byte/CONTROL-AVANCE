"""Endpoint de evidencias: URL firmada para subir directo a R2.

Spec §11.2 ("**Evidencias** — `POST /evidencias/presigned` — URL firmada para
subir directo a R2 (todos)") · §12.2 (stack: el backend emite presigned URLs,
el móvil sube en segundo plano) · §12.4 (seguridad).

**El archivo no pasa por aquí.** El endpoint solo firma; el cliente hace el
`PUT` contra R2 con la URL que recibe y luego referencia la `clave` desde la
entidad que corresponda: `revision_fisica.fotos`, `incidencia.evidencias`,
`solicitud_cierre.adjuntos`, `expediente_doc.url` (§7.8, §7.9).

**Todos** los roles pueden pedir una firma (§11.2), así que no lleva
`exigir_rol` — pero la clave del objeto la arma el servidor con el `org_id`
del token (`infrastructure.storage.r2.clave_de_evidencia`), no el cliente:
R2 no tiene RLS que aísle por organización, ese prefijo es la frontera
equivalente (§12.4). Sin él, cualquier usuario autenticado podría pedir una
firma para sobrescribir el objeto de otra organización.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from obractrl.adapters.api.dependencias import ContextoActual
from obractrl.infrastructure.storage.r2 import (
    SubidaFirmada,
    clave_de_evidencia,
    firmar_subida,
)

router = APIRouter(tags=["evidencias"])


class PresignedPeticion(BaseModel):
    """Lo que el cliente propone: nombre y tipo. La ruta la decide el servidor."""

    nombre_archivo: str = Field(
        min_length=1,
        description=(
            "Nombre original del archivo. Solo se usa como sufijo legible de "
            "la clave; el servidor lo sanea y le antepone el prefijo de la "
            "organización."
        ),
    )
    content_type: str = Field(
        default="application/octet-stream",
        min_length=1,
        description="Tipo MIME con el que se firmará el PUT; el cliente debe mandarlo igual.",
    )
    obra_id: UUID | None = Field(
        default=None,
        description="Agrupa la evidencia bajo la obra dentro del bucket (opcional).",
    )


class PresignedRespuesta(BaseModel):
    """URL firmada y la clave con la que se referenciará después.

    No incluye —ni puede incluir— ninguna credencial de R2: la firma es un
    HMAC derivado del secreto, no el secreto. Ver el docstring de
    `infrastructure.storage.r2`.
    """

    url: str = Field(description="URL firmada; caduca. Súbelo con el método indicado.")
    clave: str = Field(description="Clave del objeto en el bucket; esto es lo que se persiste.")
    metodo: str
    content_type: str
    expira_en_segundos: int
    expira_en: datetime

    @classmethod
    def desde_firma(cls, firma: SubidaFirmada) -> PresignedRespuesta:
        return cls(
            url=firma.url,
            clave=firma.clave,
            metodo=firma.metodo,
            content_type=firma.content_type,
            expira_en_segundos=firma.expira_en_segundos,
            expira_en=firma.expira_en,
        )


@router.post(
    "/evidencias/presigned",
    response_model=PresignedRespuesta,
    summary="URL firmada para subir una evidencia directo a R2",
    responses={
        503: {
            "description": (
                "El almacenamiento de evidencias no está configurado en este "
                "entorno (§12.8)."
            )
        }
    },
)
async def firmar_evidencia(
    peticion: PresignedPeticion, ctx: ContextoActual
) -> PresignedRespuesta:
    """Emite la URL firmada (§11.2, §12.2). El archivo no viaja por la API.

    `firmar_subida` es cómputo local —SigV4 no llama a R2—, así que no bloquea
    el event loop pese a que `boto3` sea síncrono.
    """
    clave = clave_de_evidencia(
        org_id=ctx.org_id,
        nombre_archivo=peticion.nombre_archivo,
        obra_id=peticion.obra_id,
    )
    firma = firmar_subida(clave=clave, content_type=peticion.content_type)
    return PresignedRespuesta.desde_firma(firma)
