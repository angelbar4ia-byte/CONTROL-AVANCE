"""Comparación del elemento contra el concepto del catálogo, insumo por insumo (plan de elementos de muro, fase D; M-46, M-135).

El concepto del catálogo trae su composición real (`ANALISIS_DE_BASICOS_CONCEPTOS` y `ANALISIS_DE_BASICOS_COMPUESTOS`): cuánto
lleva de cada insumo por unidad. El elemento calcula lo suyo con su receta. Esta función los pone lado a lado y marca cada
insumo con la **diferencia** del elemento contra el catálogo:

- ``=``  hasta 3 % de diferencia (coincide);
- ``≈``  de más de 3 % y hasta 8 % (diferencia explicable: el traslape de 40 diámetros contra el 8 % del catálogo, el desperdicio);
- ``≠``  más de 8 %;
- ``solo_catalogo`` / ``solo_elemento`` cuando un lado no trae el insumo.

Los umbrales son los del mockup (`contrasteHTML`). La **mano de obra y el destajo no se comparan**: el elemento no los calcula,
van en el concepto (se listan aparte, con su costo). Una composición puede traer el mismo insumo varias veces, con cantidades que
se compensan (el catálogo resta con una cantidad negativa): se suman por clave. Lo que el catálogo contradice **no se corrige**
aquí: se muestra. Función pura, sin base de datos.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "UMBRAL_APROXIMADO",
    "UMBRAL_IGUAL",
    "FilaDeComposicion",
    "comparar_con_concepto",
    "expandir_composicion",
    "marca_de",
]

UMBRAL_IGUAL = 0.03
"""Hasta esta fracción de diferencia, el insumo «coincide» (=)."""

UMBRAL_APROXIMADO = 0.08
"""Hasta esta fracción es «aproximado» (≈); más es distinto (≠)."""

_EPS = 1e-12


@dataclass(frozen=True, slots=True)
class FilaDeComposicion:
    """Un renglón de la composición de un concepto del catálogo."""

    clave: str
    cantidad: float
    descripcion: str = ""
    unidad: str = ""
    es_mano_de_obra: bool = False
    costo: float | None = None


def marca_de(catalogo: float | None, elemento: float | None) -> tuple[str, float | None]:
    """La marca y la diferencia (fracción del catálogo) de un insumo. `diferencia` es `None` si no se puede dividir."""
    if elemento is None:
        return "solo_catalogo", None
    if catalogo is None:
        return "solo_elemento", None
    if abs(catalogo) <= _EPS:
        return ("=", 0.0) if abs(elemento) <= _EPS else ("≠", None)
    dif = (elemento - catalogo) / catalogo
    ad = abs(dif)
    if ad <= UMBRAL_IGUAL + _EPS:
        return "=", dif
    if ad <= UMBRAL_APROXIMADO + _EPS:
        return "≈", dif
    return "≠", dif


def _sumar(filas: Iterable[FilaDeComposicion]) -> tuple[dict[str, float], dict[str, FilaDeComposicion], list[FilaDeComposicion]]:
    cantidades: dict[str, float] = {}
    datos: dict[str, FilaDeComposicion] = {}
    mano: dict[str, FilaDeComposicion] = {}
    for f in filas:
        if f.es_mano_de_obra:
            previa = mano.get(f.clave)
            mano[f.clave] = f if previa is None else FilaDeComposicion(
                f.clave, previa.cantidad + f.cantidad, previa.descripcion or f.descripcion, previa.unidad or f.unidad, True, previa.costo if previa.costo is not None else f.costo
            )
            continue
        cantidades[f.clave] = cantidades.get(f.clave, 0.0) + f.cantidad
        datos.setdefault(f.clave, f)
    return cantidades, datos, list(mano.values())


def comparar_con_concepto(
    elemento: dict[str, float],
    composicion: Iterable[FilaDeComposicion],
    *,
    descripciones: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compara lo que calcula el elemento (`{clave del insumo: cantidad por unidad del concepto}`) con la composición del
    concepto del catálogo. Devuelve `filas` (una por insumo, por clave), `mano_de_obra` (lo que el elemento no calcula) y el
    `resumen` con el conteo de cada marca."""
    catalogo, datos, mano = _sumar(composicion)
    descripciones = descripciones or {}
    filas: list[dict[str, Any]] = []
    for clave in [*catalogo, *(k for k in elemento if k not in catalogo)]:
        c = catalogo.get(clave)
        e = elemento.get(clave)
        marca, dif = marca_de(c, e)
        d = datos.get(clave)
        filas.append(
            {
                "clave": clave,
                "descripcion": (d.descripcion if d and d.descripcion else descripciones.get(clave, "")),
                "unidad": d.unidad if d else "",
                "catalogo": c,
                "elemento": e,
                "diferencia": dif,
                "diferencia_pct": round(dif * 100, 2) if dif is not None else None,
                "marca": marca,
            }
        )
    resumen = {m: sum(1 for f in filas if f["marca"] == m) for m in ("=", "≈", "≠", "solo_catalogo", "solo_elemento")}
    return {
        "filas": filas,
        "mano_de_obra": [
            {"clave": m.clave, "descripcion": m.descripcion, "unidad": m.unidad, "cantidad": m.cantidad, "costo": m.costo} for m in mano
        ],
        "resumen": resumen,
        "coincide": resumen["≠"] == 0 and resumen["solo_catalogo"] == 0 and resumen["solo_elemento"] == 0,
    }


def expandir_composicion(
    filas: Iterable[dict[str, Any]], clave_raiz: str, *, profundidad_maxima: int = 12
) -> list[FilaDeComposicion]:
    """La composición de un concepto con sus auxiliares **expandidos hasta los insumos** (el AUX-04010 de un muro se vuelve las
    50 piezas de tabique y la mezcla que lo forman). `filas` son las de `Explosion` de todo lo alcanzable, con `concepto_clave`,
    `tipo_hijo`, `categoria`, `cantidad`, `insumo_clave`, `concepto_hijo_clave`, `costo_unitario` (como las da
    `RepositorioConceptosSQL.composicion_recursiva`). Solo `material` se compara; mano de obra, destajo, subcontrato y equipo se
    marcan `es_mano_de_obra`. Un ciclo se corta."""
    por_padre: dict[str, list[dict[str, Any]]] = {}
    for f in filas:
        por_padre.setdefault(str(f["concepto_clave"]), []).append(f)
    salida: list[FilaDeComposicion] = []

    def recorrer(clave: str, factor: float, camino: tuple[str, ...]) -> None:
        if clave in camino or len(camino) > profundidad_maxima:
            return
        for f in por_padre.get(clave, []):
            cantidad = float(f["cantidad"] or 0) * factor
            if f["tipo_hijo"] == "concepto":
                recorrer(str(f["concepto_hijo_clave"]), cantidad, (*camino, clave))
            else:
                costo = f.get("costo_unitario")
                salida.append(
                    FilaDeComposicion(
                        clave=str(f["insumo_clave"]),
                        cantidad=cantidad,
                        es_mano_de_obra=str(f["categoria"]) != "material",
                        costo=float(costo) if costo is not None else None,
                    )
                )

    recorrer(clave_raiz, 1.0, ())
    return salida
