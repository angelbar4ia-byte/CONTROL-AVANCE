"""El relleno como ELEMENTO (Fase 3 de las zonas de losa): un elemento separado de la losa que se mide de los polígonos de una zona.

Decisión del usuario (2026-11-16 y 2026-11-20, «Fase 3»): el relleno **no es parte de la matriz de la losa**. Los espesores distintos de losa dentro de
una zona son por razón **estructural** (no pluvial) y el relleno **se adapta a eso**: su volumen sale de los polígonos de la zona, de los espesores
estructurales de cada subzona y de las pendientes, no de la losa. Es una familia nueva de la biblioteca (categoría «Rellenos») con su propia tabla de
elementos de zona (`relleno_zona`, migración 0144); la matriz de la losa solo le presta lo que ya calcula: el área y el espesor de cada polígono.

Qué hay en la biblioteca (dos elementos, igual que la losa tiene maciza y nervada)
-----------------------------------------------------------------------------------
- **REL-AZOTEA**, relleno de azotea con tezontle. Se paga con el concepto **existente** del catálogo ``ALB-03014`` («Relleno en azotea mezcla
  antihumedad-arena-arenilla 2:4:10…», por m²). Regla F7: se liga a un concepto que ya existe, no hay concepto nuevo. Su composición real
  (``ANALISIS_DE_BASICOS_CONCEPTOS`` líneas 255 a 257) es 0.012857 viaje de tezontle ``PET-00069`` (de 7 m³: 0.09 m³ por m², es decir 9 cm de espesor
  medio), 0.0735 m³ de mortero ``CON-00020`` y el destajo ``MOA-05012`` por m². El elemento calcula el tezontle **por geometría** (área × espesor,
  con pendiente y subzonas) y lo concilia contra la composición vigente sin editarla; el mortero es el del catálogo por m² (editable).
- **REL-COMPACTADO**, relleno compactado de nivelación (por m³). El catálogo **no trae** concepto, material (tepetate, material de banco), ni destajo
  de compactación: se propone el concepto nuevo ``EJ-810`` (clave **provisional**, sin precio, pendiente de autorizar por Control de obra, regla F7).
  Mientras no esté autorizado y en el catálogo, su cantidad se informa pero **no se escribe** en ninguna partida.

Cómo se mide (valores conservadores, ver ``PENDIENTES``)
--------------------------------------------------------
Cada polígono de la zona (o el que se elija, medición derivada del polígono del plano) tiene un **espesor de relleno**:

    espesor = espesor_m  +  compensación  +  pendiente

- ``espesor_m``: el espesor mínimo (parámetro editable). Azotea: 9 cm, el espesor medio que implica el catálogo (0.012857 × 7 m³). Compactado: 10 cm
  (el material del usuario no lo define).
- ``compensación`` (``compensar_espesores``, por omisión sí): la losa más gruesa de la zona fija el espesor mínimo y cada subzona **más delgada** recibe
  la diferencia (``espesor máximo de la zona − espesor del polígono``), porque el relleno se adapta a los espesores estructurales distintos. Es la
  lectura conservadora de la decisión (la cara superior del relleno queda a nivel); la dirección exacta es una pregunta abierta (R3).
- ``pendiente``: ``pendiente_pct`` × ``recorrido_m`` / 2 (un relleno en cuña: el espesor medio sube la mitad de lo que sube en el recorrido). Por omisión
  **0** y **0**: sin pendiente no hay volumen de pendiente; el spec no dice cómo se mide (R2).

El volumen es ``Σ área × espesor`` por polígono. En el compactado, ``abundamiento_pct`` (por omisión **0**: el catálogo no trae factor) da el volumen
**suelto** a comprar; el concepto se mide por el volumen compactado.

Sin doble conteo
----------------
Cada polígono cae en **un** espacio (el del relleno, si lo tiene, o el del polígono; 0143) y por eso en **un** grupo de ``por_espacio``: la suma de los
grupos es el total del relleno. El relleno y la losa se pagan con conceptos distintos, así que no se cuentan dos veces. Dos rellenos del mismo
elemento sobre el mismo polígono sí lo harían: ``solapes_de_rellenos`` lo detecta y la API lo rechaza.

Relleno DINÁMICO de azotea con bajadas (decisión del 2026-11-22, `azotea_con_bajadas`)
------------------------------------------------------------------------------------
Si el relleno de azotea trae **bajadas pluviales** (puntos del plano), deja de ser un espesor parejo y pasa a **dos capas**: una de **arenilla** de espesor
variable (5 cm en cada bajada + pendiente × distancia a la bajada que drena; volumen = integral del espesor sobre la zona, ver el método y su error en
`azotea_con_bajadas`) y encima una **plantilla de mortero** de 5 cm. La arenilla se paga con el concepto nuevo **propuesto** ``EJ-830`` por m³ (clave
provisional, sin precio, a autorizar por Control de obra, regla F7) y el mortero con ``ALB-03014`` por m² (existente). Sin bajadas todo sigue exactamente como
arriba. Sin escala calibrada del plano, el relleno con bajadas no da cantidades (decisión del 2026-11-22).

REL-COMPACTADO: la cantidad del concepto es el volumen compactado × el **factor de abundamiento** (editable, 1.00 por omisión), sin destajo.

Mano de obra: ninguna se calcula con importe. El destajo ``MOA-05012`` del catálogo se lista (por m²) pero no se le pone precio. Sin precios.
Función pura, sin base de datos; no lee ningún driver de la obra.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from obractrl.domain.cuantificacion.azotea_con_bajadas import (
    ESPESOR_EN_BAJADA_M,
    ESPESOR_MORTERO_M,
    METODO,
    PENDIENTE_POR_OMISION_PCT,
    Bajada,
    Poligono,
    ResultadoDeIntegral,
    bajada_que_drena,
    distancia_al_borde,
    guias_de_pendiente,
    integrar_arenilla,
    punto_en_zona,
)
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "CLAVES_DE_RELLENO",
    "CONCEPTOS_DE_RELLENO",
    "CONCEPTO_ARENILLA",
    "CONCEPTO_AZOTEA",
    "DEFECTOS",
    "DESTAJO_AZOTEA",
    "ESPESOR_DEL_CATALOGO_M",
    "MORTERO_AZOTEA",
    "PENDIENTES",
    "TEZONTLE",
    "TIPOS_DE_RELLENO",
    "EntradaRelleno",
    "ErrorDeRelleno",
    "PoligonoDeRelleno",
    "calcular_relleno",
    "categorias_de_biblioteca",
    "concepto_nuevo_de_arenilla",
    "concepto_nuevo_de_relleno",
    "definicion_de_relleno",
    "elemento_de_relleno",
    "solapes_de_rellenos",
    "validar_parametros",
]

TipoDeRelleno = Literal["azotea", "compactado"]
TIPOS_DE_RELLENO: tuple[str, ...] = ("azotea", "compactado")

CLAVES_DE_RELLENO: dict[str, str] = {"azotea": "REL-AZOTEA", "compactado": "REL-COMPACTADO"}
"""Los dos elementos de la biblioteca (categoría Rellenos): su clave por tipo."""

CONCEPTO_AZOTEA: dict[str, str] = {
    "clave": "ALB-03014",
    "descripcion": "Relleno en azotea mezcla antihumedad-arena-arenilla 2:4:10, cemento antihumedad.",
    "unidad": "m²",
}
"""El concepto EXISTENTE del catálogo (CATALOGO_DE_MATRICES línea 88, por m²) con que se paga el relleno de azotea. No se edita."""

TEZONTLE: dict[str, Any] = {
    "clave": "PET-00069",
    "descripcion": "TEZONTLE ROJO 7 MTS",
    "unidad": "SERV",
    "m3_por_viaje": 7.0,
    "por_m2_del_catalogo": 0.012857,
    "fuente": "ANALISIS_DE_BASICOS_CONCEPTOS:255",
}
"""El tezontle del catálogo: se compra por viaje de 7 m³ («7 MTS» en la descripción). 0.012857 viaje por m² son 0.09 m³ por m²."""

MORTERO_AZOTEA: dict[str, Any] = {
    "clave": "CON-00020",
    "descripcion": "Mortero fc 50 kg/cm2, Normal a 28 días, TMA 05mm Rev 14 cm, bombeado con IMPER 1%",
    "unidad": "m³",
    "por_m2_del_catalogo": 0.0735,
    "fuente": "ANALISIS_DE_BASICOS_CONCEPTOS:256",
}
"""El mortero de la composición de ALB-03014 por m². El catálogo lo trae fijo; el elemento lo toma como parámetro editable."""

DESTAJO_AZOTEA: dict[str, str] = {
    "clave": "MOA-05012",
    "descripcion": "MO ELEVACION TEZONTLE Y RELLENO FLUIDO",
    "unidad": "m²",
    "fuente": "ANALISIS_DE_BASICOS_CONCEPTOS:257",
}
"""El destajo del catálogo en la composición de ALB-03014 (por m², tipo «Contrato»). Se lista; el elemento no le pone importe."""

ESPESOR_DEL_CATALOGO_M = 0.09
"""El espesor medio que implica el catálogo: 0.012857 viaje × 7 m³ = 0.09 m³ por m² (9 cm)."""

CONCEPTOS_DE_RELLENO: dict[str, dict[str, Any]] = {
    "azotea": {**CONCEPTO_AZOTEA, "estado": "catalogo", "provisional": False},
    "compactado": {
        "clave": "EJ-810",
        "descripcion": "Relleno compactado por m³ para nivelar o dar pendiente en una zona de losa (material, tendido y compactación)",
        "unidad": "m³",
        "estado": "propuesto",
        "provisional": True,
    },
}
"""El concepto de cada relleno (regla F7): el de azotea ya existe en el catálogo; el compactado es un concepto nuevo, propuesto, de clave
**provisional**, sin precio ni destajo y pendiente de autorizar por Control de obra."""

CONCEPTO_ARENILLA: dict[str, Any] = {
    "clave": "EJ-830",
    "descripcion": "Arenilla de relleno de azotea de espesor variable según las bajadas pluviales (suministro y tendido), por m³",
    "unidad": "m³",
    "estado": "propuesto",
    "provisional": True,
}
"""El concepto NUEVO de la arenilla del relleno dinámico de azotea (regla F7): clave provisional (la siguiente libre tras EJ-820), por m³, sin precio ni destajo,
pendiente de autorizar por Control de obra. No está en el catálogo (verificado contra el código y las propuestas: EJ-800, 801, 802, 810 y 820 son los únicos EJ-8xx)."""

DEFECTOS: dict[str, dict[str, Any]] = {
    "azotea": {
        "espesor_m": ESPESOR_DEL_CATALOGO_M, "pendiente_pct": 0.0, "recorrido_m": 0.0, "compensar_espesores": True,
        "abundamiento_pct": 0.0, "mortero_m3_por_m2": MORTERO_AZOTEA["por_m2_del_catalogo"],
        "pendiente_zona_pct": PENDIENTE_POR_OMISION_PCT, "espesor_bajada_m": ESPESOR_EN_BAJADA_M, "mortero_espesor_m": ESPESOR_MORTERO_M,
        "factor_abundamiento": 1.0,
    },
    "compactado": {
        "espesor_m": 0.10, "pendiente_pct": 0.0, "recorrido_m": 0.0, "compensar_espesores": True,
        "abundamiento_pct": 0.0, "mortero_m3_por_m2": 0.0,
        "pendiente_zona_pct": 0.0, "espesor_bajada_m": ESPESOR_EN_BAJADA_M, "mortero_espesor_m": 0.0,
        "factor_abundamiento": 1.0,
    },
}
"""Los parámetros por omisión de cada relleno. Todos son editables; ninguno es un precio. ``pendiente_zona_pct``, ``espesor_bajada_m`` y ``mortero_espesor_m``
son del relleno dinámico de azotea (solo cuentan si el relleno tiene bajadas); ``espesor_m``, ``pendiente_pct`` y ``recorrido_m`` son los del relleno sin bajadas.
``abundamiento_pct`` es el viejo nombre del factor: ``factor_abundamiento = 1 + abundamiento_pct / 100``."""

PENDIENTES: tuple[dict[str, str], ...] = (
    {
        "clave": "R1",
        "texto": "El material del usuario no define cómo se mide el relleno (espesor, material, compactación). Azotea: se toma el espesor medio que implica el "
        "catálogo (9 cm = 0.012857 viaje × 7 m³). Compactado: 10 cm como valor conservador. ¿Cuáles son los espesores reales?",
    },
    {
        "clave": "R2",
        "texto": "La pendiente por bajadas pluviales: el relleno se mide como cuña (pendiente % × recorrido / 2 sobre el espesor mínimo). Por omisión la pendiente y el "
        "recorrido valen 0 (no suman volumen). ¿El 9 cm del catálogo ya incluye la pendiente medida desde el punto alto, o es el espesor mínimo?",
    },
    {
        "clave": "R3",
        "texto": "Los espesores de losa distintos de una zona son estructurales y el relleno se adapta: la subzona más delgada recibe la diferencia contra la más "
        "gruesa (la cara superior queda a nivel). ¿Es esa la dirección? Se puede apagar con «compensar espesores».",
    },
    {
        "clave": "R4",
        "texto": "El catálogo no trae tepetate, material de banco ni destajo de compactación: el relleno compactado se paga con el concepto nuevo EJ-810 (clave "
        "provisional, propuesto, sin precio) y no calcula insumos. El factor de abundamiento queda en 0 hasta que el catálogo o Costos lo definan.",
    },
    {
        "clave": "R5",
        "texto": "El mortero de ALB-03014 (0.0735 m³ por m²) lo trae el catálogo fijo, aparte del tezontle: se toma tal cual y se puede editar. ¿Es un firme sobre el relleno o "
        "va mezclado con él? El elemento no lo deduce del espesor.",
    },
    {
        "clave": "R6",
        "texto": "El relleno de cimentación y el filtro de grava del muro de contención (D11) son otras cosas: el filtro es del muro de contención, y el relleno de "
        "cimentación no lo define el material del usuario (Fase 4b, pregunta C4: puede medirse con REL-COMPACTADO sobre la zona de cimentación). Este elemento solo rellena polígonos de una zona de losa.",
    },
    {
        "clave": "R7",
        "texto": "La clave provisional EJ-810 (compactado) la confirma Control de obra al autorizar.",
    },
    {
        "clave": "R8",
        "texto": "Relleno dinámico: el usuario no dio la pendiente. Se usa 2 % por zona (la mínima habitual de una azotea) como valor editable. ¿Cuál es la pendiente real de cada azotea?",
    },
    {
        "clave": "R9",
        "texto": "Relleno dinámico: ALB-03014 del catálogo trae 0.0735 m³ de mortero por m² (14 cm) y el tezontle PET-00069; el usuario pidió arenilla + plantilla de mortero de "
        "5 cm. Con bajadas el mortero se calcula a 5 cm (0.05 m³ por m²) y el tezontle se sustituye por la arenilla EJ-830, así que la conciliación muestra esas "
        "diferencias sin corregir el catálogo. ¿Se actualiza la composición de ALB-03014 o se crea un concepto aparte?",
    },
    {
        "clave": "R10",
        "texto": "La arenilla se paga con el concepto nuevo EJ-830 por m³ (propuesto, clave provisional, sin precio): Control de obra lo autoriza y confirma la clave (el usuario pidió «la "
        "siguiente libre tras EJ-820»; si otro elemento nuevo toma la misma clave, se renumera).",
    },
    {
        "clave": "R11",
        "texto": "La distancia de drenaje es en línea recta a la bajada más cercana (sin rodear muros, pretiles ni huecos). Con una línea de pendiente trazada hacia la bajada, el "
        "agua baja a la línea y corre por ella. ¿Es esa la lectura de «la línea marca hacia dónde van las pendientes»?",
    },
    {
        "clave": "R12",
        "texto": "Los 5 cm mínimos son el espesor de arenilla en la bajada (bajo la plantilla de mortero, que va aparte y también de 5 cm). ¿O los 5 cm incluyen el mortero?",
    },
)
"""Lo que el material del usuario no resuelve y se dejó con valor conservador."""

_EPS = 1e-9
_ESPESOR_MAXIMO_M = 2.0
_AREA_MAXIMA_M2 = 1_000_000.0


class ErrorDeRelleno(ErrorDeCuantificacion):
    """Un dato que no vale: el relleno no se puede calcular con él."""


# --------------------------------------------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PoligonoDeRelleno:
    """Un polígono de losa que el relleno cubre: su área neta, su espesor estructural propio (si es una subzona) y su espacio (0143)."""

    area_m2: float
    espesor_de_losa_m: float | None = None
    id: str | None = None
    espacio_id: str | None = None
    piezas: Sequence[Poligono] | None = None
    """La geometría del polígono (cada pieza: anillo exterior y huecos, en metros): solo la necesita el relleno con bajadas, que integra el espesor sobre ella."""


@dataclass(frozen=True)
class EntradaRelleno:
    tipo: TipoDeRelleno
    espesor_de_la_zona_m: float
    """El espesor de losa de la zona: vale para el polígono que no trae espesor propio."""
    poligonos: Sequence[PoligonoDeRelleno] = ()
    espesor_maximo_de_la_zona_m: float | None = None
    """La losa más gruesa de TODA la zona (también de los polígonos que este relleno no cubre): la referencia de la compensación. Sin ella vale la
    más gruesa de los polígonos que cubre."""
    espesor_m: float = 0.0
    pendiente_pct: float = 0.0
    recorrido_m: float = 0.0
    compensar_espesores: bool = True
    abundamiento_pct: float = 0.0
    mortero_m3_por_m2: float = 0.0
    espacio_id: str | None = None
    """Si el relleno trae espacio, todos sus polígonos van a él; si no, cada uno al suyo."""
    bajadas: Sequence[Bajada] = ()
    """Las bajadas pluviales del relleno de azotea (puntos del plano en metros): con al menos una el relleno es dinámico (arenilla + mortero)."""
    pendiente_zona_pct: float = PENDIENTE_POR_OMISION_PCT
    espesor_bajada_m: float = ESPESOR_EN_BAJADA_M
    mortero_espesor_m: float = ESPESOR_MORTERO_M
    factor_abundamiento: float = 1.0
    escala_definida: bool = True
    """Sin escala calibrada el relleno con bajadas no da cantidades."""


# --------------------------------------------------------------------------------------------------------------
# Biblioteca
# --------------------------------------------------------------------------------------------------------------


def elemento_de_relleno(clave: str) -> TipoDeRelleno | None:
    """El tipo de relleno de una clave de la biblioteca (`REL-AZOTEA`, `REL-COMPACTADO`), o `None`."""
    for tipo, c in CLAVES_DE_RELLENO.items():
        if c == clave:
            return tipo  # type: ignore[return-value]
    return None


def _nombre(tipo: str) -> str:
    return "Relleno de azotea" if tipo == "azotea" else "Relleno compactado"


def _se_mide_por(tipo: str) -> str:
    return "m² de relleno de una zona del plano" if tipo == "azotea" else "m³ de relleno de una zona del plano"


def categorias_de_biblioteca() -> tuple[dict[str, Any], ...]:
    """La categoría Rellenos de la biblioteca (forma de `BIBLIOTECA`): un elemento por tipo de relleno."""

    def elemento(tipo: str) -> dict[str, Any]:
        c = CONCEPTOS_DE_RELLENO[tipo]
        return {
            "clave": CLAVES_DE_RELLENO[tipo],
            "nombre": _nombre(tipo),
            "tipo": "relleno",
            "se_mide_por": _se_mide_por(tipo),
            "concepto": {"clave": c["clave"], "descripcion": c["descripcion"], "unidad": c["unidad"]},
        }

    return (
        {
            "clave": "rellenos",
            "nombre": "Rellenos",
            "prefijo": "REL",
            "subcategorias": (
                {"clave": "azotea", "nombre": "Rellenos de azotea", "prefijo": "REL", "elementos": (elemento("azotea"),)},
                {"clave": "compactado", "nombre": "Rellenos compactados", "prefijo": "REL", "elementos": (elemento("compactado"),)},
            ),
        },
    )


def definicion_de_relleno(clave: str) -> dict[str, Any] | None:
    """La ficha de un elemento de relleno: qué calcula, qué toma del catálogo, su concepto y los pendientes."""
    tipo = elemento_de_relleno(clave)
    if tipo is None:
        return None
    azotea = tipo == "azotea"
    c = CONCEPTOS_DE_RELLENO[tipo]
    return {
        "clave": clave,
        "nombre": _nombre(tipo),
        "tipo": tipo,
        "se_mide_por": _se_mide_por(tipo),
        "categoria": {"clave": "rellenos", "nombre": "Rellenos"},
        "subcategoria": {"clave": tipo, "nombre": "Rellenos de azotea" if azotea else "Rellenos compactados"},
        "concepto": {
            "clave": c["clave"], "descripcion": c["descripcion"], "unidad": c["unidad"], "estado": c["estado"], "provisional": c["provisional"],
        },
        "parametros_por_defecto": dict(DEFECTOS[tipo]),
        "concepto_arenilla": (
            {
                "clave": CONCEPTO_ARENILLA["clave"], "descripcion": CONCEPTO_ARENILLA["descripcion"], "unidad": CONCEPTO_ARENILLA["unidad"],
                "estado": CONCEPTO_ARENILLA["estado"], "provisional": CONCEPTO_ARENILLA["provisional"],
            }
            if azotea
            else None
        ),
        "tezontle": (
            {
                "clave": TEZONTLE["clave"], "descripcion": TEZONTLE["descripcion"], "unidad": TEZONTLE["unidad"],
                "m3_por_viaje": TEZONTLE["m3_por_viaje"], "por_m2": TEZONTLE["por_m2_del_catalogo"], "fuente": TEZONTLE["fuente"],
            }
            if azotea
            else None
        ),
        "mortero": (
            {
                "clave": MORTERO_AZOTEA["clave"], "descripcion": MORTERO_AZOTEA["descripcion"], "unidad": MORTERO_AZOTEA["unidad"],
                "por_m2": MORTERO_AZOTEA["por_m2_del_catalogo"], "fuente": MORTERO_AZOTEA["fuente"],
            }
            if azotea
            else None
        ),
        "destajos_candidatos": [{"clave": DESTAJO_AZOTEA["clave"], "descripcion": DESTAJO_AZOTEA["descripcion"], "unidad": "m²"}] if azotea else [],
        "pendientes": [dict(p) for p in PENDIENTES],
    }


def concepto_nuevo_de_relleno(tipo: str = "compactado") -> dict[str, Any]:
    """La propuesta de concepto nuevo del relleno compactado por m³ (clase ``concepto_nuevo``): clave provisional, sin insumos, destajo ni precio. El
    relleno de azotea no necesita concepto nuevo: usa ALB-03014 del catálogo."""
    if tipo != "compactado":
        raise ErrorDeRelleno("Solo el relleno compactado necesita un concepto nuevo: el de azotea usa ALB-03014 del catálogo.")
    c = CONCEPTOS_DE_RELLENO["compactado"]
    return {
        "elemento_clave": CLAVES_DE_RELLENO["compactado"],
        "concepto_clave": c["clave"],
        "clase": "concepto_nuevo",
        "resumen": f"Concepto nuevo {c['clave']} (clave provisional): {c['descripcion']}, por m³, sin insumos, destajo ni precio",
        "detalle": {
            "descripcion": c["descripcion"],
            "unidad": "m³",
            "clave_provisional": True,
            "toma": {"volumen": True},
            "insumos": {},
            "motivos": [
                "Fase 3 de la losa (regla F7): el relleno es un elemento nuevo y lleva su concepto en el catálogo; el catálogo solo trae el relleno de azotea con "
                "tezontle (ALB-03014, por m²) y ningún relleno compactado.",
                "Sin insumos: el catálogo no trae tepetate ni material de banco, y el factor de abundamiento queda en 0.",
                "Sin destajo: el catálogo no trae destajo de compactación. Sin precio.",
                "Clave provisional: pendiente de autorizar por Control de obra.",
            ],
            "cambios": [],
        },
    }


# --------------------------------------------------------------------------------------------------------------
# Validación
# --------------------------------------------------------------------------------------------------------------


def validar_parametros(tipo: str, parametros: dict[str, Any]) -> dict[str, Any]:
    """Los parámetros del relleno normalizados (con los de omisión del tipo donde falten). Rechaza lo que no vale. ``abundamiento_pct`` es el nombre viejo del
    factor: si viene sin ``factor_abundamiento`` el factor es ``1 + abundamiento_pct / 100``; el factor manda y ``abundamiento_pct`` sale derivado de él."""
    if tipo not in TIPOS_DE_RELLENO:
        raise ErrorDeRelleno("El tipo de relleno es «azotea» o «compactado».")
    dados = {k: v for k, v in parametros.items() if v is not None}
    p = {**DEFECTOS[tipo], **dados}
    for campo, minimo, tope in (
        ("espesor_m", 0.0, _ESPESOR_MAXIMO_M), ("pendiente_pct", 0.0, 30.0), ("recorrido_m", 0.0, 100.0), ("abundamiento_pct", 0.0, 60.0),
        ("mortero_m3_por_m2", 0.0, 0.5), ("pendiente_zona_pct", 0.0, 30.0), ("espesor_bajada_m", 0.01, 0.30), ("mortero_espesor_m", 0.0, 0.20),
        ("factor_abundamiento", 1.0, 1.6),
    ):
        if campo == "abundamiento_pct" and "factor_abundamiento" in dados:
            continue
        if campo == "factor_abundamiento" and "factor_abundamiento" not in dados:
            continue
        valor = p[campo]
        if isinstance(valor, bool) or not isinstance(valor, int | float):
            raise ErrorDeRelleno(f"«{campo}» debe ser un número.")
        if valor < minimo or valor > tope:
            raise ErrorDeRelleno(f"«{campo}» va de {minimo:g} a {tope:g}.")
        p[campo] = float(valor)
    if "factor_abundamiento" not in dados:
        p["factor_abundamiento"] = 1 + p["abundamiento_pct"] / 100
    p["abundamiento_pct"] = round((float(p["factor_abundamiento"]) - 1) * 100, 6)
    p["compensar_espesores"] = bool(p["compensar_espesores"])
    if tipo == "azotea" and p["factor_abundamiento"] > 1 + _EPS:
        raise ErrorDeRelleno("El relleno de azotea no lleva abundamiento: el catálogo cuenta el tezontle por viaje de 7 m³ sin factor.")
    if tipo == "compactado" and p["mortero_m3_por_m2"] > _EPS:
        raise ErrorDeRelleno("El relleno compactado no lleva mortero: el mortero es de la composición del relleno de azotea.")
    return {k: p[k] for k in DEFECTOS[tipo]}


def solapes_de_rellenos(filas: Sequence[dict[str, Any]]) -> list[str]:
    """Los rellenos de una zona que contarían dos veces lo mismo: dos del mismo elemento sobre el mismo polígono, o uno de toda la zona junto a otro del mismo
    elemento sobre un polígono. `filas`: `{id, elemento_clave, trazo_id}` (`trazo_id` nulo = toda la zona). Devuelve los motivos (vacía si no hay solape)."""
    por_clave: dict[str, list[dict[str, Any]]] = {}
    for f in filas:
        por_clave.setdefault(str(f["elemento_clave"]), []).append(f)
    motivos: list[str] = []
    for clave, grupo in por_clave.items():
        enteras = [f for f in grupo if not f.get("trazo_id")]
        if len(enteras) > 1:
            motivos.append(f"{clave}: hay más de un relleno de toda la zona; los polígonos se contarían dos veces.")
        if enteras and len(grupo) > len(enteras):
            motivos.append(f"{clave}: hay un relleno de toda la zona y otro de un polígono; el polígono se contaría dos veces.")
        vistos: set[str] = set()
        for f in grupo:
            t = f.get("trazo_id")
            if t and str(t) in vistos:
                motivos.append(f"{clave}: hay dos rellenos sobre el mismo polígono; se contaría dos veces.")
            if t:
                vistos.add(str(t))
    return motivos


# --------------------------------------------------------------------------------------------------------------
# Cálculo
# --------------------------------------------------------------------------------------------------------------


def concepto_nuevo_de_arenilla() -> dict[str, Any]:
    """La propuesta de concepto nuevo de la arenilla del relleno dinámico de azotea por m³ (clase ``concepto_nuevo``): clave provisional, sin insumos, destajo ni
    precio. El volumen sale del trazo (bajadas y pendiente), así que el concepto es DINÁMICO: su cantidad cambia al mover una bajada o la pendiente."""
    c = CONCEPTO_ARENILLA
    return {
        "elemento_clave": CLAVES_DE_RELLENO["azotea"],
        "concepto_clave": c["clave"],
        "clase": "concepto_nuevo",
        "resumen": f"Concepto nuevo {c['clave']} (clave provisional): {c['descripcion']}, sin insumos, destajo ni precio",
        "detalle": {
            "descripcion": c["descripcion"],
            "unidad": "m³",
            "clave_provisional": True,
            "toma": {"volumen": True},
            "insumos": {},
            "motivos": [
                "Relleno dinámico de azotea (regla F7): el relleno lleva dos capas, arenilla de espesor variable y plantilla de mortero de 5 cm; el catálogo solo trae el "
                "relleno de azotea con tezontle por m² (ALB-03014) y ninguna arenilla por m³.",
                "Dinámico: el volumen sale de las bajadas pluviales y la pendiente de la zona (5 cm mínimo en cada bajada + pendiente × distancia); precio y cantidades "
                "cambian al hacer el trazo.",
                "Sin insumos, destajo ni precio. Clave provisional: pendiente de autorizar por Control de obra.",
            ],
            "cambios": [],
        },
    }


def _concepto_dict(c: dict[str, Any]) -> dict[str, Any]:
    return {"clave": c["clave"], "descripcion": c["descripcion"], "unidad": c["unidad"], "estado": c["estado"], "provisional": c["provisional"]}


def _celdas(c: dict[str, Any], parte: str, elemento: str, toma: list[str], cantidad: float, unidad: str, nota: str) -> dict[str, Any]:
    return {"parte": parte, "elemento_clave": elemento, "ref": None, "concepto": _concepto_dict(c), "toma": toma, "cantidad": cantidad, "unidad": unidad, "nota": nota}


def _dinamico(i: EntradaRelleno, parametros: dict[str, Any], poligonos: list[dict[str, Any]], advertencias: list[str]) -> dict[str, Any] | None:
    """El relleno con bajadas: integra el espesor de la arenilla sobre cada polígono (se pone en `poligonos`: espesor medio y volumen de la arenilla) y arma el
    bloque `dinamico` (resumen, método, error, bajadas y guías). Sin escala calibrada o sin geometría no hay cantidades."""
    bajadas = list(i.bajadas)
    if not i.escala_definida:
        advertencias.append("El plano no tiene escala calibrada: el relleno con bajadas no da cantidades hasta calibrar la escala.")
        for p in poligonos:
            p["espesor_m"] = 0.0
            p["volumen_m3"] = 0.0
            p["area_m2"] = 0.0
        return {"estado": "sin_escala", "bajadas": [{"id": b.id, "x": b.x, "y": b.y, "rotulo": b.rotulo, "linea_trazada": b.linea is not None} for b in bajadas]}
    pendiente = parametros["pendiente_zona_pct"]
    e0 = parametros["espesor_bajada_m"]
    por_bajada: dict[str, dict[str, float]] = {b.id: {"area_m2": 0.0, "distancia_maxima_m": 0.0, "espesor_maximo_m": 0.0} for b in bajadas}
    lejano: dict[str, Any] = {}
    celda = error = maximo = 0.0
    muestras = 0
    todas: list[Poligono] = []
    for p, lo in zip(poligonos, i.poligonos, strict=True):
        if not lo.piezas or p["area_m2"] <= _EPS:
            p["espesor_m"] = 0.0
            p["volumen_m3"] = 0.0
            if not lo.piezas and p["area_m2"] > _EPS:
                advertencias.append(f"El polígono {p['id']} no trae geometría: no se pudo integrar el espesor de la arenilla.")
            continue
        r = integrar_arenilla([(pz, p["compensacion_m"]) for pz in lo.piezas], bajadas, pendiente_pct=pendiente, espesor_en_bajada_m=e0)
        p["espesor_m"] = r.espesor_medio_m
        p["volumen_m3"] = r.volumen_m3
        p["area_m2"] = r.area_m2
        celda = max(celda, r.celda_m)
        error += r.error_estimado_m3
        maximo = max(maximo, r.espesor_maximo_m)
        muestras += r.muestras
        for bid, g in r.por_bajada.items():
            por_bajada[bid]["area_m2"] += g["area_m2"]
            por_bajada[bid]["distancia_maxima_m"] = max(por_bajada[bid]["distancia_maxima_m"], g["distancia_maxima_m"])
            por_bajada[bid]["espesor_maximo_m"] = max(por_bajada[bid]["espesor_maximo_m"], g["espesor_maximo_m"])
        for bid, punto in r.lejano.items():
            previo = lejano.get(bid)
            if previo is None or bajada_que_drena((punto[0], punto[1]), bajadas)[1] > previo[1]:
                lejano[bid] = (punto, bajada_que_drena((punto[0], punto[1]), bajadas)[1])
        todas.extend(lo.piezas)
    area = sum(p["area_m2"] for p in poligonos)
    volumen = sum(p["volumen_m3"] for p in poligonos)
    # Para las guías se junta lo de todos los polígonos como un solo resultado.
    junto = ResultadoDeIntegral(
        area_m2=area, espesor_medio_m=volumen / area if area > _EPS else 0.0, volumen_m3=volumen, espesor_maximo_m=maximo, muestras=muestras, celda_m=celda,
        error_estimado_m3=error, por_bajada=por_bajada, lejano={k: v[0] for k, v in lejano.items()},
    )
    guias = guias_de_pendiente(todas, bajadas, junto, pendiente_pct=pendiente, espesor_en_bajada_m=e0) if todas else []
    afuera = {b.id for b in bajadas if todas and distancia_al_borde((b.x, b.y), todas) > 0.30 and not punto_en_zona((b.x, b.y), todas)}
    for b in bajadas:
        if b.id in afuera:
            advertencias.append(f"La bajada «{b.rotulo or b.id}» está fuera del área que rellena este relleno: se mide la distancia desde donde está.")
        elif por_bajada[b.id]["area_m2"] <= _EPS and area > _EPS:
            advertencias.append(f"La bajada «{b.rotulo or b.id}» no drena ninguna parte del relleno (otra bajada queda más cerca de todo): no suma volumen.")
    if pendiente <= _EPS:
        advertencias.append("La pendiente de la zona es 0 %: la arenilla queda del mismo espesor (el de la bajada) en toda la zona. Indica la pendiente (R8).")
    return {
        "estado": "calculado",
        "pendiente_pct": pendiente,
        "espesor_en_bajada_m": e0,
        "mortero_espesor_m": parametros["mortero_espesor_m"],
        "volumen_arenilla_m3": volumen,
        "espesor_arenilla_medio_m": volumen / area if area > _EPS else 0.0,
        "espesor_arenilla_maximo_m": maximo,
        "volumen_mortero_m3": area * parametros["mortero_espesor_m"],
        "metodo": METODO,
        "celda_m": celda,
        "muestras": muestras,
        "error_estimado_m3": error,
        "error_relativo": error / volumen if volumen > _EPS else 0.0,
        "bajadas": [
            {
                "id": b.id, "x": b.x, "y": b.y, "rotulo": b.rotulo, "linea_trazada": b.linea is not None, "area_m2": por_bajada[b.id]["area_m2"],
                "distancia_maxima_m": por_bajada[b.id]["distancia_maxima_m"], "espesor_maximo_m": por_bajada[b.id]["espesor_maximo_m"], "fuera_de_la_zona": b.id in afuera,
            }
            for b in bajadas
        ],
        "guias": guias,
    }


def calcular_relleno(i: EntradaRelleno) -> dict[str, Any]:
    """El relleno de una zona: el espesor y el volumen de cada polígono, los insumos, el concepto y su cantidad, repartido por espacio. El de azotea con bajadas
    es dinámico (arenilla de espesor variable + mortero de 5 cm)."""
    parametros = validar_parametros(
        i.tipo,
        {
            "espesor_m": i.espesor_m, "pendiente_pct": i.pendiente_pct, "recorrido_m": i.recorrido_m,
            "compensar_espesores": i.compensar_espesores, "abundamiento_pct": None if i.factor_abundamiento != 1.0 else i.abundamiento_pct,
            "mortero_m3_por_m2": i.mortero_m3_por_m2, "pendiente_zona_pct": i.pendiente_zona_pct, "espesor_bajada_m": i.espesor_bajada_m,
            "mortero_espesor_m": i.mortero_espesor_m, "factor_abundamiento": i.factor_abundamiento if i.factor_abundamiento != 1.0 else None,
        },
    )
    if not 0 < i.espesor_de_la_zona_m <= 3.0:
        raise ErrorDeRelleno("El espesor de la losa de la zona va de más de 0 a 3 m.")
    for lo in i.poligonos:
        if not 0 <= lo.area_m2 <= _AREA_MAXIMA_M2:
            raise ErrorDeRelleno("El área de un polígono va de 0 a 1,000,000 m².")
        if lo.espesor_de_losa_m is not None and not 0 < lo.espesor_de_losa_m <= 3.0:
            raise ErrorDeRelleno("El espesor de una subzona va de más de 0 a 3 m.")

    dinamico_pedido = i.tipo == "azotea" and len(i.bajadas) > 0
    advertencias: list[str] = []
    espesores = [lo.espesor_de_losa_m if lo.espesor_de_losa_m is not None else i.espesor_de_la_zona_m for lo in i.poligonos]
    maximo = i.espesor_maximo_de_la_zona_m if i.espesor_maximo_de_la_zona_m is not None else (max(espesores) if espesores else i.espesor_de_la_zona_m)
    maximo = max(maximo, *espesores) if espesores else maximo
    extra_de_pendiente = 0.0 if dinamico_pedido else parametros["pendiente_pct"] / 100 * parametros["recorrido_m"] / 2
    espesor_base = 0.0 if dinamico_pedido else parametros["espesor_m"]

    poligonos: list[dict[str, Any]] = []
    for n, (lo, e_losa) in enumerate(zip(i.poligonos, espesores, strict=True)):
        compensacion = (maximo - e_losa) if parametros["compensar_espesores"] else 0.0
        espesor = espesor_base + compensacion + extra_de_pendiente
        poligonos.append(
            {
                "id": lo.id or str(n + 1),
                "area_m2": lo.area_m2,
                "espesor_de_losa_m": e_losa,
                "subzona": lo.espesor_de_losa_m is not None,
                "compensacion_m": compensacion,
                "espesor_m": espesor,
                "volumen_m3": lo.area_m2 * espesor,
                "espacio_id": i.espacio_id if i.espacio_id is not None else lo.espacio_id,
            }
        )
    dinamico = _dinamico(i, parametros, poligonos, advertencias) if dinamico_pedido else None
    area = sum(p["area_m2"] for p in poligonos)
    volumen = sum(p["volumen_m3"] for p in poligonos)
    espesor_medio = volumen / area if area > _EPS else 0.0
    if not poligonos:
        advertencias.append("El relleno no cubre ningún polígono de losa: el área y el volumen son cero. Dibuja la losa de la zona en el plano.")
    elif area <= _EPS and not (dinamico and dinamico["estado"] == "sin_escala"):
        advertencias.append("Los polígonos que cubre el relleno no tienen área.")
    if not dinamico_pedido:
        if parametros["pendiente_pct"] > _EPS and parametros["recorrido_m"] <= _EPS:
            advertencias.append("Hay pendiente pero no recorrido: la pendiente no suma volumen. Indica el recorrido (m) de la caída del relleno (R2).")
        if parametros["recorrido_m"] > _EPS and parametros["pendiente_pct"] <= _EPS:
            advertencias.append("Hay recorrido pero no pendiente: no suma volumen. Indica la pendiente (%) del relleno (R2).")
    if parametros["compensar_espesores"] and any(p["compensacion_m"] > _EPS for p in poligonos):
        advertencias.append(
            "Las subzonas de losa más delgadas reciben la diferencia contra la losa más gruesa de la zona: el relleno se adapta a los espesores estructurales (R3)."
        )
    if i.tipo == "azotea" and poligonos and not dinamico_pedido and abs(espesor_medio - ESPESOR_DEL_CATALOGO_M) > 0.0005:
        advertencias.append(
            f"El espesor medio del relleno ({espesor_medio * 100:.1f} cm) difiere del que implica el catálogo (9 cm = 0.012857 viaje × 7 m³): el tezontle se calcula con el "
            "espesor del elemento y la conciliación lo muestra."
        )
    if dinamico_pedido and dinamico and dinamico["estado"] == "calculado":
        advertencias.append(
            "Relleno con bajadas: dos capas, arenilla de espesor variable (concepto propuesto EJ-830, por m³) y plantilla de mortero (ALB-03014, por m²); el espesor mínimo, "
            "la pendiente y el recorrido del relleno sin bajadas no se usan (R9)."
        )

    concepto = dict(CONCEPTOS_DE_RELLENO[i.tipo])
    elemento = CLAVES_DE_RELLENO[i.tipo]
    insumos: list[dict[str, Any]] = []
    mano_de_obra: dict[str, Any]
    # Cada «medida» dice cómo se mide un grupo de polígonos para cada concepto del relleno: m² de área, m³ de volumen o m³ × factor.
    especificaciones: list[dict[str, Any]]
    if i.tipo == "azotea":
        mortero_por_m2 = parametros["mortero_espesor_m"] if dinamico_pedido else parametros["mortero_m3_por_m2"]
        mortero = area * mortero_por_m2
        if dinamico_pedido:
            insumos = [
                {
                    "parte": "arenilla", "clave": CONCEPTO_ARENILLA["clave"], "descripcion": CONCEPTO_ARENILLA["descripcion"], "unidad": "m³", "cantidad": volumen,
                    "origen": "zona", "nota": "Volumen de la arenilla: integral del espesor (5 cm en la bajada + pendiente × distancia) sobre la zona",
                },
                {
                    "parte": "mortero", "clave": MORTERO_AZOTEA["clave"], "descripcion": MORTERO_AZOTEA["descripcion"], "unidad": MORTERO_AZOTEA["unidad"],
                    "cantidad": mortero, "origen": "zona", "nota": f"Plantilla de mortero de {parametros['mortero_espesor_m'] * 100:g} cm sobre la arenilla",
                },
            ]
        else:
            viajes = volumen / TEZONTLE["m3_por_viaje"]
            insumos = [
                {
                    "parte": "tezontle", "clave": TEZONTLE["clave"], "descripcion": TEZONTLE["descripcion"], "unidad": TEZONTLE["unidad"],
                    "cantidad": viajes, "origen": "zona", "nota": f"{volumen:.3f} m³ de relleno entre {TEZONTLE['m3_por_viaje']:g} m³ por viaje",
                },
                {
                    "parte": "mortero", "clave": MORTERO_AZOTEA["clave"], "descripcion": MORTERO_AZOTEA["descripcion"], "unidad": MORTERO_AZOTEA["unidad"],
                    "cantidad": mortero, "origen": "catalogo" if abs(mortero_por_m2 - MORTERO_AZOTEA["por_m2_del_catalogo"]) <= _EPS else "zona",
                    "nota": "Por m² de la composición del catálogo (editable)",
                },
            ]
        nota_azotea = (
            "El concepto del catálogo ALB-03014 se mide por m² de relleno (regla F7: un concepto existente, no hay concepto nuevo)."
            if not dinamico_pedido
            else "ALB-03014 paga la plantilla de mortero por m² (regla F7: un concepto existente); la arenilla se paga aparte con EJ-830."
        )
        especificaciones = [
            {"parte": "relleno", "concepto": concepto, "toma": ["tezontle", "mortero"] if not dinamico_pedido else ["mortero"], "unidad": "m²", "nota": nota_azotea, "medida": "area"}
        ]
        if dinamico_pedido:
            especificaciones.append(
                {
                    "parte": "arenilla", "concepto": CONCEPTO_ARENILLA, "toma": ["volumen"], "unidad": "m³", "medida": "volumen",
                    "nota": "Concepto nuevo por m³ (regla F7, dinámico): propuesto, de clave provisional, sin precio. No cuenta en una partida hasta que se autorice y esté en el catálogo.",
                }
            )
        mano_de_obra = {
            "estado": "sin_mano_de_obra",
            "nota": (
                "El elemento no calcula mano de obra con importe: el destajo MOA-05012 de la composición de ALB-03014 se lista por m² y queda sin precio."
            ),
            "destajos_candidatos": [{"clave": DESTAJO_AZOTEA["clave"], "descripcion": DESTAJO_AZOTEA["descripcion"], "unidad": "m²"}],
        }
    else:
        advertencias.append("El catálogo no trae tepetate, material de banco ni compactación: el relleno compactado no calcula insumos (R4).")
        mano_de_obra = {
            "estado": "sin_mano_de_obra",
            "nota": "El catálogo no trae destajo de compactación ni de tendido de relleno. Sin precios.",
            "destajos_candidatos": [],
        }
        especificaciones = [
            {
                "parte": "relleno", "concepto": concepto, "toma": ["volumen"], "unidad": "m³", "medida": "volumen_por_factor",
                "nota": "Concepto nuevo por m³ (regla F7): propuesto, de clave provisional, sin precio. No cuenta en una partida hasta que se autorice y esté en el catálogo. "
                "Cantidad = volumen compactado × factor de abundamiento.",
            }
        ]
    factor = parametros["factor_abundamiento"]
    suelto = volumen * factor if i.tipo == "compactado" else None

    def cantidad(medida: str, a: float, v: float) -> float:
        return a if medida == "area" else v if medida == "volumen" else v * factor

    conceptos = [
        _celdas(e["concepto"], e["parte"], elemento, e["toma"], cantidad(e["medida"], area, volumen), e["unidad"], e["nota"]) for e in especificaciones
    ]
    return {
        "clave": elemento,
        "nombre": _nombre(i.tipo),
        "tipo": i.tipo,
        "modo": "bajadas" if dinamico_pedido else "uniforme",
        "parametros": parametros,
        "espesor_de_la_zona_m": i.espesor_de_la_zona_m,
        "espesor_maximo_de_la_zona_m": maximo,
        "area_m2": area,
        "volumen_m3": volumen,
        "volumen_suelto_m3": suelto,
        "espesor_medio_m": espesor_medio,
        "extra_de_pendiente_m": extra_de_pendiente,
        "poligonos": poligonos,
        "insumos": insumos,
        "conceptos": conceptos,
        "dinamico": dinamico,
        "por_espacio": _por_espacio(poligonos, elemento, especificaciones, factor, cantidad),
        "mano_de_obra": mano_de_obra,
        "advertencias": advertencias,
        "pendientes": [dict(p) for p in PENDIENTES],
    }


def _por_espacio(
    poligonos: Sequence[dict[str, Any]], elemento: str, especificaciones: Sequence[dict[str, Any]], factor: float, cantidad: Any
) -> list[dict[str, Any]]:
    """El mismo relleno repartido por espacio: cada polígono cae en un solo grupo, así que la suma de los grupos es el total (sin doble conteo). Lo que no
    tiene espacio forma el grupo «sin espacio» (`espacio_id` nulo), que va primero si existe y no escribe en ninguna partida."""
    orden: list[str | None] = []
    for p in poligonos:
        if p["espacio_id"] not in orden:
            orden.append(p["espacio_id"])
    orden.sort(key=lambda e: (e is not None, str(e)))
    grupos: list[dict[str, Any]] = []
    for espacio in orden:
        suyos = [p for p in poligonos if p["espacio_id"] == espacio]
        area = sum(p["area_m2"] for p in suyos)
        volumen = sum(p["volumen_m3"] for p in suyos)
        grupos.append(
            {
                "espacio_id": espacio,
                "area_m2": area,
                "volumen_m3": volumen,
                "conceptos": [
                    _celdas(e["concepto"], e["parte"], elemento, e["toma"], cantidad(e["medida"], area, volumen), e["unidad"], e["nota"]) for e in especificaciones
                ],
            }
        )
    return grupos
