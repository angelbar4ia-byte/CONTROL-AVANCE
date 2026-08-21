"""Consulta de la bitácora de negocio.

Spec §7.9 (`Bitacora`) · §11.7 (auditoría) · §12.12 ("quedan en **bitácora**
(quién/cuándo/qué)") · §5.1 (sidebar del Super intendente: "Bitácora de
eventos") · migración 0023.

La bitácora se escribe sola desde la Fase 8 —un trigger `security definer`
sobre las tablas que alteran resultados (migración 0023)— y hasta ahora no
había forma de leerla que no fuera `psql`. Una auditoría que solo se puede
consultar con acceso a la base no cumple lo que el §12.12 pide, porque la
persona que necesita saber quién cambió el IVA es justamente la que no tiene
ese acceso.

## Por qué no está en la lista de endpoints del §11.2

Porque el §11.2 enumera la API de las operaciones y la bitácora no es una: es
el rastro de todas ellas. Lo que sí está en el spec es la **pantalla** —§5.1
le da al Super intendente "Bitácora de eventos"—, y una pantalla sin endpoint
no existe. Esta ruta es lo mínimo que la sostiene: leer, filtrar, paginar.

## Solo lectura, y no por elección de esta ruta

No hay `POST` ni `DELETE`, y no es una omisión: `bitacora` **no tiene política
de INSERT, UPDATE ni DELETE** (migración 0023). Es append-only por
construcción, y la escribe el trigger. Una bitácora que su propio sujeto puede
editar no prueba nada.

La política `bitacora_select` la limita a Control de obra y Super intendente;
el borde repite ese par con `exigir_rol` para que el rechazo sea un 403
legible en vez de una lista vacía que parece un error de filtros.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from obractrl.adapters.api.dependencias import SesionRLS, exigir_rol
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["bitacora"])

LIMITE_MAXIMO = 200
"""Tope duro de página. La bitácora de una organización con seis meses de
operación son decenas de miles de renglones, y una consulta sin tope es la
forma más fácil de tumbar el plan chico de Render (§12.8) desde el navegador."""


class EntradaBitacora(BaseModel):
    """Un renglón: quién, cuándo, qué y sobre qué (§7.9)."""

    id: UUID
    entidad: str = Field(description="Tabla afectada, p. ej. `configuracion` o `cpu`.")
    entidad_id: UUID | None
    usuario_id: UUID | None = Field(
        default=None,
        description=(
            "Quién lo hizo. Nulo cuando el cambio no vino de una sesión con "
            "contexto — una migración o un script de mantenimiento."
        ),
    )
    usuario_nombre: str | None = None
    accion: str = Field(description="`insert` | `update` | `delete` (§11.7).")
    datos: dict[str, Any] = Field(
        description=(
            "Para un update, solo las columnas que cambiaron, con su valor "
            "antes y después; para un alta, la fila (migración 0023)."
        )
    )
    fecha: datetime


class PaginaBitacora(BaseModel):
    """Página con el total, para que la UI pueda decir "1-50 de 3 240"."""

    total: int
    page: int
    size: int
    entradas: list[EntradaBitacora]


@router.get(
    "/bitacora",
    response_model=PaginaBitacora,
    summary="Bitácora de cambios de configuración y catálogo",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))],
)
async def listar_bitacora(
    sesion: SesionRLS,
    entidad: Annotated[
        str | None, Query(description="Filtra por tabla (`configuracion`, `cpu`, …).")
    ] = None,
    entidad_id: Annotated[UUID | None, Query(description="Filtra por fila concreta.")] = None,
    usuario_id: Annotated[UUID | None, Query(description="Filtra por autor.")] = None,
    desde: Annotated[date | None, Query(description="Fecha mínima, inclusiva.")] = None,
    hasta: Annotated[
        date | None,
        Query(description="Fecha máxima, **inclusiva**: cuenta el día completo."),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Página, base 1 (§11.2).")] = 1,
    size: Annotated[int, Query(ge=1, le=LIMITE_MAXIMO, description="Tamaño de página.")] = 50,
) -> PaginaBitacora:
    """Lee la bitácora de la organización, lo más reciente primero.

    Lectura sin orquestación de dominio: consulta directa, como `GET /me`. El
    aislamiento lo pone `bitacora_select` (§12.4).

    **`hasta` incluye el día entero.** `fecha` es `timestamptz`, así que
    comparar contra la fecha pelada dejaría fuera todo lo ocurrido después de
    la medianoche del último día — que es todo. Se compara contra el día
    siguiente con `<`, no con `<=` a las 23:59:59, para no depender de la
    precisión del reloj.

    El `count(*)` va en la misma consulta con una ventana en vez de una
    segunda vuelta: dos consultas con los mismos filtros son dos lugares donde
    el filtro puede quedar desalineado, y aquí eso significaría una paginación
    que miente.
    """
    filtros = {
        "entidad": entidad,
        "entidad_id": str(entidad_id) if entidad_id else None,
        "usuario_id": str(usuario_id) if usuario_id else None,
        "desde": desde,
        "hasta": hasta,
        "limite": size,
        "salto": (page - 1) * size,
    }

    filas = (
        await sesion.execute(
            text(
                """
                select b.id, b.entidad, b.entidad_id, b.usuario_id, u.nombre as usuario_nombre,
                       b.accion, b.datos, b.fecha,
                       count(*) over () as total
                from bitacora b
                left join usuario u on u.id = b.usuario_id
                where (cast(:entidad as text) is null or b.entidad = :entidad)
                  and (cast(:entidad_id as uuid) is null or b.entidad_id = cast(:entidad_id as uuid))
                  and (cast(:usuario_id as uuid) is null or b.usuario_id = cast(:usuario_id as uuid))
                  and (cast(:desde as date) is null or b.fecha >= cast(:desde as date))
                  and (cast(:hasta as date) is null or b.fecha < cast(:hasta as date) + 1)
                order by b.fecha desc, b.id desc
                limit :limite offset :salto
                """
            ),
            filtros,
        )
    ).mappings().all()

    return PaginaBitacora(
        total=int(filas[0]["total"]) if filas else 0,
        page=page,
        size=size,
        entradas=[
            EntradaBitacora(
                id=fila["id"],
                entidad=fila["entidad"],
                entidad_id=fila["entidad_id"],
                usuario_id=fila["usuario_id"],
                usuario_nombre=fila["usuario_nombre"],
                accion=fila["accion"],
                datos=fila["datos"] or {},
                fecha=fila["fecha"],
            )
            for fila in filas
        ],
    )


@router.get(
    "/bitacora/entidades",
    response_model=list[str],
    summary="Tablas que aparecen en la bitácora",
    dependencies=[Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))],
)
async def entidades_con_bitacora(sesion: SesionRLS) -> list[str]:
    """Alimenta el filtro de la pantalla (§5.1).

    Sale de los datos y no de una lista fija en el front: las tablas
    auditadas las decide la migración 0023, y una lista escrita a mano en el
    cliente se desincroniza el día que se agregue una — mostrando un filtro
    que no encuentra nada, o escondiendo cambios que sí se registraron.
    """
    filas = (
        await sesion.execute(text("select distinct entidad from bitacora order by entidad"))
    ).all()
    return [str(fila.entidad) for fila in filas]
