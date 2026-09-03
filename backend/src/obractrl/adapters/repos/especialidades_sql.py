"""Repositorio del catálogo de especialidades (§8.3, §12.4, migración 0047).

La especialidad es el **oficio** con el que se ejecuta un concepto —ESTRUCTURA,
ACABADOS, CARPINTERIA, HERRERIA…—. Es el segundo eje del trabajo:

* `frente` (0005) — la clase de fuerza de trabajo que se contrata: OBRA,
  INSTALACIONES, SUBCONTRATOS, PINTURA. Cuelga de la **etapa**.
* `especialidad` (0047) — el oficio. Cuelga del **concepto**, y es más fino: una
  etapa de frente OBRA contiene conceptos de acabados, estructura y albañilería.

`especialidad` entra por el loop de catálogos de la 0012 —alcance de
organización—, así que ningún método de aquí filtra por `org_id`: eso lo impone
la base. En el INSERT sale de `current_setting('app.org_id')`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioEspecialidadesSQL"]

_COLUMNAS = "id, clave, nombre, orden, estatus"


class RepositorioEspecialidadesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def listar(self, *, solo_activos: bool = True) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                      from especialidad
                     where not cast(:solo_activos as boolean) or estatus = 'activo'
                     order by orden, clave
                    """
                ),
                {"solo_activos": solo_activos},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta idempotente por clave.

        `on conflict do update` sobre el nombre: cargar dos veces el mismo
        catálogo es lo normal —se corrige una descripción y se vuelve a subir—
        y un alta que falla la segunda vez obligaría a limpiar a mano.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into especialidad (org_id, clave, nombre, orden)
                    values (cast(current_setting('app.org_id') as uuid),
                            :clave, :nombre, coalesce(cast(:orden as smallint), 0))
                    on conflict (org_id, clave) do update set nombre = excluded.nombre
                    returning id
                    """
                ),
                {
                    "clave": datos["clave"],
                    "nombre": datos["nombre"],
                    "orden": datos.get("orden"),
                },
            )
        ).scalar_one()

    async def asignar_a_conceptos(
        self, especialidad_id: UUID | None, claves_concepto: list[str]
    ) -> int:
        """Le pone esa especialidad a los conceptos de la lista.

        Por clave y no por id porque quien la trae es el archivo (§3.3: la clave
        manda) y resolver a id fila por fila serían cuatrocientas idas a la base
        para el mismo catálogo.

        `especialidad_id` nulo la quita: un concepto que dejó de tener oficio en
        el archivo tiene que perderlo aquí, igual que en el puente de
        contratistas.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    update concepto
                       set especialidad_id = cast(:especialidad_id as uuid)
                     where clave = any(cast(:claves as text[]))
                    """
                ),
                {
                    "especialidad_id": (
                        str(especialidad_id) if especialidad_id else None
                    ),
                    "claves": claves_concepto,
                },
            )
        ).rowcount
