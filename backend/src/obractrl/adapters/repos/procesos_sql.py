"""Repositorio de procesos de mejora (§7.9 `Proceso`, §11.2 "Procesos").

Spec §12.11 (adaptador de persistencia) · §12.4 (RLS).

`proceso` entra al loop de **catálogos** de
`database/migrations/20260814000012_rls_policies.sql`: lectura para toda la
organización, escritura para `app.es_config()` —Control de obra y Super
intendente—. Ningún método filtra por `org_id` a mano; eso lo impone la base.

Que RLS deje escribir a Control de obra y el §11.2 marque procesos como
**(SI)** no es una contradicción: RLS es el piso —el aislamiento que no se
puede saltar— y el rol exacto lo aplica el borde con `exigir_rol`. Es el mismo
reparto que documenta `adapters/api/dependencias.py`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["ProcesoNoEncontrado", "RepositorioProcesosSQL"]

_COLUMNAS = """
    id, nombre, descripcion, definido_por, estatus, created_at, updated_at
"""


class ProcesoNoEncontrado(LookupError):
    """No existe, o es de otra organización. Las dos se ven igual desde aquí,
    y las dos son un 404 (§12.4: no se confirma la existencia de lo ajeno)."""


class RepositorioProcesosSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def listar(self, *, estatus: str | None = None) -> list[dict[str, Any]]:
        """El tablero de mejora, lo más reciente primero.

        Orden por `updated_at` y no por `created_at`: un proceso propuesto hace
        seis meses que acaba de moverse a `adoptado` es la noticia, no el que
        se dio de alta ayer y sigue quieto.
        """
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from proceso
                    where (cast(:estatus as text) is null or estatus = :estatus)
                    order by updated_at desc
                    """
                ),
                {"estatus": estatus},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def obtener(self, proceso_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from proceso where id = :id"),
                {"id": str(proceso_id)},
            )
        ).mappings().first()
        return dict(fila) if fila else None

    async def crear(
        self,
        *,
        nombre: str,
        descripcion: str | None,
        definido_por: UUID,
        estatus: str,
    ) -> dict[str, Any]:
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    insert into proceso
                        (org_id, nombre, descripcion, definido_por, estatus)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :nombre, :descripcion, cast(:definido_por as uuid),
                         :estatus)
                    returning {_COLUMNAS}
                    """
                ),
                {
                    "nombre": nombre,
                    "descripcion": descripcion,
                    "definido_por": str(definido_por),
                    "estatus": estatus,
                },
            )
        ).mappings().one()
        return dict(fila)

    async def cambiar_estatus(self, proceso_id: UUID, estatus: str) -> dict[str, Any]:
        """Mueve el proceso de etapa. Levanta si el `UPDATE` no tocó nada.

        El `returning` vacío es la única señal disponible: RLS filtra la fila
        ajena **antes** del update, así que "no existe" y "no es tuyo" llegan
        aquí exactamente igual — y así deben salir (§12.4).
        """
        fila = (
            await self._sesion.execute(
                text(
                    f"""
                    update proceso
                       set estatus = :estatus
                     where id = cast(:id as uuid)
                    returning {_COLUMNAS}
                    """
                ),
                {"id": str(proceso_id), "estatus": estatus},
            )
        ).mappings().first()

        if fila is None:
            raise ProcesoNoEncontrado(
                f"El proceso {proceso_id} no existe o está fuera de tu alcance."
            )
        return dict(fila)
