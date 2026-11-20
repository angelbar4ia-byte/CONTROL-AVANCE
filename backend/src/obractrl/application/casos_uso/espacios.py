"""Los espacios de una obra (0143, D-565/D-566): alta y edición, las ramas del árbol de cada uno y la asignación de muros y polígonos de losa.

Solo **Control de obra** edita la estructura de los espacios y asigna (lo exige la API y también RLS); los demás roles leen. Lo asignado a un
espacio alimenta la partida de ese espacio: al cambiar la estructura o una asignación se rehacen las tomas de la obra (`SincronizarTomas`) en la misma
transacción, igual que al elegir una plantilla de muro. Un muro compartido entre dos espacios se reparte (por omisión mitad y mitad) y suma una sola
vez. Las reglas viven en `domain.cuantificacion.espacios`.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import TrazoNoEncontrado
from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.puertos.espacios import RepositorioEspacios
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.cuantificacion.espacios import (
    ErrorDeEspacio,
    reparto_de_muro,
    validar_asignacion_de_muro,
    validar_espacio,
    validar_que_edita,
)

__all__ = ["EspacioNoEncontrado", "GestionarEspacios"]


class EspacioNoEncontrado(LookupError):
    """El espacio no existe o salió del alcance (RLS): indistinguibles a propósito (§12.4)."""


class GestionarEspacios:
    def __init__(self, *, espacios: RepositorioEspacios, uow: UnidadDeTrabajo, tomas: Any | None = None) -> None:
        self._espacios = espacios
        self._uow = uow
        # Con el sincronizador de tomas, lo que cambia aquí se refleja en las partidas dentro de la misma transacción.
        self._tomas = tomas

    async def _obra(self, obra_id: UUID) -> None:
        if not await self._espacios.obra_visible(obra_id):
            raise ObraNoEncontrada(f"La obra {obra_id} no existe o está fuera de tu alcance.")

    async def _espacio(self, espacio_id: UUID) -> dict[str, Any]:
        e = await self._espacios.uno(espacio_id)
        if e is None:
            raise EspacioNoEncontrado(f"El espacio {espacio_id} no existe o no está en tu alcance.")
        return e

    async def _resincronizar(self, obra_id: UUID) -> None:
        if self._tomas is not None:
            await self._tomas.de_la_obra(obra_id)

    async def listar(self, obra_id: UUID) -> list[dict[str, Any]]:
        await self._obra(obra_id)
        return await self._espacios.listar(obra_id)

    async def crear(self, obra_id: UUID, *, rol: str, autor_id: UUID, nombre: str, tipo: str | None, nivel_id: UUID | None, area_m2: Any) -> dict[str, Any]:
        validar_que_edita(rol)
        await self._obra(obra_id)
        datos = {**validar_espacio(nombre=nombre, tipo=tipo, area_m2=area_m2), "nivel_id": nivel_id}
        async with self._uow:
            nuevo = await self._espacios.crear(obra_id=obra_id, datos=datos, autor_id=autor_id)
            await self._uow.commit()
        return await self._espacio(nuevo)

    async def cambiar(self, espacio_id: UUID, *, rol: str, nombre: str, tipo: str | None, nivel_id: UUID | None, area_m2: Any) -> dict[str, Any]:
        validar_que_edita(rol)
        await self._espacio(espacio_id)
        datos = {**validar_espacio(nombre=nombre, tipo=tipo, area_m2=area_m2), "nivel_id": nivel_id}
        async with self._uow:
            await self._espacios.actualizar(espacio_id, datos)
            await self._uow.commit()
        return await self._espacio(espacio_id)

    async def borrar(self, espacio_id: UUID, *, rol: str) -> None:
        validar_que_edita(rol)
        e = await self._espacio(espacio_id)
        async with self._uow:
            await self._espacios.eliminar(espacio_id)
            await self._resincronizar(UUID(str(e["obra_id"])))
            await self._uow.commit()

    async def fijar_nodos(self, espacio_id: UUID, *, rol: str, nodo_ids: list[UUID]) -> dict[str, Any]:
        """Las ramas del árbol del presupuesto que pertenecen al espacio (sus partidas heredan el espacio)."""
        validar_que_edita(rol)
        e = await self._espacio(espacio_id)
        obra_id = UUID(str(e["obra_id"]))
        unicos = list(dict.fromkeys(nodo_ids))
        validos = set(await self._espacios.nodos_de_la_obra(obra_id, unicos))
        if len(validos) != len(unicos):
            raise ErrorDeEspacio("Un nodo no es del árbol de esta obra.")
        async with self._uow:
            await self._espacios.fijar_nodos(obra_id=obra_id, espacio_id=espacio_id, nodo_ids=unicos)
            await self._resincronizar(obra_id)
            await self._uow.commit()
        return await self._espacio(espacio_id)

    async def _trazo(self, trazo_id: UUID) -> dict[str, Any]:
        t = await self._espacios.trazo(trazo_id)
        if t is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        return t

    @staticmethod
    def _asignacion(t: dict[str, Any]) -> dict[str, Any]:
        """La asignación de un trazo y cómo se reparte (las fracciones suman 1; sin espacio, vacío)."""
        reparto = reparto_de_muro(t["espacio_id"], t["espacio_comparte_id"], t["espacio_reparto_pct"])
        return {
            "trazo_id": t["id"], "espacio_id": t["espacio_id"], "espacio_comparte_id": t["espacio_comparte_id"],
            "reparto_pct": t["espacio_reparto_pct"],
            "reparto": [{"espacio_id": e, "fraccion": f} for e, f in reparto],
        }

    async def ver_trazo(self, trazo_id: UUID) -> dict[str, Any]:
        return self._asignacion(await self._trazo(trazo_id))

    async def asignar_trazo(
        self, trazo_id: UUID, *, rol: str, espacio_id: UUID | None, comparte_id: UUID | None, reparto_pct: Any
    ) -> dict[str, Any]:
        """Asigna un muro o un polígono de losa a un espacio (o a ninguno); un muro puede compartirse entre dos espacios con su reparto."""
        validar_que_edita(rol)
        t = await self._trazo(trazo_id)
        if t["hueco_de"] is not None:
            raise ErrorDeEspacio("Un hueco no se asigna a un espacio: va con su trazo.")
        espacio_id, comparte_id, pct = validar_asignacion_de_muro(espacio_id=espacio_id, comparte_id=comparte_id, reparto_pct=reparto_pct)
        if comparte_id is not None and t["tipo"] != "LINESTRING":
            raise ErrorDeEspacio("Solo un muro (una línea) se comparte entre dos espacios.")
        obra_id = UUID(str(t["obra_id"]))
        for ident in (espacio_id, comparte_id):
            if ident is not None:
                e = await self._espacios.uno(ident)
                if e is None or UUID(str(e["obra_id"])) != obra_id:
                    raise ErrorDeEspacio("El espacio no existe en la obra de este trazo.")
        async with self._uow:
            await self._espacios.fijar_espacio_de_trazo(trazo_id, espacio_id, comparte_id, pct)
            await self._resincronizar(obra_id)
            await self._uow.commit()
        return self._asignacion(await self._trazo(trazo_id))
