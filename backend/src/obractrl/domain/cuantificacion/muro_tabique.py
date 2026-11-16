"""Muros de tabique, aparejos y piso de petatillo (plan de elementos de muro, Ola 3, lane 3C; M-92, M-103 a M-107, M-133 a M-136).

Siete elementos en la categoría **Muros › Muros de tabique** y uno en **Pisos › Pisos de petatillo**, todos con la **misma pieza** de
tabique (PET-00001, 14 × 6 × 26 cm: ancho × alto × largo visible), **junta de 2 cm**, **12 % de desperdicio de pieza y 5 % de mezcla**
(sin el driver de 5 % sobre m²: el desperdicio ya va dentro del elemento, M-105) y mezcla cemento-arena 1:4 (MEZ-07010):

=========  ==============================================  ==================  =========================================
Clave      Aparejo                                          Espesor real        Concepto
=========  ==============================================  ==================  =========================================
EST-02010  a soga (al hilo)                                 14 cm               del catálogo; nivel ≥ 3 paga EST-02011
EST-02020  soga de 14 + junta de 1 cm + canto de 6          21 cm               del catálogo (MOE-02013)
AUX-04010  a soga, material auxiliar sin destajo            14 cm               del catálogo (material)
EST-02005  capuchino (de canto)                             6 cm                **nuevo propuesto**, clave provisional
EST-02030  a tizón                                          26 cm               **nuevo propuesto**, clave provisional
EST-02040  tizón + soga                                     42 cm               **nuevo propuesto**, clave provisional
EST-02050  sardinel parado (por ml de una hilada)           6 cm                **nuevo propuesto**, clave provisional
ACA-02090  petatillo (espina de pez), piso por m²           6 cm                **nuevo propuesto**, clave provisional
=========  ==============================================  ==================  =========================================

Reglas que vienen de las respuestas del usuario (Ola 3, lane 3C):

- El muro **EST-02020** («21 cm») es, en planta, un tabique de 14 cm de espesor + una junta de **1 cm** + un tabique de 6 cm de
  espesor (14 + 1 + 6 = 21). Las piezas siguen siendo 14×6×26 y las juntas de cada hilera siguen en 2 cm; solo la junta **entre las
  dos hileras** es de 1 cm. La hilera de 14 es de soga (6 cm de alto) y la de 6 es de canto (14 cm de alto). El cálculo sale con esa
  geometría y **se muestra la diferencia contra el catálogo** (86 pza y 0.0939 m³ por m²): el catálogo no se edita; si hace falta
  se propone una nueva versión del concepto (`propuestas_de_actualizacion_de_apu`).
- **EST-02010 / EST-02011**: el elemento es uno solo y el concepto se elige por el nivel del plano: nivel ≥ 3 paga EST-02011 (la azotea
  de una casa de dos plantas es el tercer nivel; Q69). Se usa la infraestructura de contextos de 2A (`Contexto`). EST-02020 no tiene
  variante de 3.er nivel (Q98).
- Los aparejos que el catálogo no trae (capuchino, tizón, muro de 42, sardinel y petatillo) son **conceptos nuevos propuestos**, con
  clave **provisional**, sin destajo y sin precio (Q74, Q99); el usuario revisa claves y nombres con la tabla `tabla_de_revision`.
- **Sardinel**: pieza parada, por metro lineal de una hilada; hay varios tipos que se revisan más adelante, así que el **tipo** es un
  parámetro con un solo valor hoy (`parado`); no se inventan variantes (Q102).
- **Petatillo**: piezas planas de 26 × 14 en espina de pez, por m², con una cama en **0 cm editable** y sin mortero inventado (Q103).
- **Herramienta y equipo** (andamios): sección opcional, vacía y **sin precios** (M-134).

Función pura, sin base de datos.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from obractrl.domain.cuantificacion.comparacion_con_catalogo import (
    FilaDeComposicion,
    comparar_con_concepto,
    marca_de,
)
from obractrl.domain.cuantificacion.conceptos_de_elemento import Contexto
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "AVISO_DEL_MORTERO_DE_AUX_04010",
    "CLAVE_MEZCLA",
    "CLAVE_PIEZA",
    "ELEMENTOS_DE_TABIQUE",
    "NIVEL_DEL_TERCER_NIVEL",
    "TIPOS_DE_SARDINEL",
    "AparejoDeTabique",
    "ConceptoDeTabique",
    "ElementoDeTabiqueNoEncontrado",
    "EntradaMuroDeTabique",
    "ErrorDeMuroDeTabique",
    "calcular_muro_de_tabique",
    "categorias_de_biblioteca",
    "claves_de_tabique",
    "concepto_nuevo_de",
    "correcciones_de",
    "definicion_de",
    "propuestas_de_actualizacion_de_apu",
    "tabla_de_revision",
]

CLAVE_PIEZA = "PET-00001"
CLAVE_MEZCLA = "MEZ-07010"
PIEZA_ANCHO_CM = 14.0
PIEZA_ALTO_CM = 6.0
PIEZA_LARGO_CM = 26.0
JUNTA_CM = 2.0
DESPERDICIO_DE_PIEZA_PCT = 12.0
DESPERDICIO_DE_MEZCLA_PCT = 5.0
NIVEL_DEL_TERCER_NIVEL = 3
"""El 3.er nivel cuenta desde la planta baja como nivel 1; la regla «nivel ≥ 3 → EST-02011» es configurable (M-107)."""

TIPOS_DE_SARDINEL: dict[str, str] = {
    "parado": "Parado sobre su extremo: cara de 14 × 26 cm a la vista y 6 cm de espesor",
}
"""Hay varios tipos de sardinel y se revisan más adelante (Q102): hoy solo existe el que el mockup interpretó; no se inventan más."""

AVISO_DEL_MORTERO_DE_AUX_04010 = (
    "El texto del catálogo de AUX-04010 dice «mezcla mortero-arena 1:5», pero su composición usa MEZ-07010 (cemento-arena 1:4). "
    "El elemento calcula con la mezcla 1:4 de la composición; Costos debe decidir si corrige el texto o la composición."
)

_MEZCLA_COMPUESTA: tuple[tuple[str, str, str, float, str], ...] = (
    ("ADH-00005", "CEMENTO SACO DE 50 KG", "bts", 7.28, "ANALISIS_DE_BASICOS_COMPUESTOS:261"),
    ("PET-00015", "ARENA DE RIO 14 M3", "serv", 0.078571, "ANALISIS_DE_BASICOS_COMPUESTOS:262"),
    ("SER-00003", "PIPA 10000", "serv", 0.0185, "ANALISIS_DE_BASICOS_COMPUESTOS:263"),
)
"""Lo que lleva 1 m³ de MEZ-07010 según el catálogo (clave, descripción, unidad, cantidad, línea del CSV)."""

_DESCRIPCIONES = {CLAVE_PIEZA: "TABIQUE", CLAVE_MEZCLA: "MEZCLA CEMENTO-ARENA 1:4"}


class ErrorDeMuroDeTabique(ErrorDeCuantificacion):
    """Un parámetro del muro de tabique que no vale."""


class ElementoDeTabiqueNoEncontrado(ErrorDeMuroDeTabique):
    """No hay un elemento de tabique con esa clave."""


# --- Orientaciones de la pieza ---------------------------------------------------------------------------------------------
# Cada una devuelve (cara visible a lo largo del muro, alto de la hilera, fondo = lo que aporta al espesor), en metros.

_ORIENTACIONES: dict[str, tuple[str, Callable[[float, float, float], tuple[float, float, float]]]] = {
    "soga": ("a soga", lambda a, h, ll: (ll, h, a)),
    "tizon": ("a tizón", lambda a, h, ll: (a, h, ll)),
    "canto": ("de canto", lambda a, h, ll: (ll, a, h)),
    "parado": ("parado", lambda a, h, ll: (a, ll, h)),
    "plana": ("plana", lambda a, h, ll: (ll, a, h)),
}


@dataclass(frozen=True, slots=True)
class ConceptoDeTabique:
    """Un concepto que paga el elemento. `nivel_desde` y `nivel_hasta_antes_de` arman su `Contexto` (2A) con la regla de nivel."""

    clave: str
    etiqueta: str
    descripcion: str
    unidad: str
    destajo: tuple[str, str, str] | None = None
    """Clave, descripción y unidad del destajo del catálogo; `None` = sin destajo."""
    nuevo: bool = False
    """Concepto que el catálogo no trae: propuesto, pendiente de autorizar por Control de obra, con clave provisional."""
    tercer_nivel: bool = False
    """`True` = paga desde el nivel de la regla de 3.er nivel; `False` en el concepto base de un elemento con dos conceptos."""
    con_variante_de_nivel: bool = False


@dataclass(frozen=True, slots=True)
class AparejoDeTabique:
    clave: str
    nombre: str
    nombre_nominal: str
    nominal_cm: int | None
    categoria: tuple[str, str]
    subcategoria: tuple[str, str]
    medida: str
    """`m2` o `ml`."""
    aparejo: str
    aparejo_largo: str
    aparejo_texto: str
    planta_nota: str
    hiladas: tuple[tuple[float, tuple[str, ...]], ...]
    """(peso, orientaciones de las hileras): el peso es la fracción de la altura que ocupa ese tipo de hilada."""
    conceptos: tuple[ConceptoDeTabique, ...]
    junta_entre_hileras_cm: float | None = None
    """Junta entre las hileras de una misma hilada; `None` = la misma junta de 2 cm."""
    cama_cm: float | None = None
    con_tipo: bool = False
    fuente: str = ""
    avisos_de_catalogo: tuple[str, ...] = ()
    catalogo: tuple[tuple[str, tuple[tuple[str, float, bool, float | None, str], ...]], ...] = ()
    """La composición real de cada concepto del catálogo: (concepto, ((insumo, cantidad, es_mano_de_obra, costo, línea del CSV),…))."""
    pendientes: tuple[tuple[str, str], ...] = field(default=())

    @property
    def con_variante_de_nivel(self) -> bool:
        return any(c.con_variante_de_nivel for c in self.conceptos)


_C = "ANALISIS_DE_BASICOS_CONCEPTOS"

_DESTAJO_02010 = ("MOE-02010", "MO MURO DE TABIQUE- HILO", "m2")
_DESTAJO_02012 = ("MOE-02012", "MO MURO DE TABIQUE- HILO 3ER NIVEL", "m2")
_DESTAJO_02013 = ("MOE-02013", "MO MURO 21 DE TABIQUE- APAREJO INGLES", "m2")

_CATALOGO_02010 = (
    ("EST-02010", (
        (CLAVE_PIEZA, 50.0, False, 2.9, f"{_C}:808"),
        (CLAVE_MEZCLA, 0.0447, False, 2058.26, f"{_C}:809"),
        ("MOE-02010", 1.0, True, 150.0, f"{_C}:810"),
    )),
    ("EST-02011", (
        (CLAVE_PIEZA, 50.0, False, 2.9, f"{_C}:811"),
        (CLAVE_MEZCLA, 0.0447, False, 2058.26, f"{_C}:812"),
        ("MOE-02012", 1.0, True, 180.0, f"{_C}:813"),
    )),
)
_CATALOGO_02020 = (
    ("EST-02020", (
        (CLAVE_PIEZA, 86.0, False, 2.9, f"{_C}:814"),
        (CLAVE_MEZCLA, 0.0939, False, 2058.26, f"{_C}:815"),
        ("MOE-02013", 1.0, True, 175.0, f"{_C}:816"),
    )),
)
_CATALOGO_AUX_04010 = (
    ("AUX-04010", (
        (CLAVE_PIEZA, 50.0, False, 2.9, "ANALISIS_DE_BASICOS_COMPUESTOS:137"),
        (CLAVE_MEZCLA, 0.0447, False, 2058.26, "ANALISIS_DE_BASICOS_COMPUESTOS:138"),
    )),
)

_MUROS = ("muros", "Muros")
_TABIQUE = ("tabique", "Muros de tabique")
_PISOS = ("pisos", "Pisos")
_PETATILLO = ("petatillo", "Pisos de petatillo (tabique)")

_TEXTO_NUEVO = (
    "Concepto NUEVO propuesto: el catálogo no trae este aparejo. Se calcula con la pieza 14×6×26, junta de 2 cm, 12 % de pieza y 5 % de "
    "mezcla; sin destajo (pendiente de definir por Costos) y sin precio."
)


def _nuevo(clave: str, descripcion: str, unidad: str = "m2") -> ConceptoDeTabique:
    return ConceptoDeTabique(clave, "Concepto nuevo propuesto (clave provisional)", descripcion, unidad, None, nuevo=True)


_LISTA: tuple[AparejoDeTabique, ...] = (
    AparejoDeTabique(
        clave="EST-02005",
        nombre="Muro capuchino de tabique de canto (7 cm nominal)",
        nombre_nominal="Muro capuchino de 7 cm",
        nominal_cm=7,
        categoria=_MUROS, subcategoria=_TABIQUE, medida="m2",
        aparejo="capuchino (de canto)",
        aparejo_largo="Capuchino (de canto): la pieza se coloca de canto, cara de 26 × 14 cm visible",
        aparejo_texto="colocada de canto: la cara de 26 × 14 cm queda a la vista y el espesor es el de la pieza (6 cm; la imagen del usuario lo nombra de 7 cm).",
        planta_nota="Planta de una hilada de canto: la pieza de 26 cm corre a lo largo del muro y el espesor es de 6 cm.",
        hiladas=((1.0, ("canto",)),),
        conceptos=(_nuevo("EST-02005", "Muro capuchino de tabique rojo recocido de canto (6 cm de espesor real), asentado con mezcla cemento-arena 1:4, acabado común"),),
        fuente=_TEXTO_NUEVO,
    ),
    AparejoDeTabique(
        clave="EST-02010",
        nombre="Muro de tabique 14 cm, a hilo",
        nombre_nominal="Muro de 14 cm a hilo (soga)",
        nominal_cm=14,
        categoria=_MUROS, subcategoria=_TABIQUE, medida="m2",
        aparejo="a soga (al hilo)",
        aparejo_largo="A soga (al hilo): lado de 26 cm visible, tendido",
        aparejo_texto="colocada a soga: el lado de 26 cm queda visible y tendido (6 cm de alto); el espesor del muro es el ancho de la pieza, 14 cm. Las hiladas se traban a media pieza.",
        planta_nota="Planta de dos hiladas consecutivas, de soga: la pieza de 26 cm corre a lo largo del muro y su ancho de 14 cm es el espesor.",
        hiladas=((1.0, ("soga",)),),
        conceptos=(
            ConceptoDeTabique(
                "EST-02010", "Niveles 1 y 2", "Muro de 14 cm de espesor, de tabique rojo recocido, asentado con mezcla cemento-arena 1:4, acabado común",
                "m2", _DESTAJO_02010, con_variante_de_nivel=True,
            ),
            ConceptoDeTabique(
                "EST-02011", "Nivel 3 en adelante", "Muro de 14 cm de espesor 3er nivel, de tabique rojo recocido, asentado con mezcla cemento-arena 1:4, acabado común",
                "m2", _DESTAJO_02012, tercer_nivel=True, con_variante_de_nivel=True,
            ),
        ),
        fuente="EST-02010 y EST-02011 (CATALOGO_DE_MATRICES líneas 177 y 178; composición en ANALISIS_DE_BASICOS_CONCEPTOS); destajos MOE-02010 y MOE-02012 (CATALOGO_DE_TRABAJOS).",
        catalogo=_CATALOGO_02010,
    ),
    AparejoDeTabique(
        clave="EST-02020",
        nombre="Muro de tabique 21 cm (14 + 1 + 6)",
        nombre_nominal="Muro de 21 cm",
        nominal_cm=21,
        categoria=_MUROS, subcategoria=_TABIQUE, medida="m2",
        aparejo="soga de 14 + junta de 1 cm + canto de 6",
        aparejo_largo="Muro de 21 cm: hilera a soga de 14 cm, junta de 1 cm y hilera de canto de 6 cm",
        aparejo_texto="en planta, un tabique de 14 cm de espesor (a soga, 6 cm de alto), una junta de 1 cm y un tabique de 6 cm de espesor (de canto, 14 cm de alto): 14 + 1 + 6 = 21 cm. Las piezas son 14×6×26 y las juntas de cada hilera siguen en 2 cm; solo la junta entre las dos hileras es de 1 cm.",
        planta_nota="Planta de la hilada: soga de 14 cm, junta de 1 cm y canto de 6 cm = 21 cm. El catálogo lo llama «aparejo inglés» (MOE-02013).",
        hiladas=((1.0, ("soga", "canto")),),
        junta_entre_hileras_cm=1.0,
        conceptos=(
            ConceptoDeTabique(
                "EST-02020", "Muro de 21 cm (el catálogo no trae variante de 3er nivel)",
                "Muro de 21 cm de espesor, de tabique rojo recocido, asentado con mezcla cemento-arena 1:4, acabado común",
                "m2", _DESTAJO_02013,
            ),
        ),
        fuente="EST-02020 (CATALOGO_DE_MATRICES línea 179; composición en ANALISIS_DE_BASICOS_CONCEPTOS); destajo MOE-02013 (CATALOGO_DE_TRABAJOS).",
        catalogo=_CATALOGO_02020,
        pendientes=(
            (
                "Q97",
                "EST-02020 se calcula como tabique de 14 + junta de 1 cm + tabique de 6 (14 + 1 + 6 = 21 cm), la geometría que confirmó el usuario. "
                "La diferencia contra el catálogo (86 pza y 0.0939 m³ por m²) se muestra en la conciliación y el catálogo no se edita: el usuario "
                "aceptó el cálculo del elemento y la corrección se propone por defecto como nueva versión del concepto (la autoriza Control de obra).",
            ),
            ("Q98", "EST-02020 no tiene variante de 3er nivel: el usuario la descartó («no de momento»)."),
        ),
    ),
    AparejoDeTabique(
        clave="EST-02030",
        nombre="Muro de tabique a tizón (28 cm nominal)",
        nombre_nominal="Muro a tizón de 28 cm",
        nominal_cm=28,
        categoria=_MUROS, subcategoria=_TABIQUE, medida="m2",
        aparejo="a tizón",
        aparejo_largo="A tizón: lado corto de 14 cm visible, la pieza atraviesa el muro",
        aparejo_texto="colocada a tizón: la cara corta de 14 × 6 cm queda a la vista y la pieza de 26 cm atraviesa el muro; el espesor real es de 26 cm (la imagen del usuario lo nombra de 28 cm).",
        planta_nota="Planta de una hilada a tizón: cada pieza de 26 cm de fondo atraviesa el muro.",
        hiladas=((1.0, ("tizon",)),),
        conceptos=(_nuevo("EST-02030", "Muro a tizón de tabique rojo recocido (26 cm de espesor real), asentado con mezcla cemento-arena 1:4, acabado común"),),
        fuente=_TEXTO_NUEVO,
    ),
    AparejoDeTabique(
        clave="EST-02040",
        nombre="Muro de tabique de 42 cm (tizón y soga)",
        nombre_nominal="Muro de 42 cm",
        nominal_cm=42,
        categoria=_MUROS, subcategoria=_TABIQUE, medida="m2",
        aparejo="muro de 42 cm (tizón y soga)",
        aparejo_largo="Muro de 42 cm: en cada hilada, una pieza a tizón y una hilera de soga",
        aparejo_texto="cada hilada lleva una pieza a tizón (26 cm de fondo) y, detrás, una hilera de soga (14 cm), con 2 cm de junta entre ellas: 26 + 2 + 14 = 42 cm. Es una sola variante: los datos no alcanzan para las tres de la imagen (Q101).",
        planta_nota="Planta de la hilada: tizón (26 cm) y soga (14 cm) con la junta de 2 cm entre ambos: 42 cm.",
        hiladas=((1.0, ("tizon", "soga")),),
        conceptos=(_nuevo("EST-02040", "Muro de 42 cm de tabique rojo recocido (tizón y soga), asentado con mezcla cemento-arena 1:4, acabado común"),),
        fuente=_TEXTO_NUEVO,
        pendientes=(("Q101", "El muro de 42 cm tiene una sola variante (tizón y soga): los datos de la imagen no alcanzan para las tres que muestra."),),
    ),
    AparejoDeTabique(
        clave="EST-02050",
        nombre="Sardinel de tabique parado",
        nombre_nominal="Sardinel de tabique",
        nominal_cm=None,
        categoria=_MUROS, subcategoria=_TABIQUE, medida="ml",
        aparejo="sardinel (parado)",
        aparejo_largo="Sardinel: pieza parada sobre su extremo, cara de 14 × 26 cm visible",
        aparejo_texto="colocada parada sobre su extremo: la cara de 14 × 26 cm queda a la vista y el espesor es de 6 cm. Se mide por metro lineal de una hilada (Q102).",
        planta_nota="Planta del sardinel: piezas de 14 cm de largo en el sentido del trazo y 6 cm de espesor.",
        hiladas=((1.0, ("parado",)),),
        con_tipo=True,
        conceptos=(_nuevo("EST-02050", "Sardinel de tabique rojo recocido parado, asentado con mezcla cemento-arena 1:4, por metro lineal de una hilada", "ml"),),
        fuente=_TEXTO_NUEVO,
        pendientes=(("Q102", "Hay varios tipos de sardinel y se revisan más adelante: el tipo es un parámetro con un solo valor hoy (parado); no se inventan variantes."),),
    ),
    AparejoDeTabique(
        clave="AUX-04010",
        nombre="Muro de tabique 14 cm, sin destajo (material auxiliar)",
        nombre_nominal="Muro de 14 cm sin destajo (auxiliar)",
        nominal_cm=14,
        categoria=_MUROS, subcategoria=_TABIQUE, medida="m2",
        aparejo="a soga (al hilo)",
        aparejo_largo="A soga (al hilo): lado de 26 cm visible, tendido",
        aparejo_texto="colocada a soga: el lado de 26 cm queda visible y tendido; el espesor es de 14 cm.",
        planta_nota="Planta de dos hiladas consecutivas, de soga: la pieza de 26 cm corre a lo largo del muro y su ancho de 14 cm es el espesor.",
        hiladas=((1.0, ("soga",)),),
        conceptos=(
            ConceptoDeTabique(
                "AUX-04010", "Material auxiliar sin destajo",
                "Muro de 14 cm de espesor, de tabique rojo recocido, asentado con mezcla mortero-arena 1:5 acabado común", "m2", None,
            ),
        ),
        fuente="AUX-04010 (CATALOGO_DE_MATERIALES línea 82, familia Elemento Estructural, subfamilia Mampostería; composición en ANALISIS_DE_BASICOS_COMPUESTOS). Mismo cálculo que EST-02010 y sin concepto de destajo.",
        avisos_de_catalogo=(AVISO_DEL_MORTERO_DE_AUX_04010,),
        catalogo=_CATALOGO_AUX_04010,
        pendientes=(
            (
                "AUX-04010",
                "Las columnas forjadas EST-07010 y EST-07011 usaban AUX-04010 como forro en el catálogo; ahora calculan el forro por geometría y este elemento no las modifica.",
            ),
        ),
    ),
    AparejoDeTabique(
        clave="ACA-02090",
        nombre="Piso de petatillo de tabique",
        nombre_nominal="Piso de petatillo",
        nominal_cm=None,
        categoria=_PISOS, subcategoria=_PETATILLO, medida="m2",
        aparejo="petatillo (espina de pez)",
        aparejo_largo="Petatillo: piezas planas en espina de pez, cara de 26 × 14 cm",
        aparejo_texto="colocada plana en espina de pez: la cara de 26 × 14 cm queda a la vista y el espesor es de 6 cm. Es un piso, no un muro; la cama de mortero no se conoce (Q103): queda en 0 cm editable.",
        planta_nota="Planta del piso: el dibujo es esquemático, la cantidad por m² es la de las piezas planas.",
        hiladas=((1.0, ("plana",)),),
        cama_cm=0.0,
        conceptos=(_nuevo("ACA-02090", "Piso de petatillo de tabique rojo recocido, piezas planas en espina de pez, asentado con mezcla cemento-arena 1:4"),),
        fuente=_TEXTO_NUEVO,
        pendientes=(
            (
                "Q103",
                "El catálogo no trae la cama de mortero ni el material de asiento del petatillo: la cama queda en 0 cm editable, sin mortero inventado. "
                "Falta confirmar qué lleva el piso (cama, mortero, lechadeo) y que viva en Acabados (ACA-02xxx).",
            ),
        ),
    ),
)

ELEMENTOS_DE_TABIQUE: dict[str, AparejoDeTabique] = {a.clave: a for a in _LISTA}

_ORDEN_DE_BIBLIOTECA = ("EST-02005", "EST-02010", "EST-02020", "EST-02030", "EST-02040", "EST-02050", "AUX-04010", "ACA-02090")

_PENDIENTES_COMUNES: tuple[tuple[str, str], ...] = (
    ("Q99", "Las claves de los aparejos nuevos (EST-02005, EST-02030, EST-02040, EST-02050 y ACA-02090) son provisionales: Control de obra las confirma con la tabla de revisión; no chocan con ninguna clave del catálogo."),
    ("Q100", "Los nombres conservan el espesor nominal de la imagen (7, 14, 21, 28, 42) y el cálculo usa el espesor real de la pieza 14×6×26."),
    ("Q70", "Los huecos vienen del Cuantificador: la cantidad se captura en m² ya descontados; los elementos de vano se construyen después."),
    ("Q32", "Herramienta y equipo: el catálogo no trae insumos de esa clase (ni andamios); la sección es opcional, vacía y sin precios."),
)


def claves_de_tabique() -> tuple[str, ...]:
    return _ORDEN_DE_BIBLIOTECA


def elemento_de_tabique(clave: str) -> AparejoDeTabique:
    e = ELEMENTOS_DE_TABIQUE.get(clave.strip().upper())
    if e is None:
        raise ElementoDeTabiqueNoEncontrado(f"No hay un elemento de tabique {clave}.")
    return e


# --- Biblioteca ------------------------------------------------------------------------------------------------------------


def _entrada_de_biblioteca(e: AparejoDeTabique) -> dict[str, Any]:
    c = e.conceptos[0]
    return {
        "clave": e.clave,
        "nombre": e.nombre,
        "tipo": "tabique",
        "se_mide_por": "metro lineal de una hilada" if e.medida == "ml" else "m²",
        "concepto": {"clave": c.clave, "descripcion": c.descripcion, "unidad": e.medida},
    }


def categorias_de_biblioteca() -> tuple[dict[str, Any], ...]:
    """Lo que estos elementos agregan a la biblioteca (Muros › Muros de tabique, Pisos › Pisos de petatillo)."""
    def elementos(cat: str) -> tuple[dict[str, Any], ...]:
        return tuple(_entrada_de_biblioteca(ELEMENTOS_DE_TABIQUE[k]) for k in _ORDEN_DE_BIBLIOTECA if ELEMENTOS_DE_TABIQUE[k].categoria[0] == cat)

    return (
        {
            "clave": "muros", "nombre": "Muros", "prefijo": "MT",
            "subcategorias": ({"clave": "tabique", "nombre": "Muros de tabique", "prefijo": "MT", "elementos": elementos("muros")},),
        },
        {
            "clave": "pisos", "nombre": "Pisos", "prefijo": "P",
            "subcategorias": ({"clave": "petatillo", "nombre": "Pisos de petatillo (tabique)", "prefijo": "P", "elementos": elementos("pisos")},),
        },
    )


# --- Cálculo -----------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EntradaMuroDeTabique:
    """Lo que se captura. `cantidad` son m² de muro (o metros de hilada del sardinel) ya sin huecos; lo que viene vacío usa el valor
    del elemento."""

    cantidad: float = 1.0
    nivel: int | None = None
    nivel_desde_3er_nivel: int = NIVEL_DEL_TERCER_NIVEL
    junta_cm: float = JUNTA_CM
    junta_entre_hileras_cm: float | None = None
    desperdicio_de_pieza_pct: float = DESPERDICIO_DE_PIEZA_PCT
    desperdicio_de_mezcla_pct: float = DESPERDICIO_DE_MEZCLA_PCT
    pieza_alto_cm: float = PIEZA_ALTO_CM
    pieza_largo_cm: float = PIEZA_LARGO_CM
    cama_cm: float | None = None
    tipo_de_sardinel: str | None = None
    herramienta: tuple[tuple[str, str, float], ...] = ()
    """(descripción, unidad, cantidad por unidad de medida): herramienta y equipo opcional, sin precio."""


def _validar(e: AparejoDeTabique, i: EntradaMuroDeTabique) -> None:
    if not (0 < i.cantidad <= 1_000_000):
        raise ErrorDeMuroDeTabique("La cantidad debe ser mayor que cero (m² del muro, o metros de la hilada del sardinel).")
    if i.nivel is not None and not (1 <= i.nivel <= 100):
        raise ErrorDeMuroDeTabique("El nivel es 1 (planta baja) o más.")
    if not (2 <= i.nivel_desde_3er_nivel <= 100):
        raise ErrorDeMuroDeTabique("La regla del 3.er nivel empieza en el nivel 2 o más.")
    if not (0 <= i.junta_cm <= 10):
        raise ErrorDeMuroDeTabique("La junta va en centímetros, entre 0 y 10.")
    if i.junta_entre_hileras_cm is not None and not (0 <= i.junta_entre_hileras_cm <= 10):
        raise ErrorDeMuroDeTabique("La junta entre hileras va en centímetros, entre 0 y 10.")
    for nombre, valor in (("de pieza", i.desperdicio_de_pieza_pct), ("de mezcla", i.desperdicio_de_mezcla_pct)):
        if not (0 <= valor <= 100):
            raise ErrorDeMuroDeTabique(f"El desperdicio {nombre} va en por ciento, entre 0 y 100.")
    for nombre, valor in (("alto", i.pieza_alto_cm), ("largo", i.pieza_largo_cm)):
        if not (1 <= valor <= 100):
            raise ErrorDeMuroDeTabique(f"El {nombre} de la pieza va en centímetros, entre 1 y 100.")
    if i.cama_cm is not None:
        if e.cama_cm is None:
            raise ErrorDeMuroDeTabique("Solo el piso de petatillo lleva cama de mortero.")
        if not (0 <= i.cama_cm <= 20):
            raise ErrorDeMuroDeTabique("La cama de mortero va en centímetros, entre 0 y 20.")
    if i.tipo_de_sardinel is not None:
        if not e.con_tipo:
            raise ErrorDeMuroDeTabique("Solo el sardinel tiene tipo.")
        if i.tipo_de_sardinel not in TIPOS_DE_SARDINEL:
            raise ErrorDeMuroDeTabique(
                f"El tipo de sardinel «{i.tipo_de_sardinel}» no está definido: hay varios tipos y se revisan más adelante (hoy: {', '.join(TIPOS_DE_SARDINEL)})."
            )
    if len(i.herramienta) > 20:
        raise ErrorDeMuroDeTabique("La herramienta y equipo admite hasta 20 renglones.")
    for descripcion, unidad, cantidad in i.herramienta:
        if not descripcion.strip() or not unidad.strip() or not (0 <= cantidad <= 1_000_000):
            raise ErrorDeMuroDeTabique("Cada renglón de herramienta y equipo lleva descripción, unidad y una cantidad de cero o más.")


def _concepto_del_contexto(e: AparejoDeTabique, nivel: int | None, desde: int) -> tuple[ConceptoDeTabique, list[str]]:
    """El concepto que paga el elemento en el nivel dado, con los `Contexto` de 2A: nivel ≥ `desde` paga el de 3.er nivel."""
    avisos: list[str] = []
    if len(e.conceptos) == 1:
        return e.conceptos[0], avisos
    contextos = [
        (c, Contexto(nivel_min=desde) if c.tercer_nivel else Contexto(nivel_max=desde - 1)) for c in e.conceptos
    ]
    if nivel is None:
        avisos.append("No se dio el nivel: se usa el concepto de los niveles 1 y 2. Con el nivel del plano se elige EST-02011 desde el 3.º.")
        return next(c for c, _ in contextos if not c.tercer_nivel), avisos
    for c, ctx in contextos:
        if ctx.abarca(nivel, None):
            return c, avisos
    return e.conceptos[0], avisos  # pragma: no cover - los dos contextos cubren todos los niveles


def _geometria(e: AparejoDeTabique, i: EntradaMuroDeTabique) -> dict[str, Any]:
    a, h, ll = PIEZA_ANCHO_CM / 100, i.pieza_alto_cm / 100, i.pieza_largo_cm / 100
    j = i.junta_cm / 100
    jh = (i.junta_entre_hileras_cm if i.junta_entre_hileras_cm is not None else (e.junta_entre_hileras_cm if e.junta_entre_hileras_cm is not None else i.junta_cm)) / 100
    vp = a * h * ll
    netas = espesor_medio = 0.0
    inverso_de_hilada = 0.0
    espesores: list[float] = []
    detalle: list[dict[str, Any]] = []
    por_hilada = 1.0
    for peso, orientaciones in e.hiladas:
        filas = []
        alto_de_hilera = 0.0
        for o in orientaciones:
            visible, ch, fondo = _ORIENTACIONES[o][1](a, h, ll)
            filas.append((o, visible, ch, fondo))
            alto_de_hilera = max(alto_de_hilera, ch)
        espesor = sum(f[3] for f in filas) + jh * (len(filas) - 1)
        n_de_hilada = sum(1 / ((v + j) * (ch + j)) for _, v, ch, _ in filas)
        netas += peso * n_de_hilada
        espesor_medio += peso * espesor
        inverso_de_hilada += peso / (alto_de_hilera + j)
        espesores.append(espesor)
        por_hilada = 1 / (filas[0][1] + j)
        detalle.append(
            {
                "peso": peso,
                "espesor_cm": round(espesor * 100, 4),
                "filas": [
                    {
                        "orientacion": o,
                        "etiqueta": _ORIENTACIONES[o][0],
                        "visible_cm": round(v * 100, 4),
                        "alto_cm": round(ch * 100, 4),
                        "espesor_cm": round(f * 100, 4),
                        "piezas_netas_m2": 1 / ((v + j) * (ch + j)),
                    }
                    for o, v, ch, f in filas
                ],
            }
        )
    hilada = 1 / inverso_de_hilada
    por_unidad = hilada if e.medida == "ml" else 1.0
    cama_cm = (i.cama_cm if i.cama_cm is not None else e.cama_cm) if e.cama_cm is not None else None
    cama = (cama_cm or 0.0) / 100
    mezcla_neta_m2 = max(0.0, espesor_medio - netas * vp) + cama
    return {
        "netas": netas * por_unidad,
        "mezcla_neta": mezcla_neta_m2 * por_unidad,
        "espesor_maximo_cm": round(max(espesores) * 100, 6),
        "espesor_minimo_cm": round(min(espesores) * 100, 6),
        "espesor_medio_cm": round(espesor_medio * 100, 6),
        "hilada_cm": round(hilada * 100, 6),
        "piezas_por_hilada": por_hilada,
        "hiladas": detalle,
        "cama_cm": cama_cm,
    }


def _insumos_por_unidad(piezas: float, mezcla: float) -> dict[str, float]:
    return {CLAVE_PIEZA: piezas, CLAVE_MEZCLA: mezcla}


def _conciliar(e: AparejoDeTabique, piezas: float, mezcla: float) -> list[dict[str, Any]]:
    bloques: list[dict[str, Any]] = []
    for concepto, filas in e.catalogo:
        composicion = [
            FilaDeComposicion(
                clave=clave, cantidad=cantidad, descripcion=_DESCRIPCIONES.get(clave) or _descripcion_del_destajo(clave),
                unidad=("pza" if clave == CLAVE_PIEZA else "m3" if clave == CLAVE_MEZCLA else "m2"), es_mano_de_obra=es_mo, costo=costo if es_mo else None,
            )
            for clave, cantidad, es_mo, costo, _ in filas
        ]
        comparado = comparar_con_concepto(_insumos_por_unidad(piezas, mezcla), composicion, descripciones=_DESCRIPCIONES)
        c = next((x for x in e.conceptos if x.clave == concepto), e.conceptos[0])
        bloques.append(
            {
                "concepto": {"clave": concepto, "descripcion": c.descripcion, "unidad": "m2"},
                "sobre": "por m² de muro",
                "filas": comparado["filas"],
                "mano_de_obra": comparado["mano_de_obra"],
                "resumen": comparado["resumen"],
                "coincide": comparado["coincide"],
                "fuente_de_las_filas": [linea for _, _, _, _, linea in filas],
                "avisos": list(e.avisos_de_catalogo),
            }
        )
    return bloques


def _descripcion_del_destajo(clave: str) -> str:
    for a in _LISTA:
        for c in a.conceptos:
            if c.destajo and c.destajo[0] == clave:
                return c.destajo[1]
    return ""


def calcular_muro_de_tabique(clave: str, i: EntradaMuroDeTabique | None = None) -> dict[str, Any]:
    """Piezas y mezcla por m² (o por ml de hilada), el concepto del contexto, el contraste con el catálogo y los totales de `cantidad`."""
    e = elemento_de_tabique(clave)
    entrada = i or EntradaMuroDeTabique()
    _validar(e, entrada)
    g = _geometria(e, entrada)
    dp, dm = entrada.desperdicio_de_pieza_pct / 100, entrada.desperdicio_de_mezcla_pct / 100
    piezas = g["netas"] * (1 + dp)
    mezcla = g["mezcla_neta"] * (1 + dm)
    cantidad = entrada.cantidad
    concepto, avisos = _concepto_del_contexto(e, entrada.nivel, entrada.nivel_desde_3er_nivel)
    unidad = "ml" if e.medida == "ml" else "m²"

    insumos = [
        {
            "parte": "tabique", "clave": CLAVE_PIEZA, "descripcion": _DESCRIPCIONES[CLAVE_PIEZA], "unidad": "pza",
            "por_unidad": piezas, "total": piezas * cantidad, "a_comprar": float(math.ceil(piezas * cantidad - 1e-9)),
        },
        {
            "parte": "mezcla", "clave": CLAVE_MEZCLA, "descripcion": _DESCRIPCIONES[CLAVE_MEZCLA], "unidad": "m3",
            "por_unidad": mezcla, "total": mezcla * cantidad, "a_comprar": None,
        },
    ]
    total_mezcla = mezcla * cantidad
    compuesta = [
        {"clave": k, "descripcion": d, "unidad": u, "por_m3": q, "total": q * total_mezcla, "linea": linea}
        for k, d, u, q, linea in _MEZCLA_COMPUESTA
    ]
    if concepto.destajo:
        mano = {
            "estado": "destajo_del_catalogo",
            "destajo": {"clave": concepto.destajo[0], "descripcion": concepto.destajo[1], "unidad": concepto.destajo[2]},
            "cantidad": cantidad,
            "nota": "El destajo es el del catálogo y se paga por m² con el concepto; el elemento no lo calcula ni pone precio.",
        }
    elif concepto.nuevo:
        mano = {
            "estado": "sin_destajo", "destajo": None, "cantidad": cantidad,
            "nota": "Concepto nuevo sin destajo: pendiente de definir por Costos. Sin mano de obra y sin precio.",
        }
    else:
        mano = {"estado": "sin_destajo", "destajo": None, "cantidad": cantidad, "nota": "Material auxiliar sin destajo: no lleva mano de obra."}

    if e.clave == "EST-02020":
        avisos.append(
            f"El catálogo trae 86 pza y 0.0939 m³ por m²; con 14 + 1 + 6 el cálculo da {piezas:.1f} pza y {mezcla:.4f} m³. "
            "La diferencia está en la conciliación: el catálogo no se edita."
        )
    if e.nominal_cm is not None and abs(g["espesor_maximo_cm"] - e.nominal_cm) > 0.5:
        avisos.append(f"El nombre dice {e.nominal_cm} cm (nominal); con la pieza 14×6×26 el espesor real es de {g['espesor_maximo_cm']:.1f} cm.")
    if e.cama_cm is not None and (g["cama_cm"] or 0) == 0:
        avisos.append("La cama de mortero está en 0 cm: el catálogo no la trae y no se inventa mortero (Q103).")
    avisos.extend(e.avisos_de_catalogo)

    herramienta = [
        {"descripcion": d.strip(), "unidad": u.strip(), "por_unidad": q, "total": q * cantidad} for d, u, q in entrada.herramienta
    ]
    return {
        "clave": e.clave,
        "nombre": e.nombre,
        "medida": e.medida,
        "unidad": unidad,
        "cantidad": cantidad,
        "nivel": entrada.nivel,
        "concepto": {
            "clave": concepto.clave,
            "descripcion": concepto.descripcion,
            "unidad": e.medida,
            "etiqueta": concepto.etiqueta,
            "estado": "propuesto" if concepto.nuevo else "catalogo",
            "clave_provisional": concepto.nuevo,
            "nivel_desde": entrada.nivel_desde_3er_nivel if concepto.tercer_nivel else None,
        },
        "pieza": {"insumo": CLAVE_PIEZA, "ancho_cm": PIEZA_ANCHO_CM, "alto_cm": entrada.pieza_alto_cm, "largo_cm": entrada.pieza_largo_cm},
        "parametros": {
            "junta_cm": entrada.junta_cm,
            "junta_entre_hileras_cm": (
                entrada.junta_entre_hileras_cm if entrada.junta_entre_hileras_cm is not None else e.junta_entre_hileras_cm
            ),
            "desperdicio_de_pieza_pct": entrada.desperdicio_de_pieza_pct,
            "desperdicio_de_mezcla_pct": entrada.desperdicio_de_mezcla_pct,
            "cama_cm": g["cama_cm"],
            "tipo_de_sardinel": (entrada.tipo_de_sardinel or next(iter(TIPOS_DE_SARDINEL))) if e.con_tipo else None,
            "nivel_desde_3er_nivel": entrada.nivel_desde_3er_nivel if e.con_variante_de_nivel else None,
        },
        "geometria": {
            "espesor_real_cm": g["espesor_maximo_cm"],
            "espesor_minimo_cm": g["espesor_minimo_cm"],
            "espesor_medio_cm": g["espesor_medio_cm"],
            "hilada_promedio_cm": g["hilada_cm"],
            "piezas_por_hilada": g["piezas_por_hilada"],
            "hiladas": g["hiladas"],
        },
        "piezas": {"netas_por_unidad": g["netas"], "por_unidad": piezas, "total": piezas * cantidad, "a_comprar": math.ceil(piezas * cantidad - 1e-9)},
        "mezcla": {"neta_por_unidad": g["mezcla_neta"], "por_unidad": mezcla, "total_m3": total_mezcla},
        "insumos": insumos,
        "mezcla_compuesta": compuesta,
        "mano_de_obra": mano,
        "herramienta": herramienta,
        "conciliacion": _conciliar(e, piezas, mezcla),
        "avisos": list(dict.fromkeys(avisos)),
    }


# --- Definición ---------------------------------------------------------------------------------------------------------------


def definicion_de(clave: str) -> dict[str, Any]:
    """La ficha del elemento: sus parámetros por defecto, el aparejo con sus hiladas, los conceptos que lo pagan y los pendientes."""
    e = elemento_de_tabique(clave)
    g = _geometria(e, EntradaMuroDeTabique())
    return {
        "clave": e.clave,
        "nombre": e.nombre,
        "nombre_nominal": e.nombre_nominal,
        "tipo": "tabique",
        "medida": e.medida,
        "se_mide_por": "metro lineal de una hilada" if e.medida == "ml" else "m²",
        "categoria": {"clave": e.categoria[0], "nombre": e.categoria[1]},
        "subcategoria": {"clave": e.subcategoria[0], "nombre": e.subcategoria[1]},
        "espesor_nominal_cm": e.nominal_cm,
        "espesor_real_cm": g["espesor_maximo_cm"],
        "aparejo": e.aparejo,
        "aparejo_largo": e.aparejo_largo,
        "aparejo_texto": e.aparejo_texto,
        "planta_nota": e.planta_nota,
        "pieza": {"insumo": CLAVE_PIEZA, "ancho_cm": PIEZA_ANCHO_CM, "alto_cm": PIEZA_ALTO_CM, "largo_cm": PIEZA_LARGO_CM},
        "mezcla": CLAVE_MEZCLA,
        "parametros_por_defecto": {
            "junta_cm": JUNTA_CM,
            "junta_entre_hileras_cm": e.junta_entre_hileras_cm,
            "desperdicio_de_pieza_pct": DESPERDICIO_DE_PIEZA_PCT,
            "desperdicio_de_mezcla_pct": DESPERDICIO_DE_MEZCLA_PCT,
            "cama_cm": e.cama_cm,
            "tipo_de_sardinel": next(iter(TIPOS_DE_SARDINEL)) if e.con_tipo else None,
            "nivel_desde_3er_nivel": NIVEL_DEL_TERCER_NIVEL if e.con_variante_de_nivel else None,
        },
        "tipos_de_sardinel": [{"clave": k, "descripcion": v} for k, v in TIPOS_DE_SARDINEL.items()] if e.con_tipo else [],
        "hiladas": [{"peso": p, "filas": list(f)} for p, f in e.hiladas],
        "conceptos": [
            {
                "clave": c.clave,
                "etiqueta": c.etiqueta,
                "descripcion": c.descripcion,
                "unidad": e.medida,
                "estado": "propuesto" if c.nuevo else "catalogo",
                "clave_provisional": c.nuevo,
                "en_catalogo": not c.nuevo,
                "destajo": {"clave": c.destajo[0], "descripcion": c.destajo[1], "unidad": c.destajo[2]} if c.destajo else None,
                "nivel_desde": NIVEL_DEL_TERCER_NIVEL if c.tercer_nivel else None,
            }
            for c in e.conceptos
        ],
        "fuente": e.fuente,
        "avisos_de_catalogo": list(e.avisos_de_catalogo),
        "pendientes": [{"clave": k, "texto": t} for k, t in (*e.pendientes, *_PENDIENTES_COMUNES)],
    }


# --- Tabla de revisión ----------------------------------------------------------------------------------------------------------


def _contraste(e: AparejoDeTabique, piezas: float, mezcla: float) -> str:
    if not e.catalogo:
        return "Sin concepto en el catálogo: concepto nuevo propuesto, sin destajo ni precio."
    concepto, filas = e.catalogo[0]
    pz = next(c for k, c, *_ in filas if k == CLAVE_PIEZA)
    mz = next(c for k, c, *_ in filas if k == CLAVE_MEZCLA)
    mp, dp = marca_de(pz, piezas)
    mm, dm = marca_de(mz, mezcla)
    nota = {
        "EST-02020": " El usuario aceptó la nueva versión propuesta con el cálculo del elemento (por defecto, vía autorización).",
        "AUX-04010": " Corrección propuesta de texto: «mortero-arena 1:5» → «1:4» (la composición manda).",
    }.get(e.clave, "")
    return (
        f"{concepto} del catálogo: {pz:g} pza y {mz:g} m³ por m²; pieza {mp} ({(dp or 0) * 100:+.1f} %), mezcla {mm} ({(dm or 0) * 100:+.1f} %)."
        + nota
    )


def tabla_de_revision() -> list[dict[str, Any]]:
    """La tabla que el usuario pidió para revisar claves y nombres (Q99, Q100): clave propuesta, nombre nominal, espesor real, aparejo,
    piezas y mezcla por unidad y el contraste contra el catálogo, con los valores por defecto del elemento."""
    filas: list[dict[str, Any]] = []
    for clave in _ORDEN_DE_BIBLIOTECA:
        e = ELEMENTOS_DE_TABIQUE[clave]
        r = calcular_muro_de_tabique(clave)
        nuevo = e.conceptos[0].nuevo
        filas.append(
            {
                "clave": clave,
                "provisional": nuevo,
                "estado": "propuesto" if nuevo else "catalogo",
                "nombre_nominal": e.nombre_nominal,
                "nombre": e.nombre,
                "espesor_real_cm": r["geometria"]["espesor_real_cm"],
                "aparejo": e.aparejo,
                "unidad": r["unidad"],
                "piezas_por_unidad": r["piezas"]["por_unidad"],
                "mezcla_m3_por_unidad": r["mezcla"]["por_unidad"],
                "contraste": _contraste(e, r["piezas"]["por_unidad"], r["mezcla"]["por_unidad"]),
            }
        )
    return filas


# --- Propuestas de versión de concepto ---------------------------------------------------------------------------------------------


def concepto_nuevo_de(clave: str) -> dict[str, Any]:
    """El concepto nuevo propuesto de un aparejo que el catálogo no trae (con su clave provisional): sin precio ni destajo."""
    e = elemento_de_tabique(clave)
    c = e.conceptos[0]
    if not c.nuevo:
        raise ErrorDeMuroDeTabique(f"{e.clave} ya está en el catálogo: no hace falta un concepto nuevo.")
    r = calcular_muro_de_tabique(clave)
    insumos = {x["clave"]: round(x["por_unidad"], 6) for x in r["insumos"]}
    return {
        "elemento_clave": e.clave,
        "concepto_clave": c.clave,
        "clase": "concepto_nuevo",
        "resumen": f"Concepto nuevo {c.clave} (clave provisional): {e.nombre_nominal}, por {'metro lineal de una hilada' if e.medida == 'ml' else 'm²'}, sin destajo ni precio",
        "detalle": {
            "descripcion": c.descripcion,
            "unidad": e.medida,
            "clave_provisional": True,
            "insumos": insumos,
            "motivos": [
                "Q74: el catálogo no trae este aparejo; queda como concepto nuevo propuesto, pendiente de autorizar por Control de obra.",
                "Sin destajo: pendiente de definir por Costos. Sin precio.",
            ],
            "cambios": [],
        },
    }


def propuestas_de_actualizacion_de_apu(calculo: Mapping[str, Any]) -> list[dict[str, Any]]:
    """«Confirmar cálculo → actualizar APU»: una nueva versión propuesta por cada concepto del catálogo cuyo insumo difiere del cálculo
    (marca ≈ o ≠). Los coeficientes `antes` son los del catálogo; el catálogo no se edita. Sin cambios, no hay propuesta."""
    propuestas: list[dict[str, Any]] = []
    clave = str(calculo["clave"])
    for bloque in calculo["conciliacion"]:
        cambios = []
        for f in bloque["filas"]:
            if f["marca"] in ("≈", "≠") and f["catalogo"] is not None and f["elemento"] is not None:
                cambios.append(
                    {
                        "insumo": f["clave"],
                        "unidad": f["unidad"],
                        "antes": float(f["catalogo"]),
                        "despues": round(float(f["elemento"]), 6),
                    }
                )
        if not cambios:
            continue
        concepto = bloque["concepto"]["clave"]
        resumen = f"Nueva versión de {concepto}: " + "; ".join(f"{c['insumo']} {c['antes']:g} → {c['despues']:g}" for c in cambios)
        propuestas.append(
            {
                "elemento_clave": clave,
                "concepto_clave": concepto,
                "clase": "version_de_concepto",
                "resumen": resumen,
                "detalle": {
                    "cambios": cambios,
                    "motivos": [
                        "Confirmar cálculo → actualizar APU (Q67): los coeficientes del cálculo con la pieza 14×6×26, junta de 2 cm, 12 % de pieza y 5 % de mezcla.",
                        *(["Q97: muro de 21 cm = tabique de 14 + junta de 1 cm + tabique de 6."] if clave == "EST-02020" else []),
                    ],
                    "hasta_m": None,
                },
            }
        )
    return propuestas


TEXTO_DE_AUX_04010 = "Muro de 14 cm. de espesor, de tabique rojo recocido, asentado con mezcla mortero-arena 1:5 acabado común."


def correcciones_de(clave: str) -> list[dict[str, Any]]:
    """Las correcciones que el elemento propone de fábrica, siempre como versión propuesta (nunca se edita el catálogo):

    - EST-02020: los coeficientes del cálculo 14 + 1 + 6 (el usuario aceptó la versión propuesta: el cálculo manda);
    - AUX-04010: el texto «mortero-arena 1:5» pasa a «1:4» (manda la composición, MEZ-07010 es 1:4).
    """
    e = elemento_de_tabique(clave)
    if e.clave == "EST-02020":
        return propuestas_de_actualizacion_de_apu(calcular_muro_de_tabique(e.clave))
    if e.clave == "AUX-04010":
        despues = TEXTO_DE_AUX_04010.replace("mortero-arena 1:5", "mortero-arena 1:4")
        return [
            {
                "elemento_clave": e.clave,
                "concepto_clave": "AUX-04010",
                "clase": "version_de_concepto",
                "resumen": "Nueva versión de AUX-04010: descripción «mortero-arena 1:5» → «mortero-arena 1:4» (la composición usa MEZ-07010, 1:4)",
                "detalle": {
                    "cambios": [],
                    "descripcion": {"antes": TEXTO_DE_AUX_04010, "despues": despues},
                    "motivos": ["La composición manda: MEZ-07010 es cemento-arena 1:4; se corrige el texto de la descripción."],
                    "hasta_m": None,
                },
            }
        ]
    return []
