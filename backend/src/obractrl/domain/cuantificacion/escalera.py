"""La escalera como ELEMENTO (Fase 4a: escaleras con cotas): un elemento paramétrico que sale de la diferencia de cotas de las zonas de losa.

Decisión del usuario (2026-11-21, «Fase 4») y de la nota de las zonas (2026-11-16): la escalera **sale de la diferencia de cotas** de las zonas de losa
(cotas relativas al piso terminado de PB = 0: ``losa_zona.cota_piso_m`` y la cara alta de la losa). Es una familia nueva de la biblioteca (categoría
«Escaleras») con su propia tabla de zona (``escalera_zona``, migración 0145); no es parte de la matriz de la losa: el hueco de la escalera ya se resta del
área de la losa (``hueco_de``), así que la losa y la escalera no cuentan lo mismo dos veces.

Qué hay en la biblioteca
------------------------
- **ESC-FORJADA**, escalera forjada de concreto armado. Se paga con el concepto **existente** del catálogo ``EST-01510`` («Escalera forjada de una rampa de concreto
  armado con varilla de no.3 @20 cms en ambos sentidos», por **pza**). Regla F7: se liga a un concepto que ya existe. Qué es una «pieza»: el material del usuario la
  cuenta como **un escalón de 1.20 m de largo** (la hoja ESCALERA del paramétrico de Oro: «Escalón forjado de concreto armado (escalón de 1.20 m)», 18 escalones en
  planta baja y 6 en la alta, y la cantidad escala con el largo ÷ 1.20). Aquí la cantidad es ``peldaños × ancho ÷ 1.20``. Su composición real
  (``ANALISIS_DE_BASICOS_CONCEPTOS`` líneas 800 a 807) es 0.060583 m³ de concreto ``CON-00004``, 0.4 pza de varilla de 3/8 ``ACR-00001``, 0.44444 kg de alambre
  recocido, 0.0575 m³ de mezcla 1:4, 0.1633 pza de cimbraplay, 10 tabiques y los destajos ``MOE-02311`` (por pieza) y ``MOE-02312`` (descimbra, por m²). El elemento
  calcula concreto y acero **por geometría** y los concilia contra esa composición sin editarla; tabique, mezcla y cimbraplay no se calculan (el catálogo no explica
  cómo se rellena el peldaño): salen «solo en el catálogo».
- **El descanso** entre rampas (cuando hay más de una): el catálogo no trae un descanso de concreto (``HER-03010`` es de herrería), así que se propone el
  concepto nuevo ``EJ-820`` por m² (clave **provisional**, sin precio, pendiente de autorizar por Control de obra, regla F7). Mientras no esté autorizado y en
  el catálogo, su cantidad se informa pero **no se escribe** en ninguna partida.

Cómo se mide (valores conservadores, ver ``PENDIENTES``)
--------------------------------------------------------
    desnivel      = cota de llegada − cota de arranque
    peldaños      = el tecleado, o  ⌈desnivel ÷ contrahuella máxima⌉
    contrahuella  = desnivel ÷ peldaños
    huella        = la tecleada, o  recorrido ÷ (peldaños − rampas)  si el recorrido sale de una línea del plano

Con la contrahuella máxima de 18 cm un desnivel de 3.12 m (3.00 m de altura libre más 12 cm de losa) da 18 peldaños y uno de 1.08 m da 6: los de la hoja de Oro.
Las rampas reparten los peldaños (las primeras reciben el sobrante); entre ellas hay un **descanso** de ``ancho × largo del descanso`` (por omisión cuadrado).
Rampa y descanso son de concreto con el mismo espesor (12 cm, el de la losa por omisión y el que implican 0.060583 m³ de concreto por escalón sobre la superficie
inclinada del peldaño). El acero por m² de rampa o de descanso es el de la **parrilla** del catálogo ``AUX-06010`` (varilla del no. 3 @ 20 cm: el mismo armado
que dice el concepto), el mismo dato que ya usa la losa maciza.

Medición derivada: una línea del plano (``trazo_id``) da el **recorrido horizontal** de las rampas; con la escala del plano sale la huella al calcular, sin guardarla.

Mano de obra: ninguna se calcula con importe. Los destajos ``MOE-02311`` y ``MOE-02312`` del catálogo se listan y no se les pone precio. Sin precios.
Función pura, sin base de datos; no lee ningún driver de la obra.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "CLAVE_DE_ESCALERA",
    "COMPOSICION_DEL_ESCALON",
    "CONCEPTO_DE_DESCANSO",
    "CONCEPTO_DE_ESCALON",
    "DEFECTOS",
    "DESTAJOS_DEL_ESCALON",
    "LARGO_BASE_DEL_ESCALON_M",
    "PARRILLA_POR_M2",
    "PENDIENTES",
    "EntradaEscalera",
    "ErrorDeEscalera",
    "calcular_escalera",
    "categorias_de_biblioteca",
    "concepto_nuevo_de_descanso",
    "definicion_de_escalera",
    "elemento_de_escalera",
    "solapes_de_escaleras",
    "validar_parametros",
]

CLAVE_DE_ESCALERA = "ESC-FORJADA"
"""El elemento de la biblioteca (categoría Escaleras)."""

LARGO_BASE_DEL_ESCALON_M = 1.20
"""El largo del escalón de 1.20 m que cuenta el catálogo por pieza (hoja ESCALERA del paramétrico de Oro: la cantidad escala con el largo ÷ 1.20)."""

CONCEPTO_DE_ESCALON: dict[str, Any] = {
    "clave": "EST-01510",
    "descripcion": (
        "Escalera forjada de una rampa de concreto armado con varilla de no.3 @20 cms en ambos sentidos. Incluye: Limpieza, cimbra, descimbra, armado, colado, "
        "materiales, mano de obra, herramientas, equipo y todo lo necesario para una correcta ejecución."
    ),
    "unidad": "pza",
    "estado": "catalogo",
    "provisional": False,
}
"""El concepto EXISTENTE del catálogo (CATALOGO_DE_MATRICES, por pza = escalón de 1.20 m) con que se paga la escalera. No se edita."""

CONCEPTO_DE_DESCANSO: dict[str, Any] = {
    "clave": "EJ-820",
    "descripcion": "Descanso de escalera forjada de concreto armado por m²: concreto, cimbra y parrilla de acero",
    "unidad": "m²",
    "estado": "propuesto",
    "provisional": True,
}
"""El concepto nuevo del descanso (regla F7): el catálogo no trae uno de concreto. Clave **provisional**, propuesto, sin precio ni destajo."""

COMPOSICION_DEL_ESCALON: tuple[tuple[str, str, str, float, str], ...] = (
    ("CON-00004", "CONCRETO BOMBEADO 250 RAPISO 7 DIAS REVENIMIENTO (LOSAS AZOTEA Y ROOF)", "m³", 0.060583, "ANALISIS_DE_BASICOS_CONCEPTOS:800"),
    ("ACE-00001", "ALAMBRE RECOCIDO", "kg", 0.44444, "ANALISIS_DE_BASICOS_CONCEPTOS:801"),
    ("MEZ-07010", "MEZCLA CEMENTO-ARENA 1:4", "m³", 0.0575, "ANALISIS_DE_BASICOS_CONCEPTOS:802"),
    ("MAD-00003", "CIMBRAPLAY 12 MM", "pza", 0.1633, "ANALISIS_DE_BASICOS_CONCEPTOS:803"),
    ("PET-00001", "TABIQUE", "pza", 10.0, "ANALISIS_DE_BASICOS_CONCEPTOS:804"),
    ("ACR-00001", "VARILLA 3/8", "pza", 0.4, "ANALISIS_DE_BASICOS_CONCEPTOS:805"),
)
"""Los materiales de la composición de EST-01510 **por escalón** (clave, descripción, unidad, cantidad, línea del CSV). Dato del catálogo, no un cálculo."""

DESTAJOS_DEL_ESCALON: tuple[tuple[str, str, str, float, str], ...] = (
    ("MOE-02311", "MO ARMADO Y COLADO ESCALERA", "pza", 1.0, "ANALISIS_DE_BASICOS_CONCEPTOS:806"),
    ("MOE-02312", "MO DESCIMBRA ESCALERA", "m²", 0.486111, "ANALISIS_DE_BASICOS_CONCEPTOS:807"),
)
"""Los destajos de la composición de EST-01510 (tipo «Contrato»). Se listan; el elemento no les pone importe."""

PARRILLA_POR_M2: tuple[tuple[str, str, str, float, str], ...] = (
    ("ACR-00001", "VARILLA 3/8", "pza", 0.9, "ANALISIS_DE_BASICOS_COMPUESTOS:139"),
    ("ACE-00001", "ALAMBRE RECOCIDO", "kg", 0.20685, "ANALISIS_DE_BASICOS_COMPUESTOS:140"),
)
"""El auxiliar ``AUX-06010`` (varilla del no. 3 @ 20 cm) **por m²**: el armado que dice el concepto de la escalera. El mismo dato de la losa maciza."""

CONCRETO = {"clave": "CON-00004", "descripcion": "CONCRETO BOMBEADO 250 RAPISO 7 DIAS REVENIMIENTO (LOSAS AZOTEA Y ROOF)", "unidad": "m³"}
"""El concreto de la composición de EST-01510 (el mismo de las losas de azotea y roof)."""

CIMBRA_DEL_DESCANSO = {"clave": "MAD-00001", "descripcion": "CIMBRA 3 MTS", "unidad": "m²"}
"""La cimbra de la losa del catálogo, en m²: el descanso la usa como la losa (1 m² por m² de descanso)."""

DEFECTOS: dict[str, Any] = {
    "peldanos": None,
    "contrahuella_max_m": 0.18,
    "huella_m": 0.25,
    "ancho_m": LARGO_BASE_DEL_ESCALON_M,
    "espesor_m": 0.12,
    "rampas": 1,
    "largo_descanso_m": None,
}
"""Los parámetros por omisión. Todos son editables; ninguno es un precio. ``peldanos`` y ``largo_descanso_m`` nulos se calculan (del desnivel; igual al ancho)."""

PENDIENTES: tuple[dict[str, str], ...] = (
    {
        "clave": "E1",
        "texto": "EST-01510 se cobra por «pza». El material del usuario la cuenta como un escalón de 1.20 m de largo (hoja ESCALERA de Oro: 18 + 6 escalones) y escala con el "
        "largo ÷ 1.20; el nombre del concepto dice «de una rampa». Se toma el escalón de 1.20 m: piezas = peldaños × ancho ÷ 1.20. ¿Confirmas que la pieza es el escalón?",
    },
    {
        "clave": "E2",
        "texto": "El material del usuario no da la contrahuella ni la huella. Valores de referencia por omisión (editables): contrahuella máxima de 18 cm y huella de 25 cm; con "
        "ellos un desnivel de 3.12 m da 18 peldaños y uno de 1.08 m da 6, como la hoja de Oro. El ancho vale 1.20 m (el del escalón del catálogo) y el espesor de rampa y "
        "descanso, 12 cm. ¿Cuáles son los valores del proyecto?",
    },
    {
        "clave": "E3",
        "texto": "Cotas: la escalera arranca en la cota del piso de su zona y llega a la de otra zona (o a la cara alta de su propia losa); se pueden teclear las dos. El desnivel "
        "es llegada − arranque. Si la escalera sube a una losa, su hueco debe estar dibujado como hueco del polígono de losa: el elemento no lo resta del área de la losa.",
    },
    {
        "clave": "E4",
        "texto": "El concreto y el acero se calculan por geometría (superficie inclinada de la rampa × espesor; acero de la parrilla AUX-06010 por m²) y se concilian contra la "
        "composición de EST-01510 por escalón; la diferencia se muestra, no se corrige. Tabique (10 por escalón), mezcla 1:4 y cimbraplay no se calculan: el catálogo no "
        "explica el relleno del peldaño ni la hoja de cimbra.",
    },
    {
        "clave": "E5",
        "texto": "El descanso entre rampas no tiene concepto de concreto en el catálogo: se paga con el concepto nuevo EJ-820 por m² (propuesto, clave provisional, sin precio). "
        "Cuenta en una partida solo cuando se autorice y esté en el catálogo.",
    },
    {
        "clave": "E6",
        "texto": "La receta de la escalera de Oro trae también el forrado del escalón (ACA-02210, Brunei 60×60), los spots (IEC-01240 y IEC-20030, uno cada 3 escalones) y el "
        "barandal (HER-02020): son acabado, instalación y herrería; no entran en este elemento. ¿Se ligan a la escalera?",
    },
    {
        "clave": "E7",
        "texto": "Medición derivada: una línea del plano da el recorrido horizontal de las rampas y de ella sale la huella (recorrido ÷ (peldaños − rampas)). Una línea no sirve a "
        "dos escaleras. Sin escala calibrada se toma 1 unidad de plano = 1 m.",
    },
    {
        "clave": "E8",
        "texto": "La clave provisional EJ-820 (descanso) la confirma Control de obra al autorizar.",
    },
)
"""Lo que el material del usuario no resuelve y se dejó con valor conservador."""

_EPS = 1e-9
_DESNIVEL_MAXIMO_M = 15.0
_PELDANOS_MAXIMOS = 120


class ErrorDeEscalera(ErrorDeCuantificacion):
    """Un dato que no vale: la escalera no se puede calcular con él."""


# --------------------------------------------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EntradaEscalera:
    cota_arranque_m: float
    cota_llegada_m: float
    peldanos: int | None = None
    """Si no viene, salen del desnivel y de la contrahuella máxima."""
    contrahuella_max_m: float = 0.18
    huella_m: float = 0.25
    recorrido_m: float | None = None
    """El recorrido horizontal de las rampas, si sale de una línea del plano: manda sobre ``huella_m``."""
    ancho_m: float = LARGO_BASE_DEL_ESCALON_M
    espesor_m: float = 0.12
    rampas: int = 1
    largo_descanso_m: float | None = None
    """Sin él, el descanso es cuadrado (largo = ancho)."""
    espacio_id: str | None = None


# --------------------------------------------------------------------------------------------------------------
# Biblioteca
# --------------------------------------------------------------------------------------------------------------

NOMBRE = "Escalera forjada"
SE_MIDE_POR = "escalones de 1.20 m según el desnivel entre cotas de las zonas del plano"


def elemento_de_escalera(clave: str) -> bool:
    """¿La clave es el elemento de escalera de la biblioteca (``ESC-FORJADA``)?"""
    return clave == CLAVE_DE_ESCALERA


def categorias_de_biblioteca() -> tuple[dict[str, Any], ...]:
    """La categoría Escaleras de la biblioteca (forma de `BIBLIOTECA`): la escalera forjada."""
    c = CONCEPTO_DE_ESCALON
    return (
        {
            "clave": "escaleras",
            "nombre": "Escaleras",
            "prefijo": "ESC",
            "subcategorias": (
                {
                    "clave": "forjadas",
                    "nombre": "Escaleras forjadas",
                    "prefijo": "ESC",
                    "elementos": (
                        {
                            "clave": CLAVE_DE_ESCALERA,
                            "nombre": NOMBRE,
                            "tipo": "escalera",
                            "se_mide_por": SE_MIDE_POR,
                            "concepto": {"clave": c["clave"], "descripcion": c["descripcion"], "unidad": c["unidad"]},
                        },
                    ),
                },
            ),
        },
    )


def _insumo_de_ficha(f: tuple[str, str, str, float, str]) -> dict[str, Any]:
    return {"clave": f[0], "descripcion": f[1], "unidad": f[2], "por_escalon": f[3], "fuente": f[4]}


def definicion_de_escalera(clave: str) -> dict[str, Any] | None:
    """La ficha del elemento: qué calcula, qué toma del catálogo, sus dos conceptos y los pendientes."""
    if not elemento_de_escalera(clave):
        return None
    c, d = CONCEPTO_DE_ESCALON, CONCEPTO_DE_DESCANSO
    return {
        "clave": clave,
        "nombre": NOMBRE,
        "se_mide_por": SE_MIDE_POR,
        "categoria": {"clave": "escaleras", "nombre": "Escaleras"},
        "subcategoria": {"clave": "forjadas", "nombre": "Escaleras forjadas"},
        "concepto": {"clave": c["clave"], "descripcion": c["descripcion"], "unidad": c["unidad"], "estado": c["estado"], "provisional": c["provisional"]},
        "concepto_del_descanso": {
            "clave": d["clave"], "descripcion": d["descripcion"], "unidad": d["unidad"], "estado": d["estado"], "provisional": d["provisional"],
        },
        "largo_base_del_escalon_m": LARGO_BASE_DEL_ESCALON_M,
        "parametros_por_defecto": dict(DEFECTOS),
        "composicion_del_escalon": [_insumo_de_ficha(f) for f in COMPOSICION_DEL_ESCALON],
        "parrilla_por_m2": [{"clave": f[0], "descripcion": f[1], "unidad": f[2], "por_m2": f[3], "fuente": f[4]} for f in PARRILLA_POR_M2],
        "destajos_candidatos": [{"clave": f[0], "descripcion": f[1], "unidad": f[2]} for f in DESTAJOS_DEL_ESCALON],
        "pendientes": [dict(p) for p in PENDIENTES],
    }


def concepto_nuevo_de_descanso() -> dict[str, Any]:
    """La propuesta de concepto nuevo del descanso por m² (clase ``concepto_nuevo``): clave provisional, sin destajo ni precio. Los insumos son los de **un m² de
    referencia** (espesor de 12 cm); el elemento los recalcula con el espesor de cada escalera."""
    d = CONCEPTO_DE_DESCANSO
    espesor = float(DEFECTOS["espesor_m"])
    insumos: dict[str, float] = {CONCRETO["clave"]: round(espesor, 6), CIMBRA_DEL_DESCANSO["clave"]: 1.0}
    for f in PARRILLA_POR_M2:
        insumos[f[0]] = round(f[3], 6)
    return {
        "elemento_clave": CLAVE_DE_ESCALERA,
        "concepto_clave": d["clave"],
        "clase": "concepto_nuevo",
        "resumen": f"Concepto nuevo {d['clave']} (clave provisional): {d['descripcion']}, por m², sin destajo ni precio",
        "detalle": {
            "descripcion": d["descripcion"],
            "unidad": "m²",
            "clave_provisional": True,
            "toma": {"concreto": True, "cimbra": True, "acero": True},
            "insumos": insumos,
            "motivos": [
                "Fase 4a de la losa (regla F7): el descanso de la escalera es parte de un elemento nuevo y lleva su concepto en el catálogo; el catálogo solo trae el "
                "escalón forjado EST-01510 por pieza y un descanso de herrería (HER-03010), ninguno de concreto.",
                "Los insumos son los de un m² de referencia (12 cm de concreto, cimbra y la parrilla AUX-06010): el elemento los recalcula con el espesor de cada escalera.",
                "Sin destajo: el catálogo no trae uno para el descanso. Sin precio.",
                "Clave provisional: pendiente de autorizar por Control de obra.",
            ],
            "cambios": [],
        },
    }


# --------------------------------------------------------------------------------------------------------------
# Validación
# --------------------------------------------------------------------------------------------------------------

_RANGOS: dict[str, tuple[float, float]] = {
    "contrahuella_max_m": (0.10, 0.30),
    "huella_m": (0.15, 0.60),
    "ancho_m": (0.40, 5.00),
    "espesor_m": (0.05, 0.50),
}


def validar_parametros(parametros: dict[str, Any]) -> dict[str, Any]:
    """Los parámetros de la escalera normalizados (con los de omisión donde falten). Rechaza lo que no vale. ``peldanos`` y ``largo_descanso_m`` nulos se dejan nulos."""
    p = {**DEFECTOS, **{k: v for k, v in parametros.items() if v is not None}}
    for campo, (minimo, maximo) in _RANGOS.items():
        valor = p[campo]
        if isinstance(valor, bool) or not isinstance(valor, int | float) or not math.isfinite(valor):
            raise ErrorDeEscalera(f"«{campo}» debe ser un número.")
        if not minimo - _EPS <= valor <= maximo + _EPS:
            raise ErrorDeEscalera(f"«{campo}» va de {minimo:g} a {maximo:g}.")
        p[campo] = float(valor)
    rampas = p["rampas"]
    if isinstance(rampas, bool) or not isinstance(rampas, int) or not 1 <= rampas <= 4:
        raise ErrorDeEscalera("«rampas» va de 1 a 4.")
    if p["peldanos"] is not None:
        n = p["peldanos"]
        if isinstance(n, bool) or not isinstance(n, int) or not 2 <= n <= _PELDANOS_MAXIMOS:
            raise ErrorDeEscalera(f"«peldanos» va de 2 a {_PELDANOS_MAXIMOS}.")
        if n < 2 * rampas:
            raise ErrorDeEscalera("Cada rampa lleva al menos 2 peldaños.")
    if p["largo_descanso_m"] is not None:
        valor = p["largo_descanso_m"]
        if isinstance(valor, bool) or not isinstance(valor, int | float) or not 0.40 - _EPS <= valor <= 6.0 + _EPS:
            raise ErrorDeEscalera("«largo_descanso_m» va de 0.4 a 6.")
        p["largo_descanso_m"] = float(valor)
    return {k: p[k] for k in DEFECTOS}


def solapes_de_escaleras(filas: Sequence[dict[str, Any]]) -> list[str]:
    """Las escaleras de una zona que contarían dos veces lo mismo: dos sobre la misma línea del plano. `filas`: `{id, trazo_id}`. Devuelve los motivos."""
    vistos: set[str] = set()
    motivos: list[str] = []
    for f in filas:
        t = f.get("trazo_id")
        if t and str(t) in vistos:
            motivos.append("Hay dos escaleras sobre la misma línea del plano: se contaría su recorrido dos veces.")
        if t:
            vistos.add(str(t))
    return motivos


# --------------------------------------------------------------------------------------------------------------
# Cálculo
# --------------------------------------------------------------------------------------------------------------


def _reparto(peldanos: int, rampas: int) -> list[int]:
    """Los peldaños de cada rampa: parejos, y las primeras reciben el sobrante."""
    base, extra = divmod(peldanos, rampas)
    return [base + (1 if r < extra else 0) for r in range(rampas)]


def calcular_escalera(i: EntradaEscalera) -> dict[str, Any]:
    """La escalera: el desnivel, los peldaños, la contrahuella y la huella, las rampas y el descanso, los insumos, los conceptos y su cantidad."""
    for que, v in (("La cota de arranque", i.cota_arranque_m), ("La cota de llegada", i.cota_llegada_m)):
        if not math.isfinite(v) or not -30.0 <= v <= 100.0:
            raise ErrorDeEscalera(f"{que} va de -30 a 100 m.")
    desnivel = i.cota_llegada_m - i.cota_arranque_m
    if desnivel <= _EPS:
        raise ErrorDeEscalera("La cota de llegada debe estar por encima de la de arranque: la escalera sube.")
    if desnivel > _DESNIVEL_MAXIMO_M:
        raise ErrorDeEscalera(f"El desnivel va de más de 0 a {_DESNIVEL_MAXIMO_M:g} m.")
    p = validar_parametros(
        {
            "peldanos": i.peldanos, "contrahuella_max_m": i.contrahuella_max_m, "huella_m": i.huella_m, "ancho_m": i.ancho_m,
            "espesor_m": i.espesor_m, "rampas": i.rampas, "largo_descanso_m": i.largo_descanso_m,
        }
    )
    advertencias: list[str] = []
    rampas = int(p["rampas"])

    peldanos = int(p["peldanos"]) if p["peldanos"] is not None else math.ceil(desnivel / p["contrahuella_max_m"] - 1e-9)
    origen_de_peldanos = "tecleados" if p["peldanos"] is not None else "desnivel"
    if peldanos > _PELDANOS_MAXIMOS:
        raise ErrorDeEscalera(f"El desnivel y la contrahuella dan {peldanos} peldaños: el máximo es {_PELDANOS_MAXIMOS}. Revisa las cotas o la contrahuella.")
    if peldanos < 2 * rampas:
        raise ErrorDeEscalera(f"Con {rampas} rampas hacen falta al menos {2 * rampas} peldaños y el desnivel solo da {peldanos}: baja el número de rampas.")
    contrahuella = desnivel / peldanos

    huella = p["huella_m"]
    origen_de_huella = "tecleada"
    if i.recorrido_m is not None:
        if not math.isfinite(i.recorrido_m) or i.recorrido_m <= _EPS:
            raise ErrorDeEscalera("La línea del plano no tiene largo: no da el recorrido de la escalera.")
        huella = i.recorrido_m / (peldanos - rampas)
        origen_de_huella = "linea"
        if not _RANGOS["huella_m"][0] - _EPS <= huella <= _RANGOS["huella_m"][1] + _EPS:
            raise ErrorDeEscalera(
                f"El recorrido de la línea ({i.recorrido_m:.2f} m) entre {peldanos - rampas} huellas da una huella de {huella * 100:.0f} cm: "
                f"debe ir de {_RANGOS['huella_m'][0] * 100:.0f} a {_RANGOS['huella_m'][1] * 100:.0f} cm. Revisa la línea o los peldaños."
            )
    if contrahuella > p["contrahuella_max_m"] + 1e-6:
        advertencias.append(
            f"La contrahuella ({contrahuella * 100:.1f} cm) pasa de la máxima ({p['contrahuella_max_m'] * 100:.0f} cm): con {peldanos} peldaños el peldaño queda más alto. "
            "Sube los peldaños o deja que salgan del desnivel."
        )
    if huella < float(DEFECTOS["huella_m"]) - 1e-6:
        advertencias.append(f"La huella ({huella * 100:.1f} cm) es menor que la de referencia (25 cm, E2): confirma con el proyecto.")

    longitud_inclinada = math.hypot(huella, contrahuella)
    ancho, espesor = p["ancho_m"], p["espesor_m"]
    reparto = _reparto(peldanos, rampas)
    detalle_de_rampas = [
        {"numero": n + 1, "peldanos": k, "recorrido_m": (k - 1) * huella, "altura_m": k * contrahuella} for n, k in enumerate(reparto)
    ]
    recorrido = (peldanos - rampas) * huella
    superficie_de_rampa = peldanos * longitud_inclinada * ancho
    volumen_de_rampa = superficie_de_rampa * espesor
    escalones = peldanos * ancho / LARGO_BASE_DEL_ESCALON_M

    descansos = rampas - 1
    largo_descanso = p["largo_descanso_m"] if p["largo_descanso_m"] is not None else ancho
    area_de_descanso = descansos * ancho * largo_descanso
    volumen_de_descanso = area_de_descanso * espesor
    if descansos == 0 and p["largo_descanso_m"] is not None:
        advertencias.append("Se tecleó el largo del descanso, pero con una sola rampa no hay descanso: no suma nada.")
    if abs(escalones - round(escalones)) > 1e-6:
        advertencias.append(
            f"El ancho de {ancho:.2f} m no es múltiplo de 1.20 m: el catálogo cuenta el escalón de 1.20 m y la cantidad queda fraccionaria ({escalones:.3f} pza, E1)."
        )

    insumos: list[dict[str, Any]] = [
        {
            "parte": "rampa", "clave": CONCRETO["clave"], "descripcion": CONCRETO["descripcion"], "unidad": CONCRETO["unidad"], "cantidad": volumen_de_rampa,
            "origen": "geometria", "nota": f"{superficie_de_rampa:.3f} m² de rampa inclinada × {espesor * 100:.0f} cm de espesor",
        }
    ]
    for clave, descripcion, unidad, por_m2, _fuente in PARRILLA_POR_M2:
        insumos.append(
            {
                "parte": "rampa", "clave": clave, "descripcion": descripcion, "unidad": unidad, "cantidad": superficie_de_rampa * por_m2,
                "origen": "catalogo", "nota": f"Parrilla AUX-06010: {por_m2:g} {unidad} por m² de rampa",
            }
        )
    if descansos > 0:
        insumos.append(
            {
                "parte": "descanso", "clave": CONCRETO["clave"], "descripcion": CONCRETO["descripcion"], "unidad": CONCRETO["unidad"],
                "cantidad": volumen_de_descanso, "origen": "geometria", "nota": f"{area_de_descanso:.3f} m² de descanso × {espesor * 100:.0f} cm de espesor",
            }
        )
        for clave, descripcion, unidad, por_m2, _fuente in PARRILLA_POR_M2:
            insumos.append(
                {
                    "parte": "descanso", "clave": clave, "descripcion": descripcion, "unidad": unidad, "cantidad": area_de_descanso * por_m2,
                    "origen": "catalogo", "nota": f"Parrilla AUX-06010: {por_m2:g} {unidad} por m² de descanso",
                }
            )
        insumos.append(
            {
                "parte": "descanso", "clave": CIMBRA_DEL_DESCANSO["clave"], "descripcion": CIMBRA_DEL_DESCANSO["descripcion"], "unidad": "m²",
                "cantidad": area_de_descanso, "origen": "catalogo", "nota": "1 m² de cimbra por m² de descanso, como la losa del catálogo",
            }
        )

    conceptos: list[dict[str, Any]] = [
        {
            "parte": "escalon", "elemento_clave": CLAVE_DE_ESCALERA, "ref": None,
            "concepto": {k: CONCEPTO_DE_ESCALON[k] for k in ("clave", "descripcion", "unidad", "estado", "provisional")},
            "toma": ["peldaños", "ancho"], "cantidad": escalones, "unidad": "pza",
            "nota": (
                "El concepto del catálogo EST-01510 se mide por pieza = escalón de 1.20 m (regla F7: un concepto existente, no hay concepto nuevo): "
                f"{peldanos} peldaños × {ancho:.2f} m ÷ 1.20 m."
            ),
        }
    ]
    if descansos > 0:
        conceptos.append(
            {
                "parte": "descanso", "elemento_clave": CLAVE_DE_ESCALERA, "ref": None,
                "concepto": {k: CONCEPTO_DE_DESCANSO[k] for k in ("clave", "descripcion", "unidad", "estado", "provisional")},
                "toma": ["área"], "cantidad": area_de_descanso, "unidad": "m²",
                "nota": (
                    f"Concepto nuevo por m² (regla F7): {descansos} descanso(s) de {ancho:.2f} × {largo_descanso:.2f} m; propuesto, de clave provisional, sin precio. "
                    "No cuenta en una partida hasta que se autorice y esté en el catálogo."
                ),
            }
        )
    mano_de_obra = {
        "estado": "sin_mano_de_obra",
        "nota": (
            "El elemento no calcula mano de obra con importe: los destajos MOE-02311 (armado y colado, por pieza) y MOE-02312 (descimbra, por m²) de la "
            "composición de EST-01510 se listan y quedan sin precio."
        ),
        "destajos_candidatos": [{"clave": f[0], "descripcion": f[1], "unidad": f[2]} for f in DESTAJOS_DEL_ESCALON],
    }
    return {
        "clave": CLAVE_DE_ESCALERA,
        "nombre": NOMBRE,
        "parametros": p,
        "cotas": {"arranque_m": i.cota_arranque_m, "llegada_m": i.cota_llegada_m, "desnivel_m": desnivel},
        "geometria": {
            "peldanos": peldanos,
            "origen_de_peldanos": origen_de_peldanos,
            "contrahuella_m": contrahuella,
            "huella_m": huella,
            "origen_de_huella": origen_de_huella,
            "longitud_inclinada_m": longitud_inclinada,
            "recorrido_horizontal_m": recorrido,
            "rampas": detalle_de_rampas,
            "descansos": descansos,
            "largo_del_descanso_m": largo_descanso,
            "area_de_descanso_m2": area_de_descanso,
            "superficie_de_rampa_m2": superficie_de_rampa,
            "volumen_de_rampa_m3": volumen_de_rampa,
            "volumen_de_descanso_m3": volumen_de_descanso,
            "escalones_de_catalogo": escalones,
        },
        "insumos": insumos,
        "conceptos": conceptos,
        "por_espacio": [{"espacio_id": i.espacio_id, "conceptos": [dict(c) for c in conceptos]}],
        "mano_de_obra": mano_de_obra,
        "advertencias": advertencias,
        "pendientes": [dict(x) for x in PENDIENTES],
    }
