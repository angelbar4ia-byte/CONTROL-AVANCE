"""Las correcciones al catálogo de los castillos, aparentes y forjadas, como **versiones propuestas** de concepto (Ola 3, lane 3A).

El usuario decidió (Q78, Q79, Q81, Q77, Q91) que lo que el catálogo trae mal **no se edita**: ni los CSV de opus ni el
catálogo. Cada corrección es una **nueva versión propuesta del concepto** que Control de obra autoriza (Ola 2C: Costos
propone, Control de obra autoriza, cada autorización crea la versión siguiente). Y la conciliación muestra, insumo por insumo, el
catálogo vigente, la versión propuesta y lo que calcula el elemento.

Hay dos clases de propuesta:

- `version_de_concepto`: cambia coeficientes de un concepto que ya está en el catálogo (EST-10070, 10071 y 10072 traen menos armex
  del que pide el corte con puntas de 50 cm (Q22); los kg del anillo pasan a lo que el elemento calcula; el concreto de los aparentes pasa a la
  medida de su título). Un destajo que no corresponde a la medida **no se cambia aquí**: queda anotado «por definir» para
  Costos (no se inventan destajos ni precios).
- `concepto_nuevo`: un concepto que el catálogo no trae (el armex 10×15 del colado de K-8, una forjada de otra altura). Nace
  pendiente y sin precio.

`antes` son los coeficientes netos del catálogo, tomados de `ANALISIS_DE_BASICOS_CONCEPTOS.csv` (una prueba los compara con el
CSV cuando lo encuentra). Funciones puras, sin base de datos.

**Q78 / D1 (decidido por el usuario el 2026-11-19):** «llevar los kg de anillo a lo real» es *igualar el catálogo al cálculo del
elemento* (perímetro del núcleo más 10 cm de gancho). Los kg del catálogo son menores que el cálculo en la mayoría de los castillos
(0.37 contra 0.50 m en K-2), así que ahí la corrección **sube** el anillo; en K-4 y K-8 lo baja. Esa opción queda como versión
**propuesta**; la opción «respetar el catálogo» queda **activa** (el catálogo vigente no se toca) y la conciliación muestra la
diferencia. Cuando se revise, Control de obra autoriza cuál de las dos queda.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from obractrl.domain.cuantificacion.comparacion_con_catalogo import (
    FilaDeComposicion,
    comparar_con_concepto,
    marca_de,
)
from obractrl.domain.cuantificacion.correcciones_de_trabes import (
    correcciones_de_elemento_lineal,
)
from obractrl.domain.cuantificacion.elementos_lineales import elemento_estructural
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)
from obractrl.domain.cuantificacion.estructura_de_catalogo import (
    ALTO_ESTANDAR_M,
    ConceptoDeEstructura,
    ElementoDeEstructura,
    concepto_nuevo_por_altura,
    elemento_de_estructura,
    insumos_del_concepto,
)

__all__ = [
    "CLASES_DE_PROPUESTA",
    "COEFICIENTES_DEL_CATALOGO",
    "alto_de_comparacion",
    "conciliar_con_catalogo",
    "correcciones_de",
    "numero_de_version",
    "propuesta_de_concepto_nuevo",
]

CLASES_DE_PROPUESTA = ("version_de_concepto", "concepto_nuevo")

COEFICIENTES_DEL_CATALOGO: dict[tuple[str, str], float] = {
    ("EST-10072", "ACE-00020"): 0.333333,
    ("EST-10070", "ACE-00020"): 0.666667,
    ("EST-10071", "ACE-00020"): 0.833333,
    ("EST-10020", "ACE-00003"): 1.9173,
    ("EST-10021", "ACE-00003"): 2.739,
    ("EST-10031", "ACE-00006"): 6.51882,
    ("EST-10041", "ACE-00004"): 6.474,
    ("EST-10051", "ACE-00002"): 9.0,
    ("EST-10060", "ACE-00003"): 2.739,
    ("EST-10081", "ACE-00006"): 16.0,
    ("BAP-03010", "MEZ-01020"): 0.0525,
    ("BAP-03030", "MEZ-01020"): 0.0315,
}
"""Los coeficientes netos del catálogo que se corrigen (la suma de los renglones de `ANALISIS_DE_BASICOS_CONCEPTOS.csv`: el de
EST-10051 suma 8.81958 + 0.18042 de alambrón; el de EST-10081 suma 16.29705 − 0.29705 de anillo)."""

_UNIDADES = {"ACE-00020": "pza", "ACE-00003": "kg", "ACE-00006": "kg", "ACE-00004": "kg", "ACE-00002": "kg", "MEZ-01020": "m³"}

_DESTAJO_POR_DEFINIR = {
    "BAP-03010": {
        "destajo": "MOE-02202",
        "dice": "MO CADENA CD-1 APARENTE (20X25)",
        "corresponde": "15 × 20",
    },
    "BAP-03020": {
        "destajo": "MOE-02025",
        "dice": "MO CASTILLOS K9 (15X25) APARENTE",
        "corresponde": "25 × 20",
    },
}
"""Aparentes cuyo destajo no corresponde a la medida de su título (Q81). No se cambia ni se inventa: queda por definir."""

_MOTIVOS = {
    "Q22": "Q22: el armex de K-7 se corta con módulos de 1 a 6 m, traslape de 15 cm y puntas de 50 cm (confirmado por el usuario): el catálogo trae menos armex del que ese corte pide.",
    "Q78": "Q78 / D1: los kg de anillo del catálogo difieren del perímetro del núcleo más el gancho; la propuesta los iguala al cálculo del elemento y el catálogo vigente sigue activo hasta que Control de obra autorice cuál queda.",
    "Q81": "Q81: el concreto del aparente se lleva a la medida de su título.",
}


def alto_de_comparacion(e: ElementoDeEstructura, c: ConceptoDeEstructura) -> float:
    """El alto con que se compara un concepto sin escalón: el alto fijo de la forjada o la altura estándar. Un concepto con
    escalón se compara a su «hasta»: el catálogo lo calcula para esa altura."""
    if c.escalones:
        return max(x.hasta_m for x in c.escalones)
    return e.alto_fijo_m or ALTO_ESTANDAR_M


def _insumos_de_escalon(e: ElementoDeEstructura, c: ConceptoDeEstructura, hasta_m: float) -> dict[str, float]:
    return insumos_del_concepto(e, c, hasta_m)


def _cambio(concepto: str, insumo: str, despues: float) -> dict[str, Any]:
    return {
        "insumo": insumo,
        "unidad": _UNIDADES.get(insumo, ""),
        "antes": COEFICIENTES_DEL_CATALOGO[(concepto, insumo)],
        "despues": round(despues, 6),
    }


def correcciones_de(clave: str) -> list[dict[str, Any]]:
    """Las propuestas que el elemento trae de fábrica: una por concepto del catálogo que se corrige y, en K-8, el concepto nuevo.
    Las trabes (T-2-12x20, T-5-12x30) las corrige `correcciones_de_trabes`."""
    if elemento_estructural(clave) is not None:
        return correcciones_de_elemento_lineal(clave)
    e = elemento_de_estructura(clave)
    propuestas: list[dict[str, Any]] = []
    for c in e.conceptos:
        if c.nuevo:
            propuestas.append(propuesta_de_concepto_nuevo(e, c))
            continue
        # La forjada paga el acero del castillo de su núcleo (EST-10011, EST-10031): ese acero lo corrige el castillo dueño.
        for esc in ([] if e.forro else sorted(c.escalones, key=lambda x: x.hasta_m)):
            cambios: list[dict[str, Any]] = []
            motivos: list[str] = []
            if (esc.clave, "ACE-00020") in COEFICIENTES_DEL_CATALOGO:
                # Q22: el cálculo con puntas de 50 cm manda (1.33 pza a 6.00 m, 1.0 a 4.00 m, 0.5 a 2.00 m).
                cambios.append(_cambio(esc.clave, "ACE-00020", _insumos_de_escalon(e, c, esc.hasta_m)["ACE-00020"]))
                motivos.append(_MOTIVOS["Q22"])
            ins = e.armado.anillo_insumo
            if ins and (esc.clave, ins) in COEFICIENTES_DEL_CATALOGO:
                real = _insumos_de_escalon(e, c, esc.hasta_m)[ins]
                cambios.append(_cambio(esc.clave, ins, real))
                motivos.append(_MOTIVOS["Q78"])
            if cambios:
                propuestas.append(_version(e, esc.clave, cambios, motivos, esc.hasta_m))
        if c.clave and c.ranura in ("completo", "colado") and not c.escalones:
            cambios = []
            if (c.clave, "MEZ-01020") in COEFICIENTES_DEL_CATALOGO:
                medida = e.ancho_cm * (e.peralte_cm or e.largo_cm or 0) / 10000
                cambios.append(_cambio(c.clave, "MEZ-01020", medida * 1.05))
            if cambios or c.clave in _DESTAJO_POR_DEFINIR:
                propuestas.append(_version(e, c.clave, cambios, [_MOTIVOS["Q81"]], None))
    return _sin_repetir(propuestas)


def _sin_repetir(propuestas: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dos propuestas del mismo concepto se juntan en una (un concepto con concreto y destajo por corregir)."""
    por_concepto: dict[str, dict[str, Any]] = {}
    for p in propuestas:
        previa = por_concepto.get(p["concepto_clave"])
        if previa is None:
            por_concepto[p["concepto_clave"]] = p
            continue
        previa["detalle"]["cambios"].extend(p["detalle"]["cambios"])
        previa["detalle"]["motivos"] = list(dict.fromkeys([*previa["detalle"]["motivos"], *p["detalle"]["motivos"]]))
        previa["resumen"] = _resumen(previa["concepto_clave"], previa["detalle"]["cambios"], previa["detalle"].get("destajo"))
    return list(por_concepto.values())


def _resumen(concepto: str, cambios: Sequence[Mapping[str, Any]], destajo: Mapping[str, Any] | None) -> str:
    partes = [f"{c['insumo']} {c['antes']:g} → {c['despues']:g}" for c in cambios]
    if destajo:
        partes.append(f"destajo {destajo['destajo']} por definir (dice {destajo['dice']}; corresponde {destajo['corresponde']})")
    return f"Nueva versión de {concepto}: " + "; ".join(partes)


def _version(
    e: ElementoDeEstructura, concepto: str, cambios: list[dict[str, Any]], motivos: list[str], hasta_m: float | None
) -> dict[str, Any]:
    destajo = _DESTAJO_POR_DEFINIR.get(concepto)
    detalle: dict[str, Any] = {"cambios": cambios, "motivos": motivos, "hasta_m": hasta_m}
    if destajo:
        detalle["destajo"] = dict(destajo)
    return {
        "elemento_clave": e.clave,
        "concepto_clave": concepto,
        "clase": "version_de_concepto",
        "resumen": _resumen(concepto, cambios, destajo),
        "detalle": detalle,
    }


def propuesta_de_concepto_nuevo(
    e: ElementoDeEstructura, c: ConceptoDeEstructura | None = None, *, alto_m: float | None = None
) -> dict[str, Any]:
    """Un concepto nuevo: el armex 10×15 del colado de K-8 (Q77) o la forjada de otra altura (Q91). Sin precio ni destajo."""
    if c is not None and c.nuevo:
        insumos = insumos_del_concepto(e, c, ALTO_ESTANDAR_M)
        return {
            "elemento_clave": e.clave,
            "concepto_clave": c.clave,
            "clase": "concepto_nuevo",
            "resumen": f"Concepto nuevo {c.clave}: colocación del armex 10×15 del colado de {e.alias or e.clave} (por metro), sin precio",
            "detalle": {
                "descripcion": f"Armex 10×15 del colado del castillo {e.alias or e.clave} (15 × 40), por metro",
                "unidad": c.unidad,
                "insumos": insumos,
                "motivos": ["Q77: en K-8 vale el acero EST-10081; el armex 10×15 del colado pasa a concepto nuevo."],
                "cambios": [],
            },
        }
    if alto_m is None:
        raise ErrorDeElementoParametrico("Falta el alto del concepto nuevo.")
    nuevo = concepto_nuevo_por_altura(e, alto_m)
    if nuevo is None:
        raise ErrorDeElementoParametrico(f"{e.clave} ya existe en el catálogo para {alto_m:.2f} m: no hace falta un concepto nuevo.")
    return {
        "elemento_clave": e.clave,
        "concepto_clave": nuevo["clave_propuesta"],
        "clase": "concepto_nuevo",
        "resumen": f"Concepto nuevo {nuevo['clave_propuesta']}: {nuevo['descripcion']}, sin precio ni destajo",
        "detalle": {
            "descripcion": nuevo["descripcion"],
            "unidad": nuevo["unidad"],
            "alto_m": alto_m,
            "motivos": ["Q91: la columna forjada es de 4.20 m fijos; otra altura es un concepto nuevo pendiente de autorizar."],
            "cambios": [],
        },
    }


def numero_de_version(clase: str, autorizadas: Iterable[int]) -> int:
    """La versión que se crea al autorizar. Un concepto del catálogo ya vale como versión 1, así que su primera versión
    propuesta autorizada es la 2; un concepto nuevo nace en la 1."""
    if clase not in CLASES_DE_PROPUESTA:
        raise ErrorDeElementoParametrico(f"Clase de propuesta desconocida: {clase}.")
    piso = 1 if clase == "version_de_concepto" else 0
    return max((int(v) for v in autorizadas), default=piso) + 1


def conciliar_con_catalogo(
    clave: str,
    composiciones: Mapping[str, Sequence[FilaDeComposicion]],
    *,
    propuestas: Sequence[Mapping[str, Any]] = (),
    descripciones: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """El elemento contra el catálogo, concepto por concepto y por insumo.

    `composiciones` trae la composición del catálogo de cada concepto, con los auxiliares ya expandidos hasta los insumos
    (`expandir_composicion`); un concepto sin composición (nuevo, o que la base no tiene) se muestra solo con lo del elemento.
    `propuestas` son las versiones propuestas o autorizadas del concepto (`estado` pendiente o autorizada): cada fila trae el valor
    propuesto y su marca contra el cálculo. Lo que el catálogo trae y el elemento no calcula sale «solo en el catálogo»."""
    e = elemento_de_estructura(clave)
    solo = dict(e.solo_en_catalogo)
    por_concepto: dict[str, list[Mapping[str, Any]]] = {}
    for p in propuestas:
        por_concepto.setdefault(str(p["concepto_clave"]), []).append(p)
    bloques: list[dict[str, Any]] = []
    for c in e.conceptos:
        escalones = sorted(c.escalones, key=lambda x: x.hasta_m) if c.escalones else [None]
        for esc in escalones:
            concepto = esc.clave if esc else c.clave
            hasta = esc.hasta_m if esc else alto_de_comparacion(e, c)
            calculo = insumos_del_concepto(e, c, hasta)
            composicion = list(composiciones.get(str(concepto), ())) if not c.nuevo else []
            comparado = comparar_con_concepto(
                {k.upper(): v for k, v in calculo.items()}, composicion, descripciones=dict(descripciones or {})
            )
            mias = por_concepto.get(str(concepto), [])
            for fila in comparado["filas"]:
                fila["motivo"] = solo.get(fila["clave"]) if fila["marca"] == "solo_catalogo" else None
                fila["propuesta"] = _propuesta_de(fila, mias)
            comparado["resumen"] = {
                m: sum(1 for f in comparado["filas"] if f["marca"] == m) for m in ("=", "≈", "≠", "solo_catalogo", "solo_elemento")
            }
            bloques.append(
                {
                    "concepto_clave": concepto,
                    "ranura": c.ranura,
                    "unidad": c.unidad,
                    "alto_m": hasta,
                    "hasta_m": esc.hasta_m if esc else None,
                    "nuevo": c.nuevo,
                    "sin_catalogo": not composicion,
                    "propuestas": [
                        {k: p.get(k) for k in ("id", "estado", "version", "resumen", "clase")} for p in mias
                    ],
                    **comparado,
                }
            )
    return {
        "elemento_clave": e.clave,
        "umbral_igual_pct": 3.0,
        "umbral_aproximado_pct": 8.0,
        "conceptos": bloques,
    }


def _propuesta_de(fila: Mapping[str, Any], propuestas: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """El valor propuesto para el insumo de la fila (la propuesta autorizada gana a la pendiente) y su marca contra el cálculo."""
    elegida: dict[str, Any] | None = None
    for p in sorted(propuestas, key=lambda x: 0 if x.get("estado") == "autorizada" else 1):
        for cambio in dict(p.get("detalle") or {}).get("cambios", []):
            if str(cambio["insumo"]).upper() == str(fila["clave"]).upper():
                marca, dif = marca_de(float(cambio["despues"]), fila["elemento"])
                elegida = {
                    "valor": float(cambio["despues"]),
                    "estado": p.get("estado"),
                    "propuesta_id": p.get("id"),
                    "marca": marca,
                    "diferencia_pct": round(dif * 100, 2) if dif is not None else None,
                }
                break
        if elegida:
            break
    return elegida
