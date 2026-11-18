"""Lo que un concepto toma de un elemento paramétrico escribe la cantidad medida de su matriz (D-639, D-630).

Un elemento colocado en el plano (castillo K-1…) trae su receta; cada concepto que sale de él toma una parte y declara en
qué unidad se cuenta. Esa toma, sumada en toda la obra, es la **cantidad medida de la matriz** del concepto dentro de
cada actividad que la tiene (`actividad_matriz`, origen `elemento`). Lo trazado directo sobre la matriz manda sobre lo
tomado (D-584 regla 2: no hay doble conteo), y si la matriz es la que cuenta para el concepto (D-636) la cantidad de la
actividad se rehace con ella.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.conceptos_de_lo_colocado import (
    conceptos_de_lo_colocado,
)
from obractrl.application.casos_uso.cuantificar import (
    _recalcular_nodo,
    altura_del_muro,
    area_de_muro,
)
from obractrl.application.casos_uso.parametrico import vigentes_de_obra
from obractrl.domain.cuantificacion.colocacion_de_plantilla import (
    colocar_plantilla,
    sembrados_por_tipo,
)
from obractrl.domain.cuantificacion.elementos_parametricos import (
    MATERIALES_DE_UN_ELEMENTO,
    lados_por_defecto,
    normalizar_parametros,
    receta,
    toma_por_unidad,
)
from obractrl.domain.cuantificacion.reglas import (
    ErrorDeCuantificacion,
    TipoNodoCuantificacion,
)

__all__ = ["SincronizarTomas", "filas_de_toma", "totales_de_trazos"]

_TOTALES = {
    "concreto": ("concreto_m3", "m³"),
    "acero": ("acero_kg", "kg"),
    "estribos": ("estribos_kg", "kg"),
    "alambre": ("alambre_kg", "kg"),
    "cimbra": ("cimbra_m2", "m²"),
}


def totales_de_trazos(elementos: dict[Any, dict[str, Any]], trazos: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    """Lo que llevan en total los elementos colocados en esos trazos: la receta de una muestra × lo que aporta cada uno."""
    por_elemento: dict[Any, dict[str, Any]] = {}
    for trazo in trazos:
        e = elementos.get(trazo["elemento_parametrico_id"])
        if e is None:
            continue
        p = normalizar_parametros(e["tipo"], dict(e["parametros"] or {}))
        r = receta(e["tipo"], p)
        q = float(trazo["cantidad"])
        lados = trazo["lados_cimbra"] or lados_por_defecto(e["tipo"], p)
        m2_por_muestra = r["cimbra_m2"].get(lados, 0.0)
        t = por_elemento.setdefault(
            e["id"],
            {
                "elemento_id": e["id"], "clave": e["clave"], "nombre": e["nombre"], "tipo": e["tipo"],
                "unidad": r["unidad"], "colocados": 0, "cantidad": 0.0, "concreto_m3": 0.0, "acero_kg": 0.0,
                "estribos_kg": 0.0, "alambre_kg": 0.0, "cimbra_m2": 0.0, "cimbra_por_lados": {},
            },
        )
        t["colocados"] += 1
        t["cantidad"] += q
        t["concreto_m3"] += r["concreto"] * q
        t["acero_kg"] += r["acero_kg"] * q
        t["estribos_kg"] += r["estribos_kg"] * q
        t["alambre_kg"] += r["alambre_kg"] * q
        t["cimbra_m2"] += m2_por_muestra * q
        t["cimbra_por_lados"][lados] = t["cimbra_por_lados"].get(lados, 0.0) + m2_por_muestra * q
    return por_elemento


def filas_de_toma(
    elementos: dict[Any, dict[str, Any]], totales: dict[Any, dict[str, Any]], vinculos: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Por cada concepto que toma de un elemento colocado: su cantidad en la unidad del concepto y lo que toma."""
    filas: list[dict[str, Any]] = []
    for f in vinculos:
        t = totales.get(f["elemento_id"])
        e = elementos.get(f["elemento_id"])
        if t is None or e is None:
            continue
        toma = {m: bool(v) for m, v in dict(f["toma"] or {}).items() if m in MATERIALES_DE_UN_ELEMENTO}
        u = toma_por_unidad(e["tipo"], dict(e["parametros"] or {}), f["unidad"], toma)
        en_ml = e["tipo"] == "castillo" and f["unidad"] == "ml"
        cantidad = t["colocados"] * u["cantidad_por_muestra"] if en_ml else t["cantidad"]
        filas.append(
            {
                "elemento_id": f["elemento_id"],
                "concepto_id": f["concepto_id"],
                "clave": f["clave"],
                "descripcion": f["descripcion"],
                "unidad": f["unidad"],
                "cantidad": cantidad,
                "materiales": {m: {"cantidad": t[campo], "unidad": un} for m, (campo, un) in _TOTALES.items() if toma.get(m)},
            }
        )
    return filas


class SincronizarTomas:
    def __init__(
        self,
        *,
        elementos: Any,
        matrices: Any,
        enlaces: Any,
        actividades: Any,
        prototipo_nodos: Any,
        desviaciones: Any,
        parametrico: Any | None = None,
        trazos: Any | None = None,
    ) -> None:
        # Con el repositorio del Paramétrico, los castillos colocados desde la plantilla de un muro también alimentan conceptos (Ola 4C).
        self._parametrico = parametrico
        # Con el de trazos, lo que trae la plantilla de un muro (cadenas y castillos estimados) alimenta conceptos sin colocarse en el plano.
        self._trazos = trazos
        self._elementos = elementos
        self._matrices = matrices
        self._enlaces = enlaces
        self._actividades = actividades
        self._prototipo_nodos = prototipo_nodos
        self._desviaciones = desviaciones

    async def tomas_de_la_obra(self, obra_id: UUID) -> dict[UUID, tuple[Decimal, str]]:
        """Concepto → (cantidad, unidad) de lo que toma de los elementos colocados en toda la obra."""
        elementos = {e["id"]: e for e in await self._elementos.listar_todos()}
        totales = totales_de_trazos(elementos, await self._elementos.trazos_de_la_obra(obra_id))
        suma: dict[UUID, tuple[Decimal, str]] = {}
        for f in filas_de_toma(elementos, totales, await self._elementos.de_todos_los_elementos()):
            cid = UUID(str(f["concepto_id"]))
            antes = suma.get(cid)
            cantidad = Decimal(str(f["cantidad"])) + (antes[0] if antes and antes[1] == f["unidad"] else Decimal(0))
            suma[cid] = (cantidad, f["unidad"])
        for cid, cantidad, unidad in [*await self._tomas_de_castillos_colocados(obra_id), *await self._tomas_de_plantillas(obra_id)]:
            antes = suma.get(cid)
            suma[cid] = (cantidad + (antes[0] if antes and antes[1] == unidad else Decimal(0)), unidad)
        return suma

    async def _tomas_de_plantillas(self, obra_id: UUID) -> list[tuple[UUID, Decimal, str]]:
        """Lo que toman los conceptos de lo que trae la plantilla de cada muro de la obra **sin colocarse en el plano**: las cadenas (el largo
        del muro, en ml) y los castillos estimados del muro confinado (sus piezas por la regla de la plantilla). Los castillos ubicados salen
        de lo colocado (`_tomas_de_castillos_colocados`), así que no se cuentan dos veces. Si el concepto no cuenta (propuesto, sin partida
        en el árbol, unidad no admitida) avisa en el reporte de lo colocado y no suma. Un muro cuya plantilla no cabe se omite aquí; el
        reporte de su colocación dice por qué."""
        if self._parametrico is None or self._trazos is None:
            return []
        filas = await self._elementos.trazos_con_plantilla_de_la_obra(obra_id)
        if not filas:
            return []
        catalogo = {str(e["clave"]): e for e in await self._elementos.listar_todos()}
        vigentes = await vigentes_de_obra(self._parametrico, obra_id)
        separacion = vigentes.get("separacion_castillos")
        grupos: list[dict[str, Any]] = []
        for f in filas:
            elementos = [
                e for e in (f["elementos"] or [])
                if e.get("clase") == "cadena" or (e.get("clase") == "castillo" and e.get("modo") == "estimado")
            ]
            if not elementos:
                continue
            try:
                largo = await self._trazos.largo_del_eje(f["trazo_id"])
                altura = await altura_del_muro(self._trazos, f["trazo_id"])
                neta = (await area_de_muro(self._trazos, f["trazo_id"], largo, altura))[2]
                colocacion = colocar_plantilla(
                    elementos, largo_m=largo, altura_m=altura, anchos_m={}, separacion_m=separacion.valor if separacion is not None else None,
                    area_m2=neta,
                    sembrados=sembrados_por_tipo(await self._trazos.vanos_de_trazo(f["trazo_id"]), f["elementos"] or []),
                )
            except ErrorDeCuantificacion:
                continue
            for i in colocacion.instancias:
                el = catalogo.get(i.ref)
                if el is None or (i.clase == "castillo" and i.piezas_exactas <= 0):
                    continue
                grupos.append(
                    {
                        "elemento_id": el["id"], "ref": i.ref, "uid": i.uid, "clase": i.clase, "nivel_orden": f.get("nivel_orden"),
                        "nivel_id": f.get("nivel_id"), "etapa_id": f.get("etapa_id"), "ubicacion": f.get("ubicacion"),
                        **({"alto_m": i.alto_m, "piezas": i.piezas_exactas} if i.clase == "castillo" else {"alto_m": None, "piezas": 1, "metros": i.metros}),
                    }
                )
        salida: list[tuple[UUID, Decimal, str]] = []
        for _, conceptos, _avisos in await conceptos_de_lo_colocado(
            elementos=self._elementos, parametrico=self._parametrico, obra_id=obra_id, instancias=grupos
        ):
            salida.extend((c.concepto_id, c.cantidad, c.unidad) for c in conceptos if c.cuenta and c.concepto_id is not None)
        return salida

    async def _tomas_de_castillos_colocados(self, obra_id: UUID) -> list[tuple[UUID, Decimal, str]]:
        """Lo que toman los conceptos de los castillos colocados desde la plantilla de un muro (0135): por cada muro y alto, el concepto lo
        eligen el nivel, la ubicación y el alto (2A) y la ranura enlazada en el Paramétrico (4B). Si la partida no está en el árbol de la
        obra, avisa (en el reporte de lo colocado) y no cuenta. Sin castillos colocados no hay nada."""
        if self._parametrico is None:
            return []
        filas = await self._elementos.instancias_de_la_obra(obra_id)
        if not filas:
            return []
        grupos: dict[tuple[Any, ...], dict[str, Any]] = {}
        for f in filas:
            clave = (f["trazo_id"], f["elemento_id"], Decimal(str(f["alto_m"])))
            g = grupos.setdefault(clave, {**f, "piezas": 0})
            g["piezas"] += int(f["piezas"])
        salida: list[tuple[UUID, Decimal, str]] = []
        for _, conceptos, _avisos in await conceptos_de_lo_colocado(
            elementos=self._elementos, parametrico=self._parametrico, obra_id=obra_id, instancias=grupos.values()
        ):
            salida.extend((c.concepto_id, c.cantidad, c.unidad) for c in conceptos if c.cuenta and c.concepto_id is not None)
        return salida

    async def de_la_obra_del_trazo(self, trazo_id: UUID) -> None:
        """Rehace las tomas de la obra del trazo (dentro de la transacción de quien llama). Para cuando cambian los castillos de un muro."""
        trazo = await self._elementos.contexto_de_trazo(trazo_id)
        if trazo is not None:
            await self.de_la_obra(UUID(str(trazo["obra_id"])))

    async def de_la_obra(self, obra_id: UUID) -> None:
        """Rehace las cantidades medidas de las matrices que toman de elementos. Se llama dentro de la transacción."""
        a_recalcular = await self._matrices.aplicar_tomas(obra_id, await self.tomas_de_la_obra(obra_id))
        for actividad_id in a_recalcular:
            await _recalcular_nodo(
                tipo_nodo=TipoNodoCuantificacion.ACTIVIDAD,
                actividad_id=actividad_id,
                prototipo_nodo_id=None,
                enlaces=self._enlaces,
                actividades=self._actividades,
                prototipo_nodos=self._prototipo_nodos,
                desviaciones=self._desviaciones,
                detectada_en=datetime.now(UTC),
                matrices=self._matrices,
            )

    async def obra_si_es_elemento(self, trazo_id: UUID) -> UUID | None:
        """La obra del trazo, si está marcado como un elemento o eligió una plantilla de muro (para rehacer sus tomas al borrarlo)."""
        trazo = await self._elementos.trazo_de(trazo_id)
        if trazo is None or (trazo["elemento_parametrico_id"] is None and not trazo.get("muro_plantilla_id")):
            return None
        return await self._elementos.obra_del_trazo(trazo_id)

    async def de_las_obras_con(self, elemento_id: UUID | None) -> None:
        for obra_id in await self._elementos.obras_con_el_elemento(elemento_id):
            await self.de_la_obra(obra_id)
