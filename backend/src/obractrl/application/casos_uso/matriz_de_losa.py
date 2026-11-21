"""La matriz de conceptos de una zona de losa (fase 2): los elementos de la zona, su matriz calculada y la propuesta de sus conceptos nuevos.

Junta lo que ya existe sin duplicarlo: las **zonas** y sus polígonos de losa (fase 1, `zonas_de_losa`), los **elementos de estructura** de la biblioteca
(trabes, contratrabes y nervaduras, 3B), los **drivers** de la obra (desperdicio de concreto y receta del acero), el **catálogo vigente** (para la
conciliación) y las **propuestas** de concepto nuevo (versionado y autorización de Control de obra). El cálculo vive en el dominio
(`matriz_de_losa`); aquí solo se arma su entrada desde la base y se anota el resultado.

Medición derivada: un elemento puede medirse de una **línea del plano** (`trazo_id`). Su longitud se lee **al calcular** de la geometría del trazo y
de la escala del plano, no se guarda: si la línea cambia, la matriz cambia. Sin escala calibrada se toma 1 unidad de plano = 1 m, como las uniones de
muro, y la matriz lo dice. Solo Control de obra escribe elementos (lo exige la API y también RLS); Costos o Control de obra proponen los conceptos.
"""

from __future__ import annotations

import math
from dataclasses import replace
from itertools import pairwise
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import TrazoNoEncontrado
from obractrl.application.casos_uso.elementos_parametricos import (
    ElementoParametricoNoEncontrado,
)
from obractrl.application.casos_uso.propuestas_de_losa import (
    GestionarPropuestasDeLosa,
)
from obractrl.application.casos_uso.zonas_de_losa import (
    ZonaDeLosaNoEncontrada,
    _poligonos,
)
from obractrl.application.puertos.matriz_de_losa import RepositorioElementosDeLosa
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.application.puertos.zonas_de_losa import RepositorioZonasDeLosa
from obractrl.domain.cuantificacion.colado_por_ml import concepto_nuevo_de_colado
from obractrl.domain.cuantificacion.comparacion_con_catalogo import (
    comparar_con_concepto,
    expandir_composicion,
)
from obractrl.domain.cuantificacion.drivers_de_elementos import (
    desperdicio_concreto_de_obra,
    receta_de_obra,
)
from obractrl.domain.cuantificacion.enlaces_de_ranura import Partida
from obractrl.domain.cuantificacion.espacios import resolver_matriz_por_espacio
from obractrl.domain.cuantificacion.matriz_de_losa import (
    CAPA_DE_COMPRESION_CM,
    ElementoDeLosa,
    EntradaMatrizDeLosa,
    ErrorDeMatrizDeLosa,
    LosaDeEntrada,
    area_de_poligonos,
    calcular_matriz_de_losa,
    concepto_nuevo_de_losa,
    validar_elemento_de_losa,
)

__all__ = ["CONSERVAR_ESPACIO", "ElementoDeLosaNoEncontrado", "GestionarMatrizDeLosa"]

CONSERVAR_ESPACIO: Any = object()
"""Al cambiar un elemento, si la petición no trae `espacio_id` el elemento conserva el suyo (un cliente que no conoce los espacios no se lo quita)."""


class ElementoDeLosaNoEncontrado(ElementoParametricoNoEncontrado):
    """El elemento de la zona no existe o salió del alcance (RLS): indistinguibles a propósito (§12.4)."""


def _largo_de_linea_m(geojson: dict[str, Any], escala: float) -> float:
    puntos = [(float(p[0]) * escala, float(p[1]) * escala) for p in geojson["coordinates"]]
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in pairwise(puntos))


class GestionarMatrizDeLosa:
    def __init__(
        self,
        *,
        zonas: RepositorioZonasDeLosa,
        elementos: RepositorioElementosDeLosa,
        drivers: Any,
        propuestas: GestionarPropuestasDeLosa,
        conceptos: Any,
        insumos: Any,
        uow: UnidadDeTrabajo,
        parametrico: Any | None = None,
        sincronizador: Any | None = None,
    ) -> None:
        # Con el sincronizador de tomas, un elemento que se asigna a un espacio (o se saca de él) rehace lo que la losa paga en las partidas (0143).
        self._sincronizador = sincronizador
        # Con el repositorio del Paramétrico (0143), la matriz dice en qué partida del árbol se mide lo de cada espacio.
        self._parametrico = parametrico
        self._zonas = zonas
        self._elementos = elementos
        self._drivers = drivers
        self._propuestas = propuestas
        self._conceptos = conceptos
        self._insumos = insumos
        self._uow = uow

    # ── Contexto ────────────────────────────────────────────────────────────────────────────────────────

    async def _zona(self, zona_id: UUID) -> dict[str, Any]:
        z = await self._zonas.zona(zona_id)
        if z is None:
            raise ZonaDeLosaNoEncontrada(f"La zona de losa {zona_id} no existe o no está en tu alcance.")
        return z

    async def _escala(self, plano_id: UUID) -> tuple[float, bool, UUID]:
        plano = await self._zonas.plano(plano_id)
        if plano is None:
            raise ZonaDeLosaNoEncontrada(f"El plano {plano_id} no existe o no está en tu alcance.")
        definida = plano["escala_m_por_unidad"] is not None
        return (float(plano["escala_m_por_unidad"]) if definida else 1.0), definida, plano["obra_id"]

    async def _resincronizar(self, plano_id: UUID, *espacios: Any) -> None:
        """Si el elemento está o estaba en un espacio, lo que la losa paga en las partidas se rehace (en la misma transacción)."""
        if self._sincronizador is None or all(e is None for e in espacios):
            return
        _, _, obra_id = await self._escala(plano_id)
        await self._sincronizador.de_la_obra(obra_id)

    # ── Elementos de la zona ────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _medida(f: dict[str, Any], escala: float) -> dict[str, Any]:
        """La medida con que cuenta el elemento: la de su línea del plano (derivada) o la tecleada."""
        base = {
            "id": f["id"], "elemento_clave": f["elemento_clave"], "modo": f["modo"], "pago": f["pago"], "trazo_id": f["trazo_id"],
            "espacio_id": f.get("espacio_id"),
        }
        if f.get("geojson"):
            largo = _largo_de_linea_m(f["geojson"], escala)
            if f["modo"] == "ml":
                return {**base, "origen": "trazo", "cantidad": round(largo, 3), "largo_m": None, "longitud_del_trazo_m": round(largo, 3)}
            return {**base, "origen": "trazo", "cantidad": 1.0, "largo_m": round(largo, 3), "longitud_del_trazo_m": round(largo, 3)}
        return {
            **base, "origen": "manual", "cantidad": float(f["cantidad"]),
            "largo_m": float(f["largo_m"]) if f["largo_m"] is not None else None, "longitud_del_trazo_m": None,
        }

    async def elementos(self, zona_id: UUID) -> list[dict[str, Any]]:
        zona = await self._zona(zona_id)
        escala, _definida, _obra = await self._escala(zona["plano_id"])
        return [self._medida(f, escala) for f in await self._elementos.de_la_zona(zona_id)]

    async def _datos_de_elemento(
        self, zona: dict[str, Any], *, elemento_clave: str, modo: str, cantidad: float | None, largo_m: float | None, pago: str,
        trazo_id: UUID | None, espacio_id: UUID | None = None,
    ) -> dict[str, Any]:
        if espacio_id is not None:
            _, _, obra_id = await self._escala(zona["plano_id"])
            if not await self._elementos.espacio_existe(obra_id, espacio_id):
                raise ErrorDeMatrizDeLosa("El espacio no existe en esta obra.")
        if trazo_id is not None:
            trazo = await self._zonas.trazo(trazo_id)
            if trazo is None:
                raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
            if trazo["tipo"] != "LINESTRING" or trazo["hueco_de"] is not None:
                raise ErrorDeMatrizDeLosa("Solo una línea del plano (no un hueco, un polígono ni un punto) puede dar la longitud de un elemento.")
            if trazo["plano_id"] != zona["plano_id"]:
                raise ErrorDeMatrizDeLosa("La línea es de otro plano que la zona.")
            escala, _, _ = await self._escala(zona["plano_id"])
            largo = _largo_de_linea_m(trazo["geojson"], escala)
            if largo < 0.001:
                raise ErrorDeMatrizDeLosa("La línea no tiene largo.")
            if modo == "pieza" and largo > 30:
                raise ErrorDeMatrizDeLosa("Una pieza de más de 30 m no vale: mide la línea por ml.")
            # La medida real sale de la línea al calcular; lo que se guarda es su instantánea (cantidad y largo válidos para la base).
            cantidad, largo_m = (round(largo, 3), None) if modo == "ml" else (1.0, round(largo, 3))
        elif cantidad is None:
            raise ErrorDeMatrizDeLosa("Falta la cantidad (metros o piezas) o la línea del plano de la que sale.")
        return {
            **validar_elemento_de_losa(clave=elemento_clave, modo=modo, cantidad=float(cantidad), largo_m=largo_m, pago=pago),
            "trazo_id": trazo_id,
            "espacio_id": espacio_id,
        }

    async def agregar_elemento(
        self, zona_id: UUID, *, elemento_clave: str, modo: str, cantidad: float | None, largo_m: float | None, pago: str,
        trazo_id: UUID | None, autor_id: UUID, espacio_id: UUID | None = None,
    ) -> dict[str, Any]:
        zona = await self._zona(zona_id)
        datos = await self._datos_de_elemento(
            zona, elemento_clave=elemento_clave, modo=modo, cantidad=cantidad, largo_m=largo_m, pago=pago, trazo_id=trazo_id,
            espacio_id=espacio_id,
        )
        async with self._uow:
            nuevo = await self._elementos.agregar(zona_id=zona_id, datos=datos, autor_id=autor_id)
            await self._resincronizar(zona["plano_id"], espacio_id)
            await self._uow.commit()
        return await self._elemento(nuevo)

    async def _elemento(self, elemento_id: UUID) -> dict[str, Any]:
        f = await self._elementos.uno(elemento_id)
        if f is None:
            raise ElementoDeLosaNoEncontrado(f"El elemento {elemento_id} no existe o no está en tu alcance.")
        zona = await self._zona(f["zona_id"])
        escala, _, _ = await self._escala(zona["plano_id"])
        return self._medida(f, escala)

    async def cambiar_elemento(
        self, elemento_id: UUID, *, elemento_clave: str, modo: str, cantidad: float | None, largo_m: float | None, pago: str,
        trazo_id: UUID | None, espacio_id: Any = CONSERVAR_ESPACIO,
    ) -> dict[str, Any]:
        f = await self._elementos.uno(elemento_id)
        if f is None:
            raise ElementoDeLosaNoEncontrado(f"El elemento {elemento_id} no existe o no está en tu alcance.")
        if espacio_id is CONSERVAR_ESPACIO:
            espacio_id = f.get("espacio_id")
        zona = await self._zona(f["zona_id"])
        datos = await self._datos_de_elemento(
            zona, elemento_clave=elemento_clave, modo=modo, cantidad=cantidad, largo_m=largo_m, pago=pago, trazo_id=trazo_id,
            espacio_id=espacio_id,
        )
        async with self._uow:
            await self._elementos.actualizar(elemento_id, datos)
            await self._resincronizar(zona["plano_id"], f.get("espacio_id"), espacio_id)
            await self._uow.commit()
        return await self._elemento(elemento_id)

    async def quitar_elemento(self, elemento_id: UUID) -> None:
        f = await self._elementos.uno(elemento_id)
        if f is None:
            raise ElementoDeLosaNoEncontrado(f"El elemento {elemento_id} no existe o no está en tu alcance.")
        zona = await self._zona(f["zona_id"])
        async with self._uow:
            await self._elementos.eliminar(elemento_id)
            await self._resincronizar(zona["plano_id"], f.get("espacio_id"))
            await self._uow.commit()

    # ── La matriz ───────────────────────────────────────────────────────────────────────────────────────

    async def matriz(self, zona_id: UUID, *, concepto_clave: str | None = None) -> dict[str, Any]:
        """La matriz de la zona calculada con lo que hay en el plano y en la base, con el estado de cada concepto propuesto y, si se pide, la
        conciliación contra un concepto del catálogo vigente."""
        zona = await self._zona(zona_id)
        plano_id = zona["plano_id"]
        escala, escala_definida, obra_id = await self._escala(plano_id)
        vigentes = await self._drivers.valores(obra_id)
        drivers, usados = receta_de_obra(vigentes)
        desperdicio, u_concreto = desperdicio_concreto_de_obra(vigentes)
        usados = [*usados, u_concreto]

        losas_de_la_zona = [lo for lo in await self._zonas.losas(plano_id) if lo["zona_id"] == zona_id]
        losas = [
            LosaDeEntrada(
                id=str(lo["id"]),
                area_m2=area_de_poligonos(_poligonos(lo["geojson"], escala)),
                espesor_m=float(lo["espesor_propio_m"]) if lo["espesor_propio_m"] is not None else None,
                espacio_id=str(lo["espacio_id"]) if lo.get("espacio_id") else None,
            )
            for lo in losas_de_la_zona
        ]
        medidas = [self._medida(f, escala) for f in await self._elementos.de_la_zona(zona_id)]
        elementos = [
            ElementoDeLosa(
                clave=m["elemento_clave"], modo=m["modo"], cantidad=m["cantidad"], largo_m=m["largo_m"], pago=m["pago"], id=str(m["id"]),
                origen=m["origen"], trazo_id=str(m["trazo_id"]) if m["trazo_id"] else None,
                espacio_id=str(m["espacio_id"]) if m.get("espacio_id") else None,
            )
            for m in medidas
        ]
        entrada = EntradaMatrizDeLosa(
            tipo=zona["tipo_de_losa"], uso=zona["uso_de_losa"], espesor_m=float(zona["espesor_m"]), losas=losas, elementos=elementos,
            capa_de_compresion_cm=CAPA_DE_COMPRESION_CM, desperdicio_concreto_pct=desperdicio, drivers=drivers,
        )
        r = calcular_matriz_de_losa(entrada)
        if not escala_definida and (losas or any(m["origen"] == "trazo" for m in medidas)):
            r["advertencias"].insert(0, "El plano no tiene escala calibrada: se toma 1 unidad de plano = 1 m para las áreas y las longitudes.")
        r["zona"] = {
            "id": zona["id"], "plano_id": plano_id, "nombre": zona["nombre"], "nivel": zona["nivel"],
            "altura_libre_m": zona["altura_libre_m"], "cota_piso_m": zona["cota_piso_m"],
        }
        r["escala_definida"] = escala_definida
        r["drivers_usados"] = usados
        for e, m in zip(r["elementos"], medidas, strict=True):
            e["longitud_del_trazo_m"] = m["longitud_del_trazo_m"]
        for c in r["conceptos"]:
            clave = c["concepto"]["clave"]
            c["propuesta"] = await self._propuestas.estado_de(clave) if c["concepto"]["provisional"] else None
        r["conciliacion"] = await self._conciliar(concepto_clave, r) if concepto_clave else None
        r["por_espacio"] = await self._por_espacio(obra_id, r["por_espacio"])
        return r

    async def _por_espacio(self, obra_id: UUID, grupos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Anota, por espacio, en qué partida del árbol se mide cada concepto de la matriz (o por qué no cuenta). Sin el Paramétrico no hay árbol que
        consultar y los conceptos quedan sin resolución (`falta_partida` para lo que sí tiene espacio)."""
        nombres: dict[UUID, str] = {}
        partidas: list[Partida] = []
        concepto_id_de: dict[str, UUID] = {}
        if self._parametrico is not None:
            nombres = {UUID(str(e["id"])): e["nombre"] for e in (await self._parametrico.capas(obra_id)).get("espacios", [])}
            partidas = [
                Partida(
                    id=f["id"], concepto_id=f["concepto_id"], nivel_id=f["nivel_id"], etapa_id=f["etapa_id"], nombre=f["nombre"],
                    orden=f["orden"], espacio_id=f.get("espacio_id"),
                )
                for f in await self._parametrico.partidas(obra_id)
            ]
            for clave in sorted({c["concepto"]["clave"] for g in grupos for c in g["conceptos"]}):
                concepto = await self._parametrico.concepto_por_clave(clave)
                if concepto is not None:
                    concepto_id_de[clave] = UUID(str(concepto["id"]))
        return resolver_matriz_por_espacio(grupos, partidas=partidas, concepto_id_de=concepto_id_de, nombres=nombres)

    async def _conciliar(self, concepto_clave: str, r: dict[str, Any]) -> dict[str, Any]:
        """El total de la zona contra la composición real de un concepto del catálogo vigente (auxiliares expandidos hasta los insumos). El
        concepto del catálogo es un lote por prototipo (p. ej. 125 m²): se compara el total de la zona con el total del lote. No se edita nada."""
        clave = concepto_clave.strip().upper()
        concepto = await self._conceptos.obtener_por_clave(clave)
        if concepto is None:
            raise ErrorDeMatrizDeLosa(f"El concepto {clave} no está en el catálogo vigente.")
        composicion = expandir_composicion(await self._conceptos.composicion_recursiva(concepto["id"]), clave)
        conocidos = await self._insumos.por_claves(sorted({f.clave.upper() for f in composicion} | {i["clave"].upper() for i in r["insumos"]}))
        composicion = [
            replace(
                f, clave=f.clave.upper(),
                descripcion=conocidos[f.clave.upper()][1].descripcion if f.clave.upper() in conocidos else f.descripcion,
                unidad=(conocidos[f.clave.upper()][1].unidad or "") if f.clave.upper() in conocidos else f.unidad,
            )
            for f in composicion
        ]
        del_elemento: dict[str, float] = {}
        for i in r["insumos"]:
            del_elemento[i["clave"].upper()] = del_elemento.get(i["clave"].upper(), 0.0) + float(i["cantidad"])
        comparado = comparar_con_concepto(del_elemento, composicion, descripciones={k: v[1].descripcion for k, v in conocidos.items()})
        return {
            "concepto": {"clave": clave, "descripcion": str(concepto.get("descripcion") or ""), "unidad": str(concepto.get("unidad") or "")},
            "nota": (
                "El concepto del catálogo es un lote por prototipo: se compara el total de la zona contra el total del lote. Lo que la matriz no "
                "calcula (casetón, bastones, malla) aparece como «solo en el catálogo». Lo que el catálogo trae distinto se muestra, no se corrige."
            ),
            "filas": comparado["filas"],
            "mano_de_obra": comparado["mano_de_obra"],
            "resumen": comparado["resumen"],
            "coincide": comparado["coincide"],
        }

    # ── Propuestas ──────────────────────────────────────────────────────────────────────────────────────

    async def proponer_conceptos(self, zona_id: UUID, *, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """Propone los conceptos nuevos que la matriz de la zona necesita (el de la losa y el de colado y cimbra por ml de cada elemento con pago
        propio). Idempotente: lo que ya está propuesto o autorizado se omite."""
        r = await self.matriz(zona_id)
        propuestas: list[dict[str, Any]] = []
        vistas: set[str] = set()
        for c in r["conceptos"]:
            concepto = c["concepto"]
            if not concepto["provisional"] or concepto["clave"] in vistas:
                continue
            vistas.add(concepto["clave"])
            if c["parte"] == "losa":
                propuestas.append(concepto_nuevo_de_losa(r["tipo"], r["uso"]))
            elif c["parte"] == "colado":
                p = concepto_nuevo_de_colado(c["elemento_clave"])
                assert p is not None
                propuestas.append(p)
        if not propuestas:
            return {"creadas": [], "omitidas": []}
        return await self._propuestas.proponer(propuestas, usuario_id=usuario_id, rol=rol)
