"""Cómo se mide una desviación (§5.1 «Rendimientos», §7.3).

La comparación en sí la hace SQL —sumar cantidades e importes es trabajo de la
base—. Lo que vive aquí es qué significan esos números, y son tres decisiones
que ninguna consulta puede tomar:

1. **Cuándo una desviación importa.** Un 0.3 % sobre un concepto de un millón no
   es lo mismo que un 40 % sobre uno de mil pesos, y ninguno de los dos se
   explica solo con el porcentaje.
2. **Qué hacer cuando no hay contra qué comparar.** Un extra-catálogo no estaba
   presupuestado: su desviación no es «infinito por ciento», es «todo esto es
   extra».
3. **Qué es peor.** Gastar de más y gastar de menos no son el mismo problema —el
   segundo suele ser trabajo que no se hizo, no un ahorro.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

__all__ = [
    "UMBRAL_DESVIACION",
    "Desviacion",
    "clasificar",
    "desviacion_de",
]

UMBRAL_DESVIACION = Decimal("5")
"""Porcentaje a partir del cual una desviación se marca (§3.6).

Es el default. El §3.6 lo declara **configurable por organización**
(`configuracion.clave = 'umbral_desviacion'`), así que quien tenga el valor de
la org debe pasarlo; esta constante es lo que se usa cuando no hay ninguno
configurado, no una regla fija.
"""

MONTO_IRRELEVANTE = Decimal("1000")
"""Por debajo de esto, un porcentaje alto no es noticia.

Sin este piso, un concepto de cien pesos que se pasó por veinte encabezaría la
lista con un 20 % y empujaría fuera de la vista a uno de un millón que se pasó
por el 3 %. La lista se ordena por importe absoluto justamente por eso, y esto
es su contraparte al clasificar.
"""


@dataclass(frozen=True, slots=True)
class Desviacion:
    """Lo que se desvió una partida, en dinero y en porcentaje."""

    importe: Decimal
    """Ejecutado menos presupuestado. Positivo es gastar de más."""
    porcentaje: Decimal | None
    """`None` cuando no había presupuesto: dividir entre cero no da infinito,
    da que la pregunta no aplica."""
    clasificacion: str
    """`sin_presupuesto` · `no_ejecutado` · `sobre_costo` · `bajo_costo` ·
    `dentro_de_rango`."""

    @property
    def relevante(self) -> bool:
        """¿Merece que alguien la mire?"""
        return self.clasificacion in ("sin_presupuesto", "no_ejecutado", "sobre_costo", "bajo_costo")


def desviacion_de(
    *,
    importe_presupuestado: Decimal,
    importe_ejecutado: Decimal,
    umbral: Decimal = UMBRAL_DESVIACION,
) -> Desviacion:
    """Compara dos importes y dice qué tan lejos quedaron (§3.6)."""
    diferencia = importe_ejecutado - importe_presupuestado

    if importe_presupuestado == 0:
        # No estaba presupuestado. Si además no se ejecutó nada, no hay nada que
        # decir; si se ejecutó, es extra y el porcentaje no aplica.
        clasificacion = "sin_presupuesto" if importe_ejecutado != 0 else "dentro_de_rango"
        return Desviacion(
            importe=diferencia, porcentaje=None, clasificacion=clasificacion
        )

    porcentaje = (diferencia / importe_presupuestado) * Decimal(100)

    if importe_ejecutado == 0:
        # Presupuestado y sin ejecutar: no es un ahorro, es trabajo que no se ha
        # hecho —o que se dejó de hacer—. Se distingue del `bajo_costo` porque
        # la acción es otra: ahí se revisa el precio, aquí se pregunta por qué
        # no se hizo.
        return Desviacion(
            importe=diferencia, porcentaje=porcentaje, clasificacion="no_ejecutado"
        )

    return Desviacion(
        importe=diferencia,
        porcentaje=porcentaje,
        clasificacion=clasificar(
            diferencia=diferencia, porcentaje=porcentaje, umbral=umbral
        ),
    )


def clasificar(
    *, diferencia: Decimal, porcentaje: Decimal, umbral: Decimal
) -> str:
    """Traduce una desviación a una de tres palabras.

    El piso de monto es lo que impide que un concepto de cien pesos con un 20 %
    de desviación se vea igual de importante que uno de un millón con un 3 %.
    """
    if abs(porcentaje) < umbral or abs(diferencia) < MONTO_IRRELEVANTE:
        return "dentro_de_rango"
    return "sobre_costo" if diferencia > 0 else "bajo_costo"
