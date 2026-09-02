"""Endpoint de insumos programados (§7.3, §7.5, §11.2).

Contesta la pregunta con la que se compra: *"¿cuánto cemento necesito la semana
22, y cuándo tengo que pedirlo?"*. Cruza el cronograma con la explosión del APU
y devuelve una matriz insumo × periodo.

Controlador delgado: valida el DTO, delega en el caso de uso y mapea el
resultado (§12.11). La aritmética vive en `domain.insumos.programado`.

## Los cuatro roles entran, pero no todos ven lo mismo

Sin `exigir_rol`: un residente necesita saber cuánto material va a pedir su
obra tanto como Control necesita saberlo de todas. **RLS acota** qué obras
alcanza cada quien (`app.obra_visible`, migración 0042), igual que en
`GET /obras`.

Lo que sí se decide por rol es el **dinero**: cantidades para los cuatro,
importes solo para Control de obra y Super intendente. Es una decisión del
borde, que es donde vive el RBAC en este repo, y por eso el caso de uso recibe
`con_importe` ya resuelto en vez de preguntar por el rol.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import ConsultarInsumosProgramadosDep
from obractrl.adapters.api.dependencias import ContextoActual
from obractrl.application.casos_uso.consultar_insumos_programados import (
    MES,
    SEMANA,
    ComandoInsumosProgramados,
    InsumosProgramados,
)
from obractrl.domain.insumos.programado import FilaDeInsumo  # noqa: F401
from obractrl.domain.shared.diccionario import Rol, TipoInsumo, TipoSemana

router = APIRouter(tags=["insumos"])

_VE_DINERO = frozenset({Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE})
"""Quién ve importes. El residente y el supervisor ven cuánto material hace
falta —lo necesitan para pedirlo— y no cuánto cuesta (§4, §5.1)."""

_SIN_CALENDARIO: dict[int | str, dict[str, Any]] = {
    404: {
        "description": (
            "El rango cae en años sin calendario generado, o el prototipo no "
            "tiene programa base y presupuesto vigentes (§3.1, §7.5)."
        )
    }
}


class PeriodoRespuesta(BaseModel):
    """Una columna de la tabla."""

    clave: str
    desde: date
    hasta: date = Field(
        description="Exclusivo: es el día siguiente al último del periodo."
    )
    etiqueta: str


class RepartoRespuesta(BaseModel):
    """De dónde salió una parte del renglón (§7.3)."""

    obra_id: str
    concepto_clave: str
    cantidad: float


class FilaDeInsumoRespuesta(BaseModel):
    insumo_id: UUID
    clave: str
    descripcion: str
    unidad: str | None
    tipo: str
    dias_entrega: int | None = Field(
        default=None,
        description=(
            "Plazo capturado del insumo (§10.1). Vacío = se usó la "
            "anticipación global de la consulta."
        ),
    )
    cantidades: list[float] = Field(
        description="Una por periodo, en el mismo orden que `periodos`."
    )
    total: float
    importe: float | None = Field(
        default=None,
        description=(
            "Solo para Control de obra y Super intendente. Nulo no es cero: "
            "cero diría que el insumo es gratis."
        ),
    )
    ya_surtido: float | None = Field(
        default=None,
        description=(
            "Lo que ya salió del almacén para estas obras (§10.5). No es una "
            "existencia: no hay inventario todavía."
        ),
    )
    desglose: list[RepartoRespuesta] = Field(default_factory=list)


class InsumosProgramadosRespuesta(BaseModel):
    """La matriz completa, más lo que quedó fuera y por qué."""

    periodos: list[PeriodoRespuesta]
    filas: list[FilaDeInsumoRespuesta]
    sin_programar: list[str] = Field(
        default_factory=list,
        description=(
            "Actividades sin ventana: la obra se generó pero no se ha "
            "calendarizado (`POST /obras/{id}/programa`). No es un error."
        ),
    )
    sin_explosion: list[str] = Field(
        default_factory=list,
        description=(
            "Actividades sin concepto —extra-catálogo (§7.6)— o cuyo APU no "
            "se pudo explotar. No tienen insumos que derivar."
        ),
    )


@router.get(
    "/insumos-programados",
    response_model=InsumosProgramadosRespuesta,
    summary="Qué insumos pide el programa, y cuándo",
    responses=_SIN_CALENDARIO,
)
async def insumos_programados_(
    ctx: ContextoActual,
    caso_uso: ConsultarInsumosProgramadosDep,
    desde: Annotated[date, Query(description="Primer día del rango.")],
    hasta: Annotated[date, Query(description="Último día del rango.")],
    granularidad: Annotated[
        str,
        Query(
            pattern=f"^({SEMANA}|{MES})$",
            description="Una columna por semana o por mes (§3.1).",
        ),
    ] = SEMANA,
    obra_id: Annotated[UUID | None, Query(description="Acota a una obra.")] = None,
    residente_id: Annotated[
        UUID | None, Query(description="Obras de un residente (§4).")
    ] = None,
    supervisor_id: Annotated[
        UUID | None, Query(description="Obras de los residentes de un supervisor (§4).")
    ] = None,
    prototipo_id: Annotated[
        UUID | None,
        Query(
            description=(
                "Simulación: en vez del cronograma real, el programa base y el "
                "presupuesto vigentes de este prototipo (§7.5)."
            )
        ),
    ] = None,
    n_casas: Annotated[
        int, Query(ge=1, description="Cuántas casas simular. Solo con `prototipo_id`.")
    ] = 1,
    tipo: Annotated[
        list[TipoInsumo] | None,
        Query(description="Filtra por tipo de insumo; vacío los trae los cuatro."),
    ] = None,
    dias_anticipacion: Annotated[
        int,
        Query(
            ge=0,
            description=(
                "Con cuántos días de anticipación se necesita el material. Lo "
                "pisa el `dias_entrega` del insumo cuando está capturado."
            ),
        ),
    ] = 0,
    tipo_semana: TipoSemana = TipoSemana.ORDINARIA,
) -> InsumosProgramadosRespuesta:
    """Insumos que el programa pide, por periodo (§7.3, §7.5).

    Todos los roles, cada uno con su alcance (§4): RLS decide qué obras entran
    y los importes solo viajan a Control de obra y Super intendente.
    """
    resultado = await caso_uso.ejecutar(
        ComandoInsumosProgramados(
            desde=desde,
            hasta=hasta,
            granularidad=granularidad,
            obra_id=obra_id,
            residente_id=residente_id,
            supervisor_id=supervisor_id,
            prototipo_id=prototipo_id,
            n_casas=n_casas,
            tipos=frozenset(str(t) for t in tipo) if tipo else None,
            dias_anticipacion=dias_anticipacion,
            con_importe=ctx.rol in _VE_DINERO,
        )
    )
    return _respuesta(resultado)


def _respuesta(resultado: InsumosProgramados) -> InsumosProgramadosRespuesta:
    matriz = resultado.matriz
    return InsumosProgramadosRespuesta(
        periodos=[
            PeriodoRespuesta(
                clave=p.clave, desde=p.desde, hasta=p.hasta, etiqueta=p.etiqueta
            )
            for p in matriz.periodos
        ],
        filas=[
            FilaDeInsumoRespuesta(
                insumo_id=UUID(fila.insumo.insumo_id),
                clave=fila.insumo.clave,
                descripcion=fila.insumo.descripcion,
                unidad=fila.insumo.unidad,
                tipo=fila.insumo.tipo,
                dias_entrega=fila.insumo.dias_entrega,
                cantidades=[float(c) for c in fila.cantidades],
                total=float(fila.total),
                importe=None if fila.importe is None else float(fila.importe),
                ya_surtido=_surtido_de(resultado, fila.insumo.insumo_id),
                desglose=[
                    RepartoRespuesta(
                        obra_id=r.obra_id,
                        concepto_clave=r.concepto_clave,
                        cantidad=float(r.cantidad),
                    )
                    for r in fila.desglose
                ],
            )
            for fila in matriz.filas
        ],
        sin_programar=list(matriz.sin_programar),
        sin_explosion=list(matriz.sin_explosion),
    )


def _surtido_de(resultado: InsumosProgramados, insumo_id: str) -> float | None:
    """Lo que ya salió del almacén de ese insumo.

    `None` —y no cero— cuando no hay dato: en una simulación por prototipo no
    hay almacén del que haya salido nada, y un cero ahí diría que no se ha
    surtido, que es otra afirmación.
    """
    if not resultado.surtido:
        return None
    return float(resultado.surtido.get(insumo_id, 0))
