"""Endpoints de reportes: encolar, consultar y descargar.

Spec §11.2 ("`GET /estimaciones/{id}/export` (xlsx, **job**) — (C, SI)";
"**Reportes** — … (job), por alcance · `GET /reportes/{id}` (estado/descarga)")
· §11.3 E.5 · §12.2 (Arq + Redis) · §12.8.

**Por qué encolar y no generar en línea.** El §11.2 marca los dos reportes
como *job*. Generar un `.xlsx` con openpyxl —o peor, un PDF con WeasyPrint— es
CPU pura dentro del event loop: en el plan chico de Render (§12.8) un reporte
grande deja a todos los demás esperando. Encolar devuelve en milisegundos y el
worker (`obractrl/trabajador.py`) hace el trabajo.

**Dos endpoints donde el §11.2 escribe uno.** El spec dice `GET /reportes/{id}`
(estado/descarga). Aquí son `GET /reportes/{id}` —JSON con el estado— y
`GET /reportes/{id}/descargar` —el archivo—. El motivo es de contrato, no de
diseño: un endpoint que a veces responde JSON y a veces binario no se puede
declarar en OpenAPI con un solo `response_model`, y Orval genera los hooks
desde ese esquema (§12.2). El estado trae el enlace de descarga, así que el
cliente sigue el mismo camino que describe el spec.

`GET /estimaciones/{id}/export` **encola**, aunque sea un GET: así lo nombra el
§11.2. No es idempotente en sentido estricto —dos llamadas dejan dos trabajos—
pero tampoco muta nada del dominio: el archivo se genera de lo que ya está en
la base.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import ColaDeTrabajosDep
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.export.trabajos import EXPORTAR_ESTIMACION_XLSX
from obractrl.domain.shared.diccionario import Rol
from obractrl.infrastructure.jobs.cola import (
    EstadoTrabajo,
    ResultadoTrabajo,
    TrabajoEncolado,
)

router = APIRouter(tags=["reportes"])

BASE_REPORTES = "/reportes"


class TrabajoRespuesta(BaseModel):
    """Identificador con el que se sigue un reporte encolado (§11.2)."""

    id: str = Field(description="Identificador del reporte; se consulta en /reportes/{id}.")
    estatus: str = Field(
        description=(
            "en_cola | en_proceso | listo | fallido. Mientras no sea `listo`, "
            "la descarga responde 409."
        )
    )
    consulta: str = Field(description="Ruta donde consultar el estado.")
    descarga: str = Field(description="Ruta de descarga, válida cuando esté `listo`.")

    @classmethod
    def desde(cls, encolado: TrabajoEncolado) -> TrabajoRespuesta:
        return cls(
            id=encolado.id,
            estatus=encolado.estatus,
            consulta=f"{BASE_REPORTES}/{encolado.id}",
            descarga=f"{BASE_REPORTES}/{encolado.id}/descargar",
        )

    @classmethod
    def desde_resultado(cls, resultado: ResultadoTrabajo) -> TrabajoRespuesta:
        return cls(
            id=resultado.id,
            estatus=resultado.estatus,
            consulta=f"{BASE_REPORTES}/{resultado.id}",
            descarga=f"{BASE_REPORTES}/{resultado.id}/descargar",
        )


class EstadoReporteRespuesta(TrabajoRespuesta):
    """Estado del reporte y, si terminó, cómo se llama el archivo."""

    listo: bool
    nombre_archivo: str | None = None
    content_type: str | None = None
    error: str | None = Field(
        default=None,
        description=(
            "Clase del fallo del worker. El detalle queda en el log del "
            "servidor, no en la respuesta (§12.4)."
        ),
    )

    @classmethod
    def desde_resultado(cls, resultado: ResultadoTrabajo) -> EstadoReporteRespuesta:
        archivo = _archivo_de(resultado)
        return cls(
            id=resultado.id,
            estatus=resultado.estatus,
            consulta=f"{BASE_REPORTES}/{resultado.id}",
            descarga=f"{BASE_REPORTES}/{resultado.id}/descargar",
            listo=resultado.listo,
            nombre_archivo=archivo.get("nombre") if archivo else None,
            content_type=archivo.get("content_type") if archivo else None,
            error=resultado.error,
        )


def _archivo_de(resultado: ResultadoTrabajo) -> dict | None:
    """El `dict` que devolvió el trabajo, si terminó bien.

    Se comprueba la forma en vez de confiar: el resultado viaja deserializado
    desde Redis, y un worker de una versión anterior pudo devolver otra cosa.
    """
    if not resultado.listo or not isinstance(resultado.valor, dict):
        return None
    return resultado.valor if "contenido" in resultado.valor else None


@router.get(
    "/estimaciones/{estimacion_id}/export",
    response_model=TrabajoRespuesta,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Exportar una estimación a Excel (job)",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))],
    responses={
        503: {"description": "La cola de trabajos no está disponible (§12.8)."},
    },
)
async def exportar_estimacion(
    estimacion_id: UUID, ctx: ContextoActual, cola: ColaDeTrabajosDep
) -> TrabajoRespuesta:
    """Encola el `.xlsx` de la estimación (§11.2, roles C y SI).

    La estimación **no se lee aquí**: si no existe o está fuera del alcance,
    el trabajo falla en el worker con el mismo `EstimacionNoEncontrada` y el
    estado sale `fallido`. Comprobarlo antes solo duplicaría la consulta —y
    el alcance del worker es el mismo, porque el contexto RLS viaja con el
    trabajo (`adapters/export/trabajos.py`).
    """
    encolado = await cola.encolar(
        EXPORTAR_ESTIMACION_XLSX,
        org_id=str(ctx.org_id),
        usuario_id=str(ctx.usuario_id),
        rol=ctx.rol,
        estimacion_id=str(estimacion_id),
    )
    return TrabajoRespuesta.desde(encolado)


@router.get(
    f"{BASE_REPORTES}/{{reporte_id}}",
    response_model=EstadoReporteRespuesta,
    summary="Estado de un reporte encolado",
    responses={
        404: {"description": "El reporte no existe o su resultado ya expiró."},
        503: {"description": "La cola de trabajos no está disponible (§12.8)."},
    },
)
async def estado_de_reporte(
    reporte_id: str, cola: ColaDeTrabajosDep
) -> EstadoReporteRespuesta:
    """§11.2 `GET /reportes/{id}` (estado). La descarga va aparte; ver el
    encabezado del módulo."""
    return EstadoReporteRespuesta.desde_resultado(await cola.consultar(reporte_id))


@router.get(
    f"{BASE_REPORTES}/{{reporte_id}}/descargar",
    summary="Descargar un reporte terminado",
    response_class=Response,
    responses={
        200: {"description": "El archivo generado (.xlsx o .pdf)."},
        404: {"description": "El reporte no existe o su resultado ya expiró."},
        409: {"description": "El reporte todavía no está listo, o falló."},
        503: {"description": "La cola de trabajos no está disponible (§12.8)."},
    },
)
async def descargar_reporte(reporte_id: str, cola: ColaDeTrabajosDep) -> Response:
    """§11.2 `GET /reportes/{id}` (descarga)."""
    resultado = await cola.consultar(reporte_id)
    archivo = _archivo_de(resultado)

    if archivo is None:
        detalle = (
            f"El reporte {reporte_id} falló en el worker ({resultado.error})."
            if resultado.estatus == EstadoTrabajo.FALLIDO
            else f"El reporte {reporte_id} todavía no está listo ({resultado.estatus})."
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)

    nombre = str(archivo.get("nombre") or f"{reporte_id}.bin")
    return Response(
        content=archivo["contenido"],
        media_type=str(archivo.get("content_type") or "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
