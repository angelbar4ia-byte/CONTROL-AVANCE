"""Reversión por destajo: reconstruir qué concepto hizo la ingeniería del
lote, que no trae conceptos — solo insumos (CONOCIMIENTO.md §11.6, §11.9,
§11.13/D-489).

Traducción fiel de `backend/core/tests/test_reversion_alamo18.py` del
cerebro (es "el algoritmo más concreto y portable que existe para esto"),
con el refinamiento de D-489 ya incluido desde el principio (nunca el
conteo ingenuo): los candidatos de un destajo son los conceptos **de su
misma etapa** (`ECO-...`), y su cantidad presupuestada es la de esa etapa,
no la de la clave en todo el capítulo (la misma clave de concepto puede
colgar de dos etapas con cantidades distintas).

**Las cuatro clases del residuo** (§11.9): único candidato (se aplica
directo), varios candidatos (la ingeniería trae la SUMA de todos ellos,
nunca "cuál es"), destajo que solo vive en la matriz de un compuesto (hay
que buscar en profundidad — aquí con `domain.catalogos.apu.explotar`, no
con un recorrido de árbol propio) y clave que no existe en ninguna matriz
del prototipo (nunca se corrige por proximidad; si hay exactamente un
sobrante y un faltante con la misma evidencia, se proponen las dos
lecturas y se reporta sin tocar nada).

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11). No persiste nada — ver
`domain.ingenieria.desviacion` para quien consume este resultado.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from obractrl.domain.cargadores.ingenieria_lote import ES_DESTAJO, FilaInsumoIngenieria
from obractrl.domain.cargadores.reporte import PendientePropuesto, TipoPendiente
from obractrl.domain.catalogos.apu import Componente, explotar
from obractrl.domain.ingenieria.matriz_completa import LineaMatrizCruda
from obractrl.domain.shared.diccionario import TipoHijoExplosion

__all__ = [
    "ClaseReversionDestajo",
    "ReversionDestajo",
    "rendimiento_profundo",
    "revertir_destajos",
]

_TOLERANCIA = Decimal("0.01")


class ClaseReversionDestajo(StrEnum):
    """Las cuatro clases del residuo de §11.9."""

    UNICO = "unico"
    """Un solo concepto de la etapa cita este destajo: se aplica directo."""

    VARIOS = "varios"
    """Más de un concepto de la etapa lo cita: la ingeniería trae la suma
    de todos, nunca "cuál es" (D-489)."""

    COMPUESTO = "compuesto"
    """Ningún concepto lo cita directo, pero sí un compuesto que algún
    concepto de la etapa usa — se encuentra con `apu.explotar`, en
    profundidad (§11.9: "se estaba buscando en la profundidad
    equivocada")."""

    SIN = "sin"
    """Ninguna matriz del prototipo (ni directa ni de compuesto) cita esta
    clave, en ninguna profundidad."""


@dataclass(frozen=True, slots=True)
class ReversionDestajo:
    """El resultado de revertir un destajo de una etapa."""

    etapa: str
    clave: str
    descripcion: str
    precio: Decimal | None
    cantidad_real: Decimal
    clase: ClaseReversionDestajo
    candidatos: tuple[str, ...]
    """Conceptos candidatos — directos (`UNICO`/`VARIOS`) o encontrados en
    profundidad (`COMPUESTO`); vacío en `SIN`."""

    cantidad_presupuestada: Decimal | None
    """Σ(cantidad presupuestada del candidato × rendimiento), para
    comparar contra ``cantidad_real``. ``None`` en `SIN` (no hay candidato
    contra el cual medir)."""

    reparto: dict[str, Decimal] | None
    """Concepto → su cantidad reconstruida, **solo** cuando el destajo
    quedó resuelto (`UNICO` siempre; `COMPUESTO` siempre que la profundidad
    encontró un único concepto; `VARIOS` solo si la suma presupuestada
    cierra exacto contra ``cantidad_real``). ``None`` en cualquier otro
    caso — nunca se rellena con un reparto adivinado."""


def _rendimiento_y_citas(
    lineas: Sequence[LineaMatrizCruda],
) -> tuple[dict[tuple[str, str], Decimal], dict[str, list[tuple[str, str]]]]:
    """``rendimiento[(concepto, destajo)]`` (solo líneas `Origen=Concepto`,
    sumando TODAS sus ocurrencias — §11.13: "sumando la cantidad del
    destajo en todas sus ocurrencias de la etapa, antes de decidir si hay
    empate") y ``citan[destajo] -> [(padre, origen), ...]`` de cualquier
    origen, igual que ``self.citan``/``self.rendimiento`` de la referencia.
    """
    rendimiento: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    citan: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for linea in lineas:
        citan[linea.hijo].append((linea.padre, linea.origen))
        if linea.origen == "concepto":
            rendimiento[(linea.padre, linea.hijo)] += linea.cantidad
    return dict(rendimiento), dict(citan)


def _candidatos_directos(
    etapa: str,
    clave: str,
    citan: Mapping[str, Sequence[tuple[str, str]]],
    presupuesto_por_etapa: Mapping[str, Mapping[str, Decimal]],
) -> tuple[list[str], list[str]]:
    """``(candidatos_concepto, candidatos_compuesto)`` de un destajo en una
    etapa: los padres `Origen=Concepto` que SÍ están en el presupuesto de
    esa etapa (candidatos directos), y los padres de cualquier otro origen
    (pista para la clase `COMPUESTO`)."""
    citas = citan.get(clave, ())
    presupuesto_etapa = presupuesto_por_etapa.get(etapa, {})
    candidatos = sorted({p for p, o in citas if o == "concepto" and p in presupuesto_etapa})
    de_compuesto = sorted({p for p, o in citas if o != "concepto"})
    return candidatos, de_compuesto


def _cantidad_presupuestada(
    etapa: str,
    clave: str,
    candidatos: Sequence[str],
    rendimiento: Mapping[tuple[str, str], Decimal],
    presupuesto_por_etapa: Mapping[str, Mapping[str, Decimal]],
) -> Decimal:
    presupuesto_etapa = presupuesto_por_etapa.get(etapa, {})
    return sum(
        (presupuesto_etapa.get(c, Decimal(0)) * rendimiento.get((c, clave), Decimal(0)) for c in candidatos),
        Decimal(0),
    )


def _rendimiento_profundo(
    concepto: str, clave: str, composiciones: Mapping[str, Sequence[Componente]], cache: dict
) -> Decimal:
    """Cuánto del destajo ``clave`` lleva UNA unidad de ``concepto``, a
    cualquier profundidad — usando `apu.explotar`, no un recorrido propio
    (§11.9: "buscar en profundidad ... usa la profundidad que ya soporta
    `apu.explotar()`").
    """
    if concepto not in cache:
        cache[concepto] = explotar(concepto, composiciones=composiciones).lineas
    lineas = cache[concepto]
    return sum(
        (
            linea.cantidad
            for linea in lineas
            if linea.tipo_hijo is TipoHijoExplosion.INSUMO and linea.referencia == clave
        ),
        Decimal(0),
    )


def rendimiento_profundo(
    concepto: str,
    clave: str,
    composiciones: Mapping[str, Sequence[Componente]],
    cache: dict | None = None,
) -> Decimal:
    """Envoltura pública de `_rendimiento_profundo` (arriba): cuánto del
    insumo ``clave`` lleva UNA unidad de ``concepto``, a cualquier
    profundidad (`apu.explotar`).

    La reconstrucción de un archivo `CON_CONCEPTO` (`domain.ingenieria.
    con_concepto.reconstruir_con_concepto`) reusa exactamente esta función
    con un ancla distinta a la de un destajo (CONOCIMIENTO.md §11.8,
    decisión explícita del encargo: "el ancla puede ser CUALQUIER insumo
    de la matriz, no solo uno que matchee ES_DESTAJO") — se expone en vez
    de duplicar el recorrido en profundidad que ya hace `_rendimiento_
    profundo` para la clase `COMPUESTO` de la reversión por destajo.
    """
    return _rendimiento_profundo(concepto, clave, composiciones, cache if cache is not None else {})


def revertir_destajos(
    filas_insumo: Sequence[FilaInsumoIngenieria],
    lineas_matriz: Sequence[LineaMatrizCruda],
    presupuesto_por_etapa: Mapping[str, Mapping[str, Decimal]],
    composiciones: Mapping[str, Sequence[Componente]],
) -> tuple[tuple[ReversionDestajo, ...], tuple[PendientePropuesto, ...]]:
    """Revierte, por etapa, cada destajo (`ES_DESTAJO`) del lote contra el
    prototipo ya identificado.

    Solo considera las filas cuya ``etapa`` es conocida (`ECO-...`): un
    destajo de un archivo `SUELTA`/`CON_CONCEPTO` sin etapa no tiene contra
    qué prototipo-etapa compararse desde aquí — mismo límite que
    `identificacion.identificar_prototipo` (ver su docstring).
    """
    rendimiento, citan = _rendimiento_y_citas(lineas_matriz)

    suma_real: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    ultima_evidencia: dict[tuple[str, str], tuple[str, Decimal | None]] = {}
    for f in filas_insumo:
        if f.etapa is None or not f.es_destajo:
            continue
        suma_real[(f.etapa, f.clave)] += f.cantidad
        ultima_evidencia[(f.etapa, f.clave)] = (f.descripcion, f.precio)

    cache_explosion: dict[str, tuple] = {}
    resultados: list[ReversionDestajo] = []
    pendientes: list[PendientePropuesto] = []

    for (etapa, clave), cantidad_real in suma_real.items():
        descripcion, precio = ultima_evidencia[(etapa, clave)]
        candidatos, de_compuesto = _candidatos_directos(etapa, clave, citan, presupuesto_por_etapa)

        if len(candidatos) == 1:
            esperado = _cantidad_presupuestada(etapa, clave, candidatos, rendimiento, presupuesto_por_etapa)
            concepto = candidatos[0]
            r = rendimiento.get((concepto, clave), Decimal(0))
            reparto = {concepto: cantidad_real / r} if r else None
            resultados.append(
                ReversionDestajo(etapa, clave, descripcion, precio, cantidad_real,
                                  ClaseReversionDestajo.UNICO, tuple(candidatos), esperado, reparto)
            )
            continue

        if candidatos:
            esperado = _cantidad_presupuestada(etapa, clave, candidatos, rendimiento, presupuesto_por_etapa)
            if esperado == cantidad_real:
                presupuesto_etapa = presupuesto_por_etapa.get(etapa, {})
                reparto = {c: presupuesto_etapa.get(c, Decimal(0)) for c in candidatos}
            else:
                reparto = None
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.DESTAJO_AMBIGUO,
                        entidad="reversion_destajo",
                        valor_origen=clave,
                        propuesta={
                            "etapa": etapa,
                            "candidatos": candidatos,
                            "cantidad_real": str(cantidad_real),
                            "cantidad_presupuestada": str(esperado),
                            "motivo": (
                                "Varios candidatos en la etapa y la suma no cierra "
                                "exacto contra la cantidad real; no se elige el más "
                                "probable (§11.9)."
                            ),
                        },
                    )
                )
            resultados.append(
                ReversionDestajo(etapa, clave, descripcion, precio, cantidad_real,
                                  ClaseReversionDestajo.VARIOS, tuple(candidatos), esperado, reparto)
            )
            continue

        if de_compuesto:
            etapa_conceptos = list(presupuesto_por_etapa.get(etapa, {}))
            profundos = [
                c for c in etapa_conceptos
                if _rendimiento_profundo(c, clave, composiciones, cache_explosion) > 0
            ]
            if len(profundos) == 1:
                concepto = profundos[0]
                r = _rendimiento_profundo(concepto, clave, composiciones, cache_explosion)
                presupuesto_etapa = presupuesto_por_etapa.get(etapa, {})
                esperado = presupuesto_etapa.get(concepto, Decimal(0)) * r
                reparto = {concepto: cantidad_real / r} if r else None
                resultados.append(
                    ReversionDestajo(etapa, clave, descripcion, precio, cantidad_real,
                                      ClaseReversionDestajo.COMPUESTO, (concepto,), esperado, reparto)
                )
                continue
            if len(profundos) > 1:
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.DESTAJO_AMBIGUO,
                        entidad="reversion_destajo",
                        valor_origen=clave,
                        propuesta={
                            "etapa": etapa,
                            "candidatos": profundos,
                            "motivo": "Varios conceptos llegan a este destajo a través de un compuesto.",
                        },
                    )
                )
                resultados.append(
                    ReversionDestajo(etapa, clave, descripcion, precio, cantidad_real,
                                      ClaseReversionDestajo.COMPUESTO, tuple(profundos), None, None)
                )
                continue
            # de_compuesto no vacío pero ningún concepto de la etapa llega a él
            # en profundidad: cae en SIN, igual que si no hubiera compuesto.

        resultados.append(
            ReversionDestajo(etapa, clave, descripcion, precio, cantidad_real,
                              ClaseReversionDestajo.SIN, (), None, None)
        )

    _marcar_sin_candidato(resultados, pendientes, lineas_matriz, presupuesto_por_etapa, rendimiento)
    return tuple(resultados), tuple(pendientes)


def _marcar_sin_candidato(
    resultados: Sequence[ReversionDestajo],
    pendientes: list[PendientePropuesto],
    lineas_matriz: Sequence[LineaMatrizCruda],
    presupuesto_por_etapa: Mapping[str, Mapping[str, Decimal]],
    rendimiento: Mapping[tuple[str, str], Decimal],
) -> None:
    """Para cada `SIN`, el pendiente `DESTAJO_SIN_CANDIDATO`. Si hay
    EXACTAMENTE un destajo que sobra (`SIN`) y exactamente uno que el
    presupuesto pide y la ingeniería nunca trajo, con la misma evidencia
    (descripción, cantidad, precio), la propuesta lleva las dos lecturas —
    errata de captura o trabajo nuevo no autorizado— y nunca autocorrige
    (§11.9: "no es proximidad... es exclusión más tres coincidencias").
    """
    sobran = [r for r in resultados if r.clase is ClaseReversionDestajo.SIN]
    if not sobran:
        return

    traidos = {r.clave for r in resultados}

    # `pide`: destajos que algún concepto presupuestado exige, según la
    # matriz, dentro de las MISMAS etapas que este lote trae — nunca todo
    # el prototipo completo (mismo criterio que `test_reversion_alamo18.py
    # ::test_mos_2079_es_el_unico_destajo...`, que restringe `pide` a las
    # cinco etapas de la cimentación, no a las ~41 del prototipo entero;
    # sin este alcance, una ingeniería parcial vería "faltar" cientos de
    # destajos de etapas que ni siquiera está cargando, y la propuesta de
    # las dos lecturas nunca podría cumplir "exactamente un sobrante y un
    # faltante").
    etapas_del_lote = {r.etapa for r in resultados}
    conceptos_presupuestados = {
        c for etapa in etapas_del_lote for c in presupuesto_por_etapa.get(etapa, {})
    }
    pide: set[str] = set()
    for linea in lineas_matriz:
        if ES_DESTAJO.match(linea.hijo) and linea.padre in conceptos_presupuestados:
            pide.add(linea.hijo)
    faltan = sorted(pide - traidos)

    evidencia_falta: dict[str, tuple[str, Decimal | None, Decimal]] = {}
    for clave in faltan:
        lineas_del_destajo = [linea for linea in lineas_matriz if linea.hijo == clave]
        if not lineas_del_destajo:
            continue
        referencia = lineas_del_destajo[0]
        for etapa in etapas_del_lote:
            conceptos = presupuesto_por_etapa.get(etapa, {})
            candidatos = sorted(
                {
                    linea.padre
                    for linea in lineas_del_destajo
                    if linea.origen == "concepto" and linea.padre in conceptos
                }
            )
            if len(candidatos) == 1:
                esperado = _cantidad_presupuestada(etapa, clave, candidatos, rendimiento, presupuesto_por_etapa)
                evidencia_falta[clave] = (referencia.descripcion, esperado, referencia.costo)
                break

    for r in sobran:
        propuesta: dict[str, object] = {
            "etapa": r.etapa,
            "descripcion": r.descripcion,
            "cantidad": str(r.cantidad_real),
            "precio": str(r.precio) if r.precio is not None else None,
            "motivo": "Ninguna matriz del prototipo cita esta clave, ni directa ni dentro de un compuesto.",
        }
        if len(sobran) == 1 and len(faltan) == 1:
            falta = faltan[0]
            evidencia = evidencia_falta.get(falta)
            if evidencia is not None:
                desc_falta, cant_falta, precio_falta = evidencia
                coincide = (
                    desc_falta == r.descripcion
                    and cant_falta == r.cantidad_real
                    and (r.precio is None or abs(precio_falta - r.precio) <= _TOLERANCIA)
                )
                propuesta["clave_que_falta"] = falta
                propuesta["coincide_evidencia"] = coincide
                if coincide:
                    propuesta["lecturas_propuestas"] = ["errata_de_captura", "trabajo_nuevo_no_autorizado"]
        pendientes.append(
            PendientePropuesto(
                tipo=TipoPendiente.DESTAJO_SIN_CANDIDATO,
                entidad="reversion_destajo",
                valor_origen=r.clave,
                propuesta=propuesta,
            )
        )
