"""Repositorio de evaluaciones de desempeño.

Spec §12.11 (adaptador de persistencia) · §7.8 (control y flujos) · §6 ·
§12.4 (RLS).

RLS ya filtra `evaluacion` por alcance de rol (política `evaluacion_select`,
`database/migrations/0012`): Control de obra y Super intendente ven todo;
cualquier otro rol solo lo que evaluó, su propia autoevaluación, o —vía
`obra_id`— lo que cae dentro de una obra que le es visible. Ningún método de
aquí filtra por `org_id` a mano. La política de **escritura** exige además
`evaluador_id = current_usuario_id()`: el `evaluador_id` que se inserta tiene
que ser el usuario de la sesión, no uno arbitrario que le pase el caso de uso
—si no coincide, Postgres rechaza el INSERT con una violación de política.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.application.puertos.repositorios import RegistroNoEncontrado

__all__ = ["EvaluacionNoModificada", "RepositorioEvaluacionesSQL"]

_COLUMNAS = """
    id, sujeto_tipo, sujeto_id, obra_id, evaluador_id, nivel, periodo,
    puntaje, comentarios
"""


class EvaluacionNoModificada(RegistroNoEncontrado):
    """El UPDATE no afectó ninguna fila: la evaluación ya no existe o salió
    del alcance del usuario (RLS) entre el `obtener()` y la escritura."""


class RepositorioEvaluacionesSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def obtener(self, evaluacion_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from evaluacion where id = :id"),
                {"id": str(evaluacion_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def crear(
        self,
        *,
        sujeto_tipo: str,
        sujeto_id: UUID,
        evaluador_id: UUID,
        nivel: str,
        periodo: str,
        obra_id: UUID | None = None,
    ) -> UUID:
        fila = (
            await self._sesion.execute(
                text(
                    """
                    insert into evaluacion
                        (org_id, sujeto_tipo, sujeto_id, obra_id, evaluador_id,
                         nivel, periodo)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         cast(:sujeto_tipo as sujeto_evaluacion), :sujeto_id,
                         :obra_id, :evaluador_id,
                         cast(:nivel as nivel_evaluacion), :periodo)
                    returning id
                    """
                ),
                {
                    "sujeto_tipo": sujeto_tipo,
                    "sujeto_id": str(sujeto_id),
                    "obra_id": str(obra_id) if obra_id else None,
                    "evaluador_id": str(evaluador_id),
                    "nivel": nivel,
                    "periodo": periodo,
                },
            )
        ).scalar_one()
        return fila

    async def respuestas_de(self, evaluacion_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select criterio_id, valor, comentario
                    from evaluacion_respuesta
                    where evaluacion_id = :evaluacion_id
                    """
                ),
                {"evaluacion_id": str(evaluacion_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def pesos_de_criterios(self, criterio_ids: list[UUID]) -> dict[UUID, Decimal]:
        if not criterio_ids:
            return {}
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, peso from criterio_evaluacion
                    where id = any(cast(:ids as uuid[]))
                    """
                ),
                {"ids": [str(criterio_id) for criterio_id in criterio_ids]},
            )
        ).all()
        return {fila.id: Decimal(str(fila.peso)) for fila in filas}

    async def agregar_respuestas(
        self,
        evaluacion_id: UUID,
        *,
        respuestas: list[dict[str, Any]],
        puntaje: Decimal | None,
    ) -> None:
        # Inserción en lote: si `evaluacion_id` salió del alcance del usuario
        # entre el `obtener()` inicial y aquí, la política de
        # `evaluacion_respuesta` (WITH CHECK) rechaza el INSERT con una
        # violación —no hace falta revisar `rowcount` como en un UPDATE
        # scoped, igual que `actividades_sql.guardar_resultado_cpm`.
        if respuestas:
            await self._sesion.execute(
                text(
                    """
                    insert into evaluacion_respuesta
                        (org_id, evaluacion_id, criterio_id, valor, comentario)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         cast(:evaluacion_id as uuid), cast(:criterio_id as uuid),
                         :valor, :comentario)
                    """
                ),
                [
                    {
                        "evaluacion_id": str(evaluacion_id),
                        "criterio_id": str(respuesta["criterio_id"]),
                        "valor": respuesta["valor"],
                        "comentario": respuesta.get("comentario"),
                    }
                    for respuesta in respuestas
                ],
            )

        resultado = await self._sesion.execute(
            text("update evaluacion set puntaje = :puntaje where id = :id"),
            {"puntaje": puntaje, "id": str(evaluacion_id)},
        )
        if resultado.rowcount == 0:
            raise EvaluacionNoModificada(
                f"No se actualizó la evaluación {evaluacion_id}: ya no existe "
                f"o salió de tu alcance."
            )

    async def listar(
        self, *, nivel: str | None = None, sujeto_tipo: str | None = None
    ) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS}
                    from evaluacion
                    -- El cast del lado `is null` fija el tipo del parámetro;
                    -- sin él asyncpg levanta AmbiguousParameterError.
                    where (cast(:nivel as nivel_evaluacion) is null
                           or nivel = cast(:nivel as nivel_evaluacion))
                      and (cast(:sujeto_tipo as sujeto_evaluacion) is null
                           or sujeto_tipo = cast(:sujeto_tipo as sujeto_evaluacion))
                    order by created_at desc
                    """
                ),
                {"nivel": nivel, "sujeto_tipo": sujeto_tipo},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def listar_criterios(self, *, aplica_a: str | None = None) -> list[dict[str, Any]]:
        """Catálogo `criterio_evaluacion` vigente (§11.2 `GET /criterios-evaluacion`).

        Semilla editable (§8.7): solo se listan los `activo`, el usuario
        agrega/edita el resto desde Configuración, no desde código.
        """
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select id, aplica_a, clave, nombre, peso, estatus
                    from criterio_evaluacion
                    where estatus = 'activo'
                      and (cast(:aplica_a as sujeto_evaluacion) is null
                           or aplica_a = cast(:aplica_a as sujeto_evaluacion))
                    order by aplica_a, nombre
                    """
                ),
                {"aplica_a": aplica_a},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]
