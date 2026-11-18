"""Aplicar al muro lo que dicen sus zonas de losa (zonas de losa 1.1): un acto explícito de quien lo pide, nunca automático.

- Un muro con **un solo tramo** (bajo una losa, o en el límite entre una de 3.00 y una de 4.20) cuenta con la altura de su zona; en el
  límite, además, con sus **partes de altura por cara** (cuerpo y enrase, con la cara interior o exterior de cada lado).
- Un muro que **cruza** de una zona a otra a lo largo de su recorrido cuenta por **tramos lógicos** dentro de UN solo trazo
  (`conversion.tramos`, 0138): no se parte el trazo ni se copian enlaces, vanos, uniones o revestimientos; cada tramo trae su altura o
  sus partes y cada vano cae en el tramo donde está su centro.

Lo hace por el camino que ya existe: reemplaza el enlace del trazo con la conversión nueva (el anterior queda como evidencia y deja de
sumar) y recalcula lo que alimenta. Los demás trazos y lo ya guardado no se tocan (Q1).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import ConversionDelEnlace, GestionarVanos
from obractrl.application.casos_uso.zonas_de_losa import GestionarZonasDeLosa
from obractrl.application.puertos.cuantificacion import RepositorioEnlacesCuantificacion
from obractrl.domain.cuantificacion.muro import ParteDeAltura
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion
from obractrl.domain.shared.diccionario import Rol

__all__ = ["AplicarZonaAlMuro"]


class AplicarZonaAlMuro:
    def __init__(
        self,
        *,
        zonas: GestionarZonasDeLosa,
        enlaces: RepositorioEnlacesCuantificacion,
        conversiones: ConversionDelEnlace,
        vanos: GestionarVanos,
    ) -> None:
        self._zonas = zonas
        self._enlaces = enlaces
        self._conversiones = conversiones
        self._vanos = vanos

    async def ejecutar(self, trazo_id: UUID, *, rol: Rol, usuario_id: UUID, detectada_en: datetime) -> dict[str, Any]:
        datos = await self._zonas.resolver_muro(trazo_id)
        r = datos["resolucion"]
        if not r.con_zona:
            raise ErrorDeCuantificacion("Este muro no cae bajo ninguna zona de losa: no hay nada que aplicar.")
        if datos["altura_explicita_m"] is not None:
            raise ErrorDeCuantificacion("Este muro trae su altura (altura única o por partes): manda sobre la de la zona.")
        tramos: list[dict[str, Any]] = datos["tramos_de_conversion"]

        aplicados = 0
        sin_conversion = 0
        for v in await self._enlaces.vigentes_de_trazo(trazo_id):
            e = await self._enlaces.obtener(v["id"])
            conv = (e or {}).get("conversion")
            if not conv:
                sin_conversion += 1
                continue
            if conv.get("modo") not in ("area", "vol"):
                continue  # un largo o una pieza no dependen de la altura
            nueva = {k: x for k, x in conv.items() if k not in ("tramos", "partes", "alt")}
            if len(tramos) == 1:
                unico = tramos[0]
                if "partes" in unico:
                    nueva["partes"] = unico["partes"]
                else:
                    nueva["alt"] = unico["alt"]
            else:
                nueva["tramos"] = tramos
                nueva["alt"] = max(
                    (sum(p["hasta_m"] - p["desde_m"] for p in t["partes"] if p["suma"]) if "partes" in t else t["alt"]) for t in tramos
                )
            await self._conversiones.aplicar(
                v["id"], nueva, a_todos=False, rol=rol, usuario_id=usuario_id, detectada_en=detectada_en
            )
            aplicados += 1

        # Con un solo tramo, además se fija cómo cuenta el muro (altura y partes con caras de la estructura 4A) para que el detalle y
        # la ubicación (regla 3: «personalizada» si una cara difiere) lo digan. Con varios tramos no hay una sola altura que guardar.
        if len(r.tramos) == 1 or not r.parte_el_muro:
            t = r.tramos[0]
            muro = await self._vanos.muro(trazo_id)
            partes = (
                [
                    ParteDeAltura(
                        nombre=p["nombre"], desde_m=Decimal(str(p["desde_m"])), hasta_m=Decimal(str(p["hasta_m"])), suma=bool(p["suma"]),
                        cara_a=p["cara_a"], cara_b=p["cara_b"], rol=p["rol"],
                    )
                    for p in t.partes
                ]
                if len(t.partes) > 1
                else None
            )
            await self._vanos.fijar_muro(
                trazo_id, altura_m=t.altura_m, caras=int(muro.get("caras") or 2), cara=muro.get("cara"), partes=partes,
                autor_id=usuario_id, rol=rol, detectada_en=detectada_en,
            )
        return {"trazo_id": trazo_id, "tramos": tramos, "enlaces_aplicados": aplicados, "enlaces_sin_conversion": sin_conversion}
