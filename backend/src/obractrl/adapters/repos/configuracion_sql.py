"""Repositorio de configurables (§8.7).

Spec §12.11 (adaptador de persistencia) · §10.7 (RLS como frontera) · §3.5,
§3.6 (IVA y umbral de desviación: los configurables reales de §8.7).

RLS ya filtra `configuracion` por `org_id` (política `configuracion_select`,
`database/migrations/0012`): este repo no pasa `org_id` en ningún WHERE,
viene implícito del contexto que fijó `sesion_con_rls` (§12.4).

Nota de alcance: `CapturarAvance` (el único caso de uso implementado hasta
ahora) **no** usa este repositorio — el tope de sobre-programación y el
umbral de "casi" del §6 son fórmulas fijas, no configurables de §8.7 (ver el
comentario en `domain.avance.reglas`). Este repositorio queda listo para los
casos de uso que sí leen configurables reales: IVA (§3.5), umbral de
desviación (§3.6), similitud mínima para homologación (§10.3), etc.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioConfiguracionSQL"]


class RepositorioConfiguracionSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def obtener(
        self, clave: str, *, ambito: str = "global", ambito_id: UUID | None = None
    ) -> object | None:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    select valor
                    from configuracion
                    where clave = :clave
                      and ambito = :ambito
                      and ambito_id is not distinct from cast(:ambito_id as uuid)
                      and vigente_hasta is null
                    limit 1
                    """
                ),
                {
                    "clave": clave,
                    "ambito": ambito,
                    "ambito_id": str(ambito_id) if ambito_id else None,
                },
            )
        ).first()
        return fila[0] if fila is not None else None

    async def decimal(
        self, clave: str, default: Decimal, *, ambito_id: UUID | None = None
    ) -> Decimal:
        """Lee un configurable numérico; el default es solo fallback (§8.7)."""
        valor = await self.obtener(clave, ambito_id=ambito_id)
        if valor is None:
            return default

        # El dialecto asyncpg deserializa jsonb solo (un número JSON llega
        # como float/int de Python, no como texto crudo). Se pasa por str()
        # antes de Decimal(): str(0.16) == '0.16' es exacto, mientras que
        # Decimal(0.16) directo arrastra el ruido binario del float — el
        # mismo motivo por el que domain.shared.valores.Dinero rechaza float.
        if not isinstance(valor, (int, float, str)):
            raise TypeError(
                f"El configurable {clave!r} no es numérico: {valor!r} "
                f"({type(valor).__name__})."
            )
        return Decimal(str(valor))

    async def fijar(self, clave: str, valor: object) -> None:
        """Deja el valor **global** vigente de un configurable (crea o actualiza)."""
        import json

        r = await self._sesion.execute(
            text(
                """
                update configuracion set valor = cast(:valor as jsonb)
                 where clave = :clave and ambito = 'global' and ambito_id is null
                   and vigente_hasta is null
                """
            ),
            {"clave": clave, "valor": json.dumps(valor)},
        )
        if r.rowcount == 0:
            await self._sesion.execute(
                text(
                    """
                    insert into configuracion (org_id, clave, valor, ambito)
                    values (current_setting('app.org_id')::uuid, :clave,
                            cast(:valor as jsonb), 'global')
                    """
                ),
                {"clave": clave, "valor": json.dumps(valor)},
            )
