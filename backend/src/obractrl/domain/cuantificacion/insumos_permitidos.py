"""Qué insumos admite cada tipo de elemento paramétrico (plan de elementos de muro, fase D; M-25, M-28, M-55, M-134).

Cada tipo de elemento solo ofrece los insumos de las **familias** que le corresponden: un castillo, una cadena o una zapata usan
Aceros (armex, anillos, alambre, clavos), Acero De Refuerzo (varillas), concretos (Mezclas · Concretos y Prefabricados ·
Concretos) y la familia nueva **Cimbra**; su mano de obra es la de la subfamilia «Albañilería y Estructura» y su destajo, el de
la subfamilia de su tipo (Castillo, Cadena, Zapata, Muro). Los datos salen de `CATALOGO_DE_MATERIALES`,
`CATALOGO_DE_MANO_DE_OBRA` y `CATALOGO_DE_TRABAJOS` (`1-mundo/opus/`, julio 2026) y de `familias_permitidas_por_tipo_de_elemento`
de la especificación del mockup.

Cuatro **clases** de insumo (M-55): materiales, trabajos y destajos, mano de obra, y **herramienta y equipo**. Esta última es
opcional y el catálogo no trae ningún insumo de ella (Q32): el andamio se ofrece como sugerencia y se crea como insumo
**provisional, sin precio** (M-134); nunca se inventa un precio.

Un insumo de otra familia se rechaza (`InsumoNoPermitido`) con un mensaje que dice cuáles sí admite el tipo. Función pura, sin
base de datos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)

__all__ = [
    "CLASES_DE_INSUMO",
    "FAMILIAS_DE_MATERIAL",
    "FAMILIA_CIMBRA",
    "FAMILIA_HERRAMIENTA_Y_EQUIPO",
    "SUBFAMILIA_DE_MANO_DE_OBRA",
    "SUGERENCIAS_DE_HERRAMIENTA",
    "FamiliaPermitida",
    "Insumo",
    "InsumoNoPermitido",
    "InsumoNuevo",
    "clase_de_insumo",
    "describir_familias",
    "es_permitido",
    "familias_de_clase",
    "normalizar_insumo_nuevo",
    "tipos_con_lista",
    "validar_permitido",
]

CLASES_DE_INSUMO: dict[str, dict[str, str]] = {
    "material": {"nombre": "Materiales", "descripcion": "Aceros, concretos, cimbra, prefabricados…"},
    "trabajo": {"nombre": "Trabajos y destajos", "descripcion": "Destajo por metro o por pieza"},
    "mano_obra": {"nombre": "Mano de obra", "descripcion": "Cuadrillas, oficiales y ayudantes"},
    "herramienta": {"nombre": "Herramienta y equipo", "descripcion": "Opcional; el catálogo aún no trae insumos de esta clase"},
}
"""Las clases de la ventana de agregar insumos (M-55), en el orden en que se ofrecen."""

FAMILIA_CIMBRA = "Cimbra"
FAMILIA_HERRAMIENTA_Y_EQUIPO = "Herramienta y equipo"
SUBFAMILIA_DE_MANO_DE_OBRA = "Albañilería y Estructura"

_RAICES_DE_MANO_DE_OBRA = frozenset(
    {
        "Ayudantes", "Contratistas", "Cuadrillas", "Laboratoristas", "Oficiales calificados", "Oficiales de albañilería",
        "Oficiales de urbanización", "Operadores", "Peones", "Supervisores",
    }
)
"""Las familias de `CATALOGO_DE_MANO_DE_OBRA`: lo que cuelga de ellas es mano de obra; el resto de lo que se paga por obra
hecha (`CATALOGO_DE_TRABAJOS`) es un trabajo o destajo. Los dos se guardan con el mismo tipo de insumo."""

_FAMILIAS_DE_DESTAJO = ("Obra Civil", "Obra Exterior")
"""Los destajos de elementos estructurales y de muro del catálogo de trabajos; los de Albañilería, Acabados y Pinturas son de otros conceptos."""

SUGERENCIAS_DE_HERRAMIENTA: tuple[dict[str, str], ...] = (
    {
        "clave": "INS-A001",
        "descripcion": "ANDAMIO (renta por jornada)",
        "unidad": "jornal",
        "subfamilia": "Andamios",
    },
)
"""El andamio, lo más común (M-134): se crea como insumo provisional sin precio en la clase Herramienta y equipo."""


@dataclass(frozen=True, slots=True)
class FamiliaPermitida:
    familia: str
    subfamilia: str | None = None

    def texto(self) -> str:
        return f"{self.familia} · {self.subfamilia}" if self.subfamilia else self.familia


_ACERO_Y_CONCRETO = (
    FamiliaPermitida("Aceros"),
    FamiliaPermitida("Acero De Refuerzo"),
    FamiliaPermitida("Mezclas", "Concretos"),
    FamiliaPermitida("Prefabricados", "Concretos"),
    FamiliaPermitida(FAMILIA_CIMBRA),
)

FAMILIAS_DE_MATERIAL: dict[str, tuple[FamiliaPermitida, ...]] = {
    "castillo": _ACERO_Y_CONCRETO,
    "lineal": _ACERO_Y_CONCRETO,
    "zapata": _ACERO_Y_CONCRETO,
    "losa": (),
    "muro": (FamiliaPermitida("Pétreos"), FamiliaPermitida("Mezclas", "Morteros")),
    "volumen": (
        FamiliaPermitida("Pétreos"),
        FamiliaPermitida("Mezclas", "Morteros"),
        FamiliaPermitida("Mezclas", "Concretos"),
        FamiliaPermitida("Tuberías"),
    ),
}
"""Las familias de materiales de cada tipo de elemento. La losa tendrá su propia lista cuando se construya (por eso está
vacía y no admite insumos todavía); `muro` y `volumen` son los tipos de las fases siguientes (muros de tabique y de piedra)."""

_SUBFAMILIA_DE_DESTAJO = {"castillo": "Castillo", "lineal": "Cadena", "zapata": "Zapata", "muro": "Muro", "volumen": "Muro"}


class InsumoNoPermitido(ErrorDeElementoParametrico):
    """El insumo es de una familia que el tipo de elemento no admite."""


@dataclass(frozen=True, slots=True)
class Insumo:
    """Un insumo de la base de datos tal como lo necesitan las reglas: su clase y su lugar en el árbol de familias."""

    clave: str
    descripcion: str
    clase: str | None
    familia: str | None
    subfamilia: str | None = None
    unidad: str | None = None
    precio: float | None = None
    provisional: bool = False

    @property
    def sin_precio(self) -> bool:
        return self.precio is None or self.precio <= 0


def clase_de_insumo(tipo: str, familia_raiz: str | None) -> str | None:
    """La clase de un insumo según su tipo en la base y la familia de la que cuelga; `None` si no es una de las cuatro
    (un flete o un subcontrato no se agrega a un elemento)."""
    if tipo == "material":
        return "material"
    if tipo in ("equipo", "herramienta"):
        return "herramienta"
    if tipo == "mano_obra":
        return "mano_obra" if familia_raiz in _RAICES_DE_MANO_DE_OBRA else "trabajo"
    return None


def tipos_con_lista() -> tuple[str, ...]:
    """Los tipos de elemento que ya tienen su lista de insumos."""
    return tuple(t for t, f in FAMILIAS_DE_MATERIAL.items() if f)


def _familias_del_tipo(tipo: str) -> tuple[FamiliaPermitida, ...]:
    if tipo not in FAMILIAS_DE_MATERIAL:
        raise ErrorDeElementoParametrico(f"Tipo de elemento desconocido: {tipo}.")
    return FAMILIAS_DE_MATERIAL[tipo]


def familias_de_clase(tipo: str, clase: str) -> tuple[FamiliaPermitida, ...]:
    """Las familias que admite un elemento de `tipo` en esa clase. En herramienta y equipo no hay restricción de familia
    (una tupla vacía no significa «ninguna»: la clase es opcional y libre); en la losa no hay lista todavía."""
    if clase not in CLASES_DE_INSUMO:
        raise ErrorDeElementoParametrico(f"La clase «{clase}» no existe ({', '.join(CLASES_DE_INSUMO)}).")
    if clase == "material":
        return _familias_del_tipo(tipo)
    if clase == "trabajo":
        sub = _SUBFAMILIA_DE_DESTAJO.get(tipo)
        return tuple(FamiliaPermitida(f, sub) for f in _FAMILIAS_DE_DESTAJO) if sub else ()
    if clase == "mano_obra":
        return (FamiliaPermitida("Mano de obra", SUBFAMILIA_DE_MANO_DE_OBRA),) if _familias_del_tipo(tipo) else ()
    return (FamiliaPermitida(FAMILIA_HERRAMIENTA_Y_EQUIPO),)


def _coincide(regla: FamiliaPermitida, familia: str | None, subfamilia: str | None) -> bool:
    if familia is None or familia.casefold() != regla.familia.casefold():
        return False
    return regla.subfamilia is None or (subfamilia or "").casefold() == regla.subfamilia.casefold()


def describir_familias(tipo: str, clase: str) -> str:
    """Las familias de la clase en palabras, para los mensajes de error."""
    fams = familias_de_clase(tipo, clase)
    if clase == "herramienta":
        return "cualquiera (herramienta y equipo es opcional y libre)"
    return ", ".join(f.texto() for f in fams) or "ninguna todavía"


def es_permitido(tipo: str, insumo: Insumo) -> bool:
    """¿Un elemento de `tipo` admite este insumo? Los materiales por familia (y subfamilia, donde la regla la pide); la mano de
    obra por su subfamilia; el destajo por familia y por la subfamilia de su tipo (si la base no la trae, solo la familia
    decide); la herramienta y el equipo, siempre."""
    reglas = _familias_del_tipo(tipo)
    if insumo.clase == "herramienta":
        return True
    if not reglas:
        return False
    if insumo.clase == "material":
        # La subfamilia «Concretos» es una sola en el árbol de familias aunque cuelgue de Mezclas o de Prefabricados: basta
        # con que la regla de alguna de las dos la pida.
        # Lo mismo la «Cimbra»: es una familia propia desde la 0129, pero un catálogo recién cargado la trae como subfamilia de Maderas.
        sub = (insumo.subfamilia or "").casefold()
        return (
            any(_coincide(r, insumo.familia, insumo.subfamilia) for r in reglas)
            or (sub == "concretos" and any(r.subfamilia == "Concretos" for r in reglas))
            or (sub == FAMILIA_CIMBRA.casefold() and any(r.familia == FAMILIA_CIMBRA for r in reglas))
        )
    if insumo.clase == "mano_obra":
        return (insumo.subfamilia or "").casefold() == SUBFAMILIA_DE_MANO_DE_OBRA.casefold()
    if insumo.clase == "trabajo":
        sub = _SUBFAMILIA_DE_DESTAJO.get(tipo)
        if sub is None or (insumo.familia or "").casefold() not in {f.casefold() for f in _FAMILIAS_DE_DESTAJO}:
            return False
        return insumo.subfamilia is None or insumo.subfamilia.casefold() == sub.casefold()
    return False


def validar_permitido(tipo: str, insumo: Insumo) -> None:
    """Rechaza el insumo de otra familia con un error que dice qué admite el tipo (M-25)."""
    if es_permitido(tipo, insumo):
        return
    clase = insumo.clase
    if clase is None:
        raise InsumoNoPermitido(
            f"{insumo.clave} no es un material, un trabajo, mano de obra ni herramienta o equipo: no se agrega a un elemento."
        )
    if not _familias_del_tipo(tipo):
        raise InsumoNoPermitido(
            f"Un elemento de tipo «{tipo}» aún no tiene lista de insumos permitidos ({'/'.join(tipos_con_lista())} sí la tienen)."
        )
    donde = insumo.familia or "sin familia"
    if insumo.subfamilia and insumo.subfamilia != insumo.familia:
        donde += f" · {insumo.subfamilia}"
    raise InsumoNoPermitido(
        f"{insumo.clave} ({donde}) no es de las familias de un elemento de tipo «{tipo}». "
        f"{CLASES_DE_INSUMO[clase]['nombre']} admitidos: {describir_familias(tipo, clase)}."
    )


_CLAVE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{1,29}$")
_UNIDAD = re.compile(r"^[A-Za-z0-9²³%./ ]{1,12}$")


@dataclass(frozen=True, slots=True)
class InsumoNuevo:
    """Un insumo que el usuario crea desde la tarjeta del elemento: nace **provisional y sin precio** (M-28, M-134)."""

    clase: str
    clave: str
    descripcion: str
    unidad: str
    familia: str
    subfamilia: str | None


def normalizar_insumo_nuevo(
    tipo: str,
    *,
    clase: str,
    clave: str,
    descripcion: str,
    unidad: str,
    familia: str | None,
    subfamilia: str | None = None,
) -> InsumoNuevo:
    """Valida el alta de un insumo desde un elemento de `tipo`. Solo se crea en una familia que el tipo admite: en la clase
    Herramienta y equipo, en su familia propia; no lleva precio (lo asigna Costos)."""
    if clase not in CLASES_DE_INSUMO:
        raise ErrorDeElementoParametrico(f"La clase «{clase}» no existe ({', '.join(CLASES_DE_INSUMO)}).")
    k = " ".join(clave.split()).upper()
    if not _CLAVE.match(k):
        raise ErrorDeElementoParametrico("La clave del insumo lleva de 2 a 30 letras mayúsculas, números, punto, guion o guion bajo.")
    d = " ".join(descripcion.split())
    if not d or len(d) > 200:
        raise ErrorDeElementoParametrico("El insumo necesita una descripción de hasta 200 caracteres.")
    u = " ".join(unidad.split())
    if not _UNIDAD.match(u):
        raise ErrorDeElementoParametrico("El insumo necesita una unidad (pza, kg, m3, jornal…).")
    fam = " ".join((familia or "").split()) or None
    sub = " ".join((subfamilia or "").split()) or None
    if clase == "herramienta":
        fam = FAMILIA_HERRAMIENTA_Y_EQUIPO
    if fam is None:
        raise ErrorDeElementoParametrico("Elige la familia en que se crea el insumo.")
    nuevo = Insumo(clave=k, descripcion=d, clase=clase, familia=fam, subfamilia=sub, unidad=u, precio=None, provisional=True)
    if clase == "mano_obra":
        # La mano de obra nueva se crea en su subfamilia: la familia es una de las de cuadrillas y oficiales.
        nuevo = replace(nuevo, subfamilia=SUBFAMILIA_DE_MANO_DE_OBRA)
        sub = SUBFAMILIA_DE_MANO_DE_OBRA
        if fam not in _RAICES_DE_MANO_DE_OBRA:
            raise InsumoNoPermitido(f"La mano de obra se crea en una de estas familias: {', '.join(sorted(_RAICES_DE_MANO_DE_OBRA))}.")
    if clase == "trabajo" and sub is None:
        sub = _SUBFAMILIA_DE_DESTAJO.get(tipo)
        nuevo = replace(nuevo, subfamilia=sub)
    validar_permitido(tipo, nuevo)
    return InsumoNuevo(clase=clase, clave=k, descripcion=d, unidad=u, familia=fam, subfamilia=sub)

