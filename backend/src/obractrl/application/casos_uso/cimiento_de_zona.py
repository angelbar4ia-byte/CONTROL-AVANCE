"""Los cimientos de una zona de losa (Fase 4b): muros de cimentación de piedra medidos sobre una línea del plano con cotas de desplante.

La altura sale de las cotas (corona − desplante); la longitud, de la línea del plano y de su escala **al calcular**; la cota de desplante, tecleada o de un **punto de nivel
exterior** del plano (si el punto cambia, el cimiento cambia). El cálculo vive en el dominio (`cimiento`, que reutiliza `calcular_muro_de_cimentacion`); aquí solo se arma
su entrada desde la base. Solo Control de obra escribe (lo exige la API y también RLS). Sin doble conteo: una línea mide un solo cimiento; cada cimiento cae en **un** espacio.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import TrazoNoEncontrado
from obractrl.application.casos_uso.elementos_parametricos import (
    ElementoParametricoNoEncontrado,
)
from obractrl.application.casos_uso.matriz_de_losa import (
    CONSERVAR_ESPACIO,
    _largo_de_linea_m,
)
from obractrl.application.casos_uso.zonas_de_losa import ZonaDeLosaNoEncontrada
from obractrl.application.puertos.cimiento_de_zona import RepositorioCimientosDeZona
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.application.puertos.zonas_de_losa import RepositorioZonasDeLosa
from obractrl.domain.cuantificacion.cimiento import (
    EntradaCimiento,
    ErrorDeCimiento,
    calcular_cimiento,
    corona_por_defecto,
    elemento_de_cimiento,
)
from obractrl.domain.cuantificacion.enlaces_de_ranura import Partida
from obractrl.domain.cuantificacion.espacios import resolver_matriz_por_espacio

__all__ = ["CimientoNoEncontrado", "GestionarCimientos"]

_CAMPOS = ("caras", "dentellon")
_COTAS = ("cota_desplante_m", "cota_corona_m")


class CimientoNoEncontrado(ElementoParametricoNoEncontrado):
    """El cimiento no existe o salió del alcance (RLS): indistinguibles a propósito (§12.4)."""


def _numero(valor: Any) -> Any:
    return float(valor) if isinstance(valor, Decimal) else valor


class GestionarCimientos:
    def __init__(
        self, *, zonas: RepositorioZonasDeLosa, cimientos: RepositorioCimientosDeZona, uow: UnidadDeTrabajo, parametrico: Any | None = None,
        sincronizador: Any | None = None,
    ) -> None:
        self._sincronizador = sincronizador
        self._parametrico = parametrico
        self._zonas = zonas
        self._cimientos = cimientos
        self._uow = uow

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
        if self._sincronizador is None:
            return
        _, _, obra_id = await self._escala(plano_id)
        await self._sincronizador.de_la_obra(obra_id)

    @staticmethod
    def _fila(f: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": f["id"], "zona_id": f["zona_id"], "elemento_clave": f["elemento_clave"], "trazo_id": f["trazo_id"], "punto_nivel_id": f.get("punto_nivel_id"),
            "espacio_id": f.get("espacio_id"), **{c: _numero(f[c]) for c in (*_CAMPOS, *_COTAS)},
        }

    async def cimientos(self, zona_id: UUID) -> list[dict[str, Any]]:
        await self._zona(zona_id)
        return [self._fila(f) for f in await self._cimientos.de_la_zona(zona_id)]

    async def _datos(
        self, zona: dict[str, Any], *, elemento_clave: str, trazo_id: UUID, cota_desplante_m: float | None, punto_nivel_id: UUID | None, cota_corona_m: float | None,
        caras: int, dentellon: bool, espacio_id: UUID | None, propio: UUID | None = None,
    ) -> dict[str, Any]:
        if not elemento_de_cimiento(elemento_clave):
            raise ErrorDeCimiento(f"«{elemento_clave}» no es un muro de cimentación de la biblioteca (CIM-01010).")
        if caras not in (1, 2):
            raise ErrorDeCimiento("Las caras inclinadas son 1 (cimiento de lindero) o 2 (simétrico).")
        if cota_desplante_m is None and punto_nivel_id is None:
            raise ErrorDeCimiento("Falta la cota de desplante: teclea una o elige un punto de nivel exterior del plano.")
        for que, cota in (("desplante", cota_desplante_m), ("corona", cota_corona_m)):
            if cota is not None and not -30.0 <= cota <= 100.0:
                raise ErrorDeCimiento(f"La cota de {que} va de -30 a 100 m.")
        escala, _, obra_id = await self._escala(zona["plano_id"])
        if punto_nivel_id is not None:
            puntos = {UUID(str(p["id"])) for p in await self._zonas.puntos_de_nivel(zona["plano_id"])}
            if punto_nivel_id not in puntos:
                raise ErrorDeCimiento("El punto de nivel no existe en este plano: marca un punto de nivel exterior con su cota.")
        if espacio_id is not None and not await self._cimientos.espacio_existe(obra_id, espacio_id):
            raise ErrorDeCimiento("El espacio no existe en esta obra.")
        trazo = await self._zonas.trazo(trazo_id)
        if trazo is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        if trazo["tipo"] != "LINESTRING" or trazo["hueco_de"] is not None:
            raise ErrorDeCimiento("Solo una línea del plano (no un hueco, un polígono ni un punto) puede dar la longitud del cimiento.")
        if trazo["plano_id"] != zona["plano_id"]:
            raise ErrorDeCimiento("La línea es de otro plano que la zona.")
        if _largo_de_linea_m(trazo["geojson"], escala) < 0.001:
            raise ErrorDeCimiento("La línea no tiene largo.")
        ya = await self._cimientos.con_la_linea(trazo_id)
        if ya is not None and ya != propio:
            raise ErrorDeCimiento("Esa línea ya mide otro cimiento: se contaría dos veces.")
        return {
            "elemento_clave": elemento_clave, "trazo_id": trazo_id, "cota_desplante_m": cota_desplante_m, "punto_nivel_id": punto_nivel_id,
            "cota_corona_m": cota_corona_m, "caras": caras, "dentellon": dentellon, "espacio_id": espacio_id,
        }

    async def agregar(self, zona_id: UUID, *, autor_id: UUID, **campos: Any) -> dict[str, Any]:
        zona = await self._zona(zona_id)
        datos = await self._datos(zona, **campos)
        async with self._uow:
            nuevo = await self._cimientos.agregar(zona_id=zona_id, datos=datos, autor_id=autor_id)
            await self._resincronizar(zona["plano_id"])
            await self._uow.commit()
        return await self._cimiento(nuevo)

    async def _cimiento(self, cimiento_id: UUID) -> dict[str, Any]:
        f = await self._cimientos.uno(cimiento_id)
        if f is None:
            raise CimientoNoEncontrado(f"El cimiento {cimiento_id} no existe o no está en tu alcance.")
        return self._fila(f)

    async def cambiar(self, cimiento_id: UUID, *, espacio_id: Any = CONSERVAR_ESPACIO, **campos: Any) -> dict[str, Any]:
        f = await self._cimientos.uno(cimiento_id)
        if f is None:
            raise CimientoNoEncontrado(f"El cimiento {cimiento_id} no existe o no está en tu alcance.")
        if espacio_id is CONSERVAR_ESPACIO:
            espacio_id = f.get("espacio_id")
        zona = await self._zona(f["zona_id"])
        datos = await self._datos(zona, espacio_id=espacio_id, propio=cimiento_id, **campos)
        async with self._uow:
            await self._cimientos.actualizar(cimiento_id, datos)
            await self._resincronizar(zona["plano_id"])
            await self._uow.commit()
        return await self._cimiento(cimiento_id)

    async def quitar(self, cimiento_id: UUID) -> None:
        f = await self._cimientos.uno(cimiento_id)
        if f is None:
            raise CimientoNoEncontrado(f"El cimiento {cimiento_id} no existe o no está en tu alcance.")
        zona = await self._zona(f["zona_id"])
        async with self._uow:
            await self._cimientos.eliminar(cimiento_id)
            await self._resincronizar(zona["plano_id"])
            await self._uow.commit()

    async def calculo(self, zona_id: UUID) -> dict[str, Any]:
        """Los cimientos de la zona con las cotas de la zona y los puntos de nivel del plano, la longitud de su línea, el estado de su concepto y lo que paga cada espacio.
        Un cimiento con un dato que no vale se devuelve con su `error` y sin cálculo."""
        zona = await self._zona(zona_id)
        plano_id = zona["plano_id"]
        escala, escala_definida, obra_id = await self._escala(plano_id)
        puntos = {UUID(str(p["id"])): float(p["cota_m"]) for p in await self._zonas.puntos_de_nivel(plano_id)}
        filas = await self._cimientos.de_la_zona(zona_id)
        calculados: list[dict[str, Any]] = []
        for f in filas:
            if f.get("cota_desplante_m") is not None:
                desplante, origen_d = float(f["cota_desplante_m"]), "explicita"
            elif f.get("punto_nivel_id") is not None and UUID(str(f["punto_nivel_id"])) in puntos:
                desplante, origen_d = puntos[UUID(str(f["punto_nivel_id"]))], "punto_de_nivel"
            else:
                desplante, origen_d = None, "sin_cota"
            corona, origen_c = (float(f["cota_corona_m"]), "explicita") if f.get("cota_corona_m") is not None else (corona_por_defecto(float(zona["cota_piso_m"])), "cadena_de_desplante")
            longitud = _largo_de_linea_m(f["geojson"], escala) if f.get("geojson") else 0.0
            item: dict[str, Any] = {
                "id": f["id"], "trazo_id": f["trazo_id"], "punto_nivel_id": f.get("punto_nivel_id"), "espacio_id": f.get("espacio_id"),
                "origen_de_cotas": {"desplante": origen_d, "corona": origen_c}, "longitud_m": longitud, "error": None, "calculo": None,
            }
            if desplante is None:
                item["error"] = "El punto de nivel del desplante ya no existe y no hay cota tecleada: teclea la cota de desplante."
                calculados.append(item)
                continue
            try:
                r = calcular_cimiento(
                    EntradaCimiento(
                        cota_desplante_m=desplante, cota_corona_m=corona, longitud_m=longitud, caras=int(f["caras"]), dentellon=bool(f["dentellon"]),
                        espacio_id=str(f["espacio_id"]) if f.get("espacio_id") else None,
                    )
                )
            except ErrorDeCimiento as e:
                item["error"] = str(e)
                calculados.append(item)
                continue
            if not escala_definida:
                r["advertencias"].insert(0, "El plano no tiene escala calibrada: se toma 1 unidad de plano = 1 m para la longitud.")
            item["calculo"] = r
            calculados.append(item)
        validas = [c["calculo"] for c in calculados if c["calculo"] is not None]
        por_espacio = await self._por_espacio(obra_id, _juntar_por_espacio(validas))
        return {
            "zona": {"id": zona["id"], "plano_id": plano_id, "nombre": zona["nombre"], "nivel": zona["nivel"], "cota_piso_m": float(zona["cota_piso_m"])},
            "escala_definida": escala_definida,
            "cimientos": calculados,
            "totales": _totales(validas),
            "por_espacio": por_espacio,
            "advertencias": [f"Un cimiento no se puede calcular: {c['error']}" for c in calculados if c["error"]],
        }

    async def _por_espacio(self, obra_id: UUID, grupos: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def _juntar_por_espacio(calculados: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Un grupo por espacio con las cantidades sumadas; cada cimiento cae en un solo espacio, así que la suma de los grupos es la de los cimientos (sin doble conteo)."""
    grupos: dict[str | None, dict[str, Any]] = {}
    for r in calculados:
        for g in r["por_espacio"]:
            suyo = grupos.setdefault(g["espacio_id"], {"espacio_id": g["espacio_id"], "conceptos": {}})
            for c in g["conceptos"]:
                previo = suyo["conceptos"].get(c["concepto"]["clave"])
                if previo is None:
                    suyo["conceptos"][c["concepto"]["clave"]] = {**c, "propuesta": None}
                else:
                    previo["cantidad"] += c["cantidad"]
    orden = sorted(grupos, key=lambda e: (e is not None, str(e)))
    return [{**grupos[e], "conceptos": list(grupos[e]["conceptos"].values())} for e in orden]


def _totales(calculados: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "longitud_m": sum(r["longitud_m"] for r in calculados),
        "volumen_m3": sum(r["volumen_m3"] for r in calculados),
        "conceptos": [
            {"concepto": calculados[0]["conceptos"][0]["concepto"], "unidad": "m3", "cantidad": sum(r["volumen_m3"] for r in calculados), "propuesta": None}
        ]
        if calculados
        else [],
    }


