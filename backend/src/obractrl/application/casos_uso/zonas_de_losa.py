"""Zonas de losa (Fase 1): alta y edición de zonas, polígonos con rol de losa, puntos de nivel exterior y la resolución de un muro
contra ellos (altura, enrase y cara interior o exterior por tramo).

Solo **Control de obra** escribe zonas (lo exige la API y también RLS); los demás roles leen. Aquí solo se orquesta: las reglas viven
en ``domain.cuantificacion.zonas_de_losa``. Lo que devuelve ``resolver_muro`` es una sugerencia para mostrar: no cambia ningún
trazo, enlace ni cantidad guardados.
"""

from __future__ import annotations

import math
from decimal import Decimal
from itertools import pairwise
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import (
    PlanoNoEncontrado,
    TrazoNoEncontrado,
)
from obractrl.application.puertos.cuantificacion import RepositorioTrazos
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.application.puertos.zonas_de_losa import RepositorioZonasDeLosa
from obractrl.domain.cuantificacion.zonas_de_losa import (
    ESPESOR_MAXIMO_M,
    ErrorDeZonaDeLosa,
    LosaEnPlano,
    Poligono,
    PuntoDeNivelExterior,
    ZonaDeLosa,
    resolver_muro,
    tramos_para_conversion,
    validar_zona,
)

__all__ = ["GestionarZonasDeLosa", "ZonaDeLosaNoEncontrada"]


class ZonaDeLosaNoEncontrada(LookupError):
    """La zona no existe o salió del alcance (RLS): indistinguibles a propósito (§12.4)."""


def _zona_de_dominio(z: dict[str, Any]) -> ZonaDeLosa:
    return ZonaDeLosa(
        id=str(z["id"]), nombre=z["nombre"], altura_libre_m=Decimal(str(z["altura_libre_m"])), espesor_m=Decimal(str(z["espesor_m"])),
        cota_piso_m=Decimal(str(z["cota_piso_m"])), nivel=z.get("nivel"),
    )


def _poligonos(geojson: dict[str, Any], escala: float) -> tuple[Poligono, ...]:
    def anillo(puntos: list[list[float]]) -> tuple[tuple[float, float], ...]:
        return tuple((float(p[0]) * escala, float(p[1]) * escala) for p in puntos)

    if geojson["type"] == "Polygon":
        return (tuple(anillo(a) for a in geojson["coordinates"]),)
    if geojson["type"] == "MultiPolygon":
        return tuple(tuple(anillo(a) for a in poli) for poli in geojson["coordinates"])
    return ()


class GestionarZonasDeLosa:
    def __init__(self, *, zonas: RepositorioZonasDeLosa, trazos: RepositorioTrazos, uow: UnidadDeTrabajo) -> None:
        self._zonas = zonas
        self._trazos = trazos
        self._uow = uow

    # ── Lectura ─────────────────────────────────────────────────────────────────────────────────────────

    async def del_plano(self, plano_id: UUID) -> dict[str, Any]:
        plano = await self._zonas.plano(plano_id)
        if plano is None:
            raise PlanoNoEncontrado(f"El plano {plano_id} no existe o no está en tu alcance.")
        zonas = await self._zonas.zonas(plano_id)
        losas = await self._zonas.losas(plano_id)
        por_zona: dict[Any, list[dict[str, Any]]] = {}
        for losa in losas:
            por_zona.setdefault(losa["zona_id"], []).append(losa)
        salida = []
        for z in zonas:
            dom = _zona_de_dominio(z)
            salida.append(
                {
                    **z,
                    "cota_inferior_m": dom.cota_inferior_m,
                    "cota_superior_m": dom.cota_superior_m,
                    "losas": [
                        {
                            "trazo_id": lo["id"],
                            "espesor_propio_m": lo["espesor_propio_m"],
                            "espesor_m": lo["espesor_propio_m"] if lo["espesor_propio_m"] is not None else z["espesor_m"],
                        }
                        for lo in por_zona.get(z["id"], [])
                    ],
                }
            )
        puntos = await self._zonas.puntos_de_nivel(plano_id)
        return {
            "plano_id": plano_id,
            "escala_definida": plano["escala_m_por_unidad"] is not None,
            "zonas": salida,
            "puntos_de_nivel": [
                {"trazo_id": p["id"], "cota_m": p["cota_m"], "rotulo": p["rotulo"]} for p in puntos
            ],
        }

    async def _zona_existente(self, zona_id: UUID) -> dict[str, Any]:
        z = await self._zonas.zona(zona_id)
        if z is None:
            raise ZonaDeLosaNoEncontrada(f"La zona de losa {zona_id} no existe o no está en tu alcance.")
        return z

    # ── Escritura (Control de obra) ─────────────────────────────────────────────────────────────────────

    async def crear(
        self, plano_id: UUID, *, nombre: str, altura_libre_m: Any, espesor_m: Any, cota_piso_m: Any = 0, nivel: str | None = None,
        autor_id: UUID,
    ) -> dict[str, Any]:
        if await self._zonas.plano(plano_id) is None:
            raise PlanoNoEncontrado(f"El plano {plano_id} no existe o no está en tu alcance.")
        datos = validar_zona(nombre=nombre, altura_libre_m=altura_libre_m, espesor_m=espesor_m, cota_piso_m=cota_piso_m, nivel=nivel)
        async with self._uow:
            nueva = await self._zonas.crear(plano_id=plano_id, datos=datos, autor_id=autor_id)
            await self._uow.commit()
        return await self._zona_existente(nueva)

    async def cambiar(
        self, zona_id: UUID, *, nombre: str, altura_libre_m: Any, espesor_m: Any, cota_piso_m: Any = 0, nivel: str | None = None
    ) -> dict[str, Any]:
        await self._zona_existente(zona_id)
        datos = validar_zona(nombre=nombre, altura_libre_m=altura_libre_m, espesor_m=espesor_m, cota_piso_m=cota_piso_m, nivel=nivel)
        async with self._uow:
            await self._zonas.actualizar(zona_id, datos)
            await self._uow.commit()
        return await self._zona_existente(zona_id)

    async def eliminar(self, zona_id: UUID) -> None:
        await self._zona_existente(zona_id)
        async with self._uow:
            await self._zonas.eliminar(zona_id)
            await self._uow.commit()

    async def fijar_losa(self, trazo_id: UUID, *, zona_id: UUID | None, espesor_m: Decimal | None) -> dict[str, Any]:
        """Da (o quita, con ``zona_id`` nulo) el rol de losa de una zona a un polígono. ``espesor_m`` lo vuelve subzona."""
        trazo = await self._zonas.trazo(trazo_id)
        if trazo is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        if zona_id is None:
            espesor_m = None
        else:
            if trazo["tipo"] not in ("POLYGON", "MULTIPOLYGON") or trazo["hueco_de"] is not None:
                raise ErrorDeZonaDeLosa("Solo un polígono (no un hueco) puede ser una losa: dibuja el área de la losa.")
            zona = await self._zona_existente(zona_id)
            if zona["plano_id"] != trazo["plano_id"]:
                raise ErrorDeZonaDeLosa("La zona es de otro plano.")
            if espesor_m is not None and not 0 < espesor_m <= ESPESOR_MAXIMO_M:
                raise ErrorDeZonaDeLosa(f"El espesor de la subzona va de más de 0 a {ESPESOR_MAXIMO_M} m.")
        async with self._uow:
            await self._zonas.fijar_losa(trazo_id, zona_id, espesor_m)
            await self._uow.commit()
        return {"trazo_id": trazo_id, "zona_id": zona_id, "espesor_propio_m": espesor_m}

    async def fijar_nivel_exterior(self, trazo_id: UUID, *, cota_m: Decimal | None, rotulo: str | None) -> dict[str, Any]:
        """Marca (o quita, con ``cota_m`` nulo) un punto como punto de nivel exterior con su cota y su rótulo."""
        trazo = await self._zonas.trazo(trazo_id)
        if trazo is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        limpio = (rotulo or "").strip() or None
        if cota_m is None:
            limpio = None
        else:
            if trazo["tipo"] != "POINT" or trazo["hueco_de"] is not None:
                raise ErrorDeZonaDeLosa("Solo un punto puede ser un punto de nivel exterior.")
            if not cota_m.is_finite() or not -30 <= cota_m <= 100:
                raise ErrorDeZonaDeLosa("La cota del punto de nivel va de -30 a 100 m (relativa al piso terminado de PB = 0).")
            if limpio is not None and len(limpio) > 60:
                raise ErrorDeZonaDeLosa("El rótulo va de 1 a 60 caracteres.")
            cota_m = cota_m.quantize(Decimal("0.001"))
        async with self._uow:
            await self._zonas.fijar_nivel_exterior(trazo_id, cota_m, limpio)
            await self._uow.commit()
        return {"trazo_id": trazo_id, "cota_m": cota_m, "rotulo": limpio}

    # ── Resolución de un muro ───────────────────────────────────────────────────────────────────────────

    async def resolver_muro(self, trazo_id: UUID) -> dict[str, Any]:
        """Qué zona, altura, enrase y cara aplicarían a este muro. Solo muestra: no cambia nada guardado (Q1)."""
        trazo = await self._zonas.trazo(trazo_id)
        if trazo is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        if trazo["tipo"] != "LINESTRING":
            raise ErrorDeZonaDeLosa("Las zonas de losa se resuelven sobre una línea (un muro).")
        plano_id = trazo["plano_id"]
        plano = await self._zonas.plano(plano_id)
        escala_definida = plano is not None and plano["escala_m_por_unidad"] is not None
        escala = float(plano["escala_m_por_unidad"]) if escala_definida and plano else 1.0
        linea = tuple((float(p[0]) * escala, float(p[1]) * escala) for p in trazo["geojson"]["coordinates"])

        zonas_filas = await self._zonas.zonas(plano_id)
        zonas = [_zona_de_dominio(z) for z in zonas_filas]
        losas = [
            LosaEnPlano(
                id=str(lo["id"]), zona_id=str(lo["zona_id"]), poligonos=_poligonos(lo["geojson"], escala),
                espesor_m=Decimal(str(lo["espesor_propio_m"])) if lo["espesor_propio_m"] is not None else None,
            )
            for lo in await self._zonas.losas(plano_id)
        ]
        puntos = [
            PuntoDeNivelExterior(
                id=str(p["id"]), x=float(p["x"]) * escala, y=float(p["y"]) * escala, cota_m=Decimal(str(p["cota_m"])), rotulo=p["rotulo"]
            )
            for p in await self._zonas.puntos_de_nivel(plano_id)
        ]

        muro = await self._trazos.muro_de_trazo(trazo_id)
        partes = muro.get("partes")
        if partes:
            explicita: Decimal | None = max(Decimal(str(p["hasta_m"])) for p in partes)
        elif muro.get("altura_m") is not None:
            explicita = Decimal(str(muro["altura_m"]))
        else:
            explicita = None
        estandar = await self._trazos.altura_estandar_de_trazo(trazo_id)
        guardada = await self._trazos.altura_de_la_conversion(trazo_id)

        r = resolver_muro(
            linea, zonas=zonas, losas=losas, puntos_de_nivel=puntos, altura_explicita_m=explicita, altura_estandar_m=estandar,
            grosor_m=float(trazo["grosor_m"]) if trazo["grosor_m"] is not None else None,
        )
        # Cada vano cae en el tramo donde está su centro (`posicion_m`, sobre el eje); sin posición, en el primero.
        largo = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in pairwise(linea))
        vanos_por_tramo: list[list[dict[str, Any]]] = [[] for _ in r.tramos]
        for v in await self._trazos.vanos_de_trazo(trazo_id):
            pos = min(max(float(v["posicion_m"] or 0), 0.0), max(largo - 1e-6, 0.0))
            for i, t in enumerate(r.tramos):
                if float(t.desde_m) - 1e-6 <= pos < float(t.hasta_m) - 1e-6:
                    vanos_por_tramo[i].append({"vano_id": v["id"], "clave": v["clave"], "tipo": v["tipo"], "posicion_m": v["posicion_m"]})
                    break
        return {
            "trazo_id": trazo_id,
            "escala_definida": escala_definida,
            "altura_explicita_m": explicita,
            "altura_estandar_m": estandar,
            "altura_guardada_m": guardada,
            "resolucion": r,
            "vanos_por_tramo": vanos_por_tramo,
            "tramos_de_conversion": tramos_para_conversion(r) if r.con_zona else [],
        }

    async def tramos_del_muro_nuevo(self, trazo_id: UUID) -> list[dict[str, Any]] | None:
        """Los tramos lógicos con los que nace un muro NUEVO que cae bajo alguna zona de losa; `None` si el trazo no es una línea o no
        toca ninguna zona (entonces nace con la altura estándar). La altura explícita del trazo no cuenta: aún no tiene."""
        trazo = await self._zonas.trazo(trazo_id)
        if trazo is None or trazo["tipo"] != "LINESTRING" or not await self._zonas.zonas(trazo["plano_id"]):
            return None
        datos = await self.resolver_muro(trazo_id)
        r = datos["resolucion"]
        return tramos_para_conversion(r) if r.con_zona else None
