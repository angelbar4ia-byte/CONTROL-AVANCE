"""Repositorio del catálogo de cuadrillas y su versionado de PU.

Spec §12.11 (adaptador de persistencia) · §7.3/§7.6 (cuadrilla) · §10.6
(cargador de mano de obra da de alta la cuadrilla; cargador de cuadrillas
carga su composición y PU) · §10.8 (versionado) · §12.4 (RLS).

`cuadrilla` está en el mismo bloque de `rls_policies`
(`database/migrations/20260814000012`) que `unidad`/`familia`: lectura para
cualquier usuario de la organización, escritura solo para `app.es_config()`.
`cuadrilla_version`/`cuadrilla_integrante` (migración 0032) tienen sus
propias políticas, mismo predicado. `org_id` en cada INSERT sale de
`current_setting('app.org_id')`, igual que en `unidades_sql.py`/
`conceptos_sql.py`.

Sin pantalla de alta manual completa todavía: el catálogo se puebla por dos
cargadores — mano de obra (clave+nombre mínimos) y cuadrillas (composición y
PU versionado, §10.6) —, más el alta mínima de `crear` que expone la API
para cuando sí exista esa pantalla.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import (
    RegistroNoEncontrado,
    VersionVigenteNoEliminable,
)

__all__ = ["RepositorioCuadrillasSQL"]

_COLUMNAS = """
    id, clave, nombre, unidad_id, rendimiento, estatus
"""

_CAMPOS_EDITABLES: dict[str, str] = {
    "nombre": "nombre = :nombre",
    "unidad_id": "unidad_id = cast(:unidad_id as uuid)",
    "rendimiento": "rendimiento = cast(:rendimiento as numeric)",
    "estatus": "estatus = cast(:estatus as estatus_registro)",
}
"""Campos que una edición puede tocar. La `clave` no está: es la identidad
del registro (§3.3)."""


class RepositorioCuadrillasSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de cuadrilla (§10.6). Claves esperadas: ``clave`` y
        ``nombre``. Opcional: ``unidad_id``."""
        return (
            await self._sesion.execute(
                text(
                    """
                    insert into cuadrilla (org_id, clave, nombre, unidad_id)
                    values (cast(current_setting('app.org_id') as uuid),
                            :clave, :nombre, cast(:unidad_id as uuid))
                    returning id
                    """
                ),
                {
                    "clave": datos["clave"],
                    "nombre": datos["nombre"],
                    "unidad_id": (
                        str(datos["unidad_id"]) if datos.get("unidad_id") else None
                    ),
                },
            )
        ).scalar_one()

    async def obtener(self, cuadrilla_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from cuadrilla where id = :id"),
                {"id": str(cuadrilla_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def listar(self, *, solo_activos: bool = True) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from cuadrilla
                    where not cast(:solo_activos as boolean) or estatus = 'activo'
                    order by clave
                    """
                ),
                {"solo_activos": solo_activos},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def actualizar(self, cuadrilla_id: UUID, cambios: dict[str, Any]) -> None:
        """Edición parcial; solo las claves presentes en ``cambios`` se
        escriben (§10.6, cargador de cuadrillas en modo Actualizar)."""
        asignaciones = [
            _CAMPOS_EDITABLES[campo] for campo in cambios if campo in _CAMPOS_EDITABLES
        ]
        if not asignaciones:
            return

        parametros: dict[str, Any] = {"id": str(cuadrilla_id)}
        for campo in cambios:
            if campo not in _CAMPOS_EDITABLES:
                continue
            valor = cambios[campo]
            parametros[campo] = (
                str(valor) if campo.endswith("_id") and valor is not None else valor
            )

        await self._sesion.execute(
            text(f"update cuadrilla set {', '.join(asignaciones)} where id = :id"),
            parametros,
        )

    async def actualizar_rendimiento(
        self, cuadrilla_id: UUID, rendimiento: Decimal
    ) -> None:
        """La cuadrilla "asume" el rendimiento teórico del destajo que se le
        asigna (§10.6) — se llama solo cuando el archivo trae el dato."""
        await self._sesion.execute(
            text("update cuadrilla set rendimiento = :rendimiento where id = :id"),
            {"rendimiento": rendimiento, "id": str(cuadrilla_id)},
        )

    # --- Versionado de PU (§10.6, §10.8) ----------------------------------

    async def versiones(self, cuadrilla_id: UUID) -> list[dict[str, Any]]:
        """Historial de PU de la cuadrilla (§10.8)."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, cuadrilla_id, version, precio_unitario, vigente, created_at
                    from cuadrilla_version
                    where cuadrilla_id = :id
                    order by version
                    """
                ),
                {"id": str(cuadrilla_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def publicar_version(
        self,
        cuadrilla_id: UUID,
        *,
        version: int,
        precio_unitario: Decimal,
        retirar: list[int],
    ) -> UUID:
        """Retira las versiones de ``retirar`` e inserta la nueva como
        vigente (§10.8). Mismo orden que `publicar_version_cpu`
        (`conceptos_sql.py`): `uq_cuadrilla_version_vigente` es un índice
        único parcial, no diferible, así que primero se baja la anterior.
        """
        if retirar:
            await self._sesion.execute(
                text(
                    """
                    update cuadrilla_version
                       set vigente = false
                     where cuadrilla_id = :id
                       and version = any(cast(:retirar as integer[]))
                    """
                ),
                {"id": str(cuadrilla_id), "retirar": list(retirar)},
            )

        return (
            await self._sesion.execute(
                text(
                    """
                    insert into cuadrilla_version
                        (org_id, cuadrilla_id, version, precio_unitario, vigente)
                    values (cast(current_setting('app.org_id') as uuid),
                            :id, :version,
                            cast(:precio_unitario as numeric), true)
                    returning id
                    """
                ),
                {
                    "id": str(cuadrilla_id),
                    "version": version,
                    "precio_unitario": precio_unitario,
                },
            )
        ).scalar_one()

    async def integrantes_de(self, cuadrilla_version_id: UUID) -> list[dict[str, Any]]:
        """Composición propia de esa versión (§10.6): cada versión es dueña
        exclusiva de sus filas."""
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, cuadrilla_version_id, insumo_id, cantidad,
                           costo_unitario, importe, orden
                    from cuadrilla_integrante
                    where cuadrilla_version_id = :id
                    order by orden, id
                    """
                ),
                {"id": str(cuadrilla_version_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def agregar_integrantes(
        self, cuadrilla_version_id: UUID, filas: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Inserta la composición de la versión y devuelve las filas
        persistidas, completas, para el snapshot del lote (§10.8)."""
        insertadas: list[dict[str, Any]] = []
        for orden, fila in enumerate(filas):
            registro = (
                await self._sesion.execute(
                    text(
                        """
                        insert into cuadrilla_integrante
                            (org_id, cuadrilla_version_id, insumo_id, cantidad,
                             costo_unitario, importe, orden)
                        values (cast(current_setting('app.org_id') as uuid),
                                :cuadrilla_version_id, cast(:insumo_id as uuid),
                                cast(:cantidad as numeric),
                                cast(:costo_unitario as numeric),
                                cast(:importe as numeric), :orden)
                        returning id, cuadrilla_version_id, insumo_id, cantidad,
                                  costo_unitario, importe, orden
                        """
                    ),
                    {
                        "cuadrilla_version_id": str(cuadrilla_version_id),
                        "insumo_id": str(fila["insumo_id"]),
                        "cantidad": fila.get("cantidad", 0),
                        "costo_unitario": fila.get("costo_unitario", 0),
                        "importe": fila.get("importe", 0),
                        "orden": fila.get("orden", orden),
                    },
                )
            ).mappings().one()
            insertadas.append(dict(registro))
        return insertadas

    async def eliminar_version(self, cuadrilla_id: UUID, version_id: UUID) -> None:
        """Borra una versión ya retirada (mantenimiento directo, §10.8, no
        ligado a una carga). `cuadrilla_integrante` se va con
        `on delete cascade`."""
        fila = (
            await self._sesion.execute(
                text(
                    "select vigente from cuadrilla_version "
                    "where id = cast(:id as uuid) and cuadrilla_id = cast(:cuadrilla_id as uuid)"
                ),
                {"id": str(version_id), "cuadrilla_id": str(cuadrilla_id)},
            )
        ).mappings().first()
        if fila is None:
            raise RegistroNoEncontrado(
                f"La versión {version_id} no existe para la cuadrilla {cuadrilla_id}."
            )
        if fila["vigente"]:
            raise VersionVigenteNoEliminable(
                f"La versión {version_id} es la vigente: no se puede eliminar (§10.8)."
            )
        await self._sesion.execute(
            text("delete from cuadrilla_version where id = cast(:id as uuid)"),
            {"id": str(version_id)},
        )
