"""Endpoints del expediente técnico.

Spec §11.2 ("**Expediente** — `GET/POST /obras/{id}/expediente` — todos
lectura / **(C, SI)** subida · `GET /obras/{id}/expediente/pdf` (job)") · §7.9
· §11.3 D (el expediente sostiene el cierre de obra) · §12.11.

Controladores delgados: validan el DTO, delegan en el caso de uso y mapean el
resultado. **Cero lógica de negocio aquí** — el rol y las validaciones de alta
las decide `domain.expediente.reglas`, y las sumas de la vista agregada
`domain.reportes.expediente`.

Como en revisiones, la `url` de un documento es la **clave** de un objeto ya
subido a R2 con `POST /evidencias/presigned` (§12.2): el binario no viaja por
la API.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    AgregarDocumentoDep,
    ArmarExpedienteDep,
    ColaDeTrabajosDep,
    ConsultarExpedienteDep,
)
from obractrl.adapters.api.dependencias import ContextoActual, exigir_rol
from obractrl.adapters.api.v1.reportes import TrabajoRespuesta
from obractrl.adapters.export.trabajos import EXPEDIENTE_PDF
from obractrl.application.casos_uso.gestionar_expediente import (
    ComandoAgregarDocumento,
)
from obractrl.domain.expediente.reglas import ROLES_QUE_SUBEN, DocumentoExpediente
from obractrl.domain.reportes.expediente import ExpedienteTecnico
from obractrl.domain.shared.diccionario import Rol, TipoExpedienteDoc

router = APIRouter(tags=["expediente"])

FiltroTipo = Annotated[
    TipoExpedienteDoc | None,
    Query(description="Filtra por tipo de documento (§7.9)."),
]


class AgregarDocumentoPeticion(BaseModel):
    """Alta de un documento del expediente (§7.9)."""

    tipo: TipoExpedienteDoc = Field(
        description="plano | contrato | acta | evidencia | bitacora | otro (§7.9)."
    )
    nombre: str = Field(min_length=1, description="Nombre legible del documento.")
    url: str = Field(
        min_length=1,
        description=(
            "Clave del objeto ya subido a R2 con `POST /evidencias/presigned` "
            "(§12.2). El archivo no viaja por la API."
        ),
    )


class DocumentoRespuesta(BaseModel):
    id: UUID
    obra_id: UUID
    tipo: str
    nombre: str
    url: str
    subido_por: UUID | None
    fecha: datetime | None = None

    @classmethod
    def desde_dominio(
        cls, documento_id: UUID, documento: DocumentoExpediente
    ) -> DocumentoRespuesta:
        return cls(
            id=documento_id,
            obra_id=UUID(documento.obra_id),
            tipo=documento.tipo.value,
            nombre=documento.nombre,
            url=documento.url,
            subido_por=UUID(documento.subido_por),
            fecha=documento.fecha,
        )

    @classmethod
    def desde_fila(cls, fila: dict) -> DocumentoRespuesta:
        return cls(
            id=fila["id"],
            obra_id=fila["obra_id"],
            tipo=str(fila["tipo"]),
            nombre=fila["nombre"],
            url=fila["url"],
            subido_por=fila["subido_por"],
            fecha=fila["fecha"],
        )


class EvidenciaRespuesta(BaseModel):
    """Una clave de R2 referenciada por alguna entidad de la obra (§7.8)."""

    origen: str = Field(description="revision_fisica | incidencia | solicitud_cierre")
    origen_id: UUID
    clave: str
    fecha: datetime | None = None


class CierreDelExpedienteRespuesta(BaseModel):
    id: UUID
    actividad_id: UUID
    estatus: str
    cantidad: Decimal
    monto: Decimal
    fecha_valida: datetime | None = None


class EstimacionDelExpedienteRespuesta(BaseModel):
    id: UUID
    folio: str | None
    semana: int
    anio: int
    modo: str
    estatus: str
    monto: Decimal


class ExpedienteRespuesta(BaseModel):
    """Vista agregada del expediente (§11.2, §7.9).

    Los montos son los **validados**: un cierre sin validar o una estimación
    en borrador aún pueden cambiar, así que no suman (`ExpedienteTecnico`).
    """

    obra_id: UUID
    obra_clave: str
    obra_estatus: str | None
    avance_pct: Decimal
    generado_en: datetime
    documentos: list[DocumentoRespuesta]
    evidencias: list[EvidenciaRespuesta]
    cierres: list[CierreDelExpedienteRespuesta]
    estimaciones: list[EstimacionDelExpedienteRespuesta]
    monto_cerrado: Decimal
    monto_estimado: Decimal
    n_evidencias: int

    @classmethod
    def desde_dominio(cls, expediente: ExpedienteTecnico) -> ExpedienteRespuesta:
        return cls(
            obra_id=UUID(expediente.obra_id),
            obra_clave=expediente.obra_clave,
            obra_estatus=expediente.obra_estatus,
            avance_pct=expediente.avance_pct,
            generado_en=expediente.generado_en,
            documentos=[
                DocumentoRespuesta(
                    id=UUID(doc.id),
                    obra_id=UUID(expediente.obra_id),
                    tipo=doc.tipo.value,
                    nombre=doc.nombre,
                    url=doc.clave,
                    subido_por=UUID(doc.subido_por) if doc.subido_por else None,
                    fecha=doc.fecha,
                )
                for doc in expediente.documentos
            ],
            evidencias=[
                EvidenciaRespuesta(
                    origen=evidencia.origen,
                    origen_id=UUID(evidencia.origen_id),
                    clave=evidencia.clave,
                    fecha=_como_datetime(evidencia.fecha),
                )
                for evidencia in expediente.evidencias
            ],
            cierres=[
                CierreDelExpedienteRespuesta(
                    id=UUID(cierre.id),
                    actividad_id=UUID(cierre.actividad_id),
                    estatus=cierre.estatus.value,
                    cantidad=cierre.cantidad,
                    monto=cierre.monto.monto,
                    fecha_valida=cierre.fecha_valida,
                )
                for cierre in expediente.cierres
            ],
            estimaciones=[
                EstimacionDelExpedienteRespuesta(
                    id=UUID(estimacion.id),
                    folio=estimacion.folio,
                    semana=estimacion.semana,
                    anio=estimacion.anio,
                    modo=estimacion.modo,
                    estatus=estimacion.estatus.value,
                    monto=estimacion.monto.monto,
                )
                for estimacion in expediente.estimaciones
            ],
            monto_cerrado=expediente.monto_cerrado.monto,
            monto_estimado=expediente.monto_estimado.monto,
            n_evidencias=expediente.n_evidencias,
        )


def _como_datetime(valor: date | datetime | None) -> datetime | None:
    """`revision_fisica.fecha` es `date` y las otras dos son `timestamptz`
    (§7.8). El DTO expone un solo tipo para no partir el contrato de Orval.

    El orden del `isinstance` importa: `datetime` **hereda** de `date`, así
    que preguntar por `date` primero se tragaría los `timestamptz` y les
    borraría la hora.
    """
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor
    return datetime(valor.year, valor.month, valor.day)


@router.get(
    "/obras/{obra_id}/expediente",
    response_model=list[DocumentoRespuesta],
    summary="Documentos del expediente de una obra",
)
async def listar_expediente(
    obra_id: UUID, caso_uso: ConsultarExpedienteDep, tipo: FiltroTipo = None
) -> list[DocumentoRespuesta]:
    """Lectura para **todos** los roles (§11.2): RLS acota el alcance (§12.4)."""
    filas = await caso_uso.listar(obra_id, tipo=tipo)
    return [DocumentoRespuesta.desde_fila(fila) for fila in filas]


@router.post(
    "/obras/{obra_id}/expediente",
    response_model=DocumentoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar un documento al expediente",
    dependencies=[Depends(exigir_rol(*ROLES_QUE_SUBEN))],
    responses={
        403: {"description": "Solo Control de obra y Super intendente suben (§11.2)."},
        404: {"description": "La obra no existe o está fuera de tu alcance."},
        422: {"description": "Tipo, nombre o clave inválidos (§7.9)."},
    },
)
async def agregar_documento(
    obra_id: UUID,
    peticion: AgregarDocumentoPeticion,
    ctx: ContextoActual,
    caso_uso: AgregarDocumentoDep,
) -> DocumentoRespuesta:
    """C y SI suben documentos (§11.2).

    La guarda y el dominio comprueban el mismo rol, como en `revisiones.py`:
    `exigir_rol` da un 403 legible antes de tocar nada y
    `DocumentoExpediente.subir` deja la regla escrita una sola vez, donde vive
    el §6. La lista de roles no se duplica —las dos leen `ROLES_QUE_SUBEN` del
    dominio.

    La obra sale de la ruta, no del body: si no es visible, la política de
    `expediente_doc` rechaza el INSERT (§12.4).
    """
    agregado = await caso_uso.ejecutar(
        ComandoAgregarDocumento(
            obra_id=obra_id,
            usuario_id=ctx.usuario_id,
            rol=Rol(ctx.rol),
            tipo=peticion.tipo,
            nombre=peticion.nombre,
            url=peticion.url,
        )
    )
    return DocumentoRespuesta.desde_dominio(agregado.id, agregado.documento)


@router.get(
    "/obras/{obra_id}/expediente/vista",
    response_model=ExpedienteRespuesta,
    summary="Vista agregada del expediente: documentos, evidencias, cierres y estimaciones",
    responses={404: {"description": "La obra no existe o está fuera de tu alcance."}},
)
async def vista_del_expediente(
    obra_id: UUID, caso_uso: ArmarExpedienteDep
) -> ExpedienteRespuesta:
    """Todo el acervo de la obra en una respuesta (§7.9, §11.2).

    El §11.2 solo nombra el PDF como salida del expediente; esta vista es su
    equivalente en JSON —los **mismos** datos y las **mismas** sumas, del
    mismo agregado de dominio— para que la web no tenga que descargar un PDF
    para pintar la pantalla (§11.3 D, "C calidad/expediente").
    """
    return ExpedienteRespuesta.desde_dominio(await caso_uso.ejecutar(obra_id))


@router.get(
    "/obras/{obra_id}/expediente/pdf",
    response_model=TrabajoRespuesta,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generar el PDF del expediente (job)",
    responses={
        503: {"description": "La cola de trabajos no está disponible (§12.8)."},
    },
)
async def pdf_del_expediente(
    obra_id: UUID, ctx: ContextoActual, cola: ColaDeTrabajosDep
) -> TrabajoRespuesta:
    """El §11.2 lo marca como **job**: encola y devuelve el identificador.

    No se genera en la petición a propósito: WeasyPrint es CPU y un expediente
    grande bloquearía el único worker de la API (§12.8). El estado y la
    descarga se consultan en `GET /reportes/{id}` (§11.2).

    El alcance del que pide viaja al worker y ahí se vuelve a fijar como
    contexto RLS: encolar **no** amplía lo que ese usuario puede ver
    (`adapters/export/trabajos.py`).
    """
    encolado = await cola.encolar(
        EXPEDIENTE_PDF,
        org_id=str(ctx.org_id),
        usuario_id=str(ctx.usuario_id),
        rol=ctx.rol,
        obra_id=str(obra_id),
    )
    return TrabajoRespuesta.desde(encolado)
