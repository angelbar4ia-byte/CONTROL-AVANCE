"""Cuántas cuadrillas hacen falta para alcanzar la meta programada (§8.3, §7.6).

## La pregunta

El jefe de obra la formuló así: *"una de sus funciones es indicar cuántas
cuadrillas necesito para alcanzar la meta programada por frente"*. El programa
dice qué hay que hacer y cuándo; el APU dice cuántas jornadas cuesta cada cosa.
Lo que falta es dividir.

## La cuenta, y por qué es tan corta

Una jornada es el trabajo de **una cuadrilla en un día**. Si el programa pide
40 jornadas de albañilería en una semana de 5 días hábiles, hacen falta 8
cuadrillas trabajando toda la semana. No hay más:

    cuadrillas = jornadas del periodo ÷ días hábiles del periodo

Las jornadas salen de la maquinaria que ya existe: `insumos.programado`
reparte cualquier cantidad sobre los periodos honrando los tramos, y filtrada a
`tipo = 'mano_obra'` esa cantidad **son** jornadas —el APU las expresa así
(`MO REPELLADO MURO`: 18.53 m² por jornada de `CUA0010`)—. Aquí no se vuelve a
repartir nada.

## No se redondea, y es la decisión del módulo

2.3 cuadrillas significa que dos no alcanzan y tres sobran un poco. Redondear
aquí escondería esa lectura justo en el número con el que se contrata: hacia
arriba diría que faltan tres cuando el residente sabe que dos aprietan y salen;
hacia abajo prometería una meta que no se cumple. La pantalla presenta la cifra
y el residente decide — y lo que decide se guarda aparte
(`frente_obra.cuadrillas_plan`), al lado de la sugerencia y no encima.

## Lo que este módulo no sabe

Si la cuadrilla existe, si el contratista la tiene disponible, o si ya está
comprometida en otra obra esa misma semana. Eso es planeación de recursos entre
obras y necesita el nivel de proyecto; aquí se contesta la pregunta de una obra.

Módulo puro (§12.11).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

__all__ = [
    "ESCALA_CUADRILLAS",
    "DemandaDeFrente",
    "cuadrillas_necesarias",
    "demanda_por_frente",
]

_CERO = Decimal(0)

ESCALA_CUADRILLAS = Decimal("0.01")
"""Dos decimales. Es lo que distingue 2.30 de 2.00 sin fingir una precisión
que el rendimiento teórico no tiene: viene de un catálogo, no de un cronómetro."""


def cuadrillas_necesarias(*, jornadas: Decimal, dias_habiles: int) -> Decimal:
    """Cuadrillas que hacen falta para gastar esas jornadas en ese periodo.

    Un periodo sin días hábiles devuelve cero y no divide: puede pasar en un
    rango que cae entero en días de descanso, y ahí la respuesta correcta es
    "no hace falta nadie", no una división por cero.
    """
    if dias_habiles <= 0 or jornadas <= 0:
        return _CERO
    return (jornadas / Decimal(dias_habiles)).quantize(ESCALA_CUADRILLAS)


@dataclass(frozen=True, slots=True)
class DemandaDeFrente:
    """Lo que un frente pide en cada periodo, y en total."""

    frente_id: str
    """`''` para lo que no tiene frente asignado; ver `demanda_por_frente`."""
    jornadas: tuple[Decimal, ...]
    cuadrillas: tuple[Decimal, ...]
    total_jornadas: Decimal
    pico_cuadrillas: Decimal
    """La semana más cargada. Es la cifra con la que se contrata: quien te
    presta dos cuadrillas todo el mes no te resuelve la semana que pide cinco."""


def demanda_por_frente(
    *,
    jornadas_por_frente: Mapping[str, Sequence[Decimal]],
    dias_habiles_por_periodo: Sequence[int],
) -> tuple[DemandaDeFrente, ...]:
    """Agrupa la demanda y la convierte a cuadrillas, frente por frente.

    `jornadas_por_frente` viene de explotar el programa y quedarse con la mano
    de obra; `dias_habiles_por_periodo` de contar los días que se trabajan en
    cada columna del calendario.

    Un frente que no aporta jornadas **no se omite**: sale con ceros. Que
    `ACABADOS` pida cero esta semana es información —todavía no arranca— y
    esconderlo dejaría la tabla con menos renglones cada vez que se cambia el
    rango, sin decir por qué.

    Sale ordenado por el pico, de mayor a menor: la pregunta es a quién hay que
    conseguirle más gente.
    """
    salida: list[DemandaDeFrente] = []

    for frente_id, jornadas in jornadas_por_frente.items():
        # Se recorta a los periodos que de verdad hay: una lista más corta que
        # las columnas dejaría celdas sin cubrir, y una más larga sumaría
        # trabajo de fuera del rango consultado.
        por_periodo = tuple(
            jornadas[i] if i < len(jornadas) else _CERO
            for i in range(len(dias_habiles_por_periodo))
        )
        cuadrillas = tuple(
            cuadrillas_necesarias(jornadas=j, dias_habiles=dias)
            for j, dias in zip(por_periodo, dias_habiles_por_periodo, strict=True)
        )
        salida.append(
            DemandaDeFrente(
                frente_id=frente_id,
                jornadas=por_periodo,
                cuadrillas=cuadrillas,
                total_jornadas=sum(por_periodo, _CERO),
                pico_cuadrillas=max(cuadrillas, default=_CERO),
            )
        )

    return tuple(
        sorted(salida, key=lambda d: (-d.pico_cuadrillas, d.frente_id))
    )
