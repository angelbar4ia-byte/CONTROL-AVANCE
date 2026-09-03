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

    async def actualizar(self, especialidad_id: UUID, cambios: dict[str, Any]) -> None:
        """Edición parcial; la `clave` no es editable (§3.3: es la identidad)."""
        campos = {c: v for c, v in cambios.items() if c in _EDITABLES}
        if not campos:
            return
        sets = ", ".join(f"{c} = :{c}" for c in campos)
        await self._sesion.execute(
            text(f"update especialidad set {sets} where id = cast(:id as uuid)"),
            {**campos, "id": str(especialidad_id)},
        )

    async def reemplazar_conceptos(
        self, especialidad_id: UUID, concepto_ids: list[UUID]
    ) -> None:
        """Deja ese oficio con **exactamente** esos conceptos.

        Reemplazo y no alta, igual que `asignar_frente` para las etapas (0045):
        un concepto que se quitó de la lista queda sin oficio en vez de
        arrastrarse, y la pantalla no manda dos llamadas para moverlo de un
        oficio a otro.

        Un concepto tiene **un** oficio: tomarlo aquí lo quita del que tuviera.
        En dos, su trabajo se contaría dos veces al desglosar un frente.
        """
        await self._sesion.execute(
            text(
                "update concepto set especialidad_id = null "
                "where especialidad_id = cast(:id as uuid)"
            ),
            {"id": str(especialidad_id)},
        )
        if not concepto_ids:
            return
        await self._sesion.execute(
            text(
                "update concepto set especialidad_id = cast(:id as uuid) "
                "where id = any(cast(:conceptos as uuid[]))"
            ),
            {"id": str(especialidad_id), "conceptos": [str(c) for c in concepto_ids]},
        )

    async def fusionar(self, *, destino: UUID, absorbida: UUID) -> dict[str, Any]:
        """Une dos oficios que resultaron ser el mismo.

        Pasa **todo** lo que apunta a `absorbida` —conceptos y contratistas— a
        `destino` y borra la absorbida. Es lo que hace falta cuando el catálogo
        del cliente escribe el mismo oficio de dos formas: `EQUIPAMIENTO` con
        claves `EQU` y `EQUIPAMIENTOS` con claves `MSA` resultaron ser uno solo,
        y separados partían el desglose de un frente en dos renglones que nadie
        podía contratar por separado.

        El puente de contratistas usa `on conflict do nothing`: quien ya sabía
        hacer los dos oficios acabaría con la fila repetida, y la única de la
        tabla lo rechazaría a media fusión.

        Devuelve qué se movió, para poder decírselo a quien lo pidió — una
        fusión es difícil de revertir y merece un resumen, no un 204 mudo.
        """
        parametros = {"destino": str(destino), "absorbida": str(absorbida)}

        conceptos = (
            await self._sesion.execute(
                text(
                    "update concepto set especialidad_id = cast(:destino as uuid) "
                    "where especialidad_id = cast(:absorbida as uuid)"
                ),
                parametros,
            )
        ).rowcount

        contratistas = (
            await self._sesion.execute(
                text(
                    """
                    insert into contratista_especialidad
                        (org_id, contratista_id, especialidad_id)
                    select org_id, contratista_id, cast(:destino as uuid)
                      from contratista_especialidad
                     where especialidad_id = cast(:absorbida as uuid)
                    on conflict (contratista_id, especialidad_id) do nothing
                    """
                ),
                parametros,
            )
        ).rowcount
        await self._sesion.execute(
            text(
                "delete from contratista_especialidad "
                "where especialidad_id = cast(:absorbida as uuid)"
            ),
            parametros,
        )

        await self._sesion.execute(
            text("delete from especialidad where id = cast(:absorbida as uuid)"),
            parametros,
        )
        return {"conceptos": conceptos, "contratistas": contratistas}


_EDITABLES = ("nombre", "orden", "estatus")
"""Lo que se puede cambiar de un oficio ya creado. La `clave` no: es la
identidad con la que se vuelve a cargar el archivo (§3.3)."""
