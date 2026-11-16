"""Colocar en el plano lo que trae la plantilla de un muro y ver a qué conceptos alimenta (Ola 4C; M-4, Q5).

`ver` no cambia nada: dice qué castillos y cadenas lleva la plantilla en ESTE muro (su largo, su altura, su nivel), cuántos ya están
colocados y qué concepto paga cada parte en ese contexto, o por qué no cuenta (falta la partida en el árbol, concepto sin autorizar).
`colocar` pone los castillos ubicados como vanos `castillo` —instancias del elemento de la plantilla— y rehace lo que los conceptos toman;
es idempotente: reemplaza solo las instancias de la plantilla, no los castillos ni los vanos puestos a mano. `retirar` las quita.

Un muro sin plantilla se comporta como siempre (la regla vieja del «muro con cadena» sigue en `GestionarVanos.agregar`).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.conceptos_de_lo_colocado import (
    conceptos_de_lo_colocado,
    nivel_para_conceptos,
)
from obractrl.application.casos_uso.cuantificar import (
    GestionarVanos,
    TrazoNoEncontrado,
    VanoCambiado,
)
from obractrl.application.casos_uso.parametrico import vigentes_de_obra
from obractrl.domain.cuantificacion.colocacion_de_plantilla import (
    Colocacion,
    ConceptoColocado,
    colocar_plantilla,
)
from obractrl.domain.cuantificacion.elementos_parametricos import normalizar_parametros
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion
from obractrl.domain.shared.diccionario import Rol

__all__ = ["ColocarElementosDeMuro"]

_PREFIJO_DE_CASTILLO = "K"


def _concepto_dict(c: ConceptoColocado) -> dict[str, Any]:
    return {
        "ranura": c.ranura, "concepto_id": c.concepto_id, "clave": c.clave, "unidad": c.unidad, "cantidad": c.cantidad,
        "cuenta": c.cuenta, "estado": c.estado, "origen": c.origen, "aviso": c.aviso, "partida_id": c.partida_id,
    }


class ColocarElementosDeMuro(GestionarVanos):
    def __init__(self, *, elementos: Any, parametrico: Any, **deps: Any) -> None:
        super().__init__(**deps)
        self._elementos = elementos
        self._parametrico = parametrico

    async def _separacion_de_castillos(self, contexto: dict[str, Any]) -> Decimal | None:
        """El driver `separacion_castillos` vigente en la obra del muro (la separación de un castillo que la plantilla no fija)."""
        if not contexto.get("obra_id"):
            return None
        vigentes = await vigentes_de_obra(self._parametrico, UUID(str(contexto["obra_id"])))
        v = vigentes.get("separacion_castillos")
        return v.valor if v is not None else None

    async def _plan(self, trazo_id: UUID) -> tuple[dict[str, Any], dict[str, Any], Colocacion, dict[str, dict[str, Any]]]:
        """(plantilla, contexto del trazo, lo que coloca la plantilla en este muro, los elementos por clave). Levanta 404 o 422."""
        if await self._trazos.obtener(trazo_id) is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        if not await self._trazos.es_linea(trazo_id):
            raise ErrorDeCuantificacion("La plantilla se coloca sobre una línea (un muro).")
        plantilla = await self._trazos.plantilla_de_muro(trazo_id)
        if plantilla is None:
            raise ErrorDeCuantificacion("Este muro no tiene plantilla: elige una en su detalle para colocar sus elementos.")
        contexto = await self._elementos.contexto_de_trazo(trazo_id) or {}
        catalogo = {e["clave"]: e for e in await self._elementos.listar()}
        anchos: dict[str, Decimal] = {}
        for e in plantilla["elementos"] or []:
            el = catalogo.get(str(e.get("ref")))
            if e.get("clase") == "castillo" and el is not None:
                p = normalizar_parametros(el["tipo"], dict(el["parametros"] or {}))
                anchos[str(e["ref"])] = Decimal(str(p["largo"]))
        colocacion = colocar_plantilla(
            plantilla["elementos"] or [],
            largo_m=await self._trazos.largo_del_eje(trazo_id),
            altura_m=await self._altura_del_muro(trazo_id),
            anchos_m=anchos,
            separacion_m=await self._separacion_de_castillos(contexto),
        )
        return plantilla, contexto, colocacion, catalogo

    async def ver_colocacion(self, trazo_id: UUID) -> dict[str, Any]:
        plantilla, contexto, colocacion, catalogo = await self._plan(trazo_id)
        puestos = [v for v in await self._trazos.vanos_de_trazo(trazo_id) if v.get("elemento_uid")]
        obra_id = UUID(str(contexto["obra_id"])) if contexto.get("obra_id") else None
        grupos = [
            {
                "elemento_id": catalogo[i.ref]["id"], "ref": i.ref, "alto_m": i.alto_m, "piezas": i.piezas, "uid": i.uid,
                "nivel_orden": contexto.get("nivel_orden"), "nivel_id": contexto.get("nivel_id"), "etapa_id": contexto.get("etapa_id"),
                "ubicacion": contexto.get("ubicacion"),
            }
            for i in colocacion.instancias
            if i.clase == "castillo" and i.ref in catalogo and i.alto_m is not None
        ]
        conceptos: dict[str, tuple[list[ConceptoColocado], list[str]]] = {}
        if obra_id is not None and grupos:
            for g, cs, avisos in await conceptos_de_lo_colocado(
                elementos=self._elementos, parametrico=self._parametrico, obra_id=obra_id, instancias=grupos
            ):
                conceptos[g["uid"]] = (cs, avisos)
        avisos_generales = list(colocacion.avisos)
        elementos = []
        for i in colocacion.instancias:
            cs, avisos = conceptos.get(i.uid, ([], []))
            avisos_generales.extend(avisos)
            elementos.append(
                {
                    "uid": i.uid, "ref": i.ref, "nombre": catalogo.get(i.ref, {}).get("nombre", i.ref), "clase": i.clase, "modo": i.modo,
                    "piezas": i.piezas, "alto_m": i.alto_m, "z_m": i.z_m, "metros": i.metros,
                    "posiciones_m": list(i.posiciones_m), "se_coloca": i.se_coloca,
                    "colocados": sum(int(v["piezas"]) for v in puestos if v["elemento_uid"] == i.uid),
                    "descuento_m2_por_cara": i.descuento_m2_por_cara,
                    "conceptos": [_concepto_dict(c) for c in cs],
                }
            )
        return {
            "trazo_id": trazo_id,
            "plantilla_id": plantilla["id"], "plantilla": plantilla["nombre"], "version": plantilla["version"],
            "largo_m": colocacion.largo_m, "altura_m": colocacion.altura_m,
            "nivel": nivel_para_conceptos(contexto.get("nivel_orden")), "ubicacion": contexto.get("ubicacion"),
            "elementos": elementos,
            "avisos": list(dict.fromkeys(avisos_generales)),
        }

    async def _claves_libres(self, trazo_id: UUID, cuantas: int) -> list[str]:
        usadas = {str(v["clave"]).upper() for v in await self._trazos.vanos_de_trazo(trazo_id) if not v.get("elemento_uid")}
        claves: list[str] = []
        n = 1
        while len(claves) < cuantas:
            clave = f"{_PREFIJO_DE_CASTILLO}-{n:02d}"
            if clave not in usadas:
                claves.append(clave)
            n += 1
        return claves

    async def colocar(self, trazo_id: UUID, *, rol: Rol, autor_id: UUID, detectada_en: datetime) -> dict[str, Any]:
        _, _, colocacion, _ = await self._plan(trazo_id)
        a_colocar = [i for i in colocacion.instancias if i.se_coloca]
        if not a_colocar:
            raise ErrorDeCuantificacion(
                "La plantilla de este muro no lleva castillos ubicados: no hay nada que colocar en el plano "
                "(los castillos estimados solo se cuentan)."
            )
        claves = await self._claves_libres(trazo_id, sum(i.piezas for i in a_colocar))
        quitados = 0

        async def poner() -> UUID:
            nonlocal quitados
            quitados = await self._trazos.quitar_instancias_de_plantilla(trazo_id)
            primero: UUID | None = None
            for i in a_colocar:
                assert i.alto_m is not None and i.ancho_m is not None
                for posicion in i.posiciones_m:
                    vano_id = await self._trazos.crear_vano(
                        trazo_id=trazo_id, clave=claves.pop(0), tipo="castillo", ancho_m=i.ancho_m, alto_m=i.alto_m,
                        antepecho_m=Decimal(0), piezas=1, posicion_m=posicion, autor_id=autor_id, elemento_uid=i.uid,
                    )
                    primero = primero or vano_id
            assert primero is not None
            return primero

        r: VanoCambiado = await self._cambiar(trazo_id, rol, autor_id, detectada_en, poner)
        return {
            "colocados": sum(i.piezas for i in a_colocar),
            "reemplazados": quitados,
            "recalculos": r.recalculos,
            "descuento_m2_por_cara": sum((i.descuento_m2_por_cara for i in a_colocar), Decimal(0)),
        }

    async def retirar(self, trazo_id: UUID, *, rol: Rol, autor_id: UUID, detectada_en: datetime) -> dict[str, Any]:
        if await self._trazos.obtener(trazo_id) is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        quitados = 0

        async def quitar() -> UUID:
            nonlocal quitados
            quitados = await self._trazos.quitar_instancias_de_plantilla(trazo_id)
            return trazo_id

        r = await self._cambiar(trazo_id, rol, autor_id, detectada_en, quitar)
        return {"retirados": quitados, "recalculos": r.recalculos}
