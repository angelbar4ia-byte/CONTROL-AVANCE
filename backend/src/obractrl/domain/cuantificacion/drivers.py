"""Los drivers del Paramétrico: parámetros globales, por obra o mixtos (plan de elementos de muro, fase F; Ola 4B).

Un **driver** es un parámetro que comparten los elementos y las plantillas de muro (la altura estándar, la separación de
castillos, los traslapes, los desperdicios…). Existe en tres niveles:

- **global**: el valor de la organización y su **modo**. `fijo` = solo vale el global; `ajustable` = una obra puede tener el suyo;
- **por obra**: el valor propio de una obra para un driver `ajustable`;
- **mixto**: lo normal: el global manda y las obras que lo necesitan lo ajustan.

El **valor vigente** de un driver en una obra: el de la obra si el global es `ajustable` y la obra lo cambió; si no, el global;
y si nadie ha tocado el global, el **valor de partida** de este catálogo (el de la especificación del mockup). Un ajuste de obra
de un driver que luego pasó a `fijo` no se borra, pero deja de valer (`ajuste_ignorado`).

Q3: Costos y Control de obra editan los drivers (globales y ajustes de obra). Residente, supervisor y el resto solo leen.

Q1: cambiar un driver **no recalcula** lo ya guardado. La altura que un trazo trae (`muro_altura_m`, las partes o el `alt` de
su conversión) es suya. Desde el desacople del plano, `altura_estandar` YA NO la lee el plano (la altura de un trazo nuevo sale de
su zona de losa, de la altura base de su artefacto o de la herramienta de trazo): el driver queda para los paramétricos de elementos.
`altura_estandar` pasó de 2.6 a 3.00 m sin mover un solo trazo viejo (la migración 0134 les fija los 2.6 m que ya contaban).

Los valores de partida son los de la especificación (`spec.js`, `drivers`); donde ella dice «por confirmar» o «supuesto» el driver
lo marca (`por_confirmar`). Nada aquí inventa un precio ni un destajo. Funciones puras, sin base de datos.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from obractrl.domain.cuantificacion.receta_acero import DriversDeReceta
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "ALTURA_ESTANDAR",
    "CATALOGO_DE_DRIVERS",
    "ROLES_QUE_EDITAN_DRIVERS",
    "DefinicionDeDriver",
    "ErrorDeDriver",
    "ModoDeDriver",
    "OrigenDelValor",
    "ValorVigente",
    "definicion_de",
    "drivers_de_receta",
    "puede_editar_drivers",
    "resolver",
    "validar_modo",
    "validar_que_edita",
    "validar_que_se_puede_cambiar",
    "validar_valor",
]

ModoDeDriver = Literal["fijo", "ajustable"]
OrigenDelValor = Literal["obra", "global", "inicial"]

ALTURA_ESTANDAR = "altura_estandar"
ROLES_QUE_EDITAN_DRIVERS = ("costos", "control_obra")
_DECIMALES = Decimal("0.000001")


class ErrorDeDriver(ErrorDeCuantificacion):
    """Un valor, un modo o un permiso de driver que no vale."""


@dataclass(frozen=True, slots=True)
class DefinicionDeDriver:
    clave: str
    nombre: str
    unidad: str
    inicial: Decimal
    """El valor de partida: el que vale mientras nadie cambie el global."""
    modo_inicial: ModoDeDriver
    nota: str
    minimo: Decimal
    maximo: Decimal
    """Los límites de sentido común de lo que se captura (no son reglas de ingeniería): atrapan un 3000 por 3.00."""
    minimo_exclusivo: bool = False
    """`True`: el valor debe ser mayor que el mínimo (la altura no puede ser 0)."""
    entero: bool = False
    por_confirmar: bool = False
    inmutable: bool = False
    """`True` (F4): ni el modo ni el valor se cambian, ni por proposición: el cálculo lo lee como constante del dominio (`escarpio_minimo`,
    `corona_cimiento_cm`). Seguir siendo `fijo` no basta: un global «fijo» todavía se podía editar y volver «ajustable»."""


def _d(valor: str) -> Decimal:
    return Decimal(valor)


CATALOGO_DE_DRIVERS: tuple[DefinicionDeDriver, ...] = (
    DefinicionDeDriver(
        "altura_estandar", "Altura estándar del muro", "m", _d("3.00"), "ajustable",
        "Alto con que se calculan los elementos paramétricos que no traen el suyo (castillos…). El plano NO lo lee: la altura de un muro trazado la fijan el trazo, la zona de losa, el artefacto (plantilla) o la herramienta.",
        _d("0"), _d("30"), minimo_exclusivo=True,
    ),
    DefinicionDeDriver(
        "separacion_castillos", "Separación entre castillos", "m", _d("3.00"), "ajustable",
        "Se usa en castillos con distribución por separación.", _d("0"), _d("30"), minimo_exclusivo=True,
    ),
    DefinicionDeDriver(
        "desperdicio_mamposteria", "Desperdicio de mampostería", "%", _d("5"), "ajustable",
        "Ejemplo. No se aplica al tabique de 14 cm (EST-02010): su desperdicio va en el elemento (12 % pieza, 5 % mezcla).",
        _d("0"), _d("100"), por_confirmar=True,
    ),
    DefinicionDeDriver(
        "desperdicio_concreto", "Desperdicio de concreto", "%", _d("5"), "ajustable",
        "El catálogo usa 5 % (0.0225 m³/m × 1.05 = 0.023625).", _d("0"), _d("100"),
    ),
    DefinicionDeDriver(
        "traslape_armex_cm", "Traslape del armex", "cm", _d("15"), "ajustable",
        "Pieza de armex de 6 m; el traslape se descuenta de cada pieza en un tramo continuo (cadena): 1 ÷ (6 − 0.15) = 0.1709 pza por metro.",
        _d("0"), _d("200"),
    ),
    DefinicionDeDriver(
        "traslape_varilla_diametros", "Traslape de varilla", "diámetros", _d("40"), "ajustable",
        "Confirmado por el usuario: 40 diámetros (NTC Concreto); pieza de varilla de 12 m.", _d("0"), _d("200"),
    ),
    DefinicionDeDriver(
        "desperdicio_acero", "Desperdicio de acero", "%", _d("0"), "ajustable",
        "El catálogo usa 5 % en lugar de traslape; aquí el traslape se calcula aparte.", _d("0"), _d("100"),
    ),
    DefinicionDeDriver(
        "puntas_inferior_diametros", "Anclaje inferior del castillo", "diámetros", _d("40"), "ajustable",
        "Anclaje en cimentación o losa, con su gancho (NTC Concreto, desarrollo de 40 diámetros). Por confirmar con el estructurista.",
        _d("0"), _d("200"), por_confirmar=True,
    ),
    DefinicionDeDriver(
        "puntas_superior_diametros", "Anclaje superior del castillo", "diámetros", _d("40"), "ajustable",
        "Espera para la losa (40 diámetros) o gancho de 12 diámetros en un remate. Por confirmar con el estructurista.",
        _d("0"), _d("200"), por_confirmar=True,
    ),
    DefinicionDeDriver(
        "puntas_armex_cm", "Puntas del armex del castillo", "cm", _d("50"), "ajustable",
        "SUPUESTO: suma de anclaje inferior y superior del armex. Por confirmar.", _d("0"), _d("500"), por_confirmar=True,
    ),
    DefinicionDeDriver(
        "tolerancia_corte_cm", "Tolerancia de corte", "cm", _d("0"), "ajustable",
        "Falta que se acepta sin pasar al corte siguiente (con 14 cm, el muro de 7 m sale con 2 piezas de 4.00 m).", _d("0"), _d("200"),
    ),
    DefinicionDeDriver(
        "max_piezas_corte", "Máximo de piezas por varilla de un castillo", "piezas", _d("3"), "ajustable",
        "Evita cortes en muchos pedazos para ahorrar unos centímetros; solo si no hay solución con menos piezas se pasa de este máximo.",
        _d("1"), _d("12"), entero=True,
    ),
    DefinicionDeDriver(
        "escarpio_minimo", "Escarpio del muro de cimentación de piedra", "V:H", _d("1.5"), "fijo",
        "Valor fijo (no editable por obra): 1.5 (vertical) : 1 (horizontal), unos 56.3° desde la horizontal. Norma de mampostería, "
        "sección 8.4 Cimientos (figura 8.1): en cimientos de piedra braza la pendiente de las caras inclinadas (escarpio), medida "
        "desde la arista de la dala o muro, no será menor que 1.5 : 1. Título y año de la norma por confirmar.",
        _d("0"), _d("10"), minimo_exclusivo=True, por_confirmar=True, inmutable=True,
    ),
    DefinicionDeDriver(
        "corona_cimiento_cm", "Corona del muro de cimentación de piedra", "cm", _d("40"), "fijo",
        "Siempre 40 cm, sin importar la altura (dato del usuario).", _d("0"), _d("300"), minimo_exclusivo=True,
        inmutable=True,
    ),
)

_POR_CLAVE = {d.clave: d for d in CATALOGO_DE_DRIVERS}


def definicion_de(clave: str) -> DefinicionDeDriver | None:
    return _POR_CLAVE.get(clave)


def puede_editar_drivers(rol: str) -> bool:
    """Q3: Costos y Control de obra editan los drivers; los demás roles solo los leen."""
    return rol in ROLES_QUE_EDITAN_DRIVERS


def validar_que_edita(rol: str) -> None:
    if not puede_editar_drivers(rol):
        raise ErrorDeDriver("Solo Costos y Control de obra editan los drivers.")


def validar_que_se_puede_cambiar(d: DefinicionDeDriver) -> None:
    """F4: `escarpio_minimo` y `corona_cimiento_cm` siguen fijos: no se cambia su valor ni su modo, ni se ajustan por obra."""
    if d.inmutable:
        raise ErrorDeDriver(
            f"«{d.nombre}» es fijo y no se cambia: el cálculo lo lee como constante del dominio (valor {d.inicial:g} {d.unidad})."
        )


def validar_modo(modo: str) -> ModoDeDriver:
    if modo not in ("fijo", "ajustable"):
        raise ErrorDeDriver("El modo de un driver es «fijo» o «ajustable».")
    return modo  # type: ignore[return-value]


def validar_valor(d: DefinicionDeDriver, valor: object) -> Decimal:
    """El valor limpio (hasta 6 decimales) o `ErrorDeDriver`. Admite coma decimal, como se teclea."""
    try:
        n = Decimal(str(valor).strip().replace(",", ".")) if not isinstance(valor, Decimal) else valor
    except (InvalidOperation, ValueError) as e:
        raise ErrorDeDriver(f"«{d.nombre}» debe ser un número.") from e
    if not n.is_finite():
        raise ErrorDeDriver(f"«{d.nombre}» debe ser un número.")
    n = n.quantize(_DECIMALES)
    if d.entero and n != n.to_integral_value():
        raise ErrorDeDriver(f"«{d.nombre}» debe ser un número entero.")
    if n < d.minimo or (d.minimo_exclusivo and n == d.minimo):
        raise ErrorDeDriver(f"«{d.nombre}» debe ser mayor que {d.minimo:g} {d.unidad}." if d.minimo_exclusivo
                            else f"«{d.nombre}» no puede ser menor que {d.minimo:g} {d.unidad}.")
    if n > d.maximo:
        raise ErrorDeDriver(f"«{d.nombre}» no puede pasar de {d.maximo:g} {d.unidad}.")
    return n


@dataclass(frozen=True, slots=True)
class ValorVigente:
    clave: str
    valor: Decimal
    origen: OrigenDelValor
    modo: ModoDeDriver
    valor_global: Decimal
    valor_obra: Decimal | None
    """Lo que la obra tiene guardado, valga o no (si el driver pasó a fijo, queda guardado pero no vale)."""
    ajuste_ignorado: bool
    """La obra tiene un ajuste, pero el driver es fijo: el global manda."""


def resolver(
    d: DefinicionDeDriver,
    *,
    valor_global: Decimal | None,
    modo_global: ModoDeDriver | None,
    valor_obra: Decimal | None,
) -> ValorVigente:
    """El valor vigente de un driver para una obra (o, sin obra, el de la organización)."""
    modo = modo_global or d.modo_inicial
    base = valor_global if valor_global is not None else d.inicial
    if modo == "ajustable" and valor_obra is not None:
        return ValorVigente(d.clave, valor_obra, "obra", modo, base, valor_obra, False)
    origen: OrigenDelValor = "global" if valor_global is not None else "inicial"
    return ValorVigente(d.clave, base, origen, modo, base, valor_obra, valor_obra is not None and modo == "fijo")


def drivers_de_receta(vigentes: Mapping[str, Decimal | float]) -> DriversDeReceta:
    """Los drivers del acero (`DriversDeReceta`) con los valores vigentes; los que no vengan quedan en su valor de partida."""
    def f(clave: str, defecto: float) -> float:
        v = vigentes.get(clave)
        return float(v) if v is not None else defecto

    base = DriversDeReceta()
    return DriversDeReceta(
        traslape_armex_cm=f("traslape_armex_cm", base.traslape_armex_cm),
        traslape_varilla_diametros=f("traslape_varilla_diametros", base.traslape_varilla_diametros),
        puntas_inferior_diametros=f("puntas_inferior_diametros", base.puntas_inferior_diametros),
        puntas_superior_diametros=f("puntas_superior_diametros", base.puntas_superior_diametros),
        puntas_armex_cm=f("puntas_armex_cm", base.puntas_armex_cm),
        tolerancia_corte_cm=f("tolerancia_corte_cm", base.tolerancia_corte_cm),
        max_piezas_corte=int(f("max_piezas_corte", float(base.max_piezas_corte))),
        desperdicio_acero_pct=f("desperdicio_acero", base.desperdicio_acero_pct),
    )
