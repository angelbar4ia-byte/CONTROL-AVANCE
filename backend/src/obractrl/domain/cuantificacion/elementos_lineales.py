"""Elementos estructurales lineales y de pieza de la biblioteca (Ola 3B): trabes, contratrabes, nervaduras, la zapata Z-1
y la columna C-1.

Dominio puro del mockup de elementos paramétricos (`muestra`, `muestraZap`, `contrasteHTML` de `app.js`; spec
`elementos_catalogo`), con los datos del catálogo en `elementos_lineales_catalogo`. Qué hace:

- **Trabes (24), contratrabes (7) y nervaduras (5)** se miden **por metro lineal** de trazo (`modo="ml"`) o **por pieza** de un
  largo conocido (`modo="pieza"`: el acero se corta con la regla de cortes y lleva puntas de anclaje, y los anillos pueden tener
  zonas en los extremos). El acero sale de `receta_acero` (traslape de 40 diámetros, cortes de 1/1.5/2/3/4/6 m); el concreto y la
  cimbra por lados, aquí. La sección «15x25» es **ancho × peralte** (Q54). Una nervadura no lleva cimbra (el casetón la forma) y su
  anillo es una pieza de largo fijo.
- **Zapata Z-1** (EST-03020), por pieza: parrilla de varilla de 3/8 a 15 cm en los dos sentidos. **Sin dado** (Q57): el título del
  concepto lo menciona pero la categoría Dados se construye después.
- **Columna C-1**, por pieza de altura conocida: habitual 4.20 m, editable (el catálogo la paga con EST-11011 «hasta 6.00 m»).

**Sin mano de obra.** El catálogo no trae destajo por metro para trabes, contratrabes ni nervaduras (Q52) y su concreto y su cimbra
se pagan dentro de la losa por m² (Q51). Esta lane **contempla pero no ejecuta** ese camino: `camino_de_colado_y_cimbra` describe
cómo se registraría después el concepto nuevo de colado y cimbra por elemento y el destajo por ml, pero no crea ningún concepto ni
ningún destajo ni pone precios. La Z-1 y la C-1 sí tienen concepto con destajo en el catálogo (MOE-05010, MOE-20210); el elemento
no lo calcula: se lista aparte en la conciliación.

**Conciliación.** Cada elemento se contrasta con la composición real de su concepto del catálogo (=, ≈ hasta 8 %, ≠, solo en el
catálogo / solo en el elemento) con `comparacion_con_catalogo`. Lo que el catálogo trae distinto **se muestra, no se corrige**.
Función pura, sin base de datos.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from obractrl.domain.cuantificacion.clasificacion_de_elementos import CATEGORIAS
from obractrl.domain.cuantificacion.comparacion_con_catalogo import (
    FilaDeComposicion,
    comparar_con_concepto,
)
from obractrl.domain.cuantificacion.elementos_lineales_catalogo import (
    DESCRIPCIONES_DE_INSUMOS,
    ELEMENTOS,
    INSUMOS,
)
from obractrl.domain.cuantificacion.receta_acero import (
    Armex,
    ConsumoDeCimbra,
    DriversDeReceta,
    EntradaRecetaAcero,
    ErrorDeRecetaAcero,
    GrupoDeVarillas,
    Varilla,
    ZonaDeAnillo,
    calcular_receta_acero,
)
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "LARGO_DE_PIEZA_POR_DEFECTO_M",
    "PENDIENTES",
    "TIPOS",
    "TIPO_COLUMNA",
    "TIPO_LINEAL",
    "TIPO_ZAPATA",
    "EntradaElementoEstructural",
    "ErrorDeElementoEstructural",
    "calcular_elemento",
    "camino_de_colado_y_cimbra",
    "categorias_de_biblioteca",
    "claves_de_elementos_estructurales",
    "definicion_del_elemento",
    "elemento_estructural",
]

TIPO_LINEAL = "lineal_estructural"
TIPO_ZAPATA = "zapata_aislada"
TIPO_COLUMNA = "columna_de_concreto"
TIPOS = (TIPO_LINEAL, TIPO_ZAPATA, TIPO_COLUMNA)

LARGO_DE_PIEZA_POR_DEFECTO_M = 4.0
"""El largo con que arranca una trabe «por pieza» en el mockup. Es un valor de arranque, no del catálogo."""

_EPS = 1e-9
_PESO_ALAMBRE_RECOCIDO_KG_M = 0.0095

_NOMBRE_DEL_TIPO = {
    TIPO_LINEAL: "metro lineal de trazo o pieza de largo conocido",
    TIPO_ZAPATA: "pieza",
    TIPO_COLUMNA: "pieza de altura conocida",
}

PENDIENTES: tuple[dict[str, str], ...] = (
    {
        "clave": "Q51",
        "texto": "El concreto y la cimbra de trabes, contratrabes y nervaduras no tienen concepto propio en el catálogo (se pagan por m² de losa). "
        "Se contempla un concepto nuevo de colado y cimbra por elemento, pero todavía no se registra.",
    },
    {
        "clave": "Q52",
        "texto": "El catálogo no trae destajo por ml para trabes, contratrabes ni nervaduras: el elemento queda sin mano de obra. Nada se inventa.",
    },
    {
        "clave": "Q55",
        "texto": "El catálogo da solo el total de varillas; el mockup las reparte mitad arriba y mitad abajo (valor conservador, sin criterio estructural).",
    },
    {
        "clave": "Q56",
        "texto": "El catálogo cuenta la varilla con 8 % de traslape y desperdicio; aquí se usa el traslape de 40 diámetros. La diferencia se muestra en la conciliación, no se corrige. Lo que el catálogo trae mal en T-2-12x20 (dos anillos) y en T-5-12x30 (anillo 10×25 en una sección 12×30) se propone como nueva versión del concepto (D7), pendiente de Control de obra.",
    },
    {
        "clave": "Q60",
        "texto": "El anclaje de la varilla en una trabe por pieza se sugiere de 40 diámetros por extremo (D6): es una sugerencia, no una regla; si se captura otro valor el elemento lo usa y avisa si cumple. Falta el gancho o la patilla del estructurista.",
    },
)
"""Lo que el usuario dejó con valor conservador o que el catálogo no responde; la tarjeta lo muestra como pendiente."""


class ErrorDeElementoEstructural(ErrorDeCuantificacion):
    """Un dato que no vale: el elemento no se puede calcular con él."""


Modo = Literal["ml", "pieza"]


@dataclass(frozen=True)
class EntradaElementoEstructural:
    """Lo que se calcula de un elemento de la biblioteca de estructura.

    - `modo`: `ml` (por metro de trazo) o `pieza`. Solo las trabes, contratrabes y nervaduras se miden por ml; la zapata y la
      columna siempre son pieza.
    - `largo_m`: largo de la pieza (trabe/contratrabe/nervadura por pieza); por defecto 4.00 m.
    - `alto_m`: altura de la columna C-1; por defecto 4.20 m, la habitual (D5; editable). El escalón del catálogo, EST-11011, llega hasta 6.00 m.
    - `zonas_de_anillo`: solo por pieza; `(largo de la zona en cada extremo en cm o None, separación en cm)`. Sin ellas se usa la
      separación única del catálogo.
    - `cantidad`: cuántos ml o piezas se piden (da los totales a comprar).
    """

    clave: str
    modo: Modo = "ml"
    largo_m: float | None = None
    alto_m: float | None = None
    cantidad: float = 1.0
    zonas_de_anillo: Sequence[tuple[float | None, float]] = ()
    desperdicio_concreto_pct: float = 5.0
    drivers: DriversDeReceta = field(default_factory=DriversDeReceta)
    anclaje_cm: float | None = None
    """Anclaje de la varilla por extremo de la pieza (cm), capturado por quien calcula. La norma lo pide como **sugerencia**: 40 diámetros
    por extremo. Si se captura, el cálculo lo usa y el resultado dice si cumple la sugerencia (`anclaje`); sin él se usa la sugerencia.
    Solo de una pieza (trabe por pieza o columna)."""


# --------------------------------------------------------------------------------------------------------------
# Catálogo
# --------------------------------------------------------------------------------------------------------------

_POR_CLAVE: dict[str, dict[str, Any]] = {e["clave"]: e for e in ELEMENTOS}


def claves_de_elementos_estructurales() -> tuple[str, ...]:
    return tuple(_POR_CLAVE)


def elemento_estructural(clave: str) -> dict[str, Any] | None:
    """El elemento tal como lo trae el catálogo de datos, o `None` si esa clave no es de esta familia."""
    return _POR_CLAVE.get(clave)


def _insumo(clave: str) -> dict[str, Any]:
    try:
        return INSUMOS[clave]
    except KeyError:
        raise ErrorDeElementoEstructural(f"El insumo {clave} no está en el catálogo de datos del elemento.") from None


def _descripcion(clave: str) -> str:
    if clave in INSUMOS:
        return str(INSUMOS[clave]["descripcion"])
    return DESCRIPCIONES_DE_INSUMOS.get(clave, "")


def _unidad_visible(unidad: str) -> str:
    return {"m3": "m³", "m2": "m²"}.get(unidad, unidad)


def _se_mide_por(e: dict[str, Any]) -> str:
    return _NOMBRE_DEL_TIPO[e["tipo"]]


def _concepto_principal(e: dict[str, Any]) -> dict[str, Any]:
    """El concepto con que el catálogo paga el elemento (el primero de su conciliación)."""
    c = e["catalogo"][0]
    return {"clave": c["clave"], "descripcion": c["descripcion"], "unidad": _unidad_visible(c["unidad"])}


def categorias_de_biblioteca() -> tuple[dict[str, Any], ...]:
    """Las categorías y subcategorías de la biblioteca con los elementos de esta familia (forma de `BIBLIOTECA`)."""
    nombres = {c["clave"]: c for c in CATEGORIAS}
    salida: list[dict[str, Any]] = []
    for cat in CATEGORIAS:
        subs: list[dict[str, Any]] = []
        for sub in cat["subcategorias"]:
            mios = [
                e for e in ELEMENTOS if e["categoria"] == cat["clave"] and e["subcategoria"] == sub["clave"]
            ]
            if not mios:
                continue
            subs.append(
                {
                    "clave": sub["clave"],
                    "nombre": sub["nombre"],
                    "prefijo": sub["prefijo"],
                    "elementos": tuple(
                        {
                            "clave": e["clave"],
                            "nombre": e["nombre"],
                            "tipo": e["tipo"],
                            "se_mide_por": _se_mide_por(e),
                            "concepto": _concepto_principal(e),
                        }
                        for e in mios
                    ),
                }
            )
        if subs:
            salida.append(
                {"clave": cat["clave"], "nombre": nombres[cat["clave"]]["nombre"], "prefijo": cat["prefijo"], "subcategorias": tuple(subs)}
            )
    return tuple(salida)


def _descripcion_de_armado(e: dict[str, Any]) -> list[dict[str, Any]]:
    a = e["armado"]
    filas: list[dict[str, Any]] = []
    if a["tipo"] == "armex":
        filas.append({"parte": "armex", "clave": a["armex"], "descripcion": _descripcion(a["armex"]), "cantidad": 1, "detalle": "una cercha"})
        return filas
    if a["tipo"] == "parrilla":
        filas.append(
            {
                "parte": "parrilla", "clave": a["varilla"], "descripcion": _descripcion(a["varilla"]), "cantidad": a["capas"],
                "detalle": f"a cada {a['sep_cm']:g} cm en los dos sentidos, {a['capas']} capa(s), recubrimiento {a['rec_cm']:g} cm",
            }
        )
        return filas
    if "varillas" in a:
        for n, ins in a["varillas"]:
            filas.append({"parte": "varillas", "clave": ins, "descripcion": _descripcion(ins), "cantidad": n, "detalle": ""})
    else:
        for n, ins in a["sup"]:
            filas.append({"parte": "arriba", "clave": ins, "descripcion": _descripcion(ins), "cantidad": n, "detalle": "arriba"})
        for n, ins in a["inf"]:
            filas.append({"parte": "abajo", "clave": ins, "descripcion": _descripcion(ins), "cantidad": n, "detalle": "abajo"})
    for sep, ins in a.get("anillos", ()):
        filas.append({"parte": "anillos", "clave": ins, "descripcion": _descripcion(ins), "cantidad": 1, "detalle": f"@{sep:g} cm"})
    return filas


def definicion_del_elemento(clave: str) -> dict[str, Any] | None:
    """La definición del elemento para la tarjeta: medidas, armado, cimbra, conceptos del catálogo y camino de colado."""
    e = _POR_CLAVE.get(clave)
    if e is None:
        return None
    from obractrl.domain.cuantificacion.correcciones_de_trabes import (
        correcciones_de_elemento_lineal,
    )

    zapata = e["tipo"] == TIPO_ZAPATA
    columna = e["tipo"] == TIPO_COLUMNA
    modos = ["pieza"] if (zapata or columna) else ["ml", "pieza"]
    cat_nombre, sub_nombre = _nombres_de_clasificacion(e["categoria"], e["subcategoria"])
    return {
        "clave": e["clave"],
        "nombre": e["nombre"],
        "tipo": e["tipo"],
        "se_mide_por": _se_mide_por(e),
        "concepto": _concepto_principal(e),
        "categoria": {"clave": e["categoria"], "nombre": cat_nombre[1]},
        "subcategoria": {"clave": e["subcategoria"], "nombre": sub_nombre},
        "seccion": {
            "ancho_cm": float(e["ancho_cm"]),
            "peralte_cm": float(e["peralte_cm"]),
            "largo_cm": float(e["largo_cm"]) if "largo_cm" in e else None,
        },
        "lados_de_cimbra": int(e["lados"]),
        "modos": modos,
        "modo_por_defecto": modos[0],
        "largo_por_defecto_m": LARGO_DE_PIEZA_POR_DEFECTO_M if e["tipo"] == TIPO_LINEAL else None,
        "alto_por_defecto_m": float(e["alto_defecto_m"]) if "alto_defecto_m" in e else None,
        "armado": _descripcion_de_armado(e),
        "concreto": {"clave": e["concreto"], "descripcion": _descripcion(e["concreto"])},
        "alambre": {"clave": e["alambre"], "descripcion": _descripcion(e["alambre"])},
        "cimbra": [
            {"clave": c, "descripcion": _descripcion(c), "consumo": como, "cantidad": q} for c, como, q in e["cimbra"]
        ],
        "conceptos_del_catalogo": [
            {
                "clave": c["clave"],
                "descripcion": c["descripcion"],
                "unidad": _unidad_visible(c["unidad"]),
                "toma": list(c["toma"]),
                "hasta_m": c["hasta_m"],
                "fuente": c["linea_catalogo"],
            }
            for c in e["catalogo"]
        ],
        "camino_de_colado_y_cimbra": camino_de_colado_y_cimbra(clave),
        "usado_en": [{"clave": k, "cantidad": q} for k, q in e.get("usado_en", ())],
        "usos_total": int(e.get("usos_total", 0)),
        "pendientes": [dict(p) for p in _pendientes_de(e)],
        "correcciones_de_fabrica": [
            {
                "concepto_clave": p["concepto_clave"],
                "resumen": p["resumen"],
                "cambios": p["detalle"]["cambios"],
                "motivos": p["detalle"]["motivos"],
            }
            for p in correcciones_de_elemento_lineal(clave)
        ],
    }


def _nombres_de_clasificacion(categoria: str, subcategoria: str) -> tuple[tuple[str, str], str]:
    for c in CATEGORIAS:
        if c["clave"] == categoria:
            for s in c["subcategorias"]:
                if s["clave"] == subcategoria:
                    return (c["clave"], c["nombre"]), str(s["nombre"])
    return (categoria, categoria), subcategoria


def _pendientes_de(e: dict[str, Any]) -> tuple[dict[str, str], ...]:
    if e["tipo"] == TIPO_ZAPATA:
        return (
            {
                "clave": "Q57",
                "texto": "El título de EST-03020 incluye un dado de 20×20×60 que el concepto no trae (0.024 m³ de concreto y unos 2.4 m de varilla): el dado NO se incluye aquí.",
            },
            {"clave": "Q58", "texto": "Las zapatas ZA-1 y ZA-2 quedan fuera: el catálogo no da separación ni capas."},
        )
    if e["tipo"] == TIPO_COLUMNA:
        return (
            {
                "clave": "Q61",
                "texto": "EST-11011 y EST-12011 llegan hasta 6.00 m y no traen mano de obra de acero; el destajo MOE-20210 va en el concepto. El capitel queda fuera.",
            },
            {"clave": "Q60", "texto": PENDIENTES[-1]["texto"]},
        )
    return PENDIENTES


# --------------------------------------------------------------------------------------------------------------
# Camino para registrar después el colado y cimbra (Q51) y el destajo por ml (Q52): NO se ejecuta
# --------------------------------------------------------------------------------------------------------------


def camino_de_colado_y_cimbra(clave: str) -> dict[str, Any] | None:
    """Cómo se registraría el concepto nuevo de colado y cimbra del elemento y su destajo por ml. **No registra nada.**

    Solo las trabes, contratrabes y nervaduras lo necesitan: su acero ya tiene concepto en el catálogo (el material auxiliar
    AUX-xxxxx), pero su concreto y su cimbra los paga la losa. La Z-1 y la C-1 ya tienen concepto de colado en el catálogo.
    El borrador deja `clave_propuesta` vacía (la clave EJ-7xx del mockup no se crea) y el destajo sin definir.
    """
    e = _POR_CLAVE.get(clave)
    if e is None:
        return None
    if e["tipo"] != TIPO_LINEAL:
        return {
            "estado": "no_aplica",
            "motivo": "El concepto del catálogo ya paga el colado del elemento.",
            "borrador": None,
            "mano_de_obra": {"estado": "en_el_concepto_del_catalogo", "destajo": None},
            "preguntas": [],
        }
    consumos = [{"clave": c, "descripcion": _descripcion(c), "consumo": como, "cantidad": q} for c, como, q in e["cimbra"]]
    return {
        "estado": "por_registrar",
        "motivo": (
            "El catálogo paga el concreto y la cimbra de este elemento dentro de la losa por m². Un concepto nuevo de colado y "
            "cimbra por ml lo registrará Costos como «propuesto»: sin precio y pendiente de Control de obra."
        ),
        "borrador": {
            "unidad": "ml",
            "toma": {"concreto": True, "cimbra": bool(e["lados"])},
            "clave_propuesta": None,
            "descripcion_sugerida": f"Colado y cimbra de {e['nombre'].rstrip('.')}",
            "concreto": {"clave": e["concreto"], "descripcion": _descripcion(e["concreto"])},
            "cimbra": consumos,
            "ruta": "POST /elementos-parametricos/{elemento_id}/conceptos con unidad, toma, clave_propuesta y descripcion",
        },
        "mano_de_obra": {
            "estado": "sin_destajo_por_ml",
            "destajo": None,
            "nota": "El catálogo de trabajos no trae destajo para trabes, contratrabes ni nervaduras. El destajo por ml se agrega después en el APU del concepto; no se inventa.",
        },
        "preguntas": ["Q51", "Q52"],
    }


# --------------------------------------------------------------------------------------------------------------
# Cálculo
# --------------------------------------------------------------------------------------------------------------


def _validar_entrada(e: dict[str, Any], i: EntradaElementoEstructural) -> tuple[Modo, float]:
    """Valida y devuelve el modo efectivo y la longitud de cálculo (m) del elemento."""
    if not (i.cantidad > 0) or not math.isfinite(i.cantidad):
        raise ErrorDeElementoEstructural("La cantidad debe ser mayor que cero.")
    if i.modo not in ("ml", "pieza"):
        raise ErrorDeElementoEstructural("El modo es «ml» o «pieza».")
    if i.anclaje_cm is not None:
        if e["tipo"] == TIPO_ZAPATA or (e["tipo"] == TIPO_LINEAL and i.modo != "pieza"):
            raise ErrorDeElementoEstructural("El anclaje es de la varilla de una pieza (trabe por pieza o columna): por ml y en la zapata no aplica.")
        if not (0 <= i.anclaje_cm <= 500) or not math.isfinite(i.anclaje_cm):
            raise ErrorDeElementoEstructural("El anclaje va en centímetros por extremo, de 0 a 500.")
    if not (0 <= i.desperdicio_concreto_pct <= 50):
        raise ErrorDeElementoEstructural("El desperdicio de concreto va de 0 a 50 %.")
    if e["tipo"] == TIPO_LINEAL:
        if i.alto_m is not None:
            raise ErrorDeElementoEstructural("La altura es de la columna; una trabe se mide por ml o por pieza de largo.")
        if i.modo == "ml":
            if i.largo_m is not None:
                raise ErrorDeElementoEstructural("Por ml no hay largo de pieza: pide la cantidad en metros.")
            if i.zonas_de_anillo:
                raise ErrorDeElementoEstructural("Las zonas de anillo son de la pieza; por ml el anillo lleva una sola separación.")
            return "ml", 1.0
        largo = LARGO_DE_PIEZA_POR_DEFECTO_M if i.largo_m is None else i.largo_m
        if not (0 < largo <= 30):
            raise ErrorDeElementoEstructural("El largo de la pieza va en metros, mayor que cero y hasta 30.")
        return "pieza", largo
    if i.modo != "pieza":
        raise ErrorDeElementoEstructural(f"{e['clave']} se mide por pieza.")
    if i.largo_m is not None:
        raise ErrorDeElementoEstructural("La zapata y la columna no tienen largo de pieza: la columna se pide por altura.")
    if e["tipo"] == TIPO_ZAPATA:
        if i.alto_m is not None or i.zonas_de_anillo:
            raise ErrorDeElementoEstructural("La zapata no tiene altura de columna ni zonas de anillo: su medida es la de la zapata.")
        return "pieza", 1.0
    alto = float(e["alto_defecto_m"]) if i.alto_m is None else i.alto_m
    if not (0 < alto <= 30):
        raise ErrorDeElementoEstructural("La altura de la columna va en metros, mayor que cero y hasta 30.")
    return "pieza", alto


def _varilla(clave: str) -> Varilla:
    x = _insumo(clave)
    if x.get("numero") is None or not x.get("peso_kg_m"):
        raise ErrorDeElementoEstructural(f"El insumo {clave} no es una varilla con número y peso.")
    return Varilla(clave, int(x["numero"]), float(x["largo_m"] or 12.0), float(x["peso_kg_m"]))


def _peso_del_anillo(clave: str) -> float:
    x = _insumo(clave)
    if not x.get("peso_kg_m"):
        raise ErrorDeElementoEstructural(f"El anillo {clave} no trae peso por metro.")
    return float(x["peso_kg_m"])


def _cimbra_de(e: dict[str, Any]) -> list[ConsumoDeCimbra]:
    return [ConsumoDeCimbra(c, por_m2=q) if como == "por_m2" else ConsumoDeCimbra(c, por_ml=q) for c, como, q in e["cimbra"]]


def _entrada_de_receta(e: dict[str, Any], i: EntradaElementoEstructural, forma: str, largo: float) -> EntradaRecetaAcero:
    a = e["armado"]
    columna = e["tipo"] == TIPO_COLUMNA
    if a["tipo"] == "armex":
        x = _insumo(a["armex"])
        return EntradaRecetaAcero(
            forma=forma,  # type: ignore[arg-type]
            ancho_cm=float(e["ancho_cm"]),
            peralte_cm=float(e["peralte_cm"]),
            longitud_m=None if forma == "ml" else largo,
            lados_cimbra=int(e["lados"]),
            armex=Armex(a["armex"], float(x["largo_m"] or 6.0), None),
            alambre_kg_ml=float(a["alambre_kg_ml"]),
            cimbra=_cimbra_de(e),
            cantidad=i.cantidad,
            drivers=i.drivers,
        )
    if columna:
        grupos = [GrupoDeVarillas(n, _varilla(ins), "") for n, ins in a["varillas"]]
    else:
        grupos = [GrupoDeVarillas(n, _varilla(ins), "arriba") for n, ins in a["sup"]] + [
            GrupoDeVarillas(n, _varilla(ins), "abajo") for n, ins in a["inf"]
        ]
    if i.zonas_de_anillo:
        ins_anillo = a["anillos"][0][1]
        zonas = [ZonaDeAnillo(sep, _peso_del_anillo(ins_anillo), largo_zona, ins_anillo) for largo_zona, sep in i.zonas_de_anillo]
    else:
        zonas = [ZonaDeAnillo(sep, _peso_del_anillo(ins), None, ins) for sep, ins in a["anillos"]]
    return EntradaRecetaAcero(
        forma=forma,  # type: ignore[arg-type]
        ancho_cm=float(e["ancho_cm"]),
        peralte_cm=float(e["peralte_cm"]),
        longitud_m=None if forma == "ml" else largo,
        lados_cimbra=int(e["lados"]),
        varillas=grupos,
        anillos=zonas,
        gancho_cm=float(a["gancho_cm"]),
        recubrimiento_cm=float(a["rec_cm"]),
        factor_anillo=float(a.get("factor_anillo", 1.0)),
        alambre_por_amarre_m=float(a.get("am_l", 0.3)),
        alambre_peso_kg_m=_PESO_ALAMBRE_RECOCIDO_KG_M,
        alambre_kg_ml=float(a["alambre_kg_ml"]) if "alambre_kg_ml" in a else None,
        cimbra=_cimbra_de(e),
        cantidad=i.cantidad,
        drivers=i.drivers,
        anclaje_cm=i.anclaje_cm,
    )


def anclaje_de(receta: dict[str, Any] | None, i: EntradaElementoEstructural, e: dict[str, Any]) -> dict[str, Any]:
    """El anclaje de la varilla por extremo: lo **sugerido** (40 diámetros por extremo, los drivers) y, si se capturó uno, si cumple.

    Es una sugerencia (D6): el elemento no rechaza un valor menor, avisa. No aplica por ml, ni a la zapata, ni al armex."""
    sugerida_d = max(i.drivers.puntas_inferior_diametros, i.drivers.puntas_superior_diametros)
    base: dict[str, Any] = {
        "aplica": False,
        "sugerido_diametros": sugerida_d,
        "capturado_cm": i.anclaje_cm,
        "cumple": None,
        "grupos": [],
        "mensaje": "El anclaje de la varilla es de una pieza (trabe por pieza o columna): por ml no aplica.",
    }
    if receta is None or not receta["varillas"] or (e["tipo"] == TIPO_LINEAL and i.modo != "pieza"):
        return base
    grupos: dict[int, dict[str, Any]] = {}
    for v in receta["varillas"]:
        if v["numero"] in grupos:
            continue
        sugerido_cm = sugerida_d * v["diametro_m"] * 100
        grupos[v["numero"]] = {
            "numero": v["numero"],
            "clave": v["clave"],
            "diametro_cm": v["diametro_m"] * 100,
            "sugerido_cm": sugerido_cm,
            "cumple": None if i.anclaje_cm is None else i.anclaje_cm + _EPS >= sugerido_cm,
        }
    lista = sorted(grupos.values(), key=lambda g: g["numero"])
    sugeridos = ", ".join(f"{g['sugerido_cm']:.0f} cm en la varilla no. {g['numero']}" for g in lista)
    base.update(aplica=True, grupos=lista)
    if i.anclaje_cm is None:
        base["mensaje"] = (
            f"Sugerido: {sugerida_d:g} diámetros por extremo ({sugeridos}). Capture el anclaje para saber si cumple; "
            "mientras tanto el cálculo usa lo sugerido."
        )
        return base
    cumple = all(g["cumple"] for g in lista)
    base["cumple"] = cumple
    base["mensaje"] = (
        f"El anclaje de {i.anclaje_cm:g} cm por extremo cumple lo sugerido ({sugerida_d:g} diámetros: {sugeridos})."
        if cumple
        else f"El anclaje de {i.anclaje_cm:g} cm por extremo NO cumple lo sugerido ({sugerida_d:g} diámetros: {sugeridos}); "
        "es una sugerencia: el cálculo usa el valor capturado."
    )
    return base


def _fila(parte: str, clave: str, unidad: str, por_unidad: float, cantidad: float, **extra: Any) -> dict[str, Any]:
    comprar = float(math.ceil(por_unidad * cantidad - _EPS)) if unidad == "pza" else None
    return {
        "parte": parte,
        "clave": clave,
        "descripcion": _descripcion(clave),
        "unidad": _unidad_visible(unidad),
        "por_unidad": por_unidad,
        "total": por_unidad * cantidad,
        "a_comprar": comprar,
        **{"kg": None, "ml": None, "detalle": ""},
        **extra,
    }


def _insumos_de_receta(e: dict[str, Any], r: dict[str, Any], cantidad: float, desp_concreto: float, largo: float, forma: str) -> list[dict[str, Any]]:
    filas: list[dict[str, Any]] = []
    if r["armex"]:
        x = r["armex"]
        filas.append(_fila("acero", x["clave"], "pza", x["piezas_comerciales"], cantidad, ml=x["ml"], detalle="armex"))
    por_clave: dict[str, dict[str, float]] = {}
    for v in r["varillas"]:
        acum = por_clave.setdefault(v["clave"], {"pza": 0.0, "ml": 0.0, "kg": 0.0, "n": 0.0})
        acum["pza"] += v["piezas_comerciales"]
        acum["ml"] += v["ml"]
        acum["kg"] += v["kg"] or 0.0
        acum["n"] += v["varillas"]
    for clave, a in por_clave.items():
        filas.append(_fila("acero", clave, "pza", a["pza"], cantidad, ml=a["ml"], kg=a["kg"], detalle=f"{int(a['n'])} varillas"))
    if r["anillos"]:
        for z in r["anillos"]["zonas"]:
            clave = z["clave"] or "anillo"
            x = INSUMOS.get(clave, {})
            detalle = f"{z['pza']:.2f} anillos @{z['sep_cm']:g} cm"
            if x.get("unidad") == "pza" and x.get("peso_kg_m"):
                # El anillo se hace con varilla del catálogo (T-14, T-15…): se compra por pieza, no por kg.
                pza = z["kg"] / float(x["peso_kg_m"]) / float(x.get("largo_m") or 12.0)
                filas.append(_fila("estribos", clave, "pza", pza, cantidad, kg=z["kg"], detalle=detalle))
            else:
                filas.append(_fila("estribos", clave, "kg", z["kg"], cantidad, kg=z["kg"], detalle=detalle))
    if r["alambre"]["kg"] > 0:
        filas.append(_fila("alambre", e["alambre"], "kg", r["alambre"]["kg"], cantidad))
    filas.extend(_insumos_de_concreto_y_cimbra(e, r["cimbra"], cantidad, desp_concreto, largo, forma))
    return filas


def _concreto_m3(e: dict[str, Any], desp: float, largo: float) -> float:
    d = 1 + desp / 100
    a = float(e["ancho_cm"]) / 100
    p = float(e["peralte_cm"]) / 100
    if e["tipo"] == TIPO_ZAPATA:
        return float(e["largo_cm"]) / 100 * a * p * d
    return a * p * largo * d


def _insumos_de_concreto_y_cimbra(
    e: dict[str, Any], cimbra: dict[str, Any], cantidad: float, desp: float, largo: float, forma: str
) -> list[dict[str, Any]]:
    filas = [
        _fila("concreto", e["concreto"], "m3", _concreto_m3(e, desp, largo), cantidad, detalle=f"con {desp:g} % de desperdicio")
    ]
    for c in cimbra["consumos"]:
        unidad = str(_insumo(c["clave"])["unidad"])
        filas.append(_fila("cimbra", c["clave"], unidad, c["cantidad"], cantidad))
    return filas


def _zapata(e: dict[str, Any], i: EntradaElementoEstructural) -> dict[str, Any]:
    """Z-1: parrilla de varilla en los dos sentidos (`muestraZap`)."""
    a = e["armado"]
    d = i.drivers
    largo = float(e["largo_cm"]) / 100
    ancho = float(e["ancho_cm"]) / 100
    peralte = float(e["peralte_cm"]) / 100
    rec = float(a["rec_cm"]) / 100
    sep = max(0.03, float(a["sep_cm"]) / 100)
    gancho = float(a["gancho_cm"]) / 100
    capas = int(a["capas"])
    n_a = max(2, math.floor((ancho - 2 * rec) / sep + _EPS) + 1)
    n_l = max(2, math.floor((largo - 2 * rec) / sep + _EPS) + 1)
    f = 1 + d.desperdicio_acero_pct / 100
    ml = (n_a * (largo - 2 * rec + 2 * gancho) + n_l * (ancho - 2 * rec + 2 * gancho)) * capas * f
    v = _varilla(a["varilla"])
    k = int(e["lados"])
    m2 = (2 * (largo + ancho) if k >= 4 else (2 * largo + ancho if k == 3 else (2 * largo if k == 2 else 0.0))) * peralte
    cimbra = {
        "m2": m2,
        "lados": k,
        "consumos": [
            {"clave": c, "cantidad": (q * m2) if como == "por_m2" else q}
            for c, como, q in e["cimbra"]
        ],
    }
    q = i.cantidad
    filas = [
        _fila("acero", v.clave, "pza", ml / v.largo_m, q, ml=ml, kg=ml * v.peso_kg_m, detalle=f"parrilla de {n_a} × {n_l} varillas"),
        _fila("alambre", e["alambre"], "kg", float(a["alambre_kg"]), q, detalle="del catálogo, por pieza"),
        *_insumos_de_concreto_y_cimbra(e, cimbra, q, i.desperdicio_concreto_pct, 1.0, "pieza"),
    ]
    return {
        "receta": None,
        "parrilla": {"varillas_por_sentido": [n_a, n_l], "ml": ml, "capas": capas, "separacion_cm": float(a["sep_cm"])},
        "cimbra": cimbra,
        "insumos": filas,
        "acero_kg": ml * v.peso_kg_m,
        "advertencias": [
            "El dado de 20×20×60 que menciona el título de EST-03020 no se incluye (Q57): la categoría Dados se construye después."
        ],
    }


def _conciliar(e: dict[str, Any], insumos: list[dict[str, Any]], unidad_de_calculo: str, divisor_ml: float, alto_m: float | None) -> list[dict[str, Any]]:
    """Contrasta el elemento con cada concepto del catálogo que lo paga, por unidad del concepto y solo las partes que toma."""
    salida: list[dict[str, Any]] = []
    for c in e["catalogo"]:
        unidad_concepto = c["unidad"]
        # De cantidad por unidad de cálculo a cantidad por unidad del concepto.
        if unidad_concepto in ("ml", "m"):
            factor = 1.0 / divisor_ml if unidad_de_calculo in ("pza",) and e["tipo"] != TIPO_ZAPATA else 1.0
            sobre = "por metro" if unidad_de_calculo == "ml" else f"por metro (de la pieza de {divisor_ml:.2f} m)"
        else:
            factor = 1.0
            sobre = "por pieza"
        toma = set(c["toma"])
        elemento: dict[str, float] = {}
        for f in insumos:
            if f["parte"] not in _PARTES_DE_LA_TOMA or _PARTES_DE_LA_TOMA[f["parte"]] not in toma:
                continue
            elemento[f["clave"]] = elemento.get(f["clave"], 0.0) + f["por_unidad"] * factor
        composicion = [
            FilaDeComposicion(
                clave=fila[0], cantidad=fila[3], descripcion=fila[1], unidad=fila[2], es_mano_de_obra=fila[4] == "Contrato", costo=fila[5]
            )
            for fila in c["filas"]
        ]
        comparado = comparar_con_concepto(elemento, composicion, descripciones={k: _descripcion(k) for k in elemento})
        avisos: list[str] = []
        if c["hasta_m"] is not None and alto_m is not None and alto_m > c["hasta_m"] + _EPS:
            avisos.append(
                f"La altura de {alto_m:.2f} m pasa del escalón del catálogo ({c['hasta_m']:.2f} m): ese concepto no la paga."
            )
        salida.append(
            {
                "concepto": {
                    "clave": c["clave"], "descripcion": c["descripcion"], "unidad": _unidad_visible(unidad_concepto),
                    "toma": list(c["toma"]), "hasta_m": c["hasta_m"], "fuente": c["linea_catalogo"],
                },
                "sobre": sobre,
                "filas": comparado["filas"],
                "mano_de_obra": comparado["mano_de_obra"],
                "resumen": comparado["resumen"],
                "coincide": comparado["coincide"],
                "fuente_de_las_filas": sorted({fila[6] for fila in c["filas"]}, key=_orden_de_linea),
                "avisos": avisos,
            }
        )
    return salida


def _orden_de_linea(ref: str) -> tuple[str, int]:
    archivo, _, n = ref.rpartition(":")
    return archivo, int(n)


_PARTES_DE_LA_TOMA = {"acero": "acero", "estribos": "acero", "alambre": "acero", "concreto": "concreto", "cimbra": "cimbra"}
"""A qué parte del concepto (acero, concreto, cimbra) pertenece cada parte de la receta."""


def calcular_elemento(i: EntradaElementoEstructural) -> dict[str, Any]:
    """La receta, los insumos, la cimbra y la conciliación del elemento, por ml o por pieza, con totales para `cantidad`."""
    e = _POR_CLAVE.get(i.clave)
    if e is None:
        raise ErrorDeElementoEstructural(f"No hay un elemento {i.clave} en la familia de estructura de la biblioteca.")
    modo, largo = _validar_entrada(e, i)
    advertencias: list[str] = []
    receta: dict[str, Any] | None = None
    parrilla: dict[str, Any] | None = None
    if e["tipo"] == TIPO_ZAPATA:
        z = _zapata(e, i)
        insumos, cimbra, parrilla, acero_kg = z["insumos"], z["cimbra"], z["parrilla"], z["acero_kg"]
        advertencias += z["advertencias"]
        unidad = "pza"
        divisor = 1.0
    else:
        forma = "ml" if modo == "ml" else ("castillo" if e["tipo"] == TIPO_COLUMNA else "pieza")
        try:
            receta = calcular_receta_acero(_entrada_de_receta(e, i, forma, largo))
        except ErrorDeRecetaAcero as err:
            raise ErrorDeElementoEstructural(str(err)) from err
        insumos = _insumos_de_receta(e, receta, i.cantidad, i.desperdicio_concreto_pct, largo, forma)
        cimbra = receta["cimbra"]
        acero_kg = receta["acero_kg"]
        advertencias += list(receta["advertencias"])
        unidad = "ml" if modo == "ml" else "pza"
        divisor = largo
    fila_concreto = next(f for f in insumos if f["parte"] == "concreto")
    anclaje = anclaje_de(receta, i, e)
    if anclaje["cumple"] is False:
        advertencias.append(anclaje["mensaje"])
    alto = largo if e["tipo"] == TIPO_COLUMNA else None
    conciliacion = _conciliar(e, insumos, unidad, divisor, alto)
    for c in conciliacion:
        advertencias += c["avisos"]
    if e["tipo"] == TIPO_LINEAL and modo == "pieza":
        advertencias.append(
            f"Por pieza se compara contra el catálogo por metro (la pieza de {largo:.2f} m entre su largo): el corte y las puntas "
            "de anclaje la separan de la cifra por ml."
        )
    return {
        "clave": e["clave"],
        "nombre": e["nombre"],
        "tipo": e["tipo"],
        "modo": modo,
        "unidad": unidad,
        "longitud_m": largo if e["tipo"] != TIPO_ZAPATA else None,
        "cantidad": i.cantidad,
        "seccion": {
            "ancho_cm": float(e["ancho_cm"]),
            "peralte_cm": float(e["peralte_cm"]),
            "largo_cm": float(e["largo_cm"]) if "largo_cm" in e else None,
        },
        "concreto": {
            "clave": fila_concreto["clave"],
            "descripcion": fila_concreto["descripcion"],
            "m3": fila_concreto["por_unidad"],
            "desperdicio_pct": i.desperdicio_concreto_pct,
        },
        "acero_kg": acero_kg,
        "cimbra": {
            "m2": cimbra["m2"],
            "lados": cimbra["lados"],
            "consumos": [{**c, "descripcion": _descripcion(c["clave"])} for c in cimbra["consumos"]],
        },
        "receta_acero": receta,
        "anclaje": anclaje,
        "parrilla": parrilla,
        "insumos": insumos,
        "mano_de_obra": {
            "estado": "sin_mano_de_obra",
            "nota": (
                "El elemento no calcula mano de obra. Su destajo, si el catálogo lo trae, va en el concepto y se lista en la "
                "conciliación; para trabes, contratrabes y nervaduras el catálogo no trae destajo por ml (Q52)."
            ),
        },
        "conciliacion": conciliacion,
        "camino_de_colado_y_cimbra": camino_de_colado_y_cimbra(e["clave"]),
        "advertencias": advertencias,
    }
