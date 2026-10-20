"""La entidad `Desviacion` (cerebro MODELO.md §5g, CONOCIMIENTO.md §13.6).

Espejo de la tabla `desviacion` (migración 0054): el dominio valida el mismo
invariante que ya impone la base —doble validación, mismo criterio que usa
`Componente` (`domain/catalogos/apu.py`, `ck_explosion_hijo`) y
`MovimientoAlmacen` (`domain/materiales/reglas.py`)— para que un caso de uso
nunca dependa solo del CHECK para enterarse de un dato mal armado.

`cantidad_plan`/`precio_plan` se congelan al detectar la desviación y nunca
se recalculan (MODELO.md §5g): este dataclass es un registro histórico, no
una vista — no hay método que los vuelva a calcular contra el catálogo
vigente.

Qué NO valida este módulo, a propósito: que `causa` corresponda a la
CATEGORÍA del insumo/concepto (material · mano_de_obra · herramienta ·
maquinaria · contratos, CONOCIMIENTO.md §13.6). Esta fila no carga esa
categoría —vive en `insumo.tipo`, otra tabla— y cruzarla exigiría una
consulta, que no es trabajo de un dataclass puro (§12.11: ningún módulo de
dominio toca la base). Lo que SÍ se valida aquí, porque no exige ninguna
consulta, es la mitad que la propia fila ya contiene: que `causa`
pertenezca al lado `precio`/`consumo` que le corresponde a `tipo`.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from obractrl.domain.shared.diccionario import (
    CausaDesviacion,
    TipoDesviacion,
    TipoNodoDesviacion,
)

__all__ = ["CAUSA_ES_DE_TIPO", "Desviacion", "ErrorDeDesviacion"]


class ErrorDeDesviacion(ValueError):
    """Dato inconsistente al construir una `Desviacion` (MODELO.md §5g)."""


CAUSA_ES_DE_TIPO: dict[CausaDesviacion, TipoDesviacion] = {
    # material · precio
    CausaDesviacion.MERCADO: TipoDesviacion.PRECIO,
    CausaDesviacion.VOLUMEN: TipoDesviacion.PRECIO,
    CausaDesviacion.PROVEEDOR_DISTINTO: TipoDesviacion.PRECIO,
    CausaDesviacion.CAMBIO_DE_PRESENTACION: TipoDesviacion.PRECIO,
    # material · consumo
    CausaDesviacion.DESPERDICIO_MAYOR_AL_TEORICO: TipoDesviacion.CONSUMO,
    CausaDesviacion.MERMA_POR_DANO_CLIMA_O_ROBO: TipoDesviacion.CONSUMO,
    CausaDesviacion.SUSTITUCION_POR_EQUIVALENTE: TipoDesviacion.CONSUMO,
    # mano_de_obra · precio
    CausaDesviacion.RENEGOCIACION: TipoDesviacion.PRECIO,
    CausaDesviacion.URGENCIA: TipoDesviacion.PRECIO,
    CausaDesviacion.ALZA_DE_TABULADOR: TipoDesviacion.PRECIO,
    # mano_de_obra · consumo
    CausaDesviacion.RENDIMIENTO_REAL_DISTINTO: TipoDesviacion.CONSUMO,
    CausaDesviacion.RETRABAJO: TipoDesviacion.CONSUMO,
    CausaDesviacion.TRABAJO_FUERA_DE_ALCANCE: TipoDesviacion.CONSUMO,
    # herramienta · precio
    CausaDesviacion.TARIFA_DISTINTA: TipoDesviacion.PRECIO,
    # herramienta · consumo
    CausaDesviacion.DIAS_REALES_DE_RENTA: TipoDesviacion.CONSUMO,
    CausaDesviacion.EQUIPO_PARADO: TipoDesviacion.CONSUMO,
    # maquinaria · precio
    CausaDesviacion.TARIFA: TipoDesviacion.PRECIO,
    CausaDesviacion.COMBUSTIBLE: TipoDesviacion.PRECIO,
    # maquinaria · consumo
    CausaDesviacion.HORAS_EFECTIVAS_CONTRA_FACTURADAS: TipoDesviacion.CONSUMO,
    # contratos · consumo
    CausaDesviacion.VOLUMEN_REALMENTE_EJECUTADO: TipoDesviacion.CONSUMO,
}
"""A qué `TipoDesviacion` pertenece cada causa de "Causas por categoría"
(CONOCIMIENTO.md §13.6). Es la mitad de la regla de la tabla que SÍ puede
validarse en dominio puro, sin consultar `insumo.tipo` (ver docstring del
módulo)."""


@dataclass(frozen=True, slots=True)
class Desviacion:
    """Una fila de `desviacion` (migración 0054), ya validada.

    ``insumo_id``/``concepto_id`` son mutuamente excluyentes — el nodo es
    exactamente uno de los dos, igual que `Componente.clave_insumo`/
    `clave_concepto` en `domain/catalogos/apu.py`. El tipo del nodo
    (:class:`TipoNodoDesviacion`) no es un campo propio: se deriva de cuál
    de los dos está lleno (propiedad :attr:`tipo_nodo`), para no poder
    guardar un ``tipo_nodo`` que contradiga a sus propios ids.
    """

    insumo_id: str | None
    concepto_id: str | None
    obra_id: str
    tipo: TipoDesviacion
    monto: Decimal
    cantidad_plan: Decimal | None
    cantidad_real: Decimal | None
    precio_plan: Decimal | None
    precio_real: Decimal | None
    detectada_en: datetime
    causa: CausaDesviacion | None = None
    causa_capturada_por: str | None = None
    causa_capturada_en: datetime | None = None

    def __post_init__(self) -> None:
        tiene_insumo = self.insumo_id is not None
        tiene_concepto = self.concepto_id is not None
        if tiene_insumo == tiene_concepto:
            raise ErrorDeDesviacion(
                "Una desviación apunta a un insumo o a un concepto, nunca a "
                "los dos ni a ninguno (MODELO.md §5g, `ck_desviacion_nodo`)."
            )

        if self.tipo is TipoDesviacion.CONSUMO:
            if self.precio_plan is not None or self.precio_real is not None:
                raise ErrorDeDesviacion(
                    "Una desviación de consumo no lleva precio_plan/"
                    "precio_real: los dos factores de la fórmula nunca se "
                    "mezclan en la misma fila (CONOCIMIENTO.md §13.6)."
                )
        else:
            if self.cantidad_plan is not None or self.cantidad_real is not None:
                raise ErrorDeDesviacion(
                    "Una desviación de precio no lleva cantidad_plan/"
                    "cantidad_real: los dos factores de la fórmula nunca se "
                    "mezclan en la misma fila (CONOCIMIENTO.md §13.6)."
                )

        if self.causa is not None and CAUSA_ES_DE_TIPO[self.causa] is not self.tipo:
            raise ErrorDeDesviacion(
                f"La causa {self.causa!r} es de tipo "
                f"{CAUSA_ES_DE_TIPO[self.causa]!r}, pero esta fila es de "
                f"tipo {self.tipo!r} (CONOCIMIENTO.md §13.6)."
            )

        # `causa_capturada_en` marca CUÁNDO se llenó `causa`: no puede
        # existir sin ella. Al revés sí se permite un instante — `causa` se
        # llena primero dentro de la misma escritura, por eso el chequeo va
        # en un solo sentido (igual que el CHECK `ck_desviacion_captura`).
        if self.causa_capturada_en is not None and self.causa is None:
            raise ErrorDeDesviacion(
                "causa_capturada_en no puede tener valor si causa sigue en "
                "null: no hay captura de una causa que no se capturó."
            )

    @property
    def tipo_nodo(self) -> TipoNodoDesviacion:
        """Derivado, no persistido como campo propio de este dataclass —la
        columna `desviacion.tipo_nodo` de la base sí lo guarda explícito,
        porque un `CHECK` de Postgres no puede inferirlo con la misma
        facilidad que una propiedad de Python."""
        return (
            TipoNodoDesviacion.INSUMO
            if self.insumo_id is not None
            else TipoNodoDesviacion.CONCEPTO
        )

    @property
    def tiene_causa(self) -> bool:
        """`causa IS NULL` es un estado válido (regla de captura 3, MODELO.md
        §5g) — esta propiedad solo nombra la pregunta, no la penaliza."""
        return self.causa is not None
