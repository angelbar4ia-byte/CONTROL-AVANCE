"""Los materiales que un elemento paramétrico elige de la base de datos de insumos (plan de elementos de muro, fase D; M-25, M-27).

La receta (`elementos_parametricos.receta`) calcula **cuánto** concreto, acero, estribos, alambre y cimbra lleva una muestra;
los materiales dicen **con qué insumo** se paga cada parte: el concreto (`MEZ-01020`), el alambre de amarre (`ACE-00001`), la
varilla, el anillo o el armex y los consumos de cimbra por unidad (clavos, tablas, alambre). Hasta la migración 0129 no se
guardaban; ahora forman parte de la identidad del elemento (entran a la firma anti-duplicados).

Aquí solo viven las reglas puras: qué claves existen, cómo se normalizan y a qué familia debe pertenecer el insumo de cada una.
La existencia del insumo en la base la comprueba el caso de uso.
"""

from __future__ import annotations

import math
import re
from typing import Any

from obractrl.domain.cuantificacion.elementos_parametricos import (
    PESO_VARILLA_KG_M,
    VARA_COMERCIAL_M,
    ErrorDeElementoParametrico,
    normalizar_parametros,
    receta,
    toma_por_unidad,
)
from obractrl.domain.cuantificacion.insumos_permitidos import (
    FAMILIA_CIMBRA,
    Insumo,
    InsumoNoPermitido,
    validar_permitido,
)

__all__ = [
    "MATERIALES_ESCALARES",
    "cantidades_por_insumo",
    "claves_de_materiales",
    "normalizar_materiales",
    "validar_materiales",
]

MATERIALES_ESCALARES: dict[str, str] = {
    "concreto": "Concreto",
    "alambre": "Alambre de amarre",
    "varilla": "Varilla longitudinal",
    "anillo": "Anillo o estribo",
    "armex": "Armex",
}
"""Cada material con un solo insumo, y cómo se llama en pantalla. La cimbra va aparte: son varios consumos (`cimbra`)."""

_CLAVE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{1,29}$")

_FAMILIAS_POR_MATERIAL: dict[str, tuple[tuple[str, str | None], ...]] = {
    "concreto": (("Mezclas", "Concretos"), ("Prefabricados", "Concretos")),
    "alambre": (("Aceros", None),),
    "varilla": (("Acero De Refuerzo", None),),
    "anillo": (("Aceros", None),),
    "armex": (("Aceros", None),),
    "cimbra": ((FAMILIA_CIMBRA, None), ("Aceros", None)),
}
"""La familia a la que debe pertenecer el insumo de cada material (el selector del mockup filtra por `grupo`): la cimbra
admite sus propios insumos y el alambre y los clavos, que son Aceros · Consumible."""


def _clave(valor: Any, que: str) -> str:
    k = " ".join(str(valor).split()).upper()
    if not _CLAVE.match(k):
        raise ErrorDeElementoParametrico(f"La clave del insumo de {que} no vale: «{valor}».")
    return k


def normalizar_materiales(materiales: dict[str, Any] | None) -> dict[str, Any]:
    """Limpia y valida los materiales de un elemento. Lo vacío se descarta: `{}` es «sin materiales elegidos».

    Claves: `concreto`, `alambre`, `varilla`, `anillo`, `armex` (la clave del insumo) y `cimbra` (`{clave del insumo: consumo
    por unidad de cálculo del elemento}`, mayor que cero)."""
    salida: dict[str, Any] = {}
    for k, v in (materiales or {}).items():
        if v is None or v == "" or v == {}:
            continue
        if k in MATERIALES_ESCALARES:
            salida[k] = _clave(v, MATERIALES_ESCALARES[k].lower())
        elif k == "cimbra":
            if not isinstance(v, dict):
                raise ErrorDeElementoParametrico("Los consumos de cimbra son un objeto {clave del insumo: consumo}.")
            consumos: dict[str, float] = {}
            for ins, q in v.items():
                try:
                    c = float(q)
                except (TypeError, ValueError):
                    raise ErrorDeElementoParametrico(f"El consumo de {ins} debe ser un número.") from None
                if not math.isfinite(c) or c <= 0 or c > 10000:
                    raise ErrorDeElementoParametrico(f"El consumo de {ins} debe ser mayor que cero.")
                clave = _clave(ins, "cimbra")
                if clave in consumos:
                    raise ErrorDeElementoParametrico(f"{clave} está repetido en los consumos de cimbra.")
                consumos[clave] = c
            salida[k] = dict(sorted(consumos.items()))
        else:
            validos = ", ".join([*MATERIALES_ESCALARES, "cimbra"])
            raise ErrorDeElementoParametrico(f"El material «{k}» no existe ({validos}).")
    return salida


def claves_de_materiales(materiales: dict[str, Any]) -> list[tuple[str, str]]:
    """Cada insumo elegido con el material al que sirve: `[("concreto", "MEZ-01020"), ("cimbra", "MAD-00001")…]`."""
    pares = [(k, str(materiales[k])) for k in MATERIALES_ESCALARES if k in materiales]
    pares += [("cimbra", c) for c in dict(materiales.get("cimbra") or {})]
    return pares


def _sirve_de(material: str, ins: Insumo) -> bool:
    """¿El insumo es de una de las familias de su parte? La subfamilia «Concretos» es una sola en el árbol de familias aunque
    cuelgue de Mezclas o de Prefabricados: para el concreto basta con ella."""
    fam, sub = (ins.familia or "").casefold(), (ins.subfamilia or "").casefold()
    if (material == "concreto" and sub == "concretos") or (material == "cimbra" and sub == FAMILIA_CIMBRA.casefold()):
        return True
    return any(fam == f.casefold() and (s is None or sub == s.casefold()) for f, s in _FAMILIAS_POR_MATERIAL[material])


def validar_materiales(tipo: str, materiales: dict[str, Any], insumos: dict[str, Insumo | None]) -> None:
    """Cada insumo elegido debe existir, ser un material y ser de las familias de su parte (y del tipo de elemento).

    `insumos` es la lectura de la base por clave (`None` si no existe)."""
    for material, clave in claves_de_materiales(materiales):
        ins = insumos.get(clave)
        if ins is None:
            raise ErrorDeElementoParametrico(f"El insumo {clave} no existe en la base de datos: créalo antes de elegirlo.")
        if ins.clase != "material":
            raise InsumoNoPermitido(f"{clave} no es un material: el {material} del elemento se elige entre materiales.")
        validar_permitido(tipo, ins)
        if not _sirve_de(material, ins):
            nombre = MATERIALES_ESCALARES.get(material, "cimbra").lower()
            admitidas = ", ".join(f"{f} · {s}" if s else f for f, s in _FAMILIAS_POR_MATERIAL[material])
            raise InsumoNoPermitido(f"{clave} no sirve de {nombre}: debe ser de {admitidas}.")


def _peso_medio_de_varilla(tipo: str, p: dict[str, Any]) -> float:
    """kg por metro de la varilla longitudinal del elemento (promedio ponderado si arriba y abajo llevan distinta)."""
    pv = PESO_VARILLA_KG_M
    if tipo == "castillo":
        return float(pv[int(p["no_var"])])
    if tipo == "lineal":
        n = p["n_sup"] + p["n_inf"]
        return float((p["n_sup"] * pv[int(p["no_sup"])] + p["n_inf"] * pv[int(p["no_inf"])]) / n)
    return float(pv[int(p["no_par"])])


def cantidades_por_insumo(
    tipo: str,
    parametros: dict[str, Any],
    materiales: dict[str, Any],
    *,
    unidad: str,
    toma: dict[str, bool],
    unidades_de_insumo: dict[str, str],
    lados: int | None = None,
) -> tuple[dict[str, float], list[str]]:
    """Lo que el elemento lleva **de cada insumo, por unidad del concepto** que paga las partes de `toma`: la receta
    (`toma_por_unidad`) puesta en los insumos que el elemento eligió.

    - concreto (m³) → el insumo de `concreto`; alambre de amarre (kg) → `alambre`;
    - acero → `varilla`: en kg si el insumo se cuenta en kg, y en piezas de 12 m (kg ÷ peso por metro ÷ 12) si es pieza;
    - estribos → `anillo`: en kg, o en piezas si el insumo se cuenta en piezas;
    - cimbra → cada consumo de `cimbra` (por unidad de cálculo del elemento: pieza, ml…; en un castillo que se cuenta en ml se
      divide entre su alto).

    Devuelve las cantidades por clave y los **avisos** de lo que no se puede calcular (un armex elegido: la receta del elemento
    aún no lo cuenta; o una parte tomada sin insumo elegido)."""
    p = normalizar_parametros(tipo, dict(parametros))
    t = toma_por_unidad(tipo, p, unidad, toma, lados)
    por = {m: v["cantidad"] for m, v in t["por_unidad"].items()}
    div = float(p["alto"]) if (tipo == "castillo" and unidad == "ml") else 1.0
    r = receta(tipo, p)
    salida: dict[str, float] = {}
    avisos: list[str] = []

    def sumar(clave: str, cantidad: float) -> None:
        salida[clave] = salida.get(clave, 0.0) + cantidad

    def en(clave: str) -> str:
        return unidades_de_insumo.get(clave, "").strip().lower()

    if "concreto" in por:
        if "concreto" in materiales:
            sumar(materiales["concreto"], por["concreto"])
        else:
            avisos.append("El concepto toma el concreto pero el elemento no eligió su insumo de concreto.")
    if "alambre" in por:
        if "alambre" in materiales:
            sumar(materiales["alambre"], por["alambre"])
        else:
            avisos.append("El concepto toma el alambre de amarre pero el elemento no eligió su insumo.")
    if "acero" in por:
        if "armex" in materiales and "varilla" not in materiales:
            avisos.append("El armex no se cuenta todavía en la receta del elemento: sale solo en el catálogo.")
        elif "varilla" in materiales:
            clave = materiales["varilla"]
            kg = por["acero"]
            if en(clave) in ("pza", "pz", "pieza"):
                sumar(clave, kg / (_peso_medio_de_varilla(tipo, p) * VARA_COMERCIAL_M))
            else:
                sumar(clave, kg)
        else:
            avisos.append("El concepto toma el acero pero el elemento no eligió su varilla.")
    if "estribos" in por:
        if "anillo" in materiales:
            clave = materiales["anillo"]
            if en(clave) in ("pza", "pz", "pieza"):
                sumar(clave, float(r["n_estribos"]) / div)
            else:
                sumar(clave, por["estribos"])
        else:
            avisos.append("El concepto toma los estribos pero el elemento no eligió su anillo.")
    if "cimbra" in por:
        consumos = dict(materiales.get("cimbra") or {})
        if not consumos:
            avisos.append("El concepto toma la cimbra pero el elemento no tiene consumos de cimbra (clavos, tablas…).")
        for clave, c in consumos.items():
            sumar(clave, float(c) / div)
    return salida, avisos
