"""Repositorio de contratistas.

Spec §12.11 (adaptador de persistencia) · §7.3 · §10.1 (listas oficiales a
homologar) · §12.4 (RLS).

`contratista` y `contratista_frente` están en el bloque A de `rls_policies`
(`database/migrations/20260814000012`): lectura para toda la organización,
escritura solo para `app.es_config()`. `org_id` en los INSERT sale de
`current_setting('app.org_id')`.

Los **alias** con que un contratista aparece en archivos externos no se
guardan aquí: van a `mapeo` (§10.3), para que la lista oficial quede limpia y
el cruce siga siendo por clave (§3.3).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioContratistasSQL"]

_COLUMNAS = """
    id, clave, razon_social, rfc, contacto, telefono, email, calificacion, estatus
"""


class RepositorioContratistasSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Alta de contratista (§11.2 `POST /contratistas`, rol C).

        Claves esperadas: ``clave`` y ``razon_social``, ya normalizadas por
        `domain.catalogos.reglas.Contratista`. ``frentes`` (opcional) puebla
        la tabla puente `contratista_frente` (§7.3).
        """
        contratista_id: UUID = (
            await self._sesion.execute(
                text(
                    """
                    insert into contratista
                        (org_id, clave, razon_social, rfc, contacto, telefono,
                         email, calificacion)
                    values (cast(current_setting('app.org_id') as uuid),
                            :clave, :razon_social, :rfc, :contacto, :telefono,
                            :email, cast(:calificacion as numeric))
                    returning id
                    """
                ),
                {
                    "clave": datos["clave"],
                    "razon_social": datos["razon_social"],
                    "rfc": datos.get("rfc"),
                    "contacto": datos.get("contacto"),
                    "telefono": datos.get("telefono"),
                    "email": datos.get("email"),
                    "calificacion": datos.get("calificacion"),
                },
            )
        ).scalar_one()

        frentes = [str(f) for f in datos.get("frentes") or []]
        if frentes:
            await self._sesion.execute(
                text(
                    """
                    insert into contratista_frente (org_id, contratista_id, frente_id)
                    select cast(current_setting('app.org_id') as uuid),
                           :contratista_id, f
                    from unnest(cast(:frentes as uuid[])) as f
                    """
                ),
                {"contratista_id": str(contratista_id), "frentes": frentes},
            )
        return contratista_id

    async def actualizar(self, contratista_id: UUID, cambios: dict[str, Any]) -> None:
        """Edición parcial; la `clave` no es editable (§3.3).

        Lista blanca como el resto de los catálogos: la clave del dict entra a
        la sentencia, así que solo pueden entrar éstas. `frentes` no está — es
        la tabla puente y se reemplaza aparte (`reemplazar_frentes`), porque un
        `update` no puede expresar "estos y no los otros".
        """
        editables = {
            "razon_social": "razon_social = :razon_social",
            "rfc": "rfc = :rfc",
            "contacto": "contacto = :contacto",
            "telefono": "telefono = :telefono",
            "email": "email = :email",
            "estatus": "estatus = cast(:estatus as estatus_registro)",
        }
        asignaciones = [sql for campo, sql in editables.items() if campo in cambios]
        if not asignaciones:
            return
        await self._sesion.execute(
            text(
                f"update contratista set {', '.join(asignaciones)} "
                f"where id = cast(:id as uuid)"
            ),
            {"id": str(contratista_id), **{c: cambios[c] for c in editables if c in cambios}},
        )

    async def reemplazar_frentes(
        self, contratista_id: UUID, frente_ids: Sequence[UUID]
    ) -> None:
        """Deja al contratista con **exactamente** esos frentes (§8.3).

        Reemplazo y no alta: un contratista que dejó de hacer instalaciones
        tiene que perder ese frente, y un `insert ... on conflict do nothing`
        lo dejaría ahí para siempre.
        """
        await self._sesion.execute(
            text(
                "delete from contratista_frente "
                "where contratista_id = cast(:id as uuid)"
            ),
            {"id": str(contratista_id)},
        )
        if not frente_ids:
            return
        await self._sesion.execute(
            text(
                """
                insert into contratista_frente (org_id, contratista_id, frente_id)
                select cast(current_setting('app.org_id') as uuid),
                       cast(:id as uuid), f
                from unnest(cast(:frentes as uuid[])) as f
                """
            ),
            {"id": str(contratista_id), "frentes": [str(f) for f in frente_ids]},
        )

    async def obtener(self, contratista_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from contratista where id = :id"),
                {"id": str(contratista_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def listar(self, *, solo_activos: bool = True) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from contratista
                    where not cast(:solo_activos as boolean) or estatus = 'activo'
                    order by clave
                    """
                ),
                {"solo_activos": solo_activos},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
