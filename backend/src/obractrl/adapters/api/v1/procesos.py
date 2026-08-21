"""Endpoints de mejora de procesos.

Spec §11.2 ("**Procesos (mejora)** — `GET/POST /procesos` — (SI)") · §7.9
(`Proceso`) · §5.1 (sidebar del Super intendente: "Mejora de procesos").

Es el último bloque del §11.2 que no tenía endpoints. La tabla `proceso`
existe desde la migración 0010 con su RLS de catálogo; lo que faltaba era la
puerta.

## Solo lectura para todos, escritura para el Super intendente

`GET` lo puede llamar cualquier rol autenticado y `POST`/`PATCH` solo el SI
(§11.2). No es una asimetría caprichosa: un proceso de mejora que solo puede
leer quien lo escribió no mejora nada — el residente tiene que poder ver la
forma de trabajar que se adoptó. Lo que no puede es cambiarla.

RLS ya deja leer a toda la organización (loop de catálogos de la migración
0012) y escribir a `app.es_config()`, o sea también a Control de obra. El
borde estrecha eso a SI con `exigir_rol`, que es el reparto de siempre: RLS es
el piso que no se puede saltar, el rol exacto lo aplica la ruta.

## Un `PATCH` que el §11.2 no pide

El spec lista `GET/POST`. Sin una forma de mover el estatus, el tablero se
queda con todo en `propuesto` para siempre y la palabra "mejora" no significa
nada: la entidad tiene `estatus` justamente porque los procesos avanzan. Se
agrega **solo** el cambio de etapa —no una edición general del texto—, para no
inventar más superficie que la que el §7.9 sostiene.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS, exigir_rol
from obractrl.adapters.repos.procesos_sql import RepositorioProcesosSQL
from obractrl.domain.shared.diccionario import EstatusProceso, Rol

router = APIRouter(tags=["procesos"])

FiltroEstatus = Annotated[
    EstatusProceso | None,
    Query(description="Filtra por etapa del tablero (§7.9)."),
]


class CrearProcesoPeticion(BaseModel):
    """Alta de un proceso de mejora (§11.2, rol SI)."""

    nombre: str = Field(min_length=1, description="Cómo se le nombra en el tablero.")
    descripcion: str | None = Field(
        default=None,
        description="Qué cambia y por qué. Es el campo que hace útil el tablero seis meses después.",
    )
    estatus: EstatusProceso = Field(
        default=EstatusProceso.PROPUESTO,
        description="Etapa inicial; casi siempre `propuesto`.",
    )


class CambiarEstatusPeticion(BaseModel):
    estatus: EstatusProceso = Field(description="Nueva etapa (§7.9).")


class ProcesoRespuesta(BaseModel):
    id: UUID
    nombre: str
    descripcion: str | None
    definido_por: UUID | None
    estatus: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def desde_fila(cls, fila: dict) -> ProcesoRespuesta:
        return cls(
            id=fila["id"],
            nombre=fila["nombre"],
            descripcion=fila["descripcion"],
            definido_por=fila["definido_por"],
            estatus=fila["estatus"],
            created_at=fila["created_at"],
            updated_at=fila["updated_at"],
        )


@router.get(
    "/procesos",
    response_model=list[ProcesoRespuesta],
    summary="Tablero de mejora de procesos",
)
async def listar_procesos(
    sesion: SesionRLS, estatus: FiltroEstatus = None
) -> list[ProcesoRespuesta]:
    """Los procesos de la organización (§7.9).

    Lectura simple sin orquestación de dominio —como `GET /me`— así que
    consulta el repositorio directo, sin caso de uso: RLS ya acotó el alcance
    (§12.4).
    """
    repo = RepositorioProcesosSQL(sesion)
    filas = await repo.listar(estatus=estatus.value if estatus else None)
    return [ProcesoRespuesta.desde_fila(fila) for fila in filas]


@router.post(
    "/procesos",
    response_model=ProcesoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Proponer un proceso de mejora",
    dependencies=[Depends(exigir_rol(Rol.SUPER_INTENDENTE))],
)
async def crear_proceso(
    peticion: CrearProcesoPeticion, ctx: ContextoActual, sesion: SesionRLS
) -> ProcesoRespuesta:
    """§11.2 — el alta es del Super intendente.

    `definido_por` sale del token y no del cuerpo (§12.4): quien define el
    proceso es quien lo está creando, y dejar que el cliente lo eligiera
    permitiría firmar una decisión a nombre de otro.

    Commitea aquí porque no hay caso de uso que lo haga —es una escritura sin
    dominio, como el registro de dispositivos—; `sesion_con_rls` no commitea
    sola.
    """
    fila = await RepositorioProcesosSQL(sesion).crear(
        nombre=peticion.nombre.strip(),
        descripcion=(peticion.descripcion or "").strip() or None,
        definido_por=ctx.usuario_id,
        estatus=peticion.estatus.value,
    )
    await sesion.commit()
    return ProcesoRespuesta.desde_fila(fila)


@router.patch(
    "/procesos/{proceso_id}",
    response_model=ProcesoRespuesta,
    summary="Mover un proceso de etapa",
    dependencies=[Depends(exigir_rol(Rol.SUPER_INTENDENTE))],
    responses={404: {"description": "El proceso no existe o está fuera de tu alcance."}},
)
async def cambiar_estatus_proceso(
    proceso_id: UUID, peticion: CambiarEstatusPeticion, sesion: SesionRLS
) -> ProcesoRespuesta:
    """Avanza o descarta un proceso (ver el encabezado del módulo).

    **Sin máquina de estados.** Cualquier etapa puede ir a cualquier otra: un
    proceso adoptado que resultó malo vuelve a `descartado`, y uno descartado
    puede reintentarse el año siguiente. Imponer un orden aquí sería inventar
    una regla que el §7.9 no da, y la única que importa —quién puede
    moverlo— ya la aplica `exigir_rol`.
    """
    fila = await RepositorioProcesosSQL(sesion).cambiar_estatus(
        proceso_id, peticion.estatus.value
    )
    await sesion.commit()
    return ProcesoRespuesta.desde_fila(fila)
