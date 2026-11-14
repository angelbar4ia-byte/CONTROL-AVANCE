"""La clasificación de los elementos paramétricos en la biblioteca (plan de elementos de muro, fase A; M-29, M-31, M-32).

Cada elemento paramétrico pertenece a una **categoría** (castillos, cadenas, trabes…) y a una **subcategoría** que
identifica su uso (en cadenas: cerramiento o desplante). Tres reglas viven aquí, en el dominio y sin base de datos:

1. **Qué categorías y subcategorías existen** y con qué tipo de elemento se calculan (`CATEGORIAS`). Es la lista del mockup
   para los tipos que ya se persisten (castillo, lineal, zapata, losa); los muros, los muros de cimentación y de contención y
   los pisos son otro motor y no pasan por aquí.
2. **La firma anti-duplicados** (`firma_de_elemento`): la categoría, la subcategoría, el tipo y los parámetros (medidas,
   armado, estribos y lados de cimbra). Dos elementos con la misma firma son el mismo elemento y el segundo no se guarda;
   como la subcategoría forma parte de la firma, una cadena de cerramiento y una de desplante con la misma geometría **no**
   chocan. Desde la migración 0129 también entran los *materiales* del elemento (el insumo del concreto, del alambre, de la
   varilla, del anillo, del armex y los consumos de cimbra; ver `materiales_de_elemento`). La base calcula la misma cadena
   con `app.firma_elemento` (migraciones 0127 y 0129); una prueba de integración comprueba que las dos coincidan.
3. **El límite de posición por subcategoría** (`validar_posicion`): una cadena de desplante solo va al pie del muro; una de
   cerramiento, en el cerramiento o en el remate. La posición no es del elemento sino del muro (un mismo elemento se coloca en
   varias posiciones, M-29): esta regla es la que usará el Artefacto al colocar el elemento.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from typing import Any

from obractrl.domain.cuantificacion.elementos_parametricos import (
    TIPOS_DE_ELEMENTO,
    ErrorDeElementoParametrico,
)

__all__ = [
    "CATEGORIAS",
    "POSICIONES_DE_MURO",
    "ElementoDuplicado",
    "categoria_por_defecto",
    "firma_de_elemento",
    "posiciones_permitidas",
    "validar_clasificacion",
    "validar_posicion",
]

POSICIONES_DE_MURO = ("desplante", "cerramiento", "remate")
"""Dónde se coloca una cadena o una dala en el muro: al pie, entre el cuerpo y el enrase, o al tope."""


def _sub(clave: str, nombre: str, prefijo: str, posiciones: tuple[str, ...] | None = None, *, en_muro: bool = True) -> dict[str, Any]:
    return {"clave": clave, "nombre": nombre, "prefijo": prefijo, "posiciones": posiciones, "en_muro": en_muro}


def _cat(clave: str, nombre: str, tipo: str, prefijo: str, subcategorias: tuple[dict[str, Any], ...], *, construida: bool = True) -> dict[str, Any]:
    return {"clave": clave, "nombre": nombre, "tipo": tipo, "prefijo": prefijo, "construida": construida, "subcategorias": subcategorias}


_CIERRE = ("cerramiento", "remate")

CATEGORIAS: tuple[dict[str, Any], ...] = (
    _cat(
        "castillos", "Castillos", "castillo", "K",
        (
            _sub("muro", "Castillos de muro", "K"),
            _sub("pretil", "Castillos de pretil", "KP"),
            _sub("aparentes", "Castillos aparentes", "KA"),
        ),
    ),
    _cat(
        "columnas", "Columnas", "castillo", "C",
        (
            _sub("concreto", "Columnas de concreto", "C"),
            _sub("forjada", "Columnas forjadas de ladrillo", "CM", en_muro=False),
        ),
    ),
    _cat(
        "cadenas", "Cadenas", "lineal", "CE",
        (
            _sub("cerramiento", "Cadenas de cerramiento", "CE", _CIERRE),
            _sub("desplante", "Cadenas de desplante", "CD", ("desplante",)),
            _sub("desplante_aparente", "Cadenas de desplante aparentes", "CDA", ("desplante",)),
            _sub("cerramiento_aparente", "Cadenas de cerramiento aparentes", "CEA", _CIERRE),
        ),
    ),
    _cat(
        "dalas", "Dalas", "lineal", "DA",
        (
            _sub("cerramiento", "Dalas de cerramiento (sobre vanos)", "DC", ("cerramiento",)),
            _sub("repison", "Dalas de repisón (bajo vanos)", "DR", ("cerramiento",)),
        ),
    ),
    _cat(
        "trabes", "Trabes", "lineal", "T",
        (
            _sub("losa", "Trabes de losa (catálogo)", "T", en_muro=False),
            _sub("piso", "Trabes de piso", "T", en_muro=False),
            _sub("cubierta", "Trabes de cubierta", "TC", en_muro=False),
        ),
    ),
    _cat("contratrabes", "Contratrabes", "lineal", "CT", (_sub("cimentacion", "Contratrabes de cimentación", "CT", en_muro=False),)),
    _cat("nervaduras", "Nervaduras", "lineal", "N", (_sub("losa_nervada", "Nervaduras de losa nervada", "N", en_muro=False),)),
    _cat(
        "zapatas", "Zapatas", "zapata", "Z",
        (
            _sub("aislada", "Zapatas aisladas", "Z", en_muro=False),
            _sub("corrida", "Zapatas corridas", "ZC", en_muro=False),
        ),
    ),
    _cat("dados", "Dados", "zapata", "D", (_sub("cimentacion", "Dados de cimentación", "D", en_muro=False),), construida=False),
    _cat(
        "losas", "Losas", "losa", "L",
        (_sub("maciza", "Losas macizas", "L", en_muro=False), _sub("nervada", "Losas nervadas", "L", en_muro=False)),
        construida=False,
    ),
)
"""La biblioteca de los elementos que se calculan con la receta paramétrica. `construida` dice si el mockup ya la construyó;
las que no (dados, losas) se aceptan igual porque un elemento de tipo `zapata` o `losa` ya se puede guardar."""

_POR_CLAVE = {c["clave"]: c for c in CATEGORIAS}

_POR_DEFECTO = {
    "castillo": ("castillos", "muro"),
    "lineal": ("cadenas", "cerramiento"),
    "zapata": ("zapatas", "aislada"),
    "losa": ("losas", "maciza"),
}
"""La clasificación de un elemento al que no se le dijo: la misma con que la migración 0127 rellenó los que ya existían."""


class ElementoDuplicado(ErrorDeElementoParametrico):
    """Ya hay un elemento idéntico (misma categoría, subcategoría, medidas y armado): se usa el existente (M-29)."""

    def __init__(self, clave_igual: str, elemento_id: Any = None) -> None:
        self.clave_igual = clave_igual
        self.elemento_id = elemento_id
        super().__init__(
            f"Ya existe un elemento idéntico: {clave_igual} (misma categoría, subcategoría, medidas, armado y cimbra). "
            "Usa el existente en lugar de guardar otro igual."
        )


def categoria_por_defecto(tipo: str) -> tuple[str, str]:
    """La categoría y la subcategoría con que nace un elemento del `tipo` si nadie las eligió."""
    if tipo not in _POR_DEFECTO:
        raise ErrorDeElementoParametrico(f"Tipo de elemento desconocido: {tipo}.")
    return _POR_DEFECTO[tipo]


def _subcategoria(categoria: str, subcategoria: str) -> dict[str, Any]:
    cat = _POR_CLAVE.get(categoria)
    if cat is None:
        raise ErrorDeElementoParametrico(f"La categoría «{categoria}» no existe en la biblioteca ({', '.join(_POR_CLAVE)}).")
    for sub in cat["subcategorias"]:
        if sub["clave"] == subcategoria:
            return sub  # type: ignore[no-any-return]
    validas = ", ".join(s["clave"] for s in cat["subcategorias"])
    raise ErrorDeElementoParametrico(f"La subcategoría «{subcategoria}» no existe en {cat['nombre']} ({validas}).")


def validar_clasificacion(tipo: str, categoria: str | None, subcategoria: str | None) -> tuple[str, str]:
    """Completa y valida la categoría y la subcategoría de un elemento de `tipo`; devuelve el par ya limpio.

    Sin categoría ni subcategoría, toma las de defecto del tipo. Con la categoría sola toma su primera subcategoría. La
    categoría debe calcularse con el mismo tipo de elemento (un castillo no va en Cadenas)."""
    if tipo not in TIPOS_DE_ELEMENTO:
        raise ErrorDeElementoParametrico(f"Tipo de elemento desconocido: {tipo}.")
    cat_def, sub_def = categoria_por_defecto(tipo)
    cat = (categoria or "").strip().lower() or None
    sub = (subcategoria or "").strip().lower() or None
    if cat is None and sub is None:
        return cat_def, sub_def
    if cat is None:
        cat = cat_def
    if sub is None:
        sub = _POR_CLAVE[cat]["subcategorias"][0]["clave"] if cat in _POR_CLAVE else sub_def
    _subcategoria(cat, sub)
    if _POR_CLAVE[cat]["tipo"] != tipo:
        raise ErrorDeElementoParametrico(
            f"{_POR_CLAVE[cat]['nombre']} se calcula como «{_POR_CLAVE[cat]['tipo']}»; un elemento de tipo «{tipo}» no va ahí."
        )
    return cat, sub


def posiciones_permitidas(categoria: str, subcategoria: str) -> tuple[str, ...] | None:
    """Dónde del muro se puede colocar un elemento de esa subcategoría; `None` si no se coloca por posición (un castillo, una
    trabe) y entonces no hay límite que validar."""
    posiciones = _subcategoria(categoria, subcategoria)["posiciones"]
    return tuple(posiciones) if posiciones else None


def validar_posicion(categoria: str, subcategoria: str, posicion: str) -> None:
    """La posición en que se coloca el elemento debe ser una que su subcategoría permite (M-32: la de desplante solo va al pie)."""
    if posicion not in POSICIONES_DE_MURO:
        raise ErrorDeElementoParametrico(f"La posición «{posicion}» no existe ({', '.join(POSICIONES_DE_MURO)}).")
    permitidas = posiciones_permitidas(categoria, subcategoria)
    if permitidas is None:
        raise ErrorDeElementoParametrico(f"Un elemento de {_subcategoria(categoria, subcategoria)['nombre']} no se coloca por posición.")
    if posicion not in permitidas:
        nombre = _subcategoria(categoria, subcategoria)["nombre"]
        raise ErrorDeElementoParametrico(
            f"{nombre} solo se coloca en {' o '.join(permitidas)}, no en {posicion}."
        )


def _numero(valor: Any) -> str:
    """El número como lo escribe la base: redondeado a 6 decimales y sin ceros sobrantes (`0.2`, `4`, `0.025`)."""
    texto = format(Decimal(repr(round(float(valor), 6))).normalize(), "f")
    return "0" if texto in ("-0", "") else texto


def _cuerpo_de_materiales(materiales: dict[str, Any]) -> str:
    """Los materiales como los escribe la base: por orden de clave, `m.concreto=MEZ-01020`; la cimbra, sus consumos por insumo."""
    partes = []
    for k in sorted(materiales):
        v = materiales[k]
        if k == "cimbra":
            partes.append("m.cimbra=" + ",".join(f"{c}:{_numero(v[c])}" for c in sorted(v)))
        else:
            partes.append(f"m.{k}={v}")
    return ";".join(partes)


def firma_de_elemento(
    categoria: str, subcategoria: str, tipo: str, parametros: dict[str, Any], materiales: dict[str, Any] | None = None
) -> str:
    """La identidad de un elemento: dos con la misma firma son duplicados. `parametros` y `materiales` deben venir ya
    normalizados. Sin materiales elegidos la firma es la de antes de la 0129 (los elementos existentes no la cambian)."""
    cuerpo = ";".join(f"{k}={_numero(parametros[k])}" for k in sorted(parametros))
    base = f"{categoria}|{subcategoria}|{tipo}|{cuerpo}"
    if materiales:
        base += "|" + _cuerpo_de_materiales(materiales)
    return hashlib.sha256(base.encode()).hexdigest()
