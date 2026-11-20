"""El relleno de una zona de losa (Fase 3): los rellenos de la zona, su cálculo con lo que hay en el plano y la base, y la propuesta de su concepto nuevo.

Junta lo que ya existe sin duplicarlo: las **zonas** y sus polígonos de losa (fase 1, `zonas_de_losa`), el **catálogo vigente** (para la conciliación del
relleno de azotea contra ALB-03014, sin editarlo), las **propuestas** de concepto nuevo (versionado y autorización de Control de obra) y la capa
**«espacio»** (0143). El cálculo vive en el dominio (`relleno`); aquí solo se arma su entrada desde la base.

Medición derivada: un relleno puede cubrir **un polígono del plano** (`trazo_id`); su área sale de la geometría y de la escala del plano **al calcular**, no se
guarda. Sin `trazo_id` cubre todos los polígonos de la zona. Sin escala calibrada se toma 1 unidad de plano = 1 m, como la matriz de la losa, y el cálculo lo
dice. Solo Control de obra escribe rellenos (lo exige la API y también RLS); Costos o Control de obra proponen el concepto.

Sin doble conteo: un elemento no cubre dos veces el mismo polígono (la base lo impide y `solapes_de_rellenos` también lo dice antes de escribir) y cada polígono
cae en un solo espacio.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import TrazoNoEncontrado
from obractrl.application.casos_uso.elementos_parametricos import (
    ElementoParametricoNoEncontrado,
)
from obractrl.application.casos_uso.matriz_de_losa import CONSERVAR_ESPACIO
from obractrl.application.casos_uso.propuestas_de_losa import (
    GestionarPropuestasDeLosa,
)
from obractrl.application.casos_uso.zonas_de_losa import (
    ZonaDeLosaNoEncontrada,
    _poligonos,
)
from obractrl.application.puertos.relleno_de_zona import RepositorioRellenosDeZona
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.application.puertos.zonas_de_losa import RepositorioZonasDeLosa
from obractrl.domain.cuantificacion.comparacion_con_catalogo import (
    comparar_con_concepto,
    expandir_composicion,
)
from obractrl.domain.cuantificacion.enlaces_de_ranura import Partida
from obractrl.domain.cuantificacion.espacios import resolver_matriz_por_espacio
from obractrl.domain.cuantificacion.matriz_de_losa import area_de_poligonos
from obractrl.domain.cuantificacion.relleno import (
    CLAVES_DE_RELLENO,
    CONCEPTO_AZOTEA,
    EntradaRelleno,
    ErrorDeRelleno,
    PoligonoDeRelleno,
    calcular_relleno,
    concepto_nuevo_de_relleno,
    elemento_de_relleno,
    solapes_de_rellenos,
    validar_parametros,
)

__all__ = ["GestionarPropuestasDeRelleno", "GestionarRellenos", "RellenoNoEncontrado"]

_CAMPOS = ("espesor_m", "pendiente_pct", "recorrido_m", "compensar_espesores", "abundamiento_pct", "mortero_m3_por_m2")


class RellenoNoEncontrado(ElementoParametricoNoEncontrado):
    """El relleno no existe o salió del alcance (RLS): indistinguibles a propósito (§12.4)."""


def _numero(valor: Any) -> Any:
    return float(valor) if isinstance(valor, Decimal) else valor


class GestionarPropuestasDeRelleno(GestionarPropuestasDeLosa):
    """Las propuestas del concepto nuevo del relleno compactado (EJ-810): el mismo ciclo y la misma tabla que la losa (`propuesta_de_estructura`, 0131)."""

    async def listar(self, elemento_clave: str) -> list[dict[str, Any]]:
        if elemento_de_relleno(elemento_clave) is None:
            raise ElementoParametricoNoEncontrado(f"No hay un elemento de relleno «{elemento_clave}» en la biblioteca.")
        return list(await self._propuestas.del_elemento(elemento_clave))

    async def proponer_concepto_de_relleno(self, elemento_clave: str, *, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """El concepto nuevo del relleno compactado por m³ (regla F7), con clave provisional, sin insumos, destajo ni precio. El relleno de azotea usa
        ALB-03014 del catálogo y no se propone nada."""
        tipo = elemento_de_relleno(elemento_clave)
        if tipo is None:
            raise ElementoParametricoNoEncontrado(f"No hay un elemento de relleno «{elemento_clave}» en la biblioteca.")
        if tipo != "compactado":
            raise ErrorDeRelleno("El relleno de azotea usa el concepto ALB-03014 del catálogo: no necesita un concepto nuevo.")
        return await self.proponer([concepto_nuevo_de_relleno(tipo)], usuario_id=usuario_id, rol=rol)


class GestionarRellenos:
    def __init__(
        self,
        *,
        zonas: RepositorioZonasDeLosa,
        rellenos: RepositorioRellenosDeZona,
        propuestas: GestionarPropuestasDeRelleno,
        conceptos: Any,
        insumos: Any,
        uow: UnidadDeTrabajo,
        parametrico: Any | None = None,
        sincronizador: Any | None = None,
    ) -> None:
        # Con el sincronizador de tomas, un relleno que se agrega, cambia o quita rehace lo que la losa y el relleno pagan en las partidas (0143).
        self._sincronizador = sincronizador
        # Con el repositorio del Paramétrico (0143), el cálculo dice en qué partida del árbol se mide lo de cada espacio.
        self._parametrico = parametrico
        self._zonas = zonas
        self._rellenos = rellenos
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

    async def _resincronizar(self, plano_id: UUID) -> None:
        """Lo que la losa y el relleno pagan en las partidas se rehace (en la misma transacción): el espacio puede venir del polígono."""
        if self._sincronizador is None:
            return
        _, _, obra_id = await self._escala(plano_id)
        await self._sincronizador.de_la_obra(obra_id)

    @staticmethod
    def _fila(f: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": f["id"], "zona_id": f["zona_id"], "elemento_clave": f["elemento_clave"], "tipo": elemento_de_relleno(f["elemento_clave"]),
            "trazo_id": f["trazo_id"], "espacio_id": f.get("espacio_id"),
            **{c: _numero(f[c]) for c in _CAMPOS},
        }

    # ── Los rellenos de la zona ─────────────────────────────────────────────────────────────────────────

    async def rellenos(self, zona_id: UUID) -> list[dict[str, Any]]:
        await self._zona(zona_id)
        return [self._fila(f) for f in await self._rellenos.de_la_zona(zona_id)]

    async def _datos(
        self, zona: dict[str, Any], *, elemento_clave: str, trazo_id: UUID | None, espacio_id: UUID | None, parametros: dict[str, Any],
        otros: list[dict[str, Any]],
    ) -> dict[str, Any]:
        tipo = elemento_de_relleno(elemento_clave)
        if tipo is None:
            raise ErrorDeRelleno(f"«{elemento_clave}» no es un elemento de relleno de la biblioteca (REL-AZOTEA o REL-COMPACTADO).")
        validados = validar_parametros(tipo, parametros)
        _, _, obra_id = await self._escala(zona["plano_id"])
        if espacio_id is not None and not await self._rellenos.espacio_existe(obra_id, espacio_id):
            raise ErrorDeRelleno("El espacio no existe en esta obra.")
        if trazo_id is not None:
            trazo = await self._zonas.trazo(trazo_id)
            if trazo is None:
                raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
            suyas = [lo for lo in await self._zonas.losas(zona["plano_id"]) if lo["zona_id"] == zona["id"]]
            if not any(UUID(str(lo["id"])) == trazo_id for lo in suyas):
                raise ErrorDeRelleno("El polígono no es un polígono de losa de esta zona: el relleno solo cubre los polígonos de la losa de su zona.")
        solapes = solapes_de_rellenos([*otros, {"id": None, "elemento_clave": elemento_clave, "trazo_id": trazo_id}])
        if solapes:
            raise ErrorDeRelleno(solapes[0])
        return {"elemento_clave": elemento_clave, "trazo_id": trazo_id, "espacio_id": espacio_id, **validados}

    async def agregar(
        self, zona_id: UUID, *, elemento_clave: str, trazo_id: UUID | None, espacio_id: UUID | None, parametros: dict[str, Any], autor_id: UUID,
    ) -> dict[str, Any]:
        zona = await self._zona(zona_id)
        otros = [{"id": f["id"], "elemento_clave": f["elemento_clave"], "trazo_id": f["trazo_id"]} for f in await self._rellenos.de_la_zona(zona_id)]
        datos = await self._datos(zona, elemento_clave=elemento_clave, trazo_id=trazo_id, espacio_id=espacio_id, parametros=parametros, otros=otros)
        async with self._uow:
            nuevo = await self._rellenos.agregar(zona_id=zona_id, datos=datos, autor_id=autor_id)
            await self._resincronizar(zona["plano_id"])
            await self._uow.commit()
        return await self._relleno(nuevo)

    async def _relleno(self, relleno_id: UUID) -> dict[str, Any]:
        f = await self._rellenos.uno(relleno_id)
        if f is None:
            raise RellenoNoEncontrado(f"El relleno {relleno_id} no existe o no está en tu alcance.")
        return self._fila(f)

    async def cambiar(
        self, relleno_id: UUID, *, elemento_clave: str, trazo_id: UUID | None, parametros: dict[str, Any], espacio_id: Any = CONSERVAR_ESPACIO,
    ) -> dict[str, Any]:
        f = await self._rellenos.uno(relleno_id)
        if f is None:
            raise RellenoNoEncontrado(f"El relleno {relleno_id} no existe o no está en tu alcance.")
        if espacio_id is CONSERVAR_ESPACIO:
            espacio_id = f.get("espacio_id")
        zona = await self._zona(f["zona_id"])
        otros = [
            {"id": o["id"], "elemento_clave": o["elemento_clave"], "trazo_id": o["trazo_id"]}
            for o in await self._rellenos.de_la_zona(f["zona_id"]) if o["id"] != f["id"]
        ]
        datos = await self._datos(zona, elemento_clave=elemento_clave, trazo_id=trazo_id, espacio_id=espacio_id, parametros=parametros, otros=otros)
        async with self._uow:
            await self._rellenos.actualizar(relleno_id, datos)
            await self._resincronizar(zona["plano_id"])
            await self._uow.commit()
        return await self._relleno(relleno_id)

    async def quitar(self, relleno_id: UUID) -> None:
        f = await self._rellenos.uno(relleno_id)
        if f is None:
            raise RellenoNoEncontrado(f"El relleno {relleno_id} no existe o no está en tu alcance.")
        zona = await self._zona(f["zona_id"])
        async with self._uow:
            await self._rellenos.eliminar(relleno_id)
            await self._resincronizar(zona["plano_id"])
            await self._uow.commit()

    # ── El cálculo ──────────────────────────────────────────────────────────────────────────────────────

    async def calculo(self, zona_id: UUID, *, conciliar: bool = False) -> dict[str, Any]:
        """Los rellenos de la zona calculados con lo que hay en el plano y en la base, el estado de su concepto propuesto, lo que paga cada espacio y, si se
        pide, la conciliación del relleno de azotea contra ALB-03014 del catálogo vigente."""
        zona = await self._zona(zona_id)
        plano_id = zona["plano_id"]
        escala, escala_definida, obra_id = await self._escala(plano_id)

        losas_de_la_zona = [lo for lo in await self._zonas.losas(plano_id) if lo["zona_id"] == zona_id]
        espesor_de_la_zona = float(zona["espesor_m"])
        poligonos = {
            str(lo["id"]): PoligonoDeRelleno(
                id=str(lo["id"]),
                area_m2=area_de_poligonos(_poligonos(lo["geojson"], escala)),
                espesor_de_losa_m=float(lo["espesor_propio_m"]) if lo["espesor_propio_m"] is not None else None,
                espacio_id=str(lo["espacio_id"]) if lo.get("espacio_id") else None,
            )
            for lo in losas_de_la_zona
        }
        maximo = max([p.espesor_de_losa_m if p.espesor_de_losa_m is not None else espesor_de_la_zona for p in poligonos.values()], default=espesor_de_la_zona)

        filas = await self._rellenos.de_la_zona(zona_id)
        calculados: list[dict[str, Any]] = []
        for f in filas:
            tipo = elemento_de_relleno(f["elemento_clave"])
            assert tipo is not None  # la base solo guarda las dos claves
            cubre = [poligonos[str(f["trazo_id"])]] if f["trazo_id"] and str(f["trazo_id"]) in poligonos else (list(poligonos.values()) if not f["trazo_id"] else [])
            r = calcular_relleno(
                EntradaRelleno(
                    tipo=tipo, espesor_de_la_zona_m=espesor_de_la_zona, poligonos=cubre, espesor_maximo_de_la_zona_m=maximo,
                    **{c: _numero(f[c]) for c in _CAMPOS}, espacio_id=str(f["espacio_id"]) if f.get("espacio_id") else None,
                )
            )
            if f["trazo_id"] and str(f["trazo_id"]) not in poligonos:
                r["advertencias"].insert(0, "El polígono que cubre este relleno ya no es de la losa de la zona: el relleno no cubre nada. Cámbialo o quítalo.")
            if not escala_definida and cubre:
                r["advertencias"].insert(0, "El plano no tiene escala calibrada: se toma 1 unidad de plano = 1 m para las áreas.")
            r["id"] = f["id"]
            r["trazo_id"] = f["trazo_id"]
            r["espacio_id"] = f.get("espacio_id")
            r["origen"] = "poligono" if f["trazo_id"] else "zona"
            if conciliar and tipo == "azotea":
                r["conciliacion"] = await self._conciliar(r)
            else:
                r["conciliacion"] = None
            for c in r["conceptos"]:
                clave = c["concepto"]["clave"]
                c["propuesta"] = await self._propuestas.estado_de(clave) if c["concepto"]["provisional"] else None
            calculados.append(r)

        por_espacio = await self._por_espacio(obra_id, _juntar_por_espacio(calculados))
        return {
            "zona": {
                "id": zona["id"], "plano_id": plano_id, "nombre": zona["nombre"], "nivel": zona["nivel"], "espesor_m": espesor_de_la_zona,
                "espesor_maximo_m": maximo,
            },
            "escala_definida": escala_definida,
            "rellenos": calculados,
            "totales": _totales(calculados),
            "por_espacio": por_espacio,
            "advertencias": _advertencias_de_la_zona(filas, poligonos),
        }

    async def _por_espacio(self, obra_id: UUID, grupos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Anota, por espacio, en qué partida del árbol se mide cada concepto del relleno (o por qué no cuenta). Sin el Paramétrico no hay árbol que
        consultar y los conceptos quedan sin resolución."""
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

    async def _conciliar(self, r: dict[str, Any]) -> dict[str, Any]:
        """El relleno de azotea contra la composición real de ALB-03014 del catálogo vigente, **por m²** (auxiliares expandidos hasta los insumos). Se
        compara lo que el elemento calcula por m² de relleno con lo que el concepto lleva por m². No se edita nada."""
        clave = CONCEPTO_AZOTEA["clave"]
        concepto = await self._conceptos.obtener_por_clave(clave)
        if concepto is None:
            return {
                "concepto": {"clave": clave, "descripcion": CONCEPTO_AZOTEA["descripcion"], "unidad": "m²"},
                "nota": f"El concepto {clave} no está en el catálogo vigente: no hay con qué conciliar.", "filas": [], "mano_de_obra": [],
                "resumen": {}, "coincide": False,
            }
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
        area = float(r["area_m2"])
        por_m2 = {i["clave"].upper(): float(i["cantidad"]) / area for i in r["insumos"]} if area > 0 else {}
        comparado = comparar_con_concepto(por_m2, composicion, descripciones={k: v[1].descripcion for k, v in conocidos.items()})
        return {
            "concepto": {"clave": clave, "descripcion": str(concepto.get("descripcion") or ""), "unidad": str(concepto.get("unidad") or "")},
            "nota": (
                "El concepto del catálogo es por m²: se compara lo que el relleno calcula por m² con lo que el concepto lleva por m². Lo que el catálogo trae "
                "distinto se muestra, no se corrige."
            ),
            "filas": comparado["filas"],
            "mano_de_obra": comparado["mano_de_obra"],
            "resumen": comparado["resumen"],
            "coincide": comparado["coincide"],
        }

    # ── Propuestas ──────────────────────────────────────────────────────────────────────────────────────

    async def proponer_conceptos(self, zona_id: UUID, *, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """Propone el concepto nuevo que los rellenos de la zona necesitan (el del relleno compactado). Idempotente: lo que ya está propuesto o autorizado
        se omite. El relleno de azotea usa ALB-03014 del catálogo y no propone nada."""
        await self._zona(zona_id)
        necesita = any(f["elemento_clave"] == CLAVES_DE_RELLENO["compactado"] for f in await self._rellenos.de_la_zona(zona_id))
        if not necesita:
            return {"creadas": [], "omitidas": []}
        return await self._propuestas.proponer([concepto_nuevo_de_relleno("compactado")], usuario_id=usuario_id, rol=rol)


def _juntar_por_espacio(calculados: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Junta el `por_espacio` de todos los rellenos de la zona: un grupo por espacio y, en él, un renglón por concepto con las cantidades sumadas. Cada
    polígono de cada relleno cae en un solo espacio, así que la suma de los grupos es la de los rellenos (sin doble conteo)."""
    grupos: dict[str | None, dict[str, Any]] = {}
    for r in calculados:
        for g in r["por_espacio"]:
            suyo = grupos.setdefault(g["espacio_id"], {"espacio_id": g["espacio_id"], "area_m2": 0.0, "volumen_m3": 0.0, "conceptos": {}})
            suyo["area_m2"] += g["area_m2"]
            suyo["volumen_m3"] += g["volumen_m3"]
            for c in g["conceptos"]:
                previo = suyo["conceptos"].get(c["concepto"]["clave"])
                if previo is None:
                    suyo["conceptos"][c["concepto"]["clave"]] = {**c, "propuesta": None}
                else:
                    previo["cantidad"] += c["cantidad"]
    orden = sorted(grupos, key=lambda e: (e is not None, str(e)))
    return [{**grupos[e], "conceptos": list(grupos[e]["conceptos"].values())} for e in orden]


def _totales(calculados: list[dict[str, Any]]) -> dict[str, Any]:
    conceptos: dict[str, dict[str, Any]] = {}
    for r in calculados:
        for c in r["conceptos"]:
            clave = c["concepto"]["clave"]
            previo = conceptos.get(clave)
            if previo is None:
                conceptos[clave] = {"concepto": c["concepto"], "unidad": c["unidad"], "cantidad": c["cantidad"], "propuesta": c.get("propuesta")}
            else:
                previo["cantidad"] += c["cantidad"]
    return {
        "area_m2": sum(r["area_m2"] for r in calculados),
        "volumen_m3": sum(r["volumen_m3"] for r in calculados),
        "conceptos": list(conceptos.values()),
    }


def _advertencias_de_la_zona(filas: list[dict[str, Any]], poligonos: dict[str, PoligonoDeRelleno]) -> list[str]:
    avisos: list[str] = []
    if filas and not poligonos:
        avisos.append("La zona no tiene polígonos de losa: los rellenos no cubren nada. Dibuja la losa de la zona en el plano.")
    avisos.extend(solapes_de_rellenos([{"id": f["id"], "elemento_clave": f["elemento_clave"], "trazo_id": f["trazo_id"]} for f in filas]))
    return avisos
