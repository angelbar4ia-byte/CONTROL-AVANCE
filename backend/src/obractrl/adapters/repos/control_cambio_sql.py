"""Repositorio del control de cambio (§11.3, §12.4, migración 0049).

`control_cambio` entra por el mismo predicado que `actividad` —
`app.obra_visible(obra_id)`—: ningún método de aquí filtra por `org_id` u
`obra_id` para decidir qué es visible, eso lo impone la base. `org_id` en los
INSERT sale de `current_setting('app.org_id')`.

La línea hereda la visibilidad de su cabecera por `exists`, así que tampoco
necesita filtro propio.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RepositorioControlCambioSQL"]


class RepositorioControlCambioSQL:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def crear(self, datos: dict[str, Any]) -> UUID:
        """Abre la solicitud con sus renglones, en una sola transacción.

        El id se genera aquí para poder insertar las líneas sin un segundo
        viaje: son cabecera y renglones de la misma cosa, y una solicitud a
        medias —con cabecera y sin líneas— no pide nada.
        """
        control_id = uuid4()
        await self._sesion.execute(
            text(
                """
                insert into control_cambio
                    (id, org_id, obra_id, tipo, nivel_id, etapa_id, motivo,
                     solicitado_por)
                values
                    (:id, cast(current_setting('app.org_id') as uuid),
                     cast(:obra_id as uuid), cast(:tipo as tipo_control_cambio),
                     cast(:nivel_id as uuid), cast(:etapa_id as uuid), :motivo,
                     cast(:solicitado_por as uuid))
                """
            ),
            {
                "id": str(control_id),
                "obra_id": str(datos["obra_id"]),
                "tipo": datos["tipo"],
                "nivel_id": _o_nulo(datos.get("nivel_id")),
                "etapa_id": _o_nulo(datos.get("etapa_id")),
                "motivo": datos["motivo"],
                "solicitado_por": str(datos["solicitado_por"]),
            },
        )

        for linea in datos["lineas"]:
            await self._sesion.execute(
                text(
                    """
                    insert into control_cambio_linea
                        (org_id, control_cambio_id, actividad_id, concepto_id,
                         descripcion, cantidad, precio_unitario, sustituye_a)
                    values
                        (cast(current_setting('app.org_id') as uuid),
                         :control_cambio_id, cast(:actividad_id as uuid),
                         cast(:concepto_id as uuid), :descripcion, :cantidad,
                         :precio_unitario, cast(:sustituye_a as uuid))
                    """
                ),
                {
                    "control_cambio_id": str(control_id),
                    "actividad_id": _o_nulo(linea.get("actividad_id")),
                    "concepto_id": _o_nulo(linea.get("concepto_id")),
                    "descripcion": linea.get("descripcion"),
                    "cantidad": linea["cantidad"],
                    "precio_unitario": linea.get("precio_unitario") or Decimal(0),
                    "sustituye_a": _o_nulo(linea.get("sustituye_a")),
                },
            )
        return control_id

    async def obtener(self, control_id: UUID) -> dict[str, Any] | None:
        fila = (
            await self._sesion.execute(
                text(f"select {_COLUMNAS} from control_cambio cc where cc.id = :id"),
                {"id": str(control_id)},
            )
        ).mappings().first()
        return dict(fila) if fila is not None else None

    async def lineas_de(self, control_id: UUID) -> list[dict[str, Any]]:
        filas = (
            await self._sesion.execute(
                text(
                    """
                    select l.id, l.actividad_id, l.concepto_id, l.descripcion,
                           l.cantidad, l.precio_unitario, l.sustituye_a,
                           act.cant_base, act.cant_programada, act.cant_ejecutada,
                           act.tolerancia_pct, act.cant_autorizada,
                           coalesce(act.descripcion, con.descripcion)
                               as actividad_descripcion,
                           con.clave as concepto_clave
                      from control_cambio_linea l
                      left join actividad act on act.id = l.actividad_id
                      left join concepto  con on con.id
                                = coalesce(l.concepto_id, act.concepto_id)
                     where l.control_cambio_id = :id
                     order by l.created_at, l.id
                    """
                ),
                {"id": str(control_id)},
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def listar(
        self, *, obra_id: UUID | None = None, estatus: str | None = None
    ) -> list[dict[str, Any]]:
        """Las solicitudes visibles, con su importe ya sumado.

        El importe se calcula en SQL y no en Python porque la lista es lo que
        Control mira para decidir cuál abrir: pedir las líneas de cada una para
        sumarlas serían N consultas para una pantalla de lectura.
        """
        filas = (
            await self._sesion.execute(
                text(
                    f"""
                    select {_COLUMNAS},
                           (select coalesce(sum(l.cantidad * l.precio_unitario), 0)
                              from control_cambio_linea l
                             where l.control_cambio_id = cc.id) as importe,
                           (select count(*)
                              from control_cambio_linea l
                             where l.control_cambio_id = cc.id) as renglones
                      from control_cambio cc
                     where (cast(:obra_id as uuid) is null
                            or cc.obra_id = cast(:obra_id as uuid))
                       and (cast(:estatus as estatus_control_cambio) is null
                            or cc.estatus = cast(:estatus as estatus_control_cambio))
                     order by cc.solicitado_en desc
                    """
                ),
                {
                    "obra_id": str(obra_id) if obra_id else None,
                    "estatus": estatus,
                },
            )
        ).mappings().all()
        return [dict(fila) for fila in filas]

    async def resolver(
        self,
        control_id: UUID,
        *,
        autorizado: bool,
        usuario_id: UUID,
        orden_cambio: str | None,
        nota: str | None,
        descuenta_ejecutado: bool = False,
    ) -> bool:
        """Cierra la solicitud. `False` si ya estaba resuelta.

        El `where estatus = 'solicitado'` es la guarda contra la doble
        autorización: dos personas abriendo la misma solicitud a la vez la
        aplicarían dos veces, y el costo de la obra subiría el doble.
        """
        return (
            await self._sesion.execute(
                text(
                    """
                    update control_cambio
                       set estatus = cast(:estatus as estatus_control_cambio),
                           orden_cambio = :orden_cambio,
                           autorizado_por = cast(:usuario_id as uuid),
                           nota_resolucion = :nota,
                           descuenta_ejecutado = :descuenta,
                           resuelto_en = now()
                     where id = :id and estatus = 'solicitado'
                    """
                ),
                {
                    "id": str(control_id),
                    "estatus": "autorizado" if autorizado else "rechazado",
                    "orden_cambio": orden_cambio,
                    "usuario_id": str(usuario_id),
                    "nota": nota,
                    "descuenta": descuenta_ejecutado,
                },
            )
        ).rowcount > 0

    async def autorizar_cantidad(
        self, actividad_id: UUID, cantidad: Decimal, orden_cambio: str
    ) -> None:
        """Sube el techo de una actividad a la cantidad que Control firmó.

        Se escribe `cant_autorizada` y **no** `cant_base`: la base es la
        cantidad del proyecto, y subirla borraría la desviación que justifica
        el control de cambio — la obra parecería haber ido según lo previsto.

        La orden de cambio se copia a la actividad para que el rastro viaje con
        ella hasta la estimación, donde alguien la va a cobrar.
        """
        await self._sesion.execute(
            text(
                """
                update actividad
                   set cant_autorizada = :cantidad,
                       orden_cambio = :orden_cambio
                 where id = :id
                """
            ),
            {
                "id": str(actividad_id),
                "cantidad": cantidad,
                "orden_cambio": orden_cambio,
            },
        )

    async def cancelar_actividad(
        self, actividad_id: UUID, *, descuenta_ejecutado: bool
    ) -> None:
        """Da de baja la actividad que una sustitución reemplaza.

        Con `descuenta_ejecutado` en falso —el default— **lo ejecutado se
        queda**: el trabajo se hizo y alguien lo pagó, así que sigue siendo
        estimable. En verdadero se pone en cero, que es la excepción que Control
        decide cuando el trabajo no se va a cobrar.

        La actividad no se borra: se congela su cantidad programada en lo
        ejecutado. Borrarla perdería el rastro de que existió, y la estimación
        que ya la incluyó dejaría de cuadrar.
        """
        await self._sesion.execute(
            text(
                """
                update actividad
                   set cant_ejecutada = case when :descuenta then 0
                                             else cant_ejecutada end,
                       cant_programada = case when :descuenta then 0
                                              else cant_ejecutada end,
                       estatus = 'concluida'
                 where id = :id
                """
            ),
            {"id": str(actividad_id), "descuenta": descuenta_ejecutado},
        )


_COLUMNAS = """
    cc.id, cc.obra_id, cc.tipo, cc.estatus, cc.nivel_id, cc.etapa_id,
    cc.motivo, cc.solicitado_por, cc.solicitado_en, cc.orden_cambio,
    cc.autorizado_por, cc.resuelto_en, cc.nota_resolucion,
    cc.descuenta_ejecutado
"""


def _o_nulo(valor: object) -> str | None:
    return str(valor) if valor else None
