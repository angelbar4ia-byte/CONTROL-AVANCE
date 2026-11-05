"""El árbol propio de una obra y las versiones de su presupuesto (D-624).

Una obra en diseño puede tener su propio árbol: un prototipo de un solo uso **clonado** del prototipo base, de modo que
editarlo no toca a las demás obras. Los cambios (niveles, etapas, conceptos) se aplican al árbol y se juntan en un
**borrador** del presupuesto que nace al primer cambio; Control de obra o Costos lo **confirma** (queda fijo) y lo **fija
como activo**. Mientras no se programe y asigne, todo es diseño y es reversible; una parte asignada no se toca.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.catalogos.reglas import ErrorDeCatalogo
from obractrl.domain.partes.estado import ErrorDeParte, EstadoDeParte

__all__ = ["ESTADOS_QUE_YA_SON_CONTRATO", "ArbolDeObra"]

# Una obra en diseño no tiene nada contratado: solo cuando una parte se programa se considera contratada (D-624).
ESTADOS_QUE_YA_SON_CONTRATO = (EstadoDeParte.PROGRAMADA.value, EstadoDeParte.ASIGNADA.value)

_HIJO_DE = {"nivel": None, "etapa": "nivel", "concepto": "etapa"}


class ArbolDeObra:
    def __init__(self, *, arbol: Any, partes: Any, uow: UnidadDeTrabajo) -> None:
        self._arbol = arbol
        self._partes = partes
        self._uow = uow

    async def _obra(self, obra_id: UUID) -> dict[str, Any]:
        obra = await self._arbol.obra(obra_id)
        if obra is None:
            raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
        return obra

    async def _propia(self, obra_id: UUID) -> dict[str, Any]:
        obra = await self._obra(obra_id)
        if not obra["de_una_obra"]:
            raise ErrorDeCatalogo(
                "Esta obra usa el árbol del prototipo base, que es compartido. Crea el árbol propio de la obra para editarlo."
            )
        return obra

    async def _exigir_parte_libre(self, obra_id: UUID, etapa_id: UUID | None) -> None:
        if etapa_id is None:
            return
        estados = await self._partes.estados_de_obra(obra_id)
        if estados.get(f"etapa:{etapa_id}") == EstadoDeParte.ASIGNADA.value:
            raise ErrorDeParte("Esa parte ya está asignada: cambiarla es control de cambio, no diseño.")

    async def _etapa_de(self, nodo: dict[str, Any]) -> UUID | None:
        """La etapa del catálogo a la que pertenece un nodo (él mismo o su ancestro), para saber si su parte está asignada."""
        actual: dict[str, Any] | None = nodo
        while actual is not None:
            if actual["tipo"] == "etapa":
                return actual["etapa_id"]
            actual = await self._arbol.nodo(actual["parent_id"]) if actual["parent_id"] else None
        return None

    async def ver(self, obra_id: UUID) -> dict[str, Any]:
        obra = await self._obra(obra_id)
        pid = obra["prototipo_id"]
        borrador = await self._arbol.borrador(pid)
        return {
            "propio": bool(obra["de_una_obra"]),
            "prototipo_id": pid,
            "prototipo_clave": obra["prototipo_clave"],
            "prototipo_nombre": obra["prototipo_nombre"],
            "forma_de_arranque": await self._arbol.forma_de_arranque(obra_id),
            "partidas": await self._arbol.partidas_de_la_obra(obra_id),
            "borrador_id": borrador["id"] if borrador else None,
            "versiones": await self._arbol.versiones(pid),
            "nodos": await self._arbol.nodos(pid),
        }

    async def crear_propio(self, obra_id: UUID) -> dict[str, Any]:
        obra = await self._obra(obra_id)
        if obra["de_una_obra"]:
            raise ErrorDeCatalogo("Esta obra ya tiene su árbol propio.")
        estados = await self._partes.estados_de_obra(obra_id)
        if any(e == EstadoDeParte.ASIGNADA.value for e in estados.values()):
            raise ErrorDeParte("La obra ya tiene partes asignadas: no se clona el árbol, eso es control de cambio.")
        async with self._uow:
            clave = await self._arbol.clave_libre(str(obra["clave"]))
            nuevo, mapa = await self._arbol.clonar(obra["prototipo_id"], clave)
            ligadas = await self._arbol.apuntar_obra(obra_id, nuevo, mapa)
            await self._uow.commit()
        return {"prototipo_id": nuevo, "clave": clave, "nodos": len(mapa), "partidas_religadas": ligadas}

    async def crear_nodo(
        self, obra_id: UUID, *, tipo: str, parent_id: UUID | None, nombre: str | None, concepto_id: UUID | None
    ) -> UUID:
        obra = await self._propia(obra_id)
        pid = obra["prototipo_id"]
        esperado = _HIJO_DE[tipo]
        padre = None
        if esperado is None:
            if parent_id is not None:
                raise ErrorDeCatalogo("Un nivel no cuelga de nada.")
        else:
            padre = await self._arbol.nodo(parent_id) if parent_id else None
            if padre is None or padre["prototipo_id"] != pid or padre["tipo"] != esperado:
                raise ErrorDeCatalogo(f"Un {tipo} cuelga de un {esperado} de este árbol.")
            await self._exigir_parte_libre(obra_id, await self._etapa_de(padre))
        clave = None
        if tipo == "concepto":
            if concepto_id is None:
                raise ErrorDeCatalogo("Elige el concepto de la partida.")
            concepto = await self._arbol.concepto(concepto_id)
            if concepto is None:
                raise ErrorDeCatalogo("El concepto no existe o está fuera de tu alcance.")
            nombre, clave = concepto["descripcion"], concepto["clave"]
        nombre = " ".join((nombre or "").split())
        if not nombre:
            raise ErrorDeCatalogo(f"El {tipo} necesita un nombre.")
        async with self._uow:
            borrador = await self._arbol.asegurar_borrador(pid)
            nodo = await self._arbol.crear_nodo(
                prototipo_id=pid, parent_id=parent_id, tipo=tipo, nombre=nombre, clave=clave, concepto_id=concepto_id
            )
            if tipo == "concepto" and concepto_id is not None:
                await self._arbol.partida_al_borrador(borrador, nodo, concepto_id)
            await self._uow.commit()
        return nodo

    async def _nodo_de_la_obra(self, obra_id: UUID, nodo_id: UUID) -> tuple[dict[str, Any], dict[str, Any]]:
        obra = await self._propia(obra_id)
        nodo = await self._arbol.nodo(nodo_id)
        if nodo is None or nodo["prototipo_id"] != obra["prototipo_id"]:
            raise ErrorDeCatalogo("El nodo no existe en el árbol de esta obra.")
        await self._exigir_parte_libre(obra_id, await self._etapa_de(nodo))
        return obra, nodo

    async def ajustar_nodo(self, obra_id: UUID, nodo_id: UUID, *, nombre: str | None, orden: int | None) -> None:
        obra, _ = await self._nodo_de_la_obra(obra_id, nodo_id)
        limpio = " ".join(nombre.split()) if nombre is not None else None
        if nombre is not None and not limpio:
            raise ErrorDeCatalogo("El nombre no puede quedar vacío.")
        async with self._uow:
            await self._arbol.asegurar_borrador(obra["prototipo_id"])
            await self._arbol.ajustar_nodo(nodo_id, limpio, orden)
            await self._uow.commit()

    async def eliminar_nodo(self, obra_id: UUID, nodo_id: UUID) -> None:
        obra, _ = await self._nodo_de_la_obra(obra_id, nodo_id)
        sub = await self._arbol.subarbol(nodo_id)
        if await self._arbol.partidas_de_obra_en(sub):
            raise ErrorDeParte(
                "La obra ya generó partidas de este nodo: quita esas partidas (o deshaz la generación) antes de quitarlo del árbol."
            )
        async with self._uow:
            borrador = await self._arbol.asegurar_borrador(obra["prototipo_id"])
            await self._arbol.eliminar_nodo(nodo_id, borrador, sub)
            await self._uow.commit()

    async def confirmar(self, obra_id: UUID, nota: str | None) -> None:
        obra = await self._propia(obra_id)
        borrador = await self._arbol.borrador(obra["prototipo_id"])
        if borrador is None:
            raise ErrorDeCatalogo("No hay cambios por confirmar: el borrador nace con el primer cambio del árbol.")
        async with self._uow:
            await self._arbol.confirmar(borrador["id"], " ".join(nota.split()) if nota else None)
            await self._uow.commit()

    async def activar(self, obra_id: UUID, presupuesto_id: UUID) -> None:
        obra = await self._propia(obra_id)
        p = await self._arbol.presupuesto(presupuesto_id)
        if p is None or p["prototipo_id"] != obra["prototipo_id"]:
            raise ErrorDeCatalogo("Esa versión no es del presupuesto de esta obra.")
        if p["estado"] != "confirmada":
            raise ErrorDeCatalogo("Solo una versión confirmada se fija como activa: confirma primero el borrador.")
        async with self._uow:
            await self._arbol.activar(presupuesto_id, obra["prototipo_id"])
            await self._uow.commit()

    async def eliminar_obra(self, obra_id: UUID, clave_confirmada: str) -> None:
        """Borra una obra que sigue en diseño. Pide la clave escrita: la segunda confirmación (la primera es de la pantalla)."""
        obra = await self._obra(obra_id)
        await self._exigir_en_diseno(obra_id)
        if clave_confirmada.strip().upper() != str(obra["clave"]).strip().upper():
            raise ErrorDeCatalogo(f"Para eliminarla escribe su clave exacta: {obra['clave']}.")
        async with self._uow:
            await self._arbol.eliminar_obra(obra_id, obra["prototipo_id"], bool(obra["de_una_obra"]))
            await self._uow.commit()

    async def reiniciar_obra(self, obra_id: UUID, clave_confirmada: str) -> dict[str, int]:
        """Reinicia una obra en diseño desde cero (mismas condiciones y misma confirmación escrita que eliminarla)."""
        obra = await self._obra(obra_id)
        await self._exigir_en_diseno(obra_id)
        if clave_confirmada.strip().upper() != str(obra["clave"]).strip().upper():
            raise ErrorDeCatalogo(f"Para reiniciarla escribe su clave exacta: {obra['clave']}.")
        async with self._uow:
            resumen = await self._arbol.reiniciar_obra(obra_id, obra["prototipo_id"], obra.get("prototipo_origen_id"))
            await self._uow.commit()
        return resumen

    async def preparar_para_cargar(self, obra_id: UUID, *, dry_run: bool) -> UUID:
        """El prototipo sobre el que se carga una ingeniería (D-628): el árbol propio de la obra. Si la obra aún usa el
        del prototipo base lo clona (salvo en una vista previa, que no escribe). Solo en diseño. No abre su propia
        transacción: corre dentro de la de la carga."""
        obra = await self._obra(obra_id)
        await self._exigir_en_diseno(obra_id)
        if obra["de_una_obra"] or dry_run:
            return UUID(str(obra["prototipo_id"]))
        clave = await self._arbol.clave_libre(str(obra["clave"]))
        nuevo, mapa = await self._arbol.clonar(obra["prototipo_id"], clave)
        await self._arbol.apuntar_obra(obra_id, nuevo, mapa)
        return UUID(str(nuevo))

    async def cargar_cantidad(self, prototipo_id: UUID, nodo_id: UUID, cantidad: Any) -> None:
        """Escribe una cantidad cargada en el árbol propio y en su borrador (nace con el primer cambio)."""
        borrador = await self._arbol.asegurar_borrador(prototipo_id)
        await self._arbol.fijar_cantidad(prototipo_id, borrador, nodo_id, cantidad)

    async def cargar_partida_nueva(
        self, prototipo_id: UUID, etapa_nodo_id: UUID, concepto_clave: str, cantidad: Any
    ) -> bool:
        """Un concepto que la ingeniería trae y el árbol no tenía: entra bajo su etapa con su cantidad. `False` si el
        concepto no existe en el catálogo."""
        concepto = await self._arbol.concepto_por_clave(concepto_clave)
        if concepto is None:
            return False
        borrador = await self._arbol.asegurar_borrador(prototipo_id)
        nodo = await self._arbol.crear_nodo(
            prototipo_id=prototipo_id,
            parent_id=etapa_nodo_id,
            tipo="concepto",
            nombre=concepto["descripcion"],
            clave=concepto["clave"],
            concepto_id=concepto["id"],
        )
        await self._arbol.partida_al_borrador(borrador, nodo, concepto["id"])
        await self._arbol.fijar_cantidad(prototipo_id, borrador, nodo, cantidad)
        return True

    async def _exigir_en_diseno(self, obra_id: UUID) -> None:
        estados = await self._partes.estados_de_obra(obra_id)
        if any(e in ESTADOS_QUE_YA_SON_CONTRATO for e in estados.values()):
            raise ErrorDeParte("La obra ya tiene partes programadas o asignadas: dejó de ser diseño.")
        trabajo = await self._arbol.trabajo_real_de_la_obra(obra_id)
        if trabajo is not None:
            raise ErrorDeParte(f"{trabajo} Dejó de ser diseño.")

    async def fijar_forma_de_arranque(self, obra_id: UUID, forma: str) -> None:
        """Por dónde se creó la obra. Solo informativa: no cambia ninguna regla (D-626)."""
        async with self._uow:
            await self._arbol.fijar_forma_de_arranque(obra_id, forma)
            await self._uow.commit()

    async def cambiar_prototipo(self, obra_id: UUID, prototipo_id: UUID, clave_confirmada: str) -> dict[str, int]:
        """Cambia el prototipo de una obra en diseño. Borra lo diseñado como al reiniciar: las partidas se generan de nuevo."""
        obra = await self._obra(obra_id)
        await self._exigir_en_diseno(obra_id)
        if clave_confirmada.strip().upper() != str(obra["clave"]).strip().upper():
            raise ErrorDeCatalogo(f"Para cambiar el prototipo escribe la clave exacta de la obra: {obra['clave']}.")
        destino = await self._arbol.prototipo(prototipo_id)
        if destino is None:
            raise ErrorDeCatalogo("El prototipo no existe o está fuera de tu alcance.")
        if destino["de_una_obra"]:
            raise ErrorDeCatalogo("Ese prototipo es de otra obra: elige uno del catálogo.")
        if destino["id"] == obra["prototipo_id"]:
            raise ErrorDeCatalogo("La obra ya usa ese prototipo.")
        async with self._uow:
            resumen = await self._arbol.reiniciar_obra(obra_id, obra["prototipo_id"], prototipo_id)
            await self._uow.commit()
        return resumen
