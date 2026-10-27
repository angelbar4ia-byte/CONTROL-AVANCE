"""El cuantificador: `plano → medida → cantidad` (cerebro MODELO.md §1b).

`TRAZO` y `NOTA_PLANO` no traen ninguna regla de dominio propia que valga
la pena —son alta simple, el §1b nunca les da un ciclo de vida— así que lo
único que vive aquí es `ENLACE_CUANTIFICACION`, que sí tiene invariantes
reales (exclusividad de nodo, factor positivo), y la única función que el
dominio necesita calcular de la cuantificación: sumar lo que el adaptador
SQL ya midió.

**Qué NO hace este módulo, a propósito (§12.11):**

- Nunca calcula `ST_Area`/`ST_Length`/`ST_Perimeter` ni ningún otro `ST_*`:
  eso vive en el adaptador SQL (`adapters/repos/cuantificacion_sql.py`),
  sobre `trazo.geometria`. Aquí solo se suma `medida_valor × factor` ya
  calculado — el dominio no sabe qué es PostGIS.
- Nunca decide qué hacer con la cantidad total (compararla contra
  `actividad.cant_base` y proponer una `Desviacion`, o sobreescribir
  `prototipo_nodo.cantidad`): eso es orquestación de la capa de
  aplicación, que reusa `domain.presupuesto.rendimiento.desviacion_de` y
  `RepositorioPrototipoNodo.actualizar_cantidad` ya existentes — no
  duplica esa lógica aquí.

Módulo puro: sin FastAPI, SQLModel, PostGIS ni RLS (§12.11).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.shared.diccionario import (
    MedidaCuantificacion,
    TipoNodoCuantificacion,
)

__all__ = [
    "EnlaceCuantificacion",
    "ErrorDeCuantificacion",
    "MedidaDeEnlace",
    "cantidad_medida",
]


class ErrorDeCuantificacion(ValueError):
    """Dato inconsistente al construir un `ENLACE_CUANTIFICACION`
    (MODELO.md §1b)."""


@dataclass(frozen=True, slots=True)
class EnlaceCuantificacion:
    """Un `ENLACE_CUANTIFICACION` ya validado (MODELO.md §1b).

    `actividad_id`/`prototipo_nodo_id` son mutuamente excluyentes — el nodo
    es exactamente uno de los dos, mismo patrón que
    `Desviacion.insumo_id`/`concepto_id` (`domain/desviacion/desviacion.py`)
    y `ck_enlace_cuantificacion_nodo` (migración 0057). El tipo de nodo no
    es un campo propio: se deriva de cuál de los dos ids está lleno
    (propiedad `tipo_nodo`), para no poder guardar un `tipo_nodo` que
    contradiga a sus propios ids — mismo criterio que
    `Desviacion.tipo_nodo`.
    """

    trazo_id: str
    actividad_id: str | None
    prototipo_nodo_id: str | None
    medida: MedidaCuantificacion
    factor: Decimal
    vigente: bool = True
    matriz_concepto_id: str | None = None
    """La matriz interna de la actividad que se mide (D-583); solo con `actividad_id`."""

    def __post_init__(self) -> None:
        if self.matriz_concepto_id is not None and self.actividad_id is None:
            raise ErrorDeCuantificacion(
                "Una matriz interna se mide dentro de una actividad: sin actividad no hay "
                "matriz que cuantificar (0085, D-583)."
            )
        tiene_actividad = self.actividad_id is not None
        tiene_prototipo = self.prototipo_nodo_id is not None
        if tiene_actividad == tiene_prototipo:
            raise ErrorDeCuantificacion(
                "Un enlace de cuantificación apunta a una actividad o a un "
                "prototipo_nodo, nunca a los dos ni a ninguno (MODELO.md "
                "§1b, `ck_enlace_cuantificacion_nodo`)."
            )

        if self.factor <= 0:
            raise ErrorDeCuantificacion(
                "El factor de un enlace de cuantificación debe ser "
                "positivo: medida × factor = cantidad no tiene sentido con "
                "un factor cero o negativo (MODELO.md §1b)."
            )

        # `conteo` ya es un número de instancias (cuántos trazos enlazan a
        # este nodo, nunca una función de PostGIS); un factor fraccionario
        # mezclaría ahí una unidad de conversión continua que el conteo no
        # es. `area`/`perimetro`/`longitud` sí la necesitan con toda
        # libertad (p. ej. convertir m² a otra unidad de presupuesto), así
        # que esta validación es exclusiva de `CONTEO` — no una regla
        # general de "factor siempre entero".
        if (
            self.medida is MedidaCuantificacion.CONTEO
            and self.factor != self.factor.to_integral_value()
        ):
            raise ErrorDeCuantificacion(
                "Un enlace de conteo espera un factor sin fracción: el "
                "conteo ya es un número de instancias, no una medida "
                "continua que admita un factor de conversión fraccionario "
                "(MODELO.md §1b)."
            )

    @property
    def tipo_nodo(self) -> TipoNodoCuantificacion:
        """Derivado, no persistido como campo propio de este dataclass —la
        columna `enlace_cuantificacion.tipo_nodo` de la base sí lo guarda
        explícito, porque un `CHECK` de Postgres no puede inferirlo con la
        misma facilidad que una propiedad de Python."""
        return (
            TipoNodoCuantificacion.ACTIVIDAD
            if self.actividad_id is not None
            else TipoNodoCuantificacion.PROTOTIPO_NODO
        )


@dataclass(frozen=True, slots=True)
class MedidaDeEnlace:
    """Lo que el adaptador SQL ya calculó para un enlace — `ST_Area`/
    `ST_Length`/`ST_Perimeter` sobre `trazo.geometria`, o `1` si la medida
    es `conteo` — junto con su `factor` y si está vigente. El dominio nunca
    vuelve a calcular `medida_valor`, solo lo suma (§12.11)."""

    medida_valor: Decimal
    factor: Decimal
    vigente: bool = True


def cantidad_medida(enlaces: Sequence[MedidaDeEnlace]) -> Decimal:
    """Suma `medida_valor × factor` sobre los enlaces **vigentes** de un
    mismo nodo (MODELO.md §1b: "un nodo puede tener muchos enlaces
    vigentes a la vez ... y todos suman entre sí").

    Los no vigentes se ignoran aquí, nunca se excluyen antes de llamar a
    esta función: así una sola lista —vigentes y reemplazados mezclados,
    tal como el adaptador los trae— basta para auditar "qué sumó" y "qué
    se reemplazó" a la vez (MODELO.md §1b: un enlace no vigente "queda
    como evidencia, no se borra").
    """
    return sum(
        (enlace.medida_valor * enlace.factor for enlace in enlaces if enlace.vigente),
        start=Decimal(0),
    )
