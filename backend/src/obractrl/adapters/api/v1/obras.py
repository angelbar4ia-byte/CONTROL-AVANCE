"""Endpoints de obra.

Spec §11.2 (Proyecto · Obra) · §7.2 · §11.3 workflow A.

Controladores delgados: validan el DTO, delegan en el caso de uso y mapean el
resultado. **Cero lógica de negocio aquí** (§12.11) — las invariantes viven en
`domain.obras.reglas` y la planeación del workflow A en
`domain.obras.generacion`.

Roles (§11.2): `GET /obras` y `GET /obras/{id}` son de todos —RLS acota el
alcance de cada rol (§4)—; el alta, la edición, la generación y el alta masiva
son de **Control de obra**, que es quien tiene "Creador de obra" en su
Configuración (§5.1).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    ActualizarObraDep,
    CrearObraDep,
    CrearObrasEnLoteDep,
    GenerarObraDesdePrototipoDep,
)
from obractrl.adapters.api.dependencias import SesionRLS, exigir_rol
from obractrl.adapters.api.idempotencia import Idempotencia
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.application.casos_uso.generar_obra_desde_prototipo import (
    ComandoGenerarObra,
    ObraNoEncontrada,
)
from obractrl.application.casos_uso.gestionar_obra import (
    SIN_CAMBIO,
    ComandoActualizarObra,
    ComandoCrearObra,
    ComandoCrearObrasEnLote,
)
from obractrl.domain.obras.reglas import Obra
from obractrl.domain.shared.diccionario import EstatusObra, ModoPago, Rol

router = APIRouter(tags=["obras"])

CREADOR_DE_OBRA = Depends(exigir_rol(Rol.CONTROL_OBRA))
"""Alta, edición y generación de obras: Control de obra (§5.1, §11.2)."""

_NO_ENCONTRADA: dict[int | str, dict[str, Any]] = {
    404: {"description": "La obra no existe o está fuera de tu alcance."}
}
"""Los tres endpoints por id devuelven lo mismo cuando RLS no deja ver la obra."""


class CrearObraPeticion(BaseModel):
    """Alta de obra (§11.3 A.1)."""

    cluster_id: UUID
    clave: str = Field(min_length=1, description="CLUSTER + LOTE, p. ej. 'FRESNO 01' (§10.1).")
    prototipo_id: UUID | None = Field(
        default=None,
        description="Obligatorio salvo en urbanización (`es_urba`), §7.2.",
    )
    residente_id: UUID | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    m2: Decimal | None = None
    es_urba: bool = False


class CrearObrasEnLotePeticion(BaseModel):
    """Alta masiva (§11.2 `POST /obras/bulk`). O entran todas o no entra ninguna."""

    obras: list[CrearObraPeticion] = Field(min_length=1)


class ActualizarObraPeticion(BaseModel):
    """Edición parcial (§11.2 `PATCH /obras/{id}`).

    El `estatus` no se edita por aquí: lo deriva el avance y lo cierra el
    cierre de obra final (§6, §11.3 D). `cluster_id` tampoco: mover una obra
    de cluster la saca de su proyecto y con eso de su alcance.
    """

    clave: str | None = Field(default=None, min_length=1)
    residente_id: UUID | None = Field(
        default=None, description="Manda `null` para liberar la obra."
    )
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    m2: Decimal | None = None


class GenerarObraPeticion(BaseModel):
    """Workflow A (§11.3 A.2)."""

    modo_pago: ModoPago = Field(
        default=ModoPago.DESTAJO,
        description="Cómo se pagan las actividades generadas (§6).",
    )


class ObraRespuesta(BaseModel):
    id: UUID
    cluster_id: UUID
    prototipo_id: UUID | None
    clave: str
    residente_id: UUID | None
    estatus: str
    fecha_inicio: date | None
    fecha_fin: date | None
    avance_pct: Decimal
    m2: Decimal | None
    es_urba: bool

    @classmethod
    def desde_dominio(cls, obra_id: UUID, obra: Obra) -> ObraRespuesta:
        return cls(
            id=obra_id,
            cluster_id=UUID(obra.cluster_id),
            prototipo_id=UUID(obra.prototipo_id) if obra.prototipo_id else None,
            clave=str(obra.clave),
            residente_id=UUID(obra.residente_id) if obra.residente_id else None,
            estatus=obra.estatus.value,
            fecha_inicio=obra.fecha_inicio,
            fecha_fin=obra.fecha_fin,
            avance_pct=obra.avance.pct,
            m2=obra.m2,
            es_urba=obra.es_urba,
        )

    @classmethod
    def desde_fila(cls, fila: dict) -> ObraRespuesta:
        return cls(
            id=fila["id"],
            cluster_id=fila["cluster_id"],
            prototipo_id=fila["prototipo_id"],
            clave=fila["clave"],
            residente_id=fila["residente_id"],
            estatus=fila["estatus"],
            fecha_inicio=fila["fecha_inicio"],
            fecha_fin=fila["fecha_fin"],
            avance_pct=fila["avance_pct"],
            m2=fila["m2"],
            es_urba=fila["es_urba"],
        )


class ObraGeneradaRespuesta(BaseModel):
    """Resultado del workflow A: qué se creó y sobre qué programa (§11.3 A)."""

    obra_id: UUID
    programa_obra_id: UUID
    n_actividades: int


@router.get(
    "/obras",
    response_model=list[ObraRespuesta],
    summary="Obras dentro del alcance del rol",
)
async def listar_obras(
    sesion: SesionRLS,
    proyecto_id: Annotated[UUID | None, Query(description="Acota al proyecto.")] = None,
    cluster_id: Annotated[UUID | None, Query(description="Acota al cluster.")] = None,
    residente_id: Annotated[
        UUID | None, Query(description="Obras de un residente (§4).")
    ] = None,
    prototipo_id: Annotated[
        UUID | None,
        Query(description="Obras construidas con el mismo modelo de casa (§7.2)."),
    ] = None,
    estatus: Annotated[
        EstatusObra | None, Query(description="Filtra por estatus de obra (§8.2).")
    ] = None,
) -> list[ObraRespuesta]:
    """Todos los roles, cada uno con su alcance (§4).

    Lectura simple sin orquestación de dominio —como `GET /cierres`
    (`adapters/api/v1/cierres.py`)— así que consulta el repo directo: RLS ya
    acota el alcance (§12.4).
    """
    filas = await RepositorioObrasSQL(sesion).listar(
        proyecto_id=proyecto_id,
        cluster_id=cluster_id,
        residente_id=residente_id,
        prototipo_id=prototipo_id,
        estatus=estatus.value if estatus else None,
    )
    return [ObraRespuesta.desde_fila(fila) for fila in filas]


@router.get(
    "/obras/{obra_id}",
    response_model=ObraRespuesta,
    summary="Detalle de una obra",
    responses=_NO_ENCONTRADA,
)
async def obtener_obra(obra_id: UUID, sesion: SesionRLS) -> ObraRespuesta:
    """Todos los roles, por alcance (§11.2)."""
    fila = await RepositorioObrasSQL(sesion).obtener(obra_id)
    if fila is None:
        # RLS hace indistinguible "no existe" de "no la puedes ver" (§12.4):
        # el 404 sale del manejador de `ObraNoEncontrada` en `main.py`.
        raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
    return ObraRespuesta.desde_fila(fila)


@router.post(
    "/obras",
    response_model=ObraRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de obra",
    dependencies=[CREADOR_DE_OBRA],
    responses={422: {"description": "Datos de obra inválidos (§7.2)."}},
)
async def crear_obra(
    peticion: CrearObraPeticion, caso_uso: CrearObraDep
) -> ObraRespuesta:
    """Control de obra crea la obra (cluster, prototipo, residente) (§11.3 A.1)."""
    creada = await caso_uso.ejecutar(
        ComandoCrearObra(
            cluster_id=peticion.cluster_id,
            clave=peticion.clave,
            prototipo_id=peticion.prototipo_id,
            residente_id=peticion.residente_id,
            fecha_inicio=peticion.fecha_inicio,
            fecha_fin=peticion.fecha_fin,
            m2=peticion.m2,
            es_urba=peticion.es_urba,
        )
    )
    return ObraRespuesta.desde_dominio(creada.id, creada.obra)


@router.post(
    "/obras/bulk",
    response_model=list[ObraRespuesta],
    status_code=status.HTTP_201_CREATED,
    summary="Alta masiva de obras",
    dependencies=[CREADOR_DE_OBRA, Idempotencia],
    responses={422: {"description": "Alguna obra del lote es inválida (§7.2)."}},
)
async def crear_obras_en_lote(
    peticion: CrearObrasEnLotePeticion, caso_uso: CrearObrasEnLoteDep
) -> list[ObraRespuesta]:
    """Da de alta el lote completo en una transacción (§11.2)."""
    creadas = await caso_uso.ejecutar(
        ComandoCrearObrasEnLote(
            obras=[
                ComandoCrearObra(
                    cluster_id=una.cluster_id,
                    clave=una.clave,
                    prototipo_id=una.prototipo_id,
                    residente_id=una.residente_id,
                    fecha_inicio=una.fecha_inicio,
                    fecha_fin=una.fecha_fin,
                    m2=una.m2,
                    es_urba=una.es_urba,
                )
                for una in peticion.obras
            ]
        )
    )
    return [
        ObraRespuesta.desde_dominio(obra_id, obra)
        for obra_id, obra in zip(creadas.ids, creadas.obras, strict=True)
    ]


@router.patch(
    "/obras/{obra_id}",
    response_model=ObraRespuesta,
    summary="Editar una obra",
    dependencies=[CREADOR_DE_OBRA],
    responses={
        **_NO_ENCONTRADA,
        409: {"description": "La obra está entregada y congelada (§11.3 D)."},
        422: {"description": "Datos de obra inválidos (§7.2)."},
    },
)
async def actualizar_obra(
    obra_id: UUID,
    peticion: ActualizarObraPeticion,
    caso_uso: ActualizarObraDep,
) -> ObraRespuesta:
    """Control de obra edita clave, residente, fechas y superficie (§11.2)."""
    # `exclude_unset` distingue "no mandaron residente_id" de "mándalo a null":
    # sin esa distinción no habría forma de liberar una obra de su residente.
    enviados = peticion.model_dump(exclude_unset=True)
    obra = await caso_uso.ejecutar(
        ComandoActualizarObra(
            obra_id=obra_id,
            clave=peticion.clave,
            residente_id=enviados.get("residente_id", SIN_CAMBIO),
            fecha_inicio=peticion.fecha_inicio,
            fecha_fin=peticion.fecha_fin,
            m2=peticion.m2,
        )
    )
    return ObraRespuesta.desde_dominio(obra_id, obra)


@router.post(
    "/obras/{obra_id}/generar",
    response_model=ObraGeneradaRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Generar actividades y programa desde el prototipo",
    dependencies=[CREADOR_DE_OBRA, Idempotencia],
    responses={
        **_NO_ENCONTRADA,
        409: {
            "description": (
                "La obra no se puede generar: es urbanización sin prototipo, "
                "ya tiene actividades, está congelada, o al prototipo le falta "
                "el CPU vigente de algún concepto (§11.3 A.2)."
            )
        },
    },
)
async def generar_obra(
    obra_id: UUID,
    peticion: GenerarObraPeticion,
    caso_uso: GenerarObraDesdePrototipoDep,
) -> ObraGeneradaRespuesta:
    """Workflow A: recorre el árbol del prototipo, crea las actividades con su
    CPU vigente e instancia el `ProgramaObra` (§11.3 A.2)."""
    generada = await caso_uso.ejecutar(
        ComandoGenerarObra(obra_id=obra_id, modo_pago=peticion.modo_pago)
    )
    return ObraGeneradaRespuesta(
        obra_id=generada.obra_id,
        programa_obra_id=generada.programa_obra_id,
        n_actividades=generada.n_actividades,
    )
