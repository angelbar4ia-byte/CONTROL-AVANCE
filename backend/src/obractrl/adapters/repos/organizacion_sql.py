"""Repositorio de operaciones a nivel de organización (§5.1).

Spec §12.11 (adaptador de persistencia) · §12.4 (RLS).

`reiniciar()` no ejecuta los DELETE aquí: llama a `app.reiniciar_organizacion()`
(`database/migrations/20260814000036_reinicio_de_organizacion.sql`), una
función `security definer` — la mayoría de las tablas que borra no son
escribibles por `control_obra` bajo su sesión RLS normal (`control_proyecto`,
`evaluacion`, `notificacion`, `idempotencia`, `dispositivo_push`, `bitacora`;
ver el comentario de esa migración), así que el borrado tiene que vivir en
una función que sí bypasea RLS, no en SQL suelto desde este repositorio.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioOrganizacionSQL"]


class RepositorioOrganizacionSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def reiniciar(self) -> dict[str, int]:
        resumen = (
            await self._sesion.execute(text("select app.reiniciar_organizacion()"))
        ).scalar_one()
        return {tabla: int(cantidad) for tabla, cantidad in resumen.items()}
