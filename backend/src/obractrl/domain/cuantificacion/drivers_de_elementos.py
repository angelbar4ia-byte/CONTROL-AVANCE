"""Los drivers de la obra que leen los cálculos de los elementos (Ola 4, «drivers conectados»).

`drivers.py` define los drivers y resuelve su valor vigente en una obra (global, por obra o mixto). Aquí se **conectan** con los
cálculos de los elementos de la biblioteca (castillos, trabes, bastones, receta del acero). Orden de precedencia, igual en todos:

1. el **valor explícito de la petición** (lo que el usuario tecleó en la tarjeta o mandó el cliente de la API);
2. el **driver vigente de la obra** (si la petición trae `obra_id`);
3. el **valor por defecto** que el cálculo ya tenía (el de `DriversDeReceta`, 5 % de concreto, 3.00 m…).

Sin obra, el cálculo es **idéntico** al de siempre: nada de lo guardado ni de lo que ya se calculaba cambia. Cada valor usado se
devuelve con su **fuente** (`peticion`, `obra`, `global` o `defecto`) para que la pantalla diga de dónde salió.

Notas del spec que se respetan aquí: `desperdicio_mamposteria` **no** se aplica al tabique de 14 cm (su desperdicio va en el
elemento: 12 % de pieza y 5 % de mezcla), y los drivers de modo «fijo» (`escarpio_minimo`, `corona_cimiento_cm`) no se editan por
obra: los cálculos de piedra los siguen leyendo como constantes.

Funciones puras, sin base de datos.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal

from obractrl.domain.cuantificacion.drivers import ValorVigente, definicion_de
from obractrl.domain.cuantificacion.receta_acero import DriversDeReceta

__all__ = [
    "CLAVES_DE_RECETA",
    "DriverUsado",
    "FuenteDelValor",
    "altura_de_obra",
    "desperdicio_concreto_de_obra",
    "receta_de_obra",
    "valor_de_driver",
]

FuenteDelValor = Literal["peticion", "obra", "global", "defecto"]

CLAVES_DE_RECETA: dict[str, str] = {
    "traslape_armex_cm": "traslape_armex_cm",
    "traslape_varilla_diametros": "traslape_varilla_diametros",
    "puntas_inferior_diametros": "puntas_inferior_diametros",
    "puntas_superior_diametros": "puntas_superior_diametros",
    "puntas_armex_cm": "puntas_armex_cm",
    "tolerancia_corte_cm": "tolerancia_corte_cm",
    "max_piezas_corte": "max_piezas_corte",
    "desperdicio_acero_pct": "desperdicio_acero",
}
"""Campo de `DriversDeReceta` → clave del driver del Paramétrico (solo difiere el desperdicio del acero)."""

Vigentes = Mapping[str, ValorVigente]


@dataclass(frozen=True, slots=True)
class DriverUsado:
    """Un driver que el cálculo leyó, con el valor que usó y de dónde salió."""

    clave: str
    nombre: str
    unidad: str
    valor: float
    fuente: FuenteDelValor


def _numero(v: Decimal | float) -> float:
    return float(v)


def valor_de_driver(
    clave: str, *, explicito: float | None, defecto: float, vigentes: Vigentes | None
) -> DriverUsado:
    """El valor de un driver para un cálculo: petición > obra > defecto.

    `vigentes` son los drivers de la obra (`None` = sin obra: el cálculo vale lo que siempre valió). Un driver cuyo valor vigente es
    el de partida sin que nadie lo cambiara cuenta como «defecto»: no es una decisión de la obra ni de la organización.
    """
    d = definicion_de(clave)
    nombre, unidad = (d.nombre, d.unidad) if d else (clave, "")
    if explicito is not None:
        return DriverUsado(clave, nombre, unidad, _numero(explicito), "peticion")
    v = vigentes.get(clave) if vigentes is not None else None
    if v is None or v.origen == "inicial":
        return DriverUsado(clave, nombre, unidad, defecto, "defecto")
    return DriverUsado(clave, nombre, unidad, _numero(v.valor), "obra" if v.origen == "obra" else "global")


def receta_de_obra(
    vigentes: Vigentes | None, explicitos: Mapping[str, float] | None = None
) -> tuple[DriversDeReceta, list[DriverUsado]]:
    """Los drivers del acero para un cálculo. `explicitos` trae solo lo que la petición mandó (campo de `DriversDeReceta` → valor)."""
    explicitos = explicitos or {}
    base = DriversDeReceta()
    cambios: dict[str, float | int] = {}
    usados: list[DriverUsado] = []
    for campo, clave in CLAVES_DE_RECETA.items():
        defecto = float(getattr(base, campo))
        u = valor_de_driver(clave, explicito=explicitos.get(campo), defecto=defecto, vigentes=vigentes)
        cambios[campo] = int(u.valor) if campo == "max_piezas_corte" else u.valor
        usados.append(u)
    return replace(base, **cambios), usados


def desperdicio_concreto_de_obra(
    vigentes: Vigentes | None, *, explicito_pct: float | None = None, defecto_pct: float = 5.0
) -> tuple[float, DriverUsado]:
    """El desperdicio de concreto (en %) del cálculo: petición > driver `desperdicio_concreto` de la obra > 5 %."""
    u = valor_de_driver("desperdicio_concreto", explicito=explicito_pct, defecto=defecto_pct, vigentes=vigentes)
    return u.valor, u


def altura_de_obra(
    vigentes: Vigentes | None, *, explicita_m: float | None = None, defecto_m: float = 3.0
) -> tuple[float, DriverUsado]:
    """La altura del cálculo (en m): petición > driver `altura_estandar` de la obra > la estándar de partida (3.00 m)."""
    u = valor_de_driver("altura_estandar", explicito=explicita_m, defecto=defecto_m, vigentes=vigentes)
    return u.valor, u
