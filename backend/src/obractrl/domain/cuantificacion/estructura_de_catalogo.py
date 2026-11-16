"""Los elementos de estructura del catálogo: castillos K-1 a K-8, castillo y cadenas aparentes y columnas forjadas
(plan de elementos de muro, Ola 3, lane 3A; M-110 a M-129 del mockup).

Cada elemento trae su **sección**, su **armado** (armex, o varillas con anillos), su **cimbra** (los consumos por metro que
trae el catálogo) y los **conceptos del catálogo que lo pagan**: el acero por pieza con un escalón por altura, el colado y la
cimbra por metro, o el concepto completo por metro de los aparentes. Todo se calcula aquí, sin base de datos, con la receta
del acero (`receta_acero`): cortes con módulos de 1 a 6 m, traslape de 40 diámetros y anillos con gancho.

Reglas que vienen de las respuestas del usuario (Ola 3, lane 3A):

- «15x30» es **ancho 15 (el espesor del muro) × largo 30** en K-3, K-5, K-7 y K-8 (Q75).
- En K-8 vale el acero EST-10081 (8 var. no.4, estribos @12); el armex 10×15 del colado (EST-02180) es un **concepto nuevo**
  pendiente de autorizar (Q77).
- Las medidas de los aparentes son las del título del catálogo (Q81); el catálogo que las contradice se corrige con una
  **nueva versión propuesta** (`correcciones_de_catalogo`), nunca editándolo.
- La columna forjada queda con alto fijo de 4.20 m; otra altura es un concepto nuevo pendiente (Q91). Su forro de tabique sale
  por geometría y su cimbra es de un solo lado (M-124 a M-126); el cierre geométrico (Q92 a Q95) sigue pendiente y **no se
  toca aquí**.
- Lo que el catálogo trae y el elemento no calcula (el mortero del aparente, el destajo) se marca «solo en el catálogo» (Q82,
  Q83): el elemento no inventa lo que el catálogo no explica. Sin precios ni destajos.

Función pura, sin base de datos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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

__all__ = [
    "ALTO_DE_LA_FORJADA_M",
    "ALTO_ESTANDAR_M",
    "CATEGORIAS_DE_ESTRUCTURA",
    "DESPERDICIO_CONCRETO",
    "ELEMENTOS_DE_ESTRUCTURA",
    "ArmadoDeEstructura",
    "ConceptoDeEstructura",
    "ElementoDeEstructura",
    "ElementoDeEstructuraNoEncontrado",
    "ErrorDeEstructura",
    "Escalon",
    "Forro",
    "calcular_elemento",
    "calcular_forro",
    "claves_de_concepto",
    "concepto_nuevo_por_altura",
    "definicion_de",
    "elemento_de_estructura",
    "insumos_del_concepto",
]

ALTO_ESTANDAR_M = 3.0
"""La altura estándar del muro del mockup (driver `altura_estandar`): con ella se calcula un elemento que no trae alto."""
ALTO_DE_LA_FORJADA_M = 4.20
"""Q91: la columna forjada tiene alto fijo; otra altura es otro concepto, pendiente de autorizar."""
DESPERDICIO_CONCRETO = 0.05
"""El catálogo cuenta 5 % de desperdicio de concreto (0.0225 m³/m × 1.05 = 0.023625)."""
ALAMBRE = "ACE-00001"
CONCRETO = "MEZ-01020"
PESO_ANILLO_KG_M = 0.249
"""Peso por metro del anillo y del alambrón (no. 2): el supuesto del mockup (`insumos_catalogo`)."""
PESO_ALAMBRE_RECOCIDO_KG_M = 0.0095
LARGO_ARMEX_M = 6.0
LARGO_VARILLA_M = 12.0
_EPS = 1e-9


class ErrorDeEstructura(ErrorDeRecetaAcero):
    """Un dato que no vale."""


class ElementoDeEstructuraNoEncontrado(ErrorDeEstructura):
    """No hay un elemento de estructura con esa clave."""


@dataclass(frozen=True, slots=True)
class Escalon:
    """Un concepto de acero que sirve hasta cierto alto (EST-10010 hasta 4.00 m, EST-10011 hasta 6.00 m…)."""

    hasta_m: float
    clave: str


@dataclass(frozen=True, slots=True)
class ConceptoDeEstructura:
    """Un concepto del catálogo que paga una parte del elemento.

    `ranura`: `acero` (por pieza, con escalones), `colado` (concreto y cimbra por metro, o por pieza en la forjada) o
    `completo` (todo por metro, los aparentes). `unidad` es la del concepto: `pza` o `m`."""

    ranura: str
    unidad: str
    clave: str | None = None
    escalones: tuple[Escalon, ...] = ()
    nuevo: bool = False
    """`True` = concepto que el catálogo no trae: queda propuesto, pendiente de autorizar."""


@dataclass(frozen=True, slots=True)
class ArmadoDeEstructura:
    """Armex (`armex` = clave del insumo) o varillas (`varillas` = (cantidad, número, insumo)) con anillos."""

    armex: str | None = None
    varillas: tuple[tuple[int, int, str], ...] = ()
    anillo_insumo: str | None = None
    anillo_sep_cm: float | None = None
    alambre_kg_ml: float | None = None
    """Kg de alambre de amarre por metro, los del catálogo; vacío = se calcula por amarres."""
    gancho_cm: float = 10.0
    recubrimiento_cm: float = 2.5


@dataclass(frozen=True, slots=True)
class Forro:
    """El forro de tabique de una columna forjada (M-126): cada cara con su ladrillo, la cimbra de un solo lado."""

    tabique: str = "PET-00001"
    mezcla: str = "MEZ-07010"
    pieza_largo_cm: float = 26.0
    pieza_ancho_cm: float = 14.0
    pieza_alto_cm: float = 6.0
    junta_cm: float = 2.0
    desperdicio_tabique: float = 0.12
    desperdicio_mezcla: float = 0.05
    seccion_largo_cm: float = 44.0
    seccion_ancho_cm: float = 33.0
    cimbra_insumo: str = "MAD-00002"


@dataclass(frozen=True, slots=True)
class ElementoDeEstructura:
    clave: str
    alias: str | None
    nombre: str
    categoria: str
    subcategoria: str
    tipo: str  # castillo | lineal
    ancho_cm: float
    """El espesor del muro (castillo) o el ancho de la cadena."""
    largo_cm: float | None
    """El largo de la sección del castillo; `None` en una cadena."""
    peralte_cm: float | None
    """El peralte de la cadena; `None` en un castillo."""
    armado: ArmadoDeEstructura
    cimbra: tuple[tuple[str, float], ...]
    """Consumos de cimbra por metro del catálogo: (insumo, cantidad)."""
    conceptos: tuple[ConceptoDeEstructura, ...]
    lados_cimbra: int = 2
    alto_fijo_m: float | None = None
    forro: Forro | None = None
    solo_en_catalogo: tuple[tuple[str, str], ...] = ()
    """Insumos del concepto del catálogo que el elemento no calcula: (clave, por qué)."""
    pendientes: tuple[str, ...] = ()
    fuente: str = ""
    posicion: str | None = None
    """Dónde del muro se coloca una cadena: `desplante` o `cerramiento`."""
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def seccion_cm(self) -> tuple[float, float]:
        return (self.ancho_cm, self.largo_cm if self.largo_cm is not None else float(self.peralte_cm or 0))


def _esc(*pares: tuple[float, str]) -> tuple[Escalon, ...]:
    return tuple(Escalon(h, c) for h, c in pares)


_CIMBRA_K1 = (("ACE-00012", 0.017021), ("ACE-00013", 0.02), ("MAD-00004", 0.01), (ALAMBRE, 0.210987))
_CIMBRA_K2 = (("ACE-00012", 0.017021), ("ACE-00013", 0.02), ("MAD-00004", 0.01), (ALAMBRE, 0.189888))
_CIMBRA_K3 = (("ACE-00012", 0.025532), ("ACE-00013", 0.02), ("MAD-00004", 0.01), (ALAMBRE, 0.189888))
_CIMBRA_K5 = (("ACE-00012", 0.034043), ("ACE-00013", 0.04), ("MAD-00004", 0.01), (ALAMBRE, 0.223398))
_CIMBRA_K6 = (("ACE-00012", 0.017021), ("ACE-00013", 0.02), ("MAD-00004", 0.01), (ALAMBRE, 0.1))
_CIMBRA_K7 = (("ACE-00012", 0.021277), ("ACE-00013", 0.02), ("MAD-00004", 0.01), (ALAMBRE, 0.189888))
_CIMBRA_K8 = (("ACE-00012", 0.029787), ("ACE-00013", 0.03), ("MAD-00004", 0.01), (ALAMBRE, 0.12))

_APARENTE_SOLO = (
    ("MEZ-07010", "Mortero cemento-arena 1:4 (0.0021 m³ por ml): el catálogo no dice para qué es; el elemento no lo calcula (Q82)."),
)
_PENDIENTE_CHAFLAN = "El tuino chaflán (MAD-00030) usa la cantidad del catálogo: falta saber de cuántos metros es la pieza y cuántas aristas lleva (Q83)."
_PENDIENTE_DESTAJO_APARENTE = "El destajo del aparente es del catálogo y el elemento no lo calcula."


def _castillo(
    clave: str, alias: str | None, nombre: str, largo: float, armado: ArmadoDeEstructura, cimbra: tuple[tuple[str, float], ...],
    conceptos: tuple[ConceptoDeEstructura, ...], fuente: str, pendientes: tuple[str, ...] = (),
) -> ElementoDeEstructura:
    return ElementoDeEstructura(
        clave=clave, alias=alias, nombre=nombre, categoria="castillos", subcategoria="muro", tipo="castillo", ancho_cm=15.0,
        largo_cm=largo, peralte_cm=None, armado=armado, cimbra=cimbra, conceptos=conceptos, fuente=fuente, pendientes=pendientes,
    )


_PEND_ESCALONES = "El catálogo no trae escalón de acero para alturas mayores a la del último: el elemento repite el último y avisa (Q80)."

_ELEMENTOS: tuple[ElementoDeEstructura, ...] = (
    _castillo(
        "K-1", None, "Castillo K-1 de 15 × 15 con armex 10×10", 15.0,
        ArmadoDeEstructura(armex="ACE-00011", alambre_kg_ml=0.02), _CIMBRA_K1,
        (
            ConceptoDeEstructura(
                "acero", "pza", escalones=_esc((1.0, "EST-10013"), (1.5, "EST-10012"), (4.0, "EST-10010"), (6.0, "EST-10011"))
            ),
            ConceptoDeEstructura("colado", "m", "EST-02110"),
        ),
        "EST-02110 y EST-10010 a EST-10013",
    ),
    _castillo(
        "K-2", None, "Castillo K-2 de 15 × 15, 4 var. no.3 y anillo 10×10 @20", 15.0,
        ArmadoDeEstructura(varillas=((4, 3, "ACR-00001"),), anillo_insumo="ACE-00003", anillo_sep_cm=20.0), _CIMBRA_K2,
        (
            ConceptoDeEstructura("acero", "pza", escalones=_esc((4.0, "EST-10020"), (6.0, "EST-10021"))),
            ConceptoDeEstructura("colado", "m", "EST-02120"),
        ),
        "EST-02120, EST-10020 y EST-10021",
    ),
    _castillo(
        "EST-02130", "K-3", "Castillo K-3 de 15 × 30, 6 var. no.4 y anillo 10×25 @15", 30.0,
        ArmadoDeEstructura(varillas=((6, 4, "ACR-00002"),), anillo_insumo="ACE-00006", anillo_sep_cm=15.0, alambre_kg_ml=0.17296),
        _CIMBRA_K3,
        (
            ConceptoDeEstructura("acero", "pza", escalones=_esc((6.0, "EST-10031"))),
            ConceptoDeEstructura("colado", "m", "EST-02130"),
        ),
        "EST-02130 y EST-10031",
        (_PEND_ESCALONES,),
    ),
    _castillo(
        "EST-02140", "K-4", "Castillo K-4 de 15 × 30, 6 var. no.3 y anillo 10×15 @20 (en ángulo)", 30.0,
        ArmadoDeEstructura(varillas=((6, 3, "ACR-00001"),), anillo_insumo="ACE-00004", anillo_sep_cm=20.0, alambre_kg_ml=0.17296),
        _CIMBRA_K3,
        (
            ConceptoDeEstructura("acero", "pza", escalones=_esc((6.0, "EST-10041"))),
            ConceptoDeEstructura("colado", "m", "EST-02140"),
        ),
        "EST-02140 y EST-10041",
        (
            "K-4 es «en ángulo» en el catálogo; el elemento solo dibuja y calcula la sección rectangular de 15 × 30 (Q76).",
            _PEND_ESCALONES,
        ),
    ),
    _castillo(
        "EST-02150", "K-5", "Castillo K-5 de 15 × 45, 8 var. no.4 y estribo de alambrón @15", 45.0,
        ArmadoDeEstructura(varillas=((8, 4, "ACR-00002"),), anillo_insumo="ACE-00002", anillo_sep_cm=15.0, alambre_kg_ml=0.28),
        _CIMBRA_K5,
        (
            ConceptoDeEstructura("acero", "pza", escalones=_esc((5.0, "EST-10051"))),
            ConceptoDeEstructura("colado", "m", "EST-02150"),
        ),
        "EST-02150 y EST-10051",
        ("El catálogo cuenta el estribo en alambrón (ACE-00002), no en anillo prefabricado.", _PEND_ESCALONES),
    ),
    _castillo(
        "EST-02160", "K-6", "Castillo K-6 de 15 × 15, 4 var. no.4 y anillo 10×10 @20", 15.0,
        ArmadoDeEstructura(varillas=((4, 4, "ACR-00002"),), anillo_insumo="ACE-00003", anillo_sep_cm=20.0, alambre_kg_ml=0.1),
        _CIMBRA_K6,
        (
            ConceptoDeEstructura("acero", "pza", escalones=_esc((4.0, "EST-10060"))),
            ConceptoDeEstructura("colado", "m", "EST-02160"),
        ),
        "EST-02160 y EST-10060",
        (_PEND_ESCALONES,),
    ),
    _castillo(
        "EST-02170", "K-7", "Castillo K-7 de 15 × 20 con armex 10×15", 20.0,
        ArmadoDeEstructura(armex="ACE-00020", alambre_kg_ml=0.0165), _CIMBRA_K7,
        (
            ConceptoDeEstructura("acero", "pza", escalones=_esc((2.0, "EST-10072"), (4.0, "EST-10070"), (6.0, "EST-10071"))),
            ConceptoDeEstructura("colado", "m", "EST-02170"),
        ),
        "EST-02170 y EST-10070, 10071, 10072",
    ),
    _castillo(
        "EST-02180", "K-8", "Castillo K-8 de 15 × 40, 8 var. no.4 y anillo @12 (acero EST-10081)", 40.0,
        ArmadoDeEstructura(varillas=((8, 4, "ACR-00002"),), anillo_insumo="ACE-00006", anillo_sep_cm=12.0, alambre_kg_ml=2.3 / 6.0),
        _CIMBRA_K8,
        (
            ConceptoDeEstructura("acero", "pza", escalones=_esc((6.0, "EST-10081"))),
            ConceptoDeEstructura("colado", "m", "EST-02180"),
            ConceptoDeEstructura("colado", "m", "EJ-780", nuevo=True),
        ),
        "EST-02180 y EST-10081",
        (
            "Vale el acero EST-10081 (Q77). El armex 10×15 que el título del colado EST-02180 menciona es un concepto nuevo "
            "(EJ-780), pendiente de autorizar.",
            "El anillo del catálogo es de 10×25, pero el núcleo de 15 × 40 mide 10 × 35: el contraste muestra la diferencia.",
            _PEND_ESCALONES,
        ),
    ),
    ElementoDeEstructura(
        clave="BAP-03020", alias="KA-1", nombre="Castillo aparente de 25 × 20 con armex 10×15", categoria="castillos",
        subcategoria="aparentes", tipo="castillo", ancho_cm=20.0, largo_cm=25.0, peralte_cm=None,
        armado=ArmadoDeEstructura(armex="ACE-00020", alambre_kg_ml=0.3),
        cimbra=(("ACE-00012", 0.025532), ("ACE-00013", 0.02), ("MAD-00004", 0.01), ("MAD-00030", 0.128205)),
        conceptos=(ConceptoDeEstructura("completo", "m", "BAP-03020"),), fuente="BAP-03020",
        solo_en_catalogo=_APARENTE_SOLO, pendientes=(_PENDIENTE_CHAFLAN, _PENDIENTE_DESTAJO_APARENTE),
    ),
    ElementoDeEstructura(
        clave="BAP-03010", alias="CD-1 aparente", nombre="Cadena de desplante aparente de 15 × 20 con armex 10×15",
        categoria="cadenas", subcategoria="desplante_aparente", tipo="lineal", ancho_cm=15.0, largo_cm=None, peralte_cm=20.0,
        armado=ArmadoDeEstructura(armex="ACE-00020", alambre_kg_ml=0.3),
        cimbra=(("ACE-00012", 0.025532), ("ACE-00013", 0.02), ("MAD-00004", 0.00667), ("MAD-00030", 0.2)),
        conceptos=(ConceptoDeEstructura("completo", "m", "BAP-03010"),), fuente="BAP-03010", posicion="desplante",
        solo_en_catalogo=_APARENTE_SOLO, pendientes=(_PENDIENTE_CHAFLAN, _PENDIENTE_DESTAJO_APARENTE),
    ),
    ElementoDeEstructura(
        clave="BAP-03030", alias="CE-1 aparente", nombre="Cadena de cerramiento aparente de 20 × 25 con armex 10×15",
        categoria="cadenas", subcategoria="cerramiento_aparente", tipo="lineal", ancho_cm=20.0, largo_cm=None, peralte_cm=25.0,
        armado=ArmadoDeEstructura(armex="ACE-00020", alambre_kg_ml=0.3),
        cimbra=(("ACE-00012", 0.025532), ("ACE-00013", 0.02), ("MAD-00004", 0.01), ("MAD-00030", 0.2)),
        conceptos=(ConceptoDeEstructura("completo", "m", "BAP-03030"),), fuente="BAP-03030", posicion="cerramiento",
        solo_en_catalogo=_APARENTE_SOLO, pendientes=(_PENDIENTE_CHAFLAN, _PENDIENTE_DESTAJO_APARENTE),
    ),
)


def _forjada(
    clave: str, alias: str, nombre: str, largo: float, armado: ArmadoDeEstructura, acero: str, fuente: str
) -> ElementoDeEstructura:
    return ElementoDeEstructura(
        clave=clave, alias=alias, nombre=nombre, categoria="columnas", subcategoria="forjada", tipo="castillo", ancho_cm=15.0,
        largo_cm=largo, peralte_cm=None, armado=armado, cimbra=((("MAD-00002"), 1.0),), lados_cimbra=0,
        alto_fijo_m=ALTO_DE_LA_FORJADA_M, forro=Forro(),
        conceptos=(
            ConceptoDeEstructura("acero", "pza", escalones=_esc((6.0, acero))),
            ConceptoDeEstructura("colado", "pza", clave),
        ),
        fuente=fuente,
        pendientes=(
            "El cierre geométrico del forro de 33 × 44 (qué lado lleva la cimbra, las esquinas y los 6 cm que faltan) y la mezcla "
            "del hueco siguen pendientes (Q92 a Q95): el elemento calcula el forro como lo decidió M-126.",
            "El alto es fijo de 4.20 m: otra altura es un concepto nuevo pendiente de autorizar (Q91).",
        ),
    )


_ELEMENTOS = (
    *_ELEMENTOS,
    _forjada(
        "EST-07010", "CM-1", "Columna forjada CM-1 de 33 × 44 × 4.20 (núcleo de 15 × 15 con armex)", 15.0,
        ArmadoDeEstructura(armex="ACE-00011", alambre_kg_ml=0.02), "EST-10011", "EST-07010 y EST-10011",
    ),
    _forjada(
        "EST-07011", "CM-2", "Columna forjada CM-2 de 33 × 44 × 4.20 (núcleo de 15 × 30)", 30.0,
        ArmadoDeEstructura(varillas=((6, 4, "ACR-00002"),), anillo_insumo="ACE-00006", anillo_sep_cm=15.0, alambre_kg_ml=0.17296),
        "EST-10031", "EST-07011 y EST-10031",
    ),
)

ELEMENTOS_DE_ESTRUCTURA: dict[str, ElementoDeEstructura] = {e.clave: e for e in _ELEMENTOS}

_NOMBRES = {
    "castillos": "Castillos",
    "cadenas": "Cadenas",
    "columnas": "Columnas",
}
_SUBCATEGORIAS = {
    ("castillos", "muro"): ("Castillos de muro", "K"),
    ("castillos", "aparentes"): ("Castillos aparentes", "KA"),
    ("cadenas", "desplante_aparente"): ("Cadenas de desplante aparentes", "CDA"),
    ("cadenas", "cerramiento_aparente"): ("Cadenas de cerramiento aparentes", "CEA"),
    ("columnas", "forjada"): ("Columnas forjadas de ladrillo", "CM"),
}
_PREFIJOS = {"castillos": "K", "cadenas": "CE", "columnas": "C"}


def _entrada_de_biblioteca(e: ElementoDeEstructura) -> dict[str, Any]:
    colado = next((c for c in e.conceptos if c.ranura in ("colado", "completo") and not c.nuevo), e.conceptos[0])
    unidad = "m" if colado.unidad == "m" else colado.unidad
    return {
        "clave": e.clave,
        "nombre": f"{e.alias} · {e.nombre}" if e.alias else e.nombre,
        "tipo": "estructura_de_catalogo",
        "se_mide_por": "pieza" if e.tipo == "castillo" and e.forro else "metro lineal",
        "concepto": {"clave": colado.clave or e.clave, "descripcion": e.nombre, "unidad": unidad},
    }


def _categorias_de_biblioteca() -> tuple[dict[str, Any], ...]:
    salida: list[dict[str, Any]] = []
    for cat in ("castillos", "cadenas", "columnas"):
        subs: list[dict[str, Any]] = []
        for (c, s), (nombre, prefijo) in _SUBCATEGORIAS.items():
            if c != cat:
                continue
            elementos = tuple(_entrada_de_biblioteca(e) for e in _ELEMENTOS if (e.categoria, e.subcategoria) == (c, s))
            subs.append({"clave": s, "nombre": nombre, "prefijo": prefijo, "elementos": elementos})
        salida.append({"clave": cat, "nombre": _NOMBRES[cat], "prefijo": _PREFIJOS[cat], "subcategorias": tuple(subs)})
    return tuple(salida)


CATEGORIAS_DE_ESTRUCTURA: tuple[dict[str, Any], ...] = _categorias_de_biblioteca()
"""Lo que estos elementos agregan a la biblioteca (categoría › subcategoría › elemento), en el formato de `BIBLIOTECA`."""


def elemento_de_estructura(clave: str) -> ElementoDeEstructura:
    e = ELEMENTOS_DE_ESTRUCTURA.get(clave.strip())
    if e is None:
        raise ElementoDeEstructuraNoEncontrado(f"No hay un elemento de estructura {clave}.")
    return e


def claves_de_concepto(e: ElementoDeEstructura) -> list[str]:
    """Todas las claves de concepto que paga el elemento (escalones y colado)."""
    salida: list[str] = []
    for c in e.conceptos:
        salida.extend(x.clave for x in c.escalones)
        if c.clave:
            salida.append(c.clave)
    return salida


# --- Cálculo ------------------------------------------------------------------------------------------------------------


def _alto_de(e: ElementoDeEstructura, alto_m: float | None, estandar_m: float | None = None) -> float:
    """El alto del cálculo: el pedido; sin él, el fijo de la forjada; sin ninguno, la altura estándar (la de la obra si se da)."""
    por_defecto = estandar_m if estandar_m is not None else ALTO_ESTANDAR_M
    alto = e.alto_fijo_m if (alto_m is None and e.alto_fijo_m) else (alto_m if alto_m is not None else por_defecto)
    if not (0 < alto <= 30):
        raise ErrorDeEstructura("El alto va en metros, entre 0 y 30.")
    return float(alto)


def _entrada_de_acero(e: ElementoDeEstructura, alto: float, drivers: DriversDeReceta | None, *, cantidad: float = 1.0) -> EntradaRecetaAcero:
    a = e.armado
    forma = "castillo" if e.tipo == "castillo" else "ml"
    ancho, peralte = e.ancho_cm, (e.largo_cm if e.tipo == "castillo" else e.peralte_cm)
    return EntradaRecetaAcero(
        forma=forma,  # type: ignore[arg-type]
        ancho_cm=ancho,
        peralte_cm=float(peralte or 0),
        longitud_m=alto if forma == "castillo" else None,
        lados_cimbra=e.lados_cimbra,
        varillas=[
            GrupoDeVarillas(n, Varilla(ins, num, LARGO_VARILLA_M, _peso_varilla(num)), f"{n} var. no.{num}") for n, num, ins in a.varillas
        ],
        armex=Armex(a.armex, LARGO_ARMEX_M, None) if a.armex else None,
        anillos=[ZonaDeAnillo(a.anillo_sep_cm, PESO_ANILLO_KG_M, None, a.anillo_insumo)] if a.anillo_sep_cm and a.anillo_insumo else [],
        gancho_cm=a.gancho_cm,
        recubrimiento_cm=a.recubrimiento_cm,
        alambre_peso_kg_m=PESO_ALAMBRE_RECOCIDO_KG_M,
        alambre_kg_ml=a.alambre_kg_ml,
        cimbra=[ConsumoDeCimbra(ins, por_ml=q) for ins, q in e.cimbra] if not e.forro else [],
        cantidad=cantidad,
        drivers=drivers or DriversDeReceta(),
    )


def _peso_varilla(numero: int) -> float:
    from obractrl.domain.cuantificacion.elementos_parametricos import PESO_VARILLA_KG_M

    return PESO_VARILLA_KG_M[numero]


def calcular_forro(f: Forro, alto_m: float) -> dict[str, Any]:
    """El forro de tabique por geometría (M-126): una cara de 6×26 frente a la cimbra y dos de 14×26, cada una con el lado
    completo de la sección (las esquinas se cuentan en las dos caras: Q94, pendiente). La cimbra es de un solo lado."""
    pieza_l, pieza_a, pieza_h, j = f.pieza_largo_cm / 100, f.pieza_ancho_cm / 100, f.pieza_alto_cm / 100, f.junta_cm / 100
    w_extremo = f.seccion_ancho_cm / 100
    w_lateral = f.seccion_largo_cm / 100

    def cara(clave: str, etiqueta: str, largo: float, h: float, profundidad: float, n: int) -> dict[str, Any]:
        celda = (pieza_l + j) * (h + j)
        area = n * largo * alto_m
        neto = area / celda
        return {
            "clave": clave,
            "etiqueta": etiqueta,
            "caras": n,
            "largo_m": largo,
            "area_m2": area,
            "hilada_m": h + j,
            "pza_por_m2": 1 / celda,
            "pza_netas": neto,
            "mezcla_neta_m3": neto * (celda - pieza_l * h) * profundidad,
        }

    c1 = cara("6x26", "Cara de 6 × 26 (frente a la cimbra)", w_extremo, pieza_h, pieza_a, 1)
    c2 = cara("14x26", "Caras de 14 × 26", w_lateral, pieza_a, pieza_h, 2)
    neto = c1["pza_netas"] + c2["pza_netas"]
    mezcla_neta = c1["mezcla_neta_m3"] + c2["mezcla_neta_m3"]
    return {
        "caras": [c1, c2],
        "pza_netas": neto,
        "tabique_pza": neto * (1 + f.desperdicio_tabique),
        "mezcla_neta_m3": mezcla_neta,
        "mezcla_m3": mezcla_neta * (1 + f.desperdicio_mezcla),
        "cimbra_m2": w_extremo * alto_m,
        "lados_cimbra": 1,
    }


def _colado_por_ml(e: ElementoDeEstructura, desperdicio: float = DESPERDICIO_CONCRETO) -> dict[str, float]:
    """Concreto y cimbra de un metro del elemento, con los consumos del catálogo. `desperdicio` es una fracción (0.05 = 5 %)."""
    seccion = (e.ancho_cm / 100) * ((e.largo_cm if e.tipo == "castillo" else e.peralte_cm) or 0) / 100
    insumos = {CONCRETO: seccion * (1 + desperdicio)}
    for ins, q in e.cimbra:
        insumos[ins] = insumos.get(ins, 0.0) + q
    return insumos


def _escalon_de(c: ConceptoDeEstructura, alto: float) -> tuple[Escalon | None, bool]:
    """El primer escalón cuyo «hasta» alcanza el alto; si el alto lo rebasa, el último, y se avisa."""
    if not c.escalones:
        return None, False
    ordenados = sorted(c.escalones, key=lambda x: x.hasta_m)
    for esc in ordenados:
        if alto <= esc.hasta_m + _EPS:
            return esc, False
    return ordenados[-1], True


def _insumos_de_acero(receta: dict[str, Any], *, por: float = 1.0) -> dict[str, float]:
    """Lo que el acero de una pieza pide, por unidad del concepto (`por` = divisor: el alto, si el concepto es por metro)."""
    salida: dict[str, float] = {}
    if receta["armex"]:
        salida[receta["armex"]["clave"]] = receta["armex"]["piezas_comerciales"] / por
    for v in receta["varillas"]:
        salida[v["clave"]] = salida.get(v["clave"], 0.0) + v["piezas_comerciales"] / por
    if receta["anillos"]:
        for z in receta["anillos"]["zonas"]:
            clave = z["clave"] or "anillo"
            salida[clave] = salida.get(clave, 0.0) + z["kg"] / por
    if receta["alambre"]["kg"] > 0:
        salida[ALAMBRE] = salida.get(ALAMBRE, 0.0) + receta["alambre"]["kg"] / por
    return salida


def _receta(e: ElementoDeEstructura, alto: float, drivers: DriversDeReceta | None) -> dict[str, Any]:
    return calcular_receta_acero(_entrada_de_acero(e, alto, drivers))


def insumos_del_concepto(
    e: ElementoDeEstructura,
    c: ConceptoDeEstructura,
    alto: float,
    *,
    drivers: DriversDeReceta | None = None,
    desperdicio_concreto: float = DESPERDICIO_CONCRETO,
) -> dict[str, float]:
    """Lo que calcula el elemento por **unidad del concepto** (`{clave del insumo: cantidad}`), con el alto dado.

    - `acero` por pieza: armex o varillas, anillos y alambre de amarre.
    - `colado` por metro: concreto y consumos de cimbra del catálogo. En la forjada, por pieza: forro, concreto del núcleo y
      cimbra de un lado.
    - `completo` por metro: el acero por metro más el colado.
    """
    if c.nuevo:
        return _insumos_de_concepto_nuevo(e, drivers)
    if c.ranura == "acero":
        return _insumos_de_acero(_receta(e, alto, drivers))
    if e.forro is not None:
        forro = calcular_forro(e.forro, alto)
        nucleo = (e.ancho_cm / 100) * ((e.largo_cm or 0) / 100) * alto * (1 + desperdicio_concreto)
        return {
            e.forro.tabique: forro["tabique_pza"],
            e.forro.mezcla: forro["mezcla_m3"],
            CONCRETO: nucleo,
            e.forro.cimbra_insumo: forro["cimbra_m2"],
        }
    colado = _colado_por_ml(e, desperdicio_concreto)
    if c.ranura == "colado":
        return colado
    # completo (aparentes): por metro. El castillo aparente se calcula por pieza y se divide entre su alto.
    if e.tipo == "castillo":
        acero = _insumos_de_acero(_receta(e, alto, drivers), por=alto)
    else:
        acero = _insumos_de_acero(calcular_receta_acero(_entrada_de_acero(e, alto, drivers)))
    for ins, q in colado.items():
        acero[ins] = acero.get(ins, 0.0) + q
    return acero


def _insumos_de_concepto_nuevo(e: ElementoDeEstructura, drivers: DriversDeReceta | None = None) -> dict[str, float]:
    """El concepto nuevo de K-8: el armex 10×15 del colado, de 6 m con el traslape del driver (15 cm), por metro de castillo."""
    drivers = drivers or DriversDeReceta()
    return {"ACE-00020": 1.0 / (LARGO_ARMEX_M - drivers.traslape_armex_cm / 100)}


def concepto_nuevo_por_altura(e: ElementoDeEstructura, alto_m: float) -> dict[str, Any] | None:
    """Q91: la forjada con otra altura que 4.20 m pide un concepto nuevo (el catálogo es por pieza de 4.20 m)."""
    if e.alto_fijo_m is None or abs(alto_m - e.alto_fijo_m) <= _EPS:
        return None
    centimetros = round(alto_m * 100)
    return {
        "clave_propuesta": f"{e.clave}-H{centimetros}"[:20],
        "descripcion": f"{e.nombre.split(' (')[0]} de {alto_m:.2f} m de alto",
        "unidad": "pza",
        "alto_m": alto_m,
    }


def calcular_elemento(
    clave: str,
    alto_m: float | None = None,
    *,
    drivers: DriversDeReceta | None = None,
    desperdicio_concreto: float = DESPERDICIO_CONCRETO,
    alto_estandar_m: float | None = None,
) -> dict[str, Any]:
    """El elemento calculado con el `alto_m` dado (la altura estándar de 3.00 m si no se dice; 4.20 m en la forjada).

    Devuelve la receta del acero, el colado, el forro de la forjada, y por cada concepto lo que calcula el elemento por unidad
    del concepto, con el escalón que corresponde al alto y los avisos."""
    e = elemento_de_estructura(clave)
    alto = _alto_de(e, alto_m, alto_estandar_m)
    avisos: list[str] = []
    nuevo = concepto_nuevo_por_altura(e, alto)
    if nuevo:
        avisos.append(
            f"El catálogo trae {e.clave} solo para {e.alto_fijo_m:.2f} m: con {alto:.2f} m hace falta un concepto nuevo "
            f"({nuevo['clave_propuesta']}), pendiente de autorizar por Control de obra."
        )
    receta = _receta(e, alto, drivers)
    avisos.extend(receta["advertencias"])
    conceptos: list[dict[str, Any]] = []
    for c in e.conceptos:
        esc, rebasa = _escalon_de(c, alto)
        if rebasa and esc is not None:
            avisos.append(
                f"El alto de {alto:.2f} m rebasa el último escalón de acero ({esc.clave}, hasta {esc.hasta_m:.2f} m): se usa ese "
                "mismo concepto y falta uno para la altura (Q80)."
            )
        alto_del_concepto = alto
        concepto_clave = esc.clave if esc else c.clave
        insumos = insumos_del_concepto(e, c, alto_del_concepto, drivers=drivers, desperdicio_concreto=desperdicio_concreto)
        conceptos.append(
            {
                "ranura": c.ranura,
                "unidad": c.unidad,
                "clave": concepto_clave,
                "hasta_m": esc.hasta_m if esc else None,
                "escalones": [{"clave": x.clave, "hasta_m": x.hasta_m} for x in sorted(c.escalones, key=lambda x: x.hasta_m)],
                "nuevo": c.nuevo,
                "rebasa": rebasa,
                "insumos": insumos,
            }
        )
    colado = _colado_por_ml(e, desperdicio_concreto) if not e.forro else {}
    return {
        "clave": e.clave,
        "alias": e.alias,
        "nombre": e.nombre,
        "tipo": e.tipo,
        "categoria": e.categoria,
        "subcategoria": e.subcategoria,
        "posicion": e.posicion,
        "seccion": {"ancho_cm": e.ancho_cm, "largo_cm": e.largo_cm, "peralte_cm": e.peralte_cm},
        "alto_m": alto,
        "alto_fijo": e.alto_fijo_m is not None,
        "unidad_de_calculo": "pza" if e.tipo == "castillo" else "ml",
        "lados_cimbra": e.lados_cimbra if not e.forro else 1,
        "armado": _armado_a_dict(e),
        "acero": receta,
        "colado": {
            "concreto_m3_ml": colado.get(CONCRETO),
            "consumos": [{"clave": k, "cantidad": v} for k, v in colado.items() if k != CONCRETO],
        },
        "forro": calcular_forro(e.forro, alto) if e.forro else None,
        "conceptos": conceptos,
        "concepto_nuevo_por_altura": nuevo,
        "solo_en_catalogo": [{"clave": c, "motivo": m} for c, m in e.solo_en_catalogo],
        "pendientes": list(e.pendientes),
        "advertencias": list(dict.fromkeys(avisos)),
        "fuente": e.fuente,
    }


def _armado_a_dict(e: ElementoDeEstructura) -> dict[str, Any]:
    a = e.armado
    return {
        "tipo": "armex" if a.armex else "varillas",
        "armex": a.armex,
        "varillas": [{"cantidad": n, "numero": num, "insumo": ins} for n, num, ins in a.varillas],
        "anillo": {"insumo": a.anillo_insumo, "sep_cm": a.anillo_sep_cm} if a.anillo_insumo else None,
        "alambre_kg_ml": a.alambre_kg_ml,
    }


def definicion_de(clave: str) -> dict[str, Any]:
    """La ficha del elemento sin calcular: lo que la tarjeta muestra antes de pedir el cálculo."""
    e = elemento_de_estructura(clave)
    return {
        "clave": e.clave,
        "alias": e.alias,
        "nombre": e.nombre,
        "tipo": e.tipo,
        "categoria": {"clave": e.categoria, "nombre": _NOMBRES[e.categoria]},
        "subcategoria": {"clave": e.subcategoria, "nombre": _SUBCATEGORIAS[(e.categoria, e.subcategoria)][0]},
        "seccion": {"ancho_cm": e.ancho_cm, "largo_cm": e.largo_cm, "peralte_cm": e.peralte_cm},
        "posicion": e.posicion,
        "alto_fijo_m": e.alto_fijo_m,
        "alto_por_defecto_m": e.alto_fijo_m or ALTO_ESTANDAR_M,
        "armado": _armado_a_dict(e),
        "conceptos": [
            {
                "ranura": c.ranura,
                "unidad": c.unidad,
                "clave": c.clave,
                "nuevo": c.nuevo,
                "escalones": [{"clave": x.clave, "hasta_m": x.hasta_m} for x in sorted(c.escalones, key=lambda x: x.hasta_m)],
            }
            for c in e.conceptos
        ],
        "pendientes": list(e.pendientes),
        "fuente": e.fuente,
    }
