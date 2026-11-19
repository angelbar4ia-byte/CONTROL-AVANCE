"""La fachada de un plano por bandas de altura (F1, 2026-11-19): lee los muros REALES del plano, sus zonas de losa y sus puntos de nivel
exterior, y reparte los m² de cara exterior en la banda baja (0 a 3.00), la media («+3.00», de 3.00 a 4.20) y el resto.

No usa ningún selector ni cantidad capturada aparte: si cambia el largo de un muro, su altura, su ubicación, una zona de losa o un punto de
nivel, la fachada cambia sola. Descuenta solo puertas y ventanas (los castillos colocados no son vanos). Solo lee: no cambia ningún trazo ni cantidad guardados ni cobra nada. No lee ningún driver (ni `altura_estandar`):
las bandas son las de la decisión F1 (0 a 3.00, 3.00 a 4.20, resto), constantes del dominio.

De dónde sale la cara exterior de cada muro, en este orden: (1) las **partes de altura con caras** que el muro ya trae guardadas; (2) la
**zona de losa** bajo la que cae cada tramo (la cara sin losa es exterior); (3) la **ubicación** del muro (fachada A o B, pretil, barda). Un muro
sin ninguna de las tres no dice cuál de sus caras es exterior: no se cuenta y se avisa.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import PlanoNoEncontrado
from obractrl.application.casos_uso.zonas_de_losa import GestionarZonasDeLosa
from obractrl.application.puertos.cuantificacion import RepositorioTrazos
from obractrl.application.puertos.zonas_de_losa import RepositorioZonasDeLosa
from obractrl.domain.cuantificacion.fachada_por_bandas import (
    LIMITE_ALTO_POR_DEFECTO_M,
    LIMITE_BAJO_POR_DEFECTO_M,
    ParteConCaras,
    ReparticionPorBandas,
    TramoConCaras,
    VanoEnTramo,
    bandas_de_fachada,
    franjas_exteriores,
    redondear,
    repartir_en_bandas,
    se_descuenta_de_la_fachada,
)
from obractrl.domain.cuantificacion.muro_ubicacion import UBICACIONES_DE_MURO

__all__ = ["ConsultarFachadaPorBandas"]

_CERO = Decimal(0)


def _caras_de_ubicacion(ubicacion: str | None) -> tuple[str | None, str | None]:
    caras = UBICACIONES_DE_MURO.get(ubicacion or "", {}).get("caras")
    return (caras[0], caras[1]) if caras else (None, None)


def _filas(r: ReparticionPorBandas) -> list[dict[str, Any]]:
    return [
        {
            "banda": f.banda.clave, "nombre": f.banda.nombre, "desde_m": f.banda.desde_m, "hasta_m": f.banda.hasta_m,
            "bruto_m2": redondear(f.bruto_m2), "vanos_m2": redondear(f.vanos_m2), "neto_m2": redondear(f.neto_m2),
        }
        for f in r.bandas
    ]


class ConsultarFachadaPorBandas:
    def __init__(self, *, zonas: GestionarZonasDeLosa, repo_zonas: RepositorioZonasDeLosa, trazos: RepositorioTrazos) -> None:
        self._zonas = zonas
        self._repo = repo_zonas
        self._trazos = trazos

    async def del_plano(self, plano_id: UUID) -> dict[str, Any]:
        plano = await self._repo.plano(plano_id)
        if plano is None:
            raise PlanoNoEncontrado(f"El plano {plano_id} no existe o no está en tu alcance.")
        baja, alta = LIMITE_BAJO_POR_DEFECTO_M, LIMITE_ALTO_POR_DEFECTO_M
        bandas = bandas_de_fachada(baja, alta)

        todas = []
        por_muro: list[dict[str, Any]] = []
        sin_cara: list[dict[str, Any]] = []
        for m in await self._repo.muros(plano_id):
            tramos, origen = await self._tramos_del_muro(m["id"], m.get("ubicacion"))
            franjas = [f for t in tramos for f in franjas_exteriores(t)]
            if not franjas:
                sin_cara.append({"trazo_id": m["id"], "motivo": "No dice cuál de sus caras es exterior: pon su ubicación, sus caras por parte o dibuja su zona de losa."})
                continue
            todas.extend(franjas)
            r = repartir_en_bandas(franjas, bandas)
            por_muro.append({"trazo_id": m["id"], "origen_de_caras": origen, "ubicacion": m.get("ubicacion"), "bandas": _filas(r), "neto_m2": redondear(r.neto_m2)})

        total = repartir_en_bandas(todas, bandas)
        return {
            "plano_id": plano_id,
            "obra_id": plano.get("obra_id"),
            "limite_bajo_m": baja,
            "limite_alto_m": alta,
            "bandas": _filas(total),
            "bruto_m2": redondear(total.bruto_m2),
            "vanos_m2": redondear(total.vanos_m2),
            "neto_m2": redondear(total.neto_m2),
            "muros": por_muro,
            "muros_sin_cara_exterior": sin_cara,
        }

    async def _tramos_del_muro(self, trazo_id: UUID, ubicacion: str | None) -> tuple[list[TramoConCaras], str]:
        datos = await self._zonas.resolver_muro(trazo_id)
        r = datos["resolucion"]
        muro = await self._trazos.muro_de_trazo(trazo_id)
        guardadas = [
            ParteConCaras(
                Decimal(str(p["desde_m"])), Decimal(str(p["hasta_m"])), p.get("cara_a"), p.get("cara_b"), bool(p.get("suma", True))
            )
            for p in (muro.get("partes") or [])
        ]
        ubic_a, ubic_b = _caras_de_ubicacion(ubicacion)
        if guardadas and all(p.cara_a is None and p.cara_b is None for p in guardadas):
            guardadas = [ParteConCaras(p.desde_m, p.hasta_m, ubic_a, ubic_b, p.suma) for p in guardadas]
        # Solo puertas y ventanas: los castillos colocados (tipo «castillo», misma tabla) no son huecos y no se restan.
        vanos = [v for v in await self._trazos.vanos_de_trazo(trazo_id) if se_descuenta_de_la_fachada(v.get("tipo"))]

        tramos: list[TramoConCaras] = []
        origen = "ubicacion"
        for t in r.tramos:
            cubiertos = [x for x in (t.lado_a, t.lado_b) if x.origen == "losa" and x.cota_inferior_m is not None and x.altura_m is not None]
            base = min((x.cota_inferior_m - x.altura_m for x in cubiertos), default=_CERO)  # type: ignore[operator]
            if guardadas and any(p.cara_a or p.cara_b for p in guardadas):
                partes, origen = tuple(guardadas), "partes_del_muro"
            elif t.partes and any(p["cara_a"] or p["cara_b"] for p in t.partes):
                partes = tuple(
                    ParteConCaras(Decimal(str(p["desde_m"])), Decimal(str(p["hasta_m"])), p["cara_a"], p["cara_b"], bool(p["suma"]))
                    for p in t.partes
                )
                origen = "zona_de_losa"
            else:
                altura = t.altura_m
                a, b = (t.lado_a.cara, t.lado_b.cara) if (t.lado_a.cara or t.lado_b.cara) else (ubic_a, ubic_b)
                partes = (ParteConCaras(_CERO, altura, a, b),)
                origen = "zona_de_losa" if (t.lado_a.cara or t.lado_b.cara) else "ubicacion"
            en_el_tramo = tuple(
                VanoEnTramo(
                    ancho_m=Decimal(str(v["ancho_m"])) * int(v.get("piezas") or 1),
                    desde_m=Decimal(str(v["antepecho_m"] or 0)),
                    hasta_m=Decimal(str(v["antepecho_m"] or 0)) + Decimal(str(v["alto_m"])),
                )
                for v in vanos
                if t.desde_m - Decimal("0.000001") <= Decimal(str(v["posicion_m"] or 0)) < t.hasta_m - Decimal("0.000001")
            )
            tramos.append(
                TramoConCaras(
                    largo_m=t.longitud_m,
                    partes=partes,
                    base_m=base,
                    suelo_a_m=t.lado_a.nivel_exterior_m if t.lado_a.origen == "punto_de_nivel" else None,
                    suelo_b_m=t.lado_b.nivel_exterior_m if t.lado_b.origen == "punto_de_nivel" else None,
                    vanos=en_el_tramo,
                )
            )
        return tramos, origen
