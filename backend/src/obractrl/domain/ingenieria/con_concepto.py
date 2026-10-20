"""Reconstrucción de un archivo `CON_CONCEPTO`: el concepto ya viene
nombrado por `fila.agrupador` (CONOCIMIENTO.md §11.8) — a diferencia de la
reversión por destajo (`domain.ingenieria.reversion`), aquí no hay que
*buscar* candidatos, porque el archivo ya dice cuál es.

Verificado contra el archivo real de `ALAMO 18`
(`INGENIERIA_-_ALAMO_18__-_CEMENTO_EXTRA_EN_FACHADA_POR_AJUSTE_DEL_NUEVO_
RENDIMIENTO.csv`): el agrupador `ALB-01212` ("Repellado en muros de
fachada...") es un concepto real, y su insumo anclado (`ADH-00005`,
CEMENTO) es un **material**, no un destajo — `ES_DESTAJO` no aplicaría, y
no tiene por qué: esta reconstrucción nunca filtra por esa huella.

**La fórmula, decidida con el usuario:** para cada fila del bloque,
``cantidad_real_del_concepto = fila.cantidad ÷ rendimiento(agrupador,
fila.clave)``. El rendimiento se busca en profundidad
(`reversion.rendimiento_profundo`, que ya usa `apu.explotar` para la clase
`COMPUESTO` de la reversión por destajo) y no solo en la matriz directa
del concepto: verificado contra el catálogo real, `ADH-00005` no es hijo
directo de `ALB-01212` —solo lo es del compuesto `MEZ-07010`, que SÍ cuelga
de `ALB-01212`—, así que limitarse a la matriz directa dejaría este mismo
archivo real sin nada que reconstruir. "El ancla puede ser CUALQUIER
insumo de la matriz" (decisión del encargo) se lee, por eso, como
"cualquier insumo alcanzable desde el concepto, a cualquier profundidad" —
el mismo criterio de alcance que ya usa la clase `COMPUESTO`, nunca uno
más estrecho que el real.

Si la clave no aparece en ninguna profundidad de la matriz del concepto,
no se inventa un rendimiento (§3.3): la fila queda como
`TipoPendiente.RENDIMIENTO_NO_ENCONTRADO`.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11). No decide a qué etapa
del presupuesto pertenece el concepto reconstruido —eso exige el árbol ya
resuelto contra un prototipo concreto, que este módulo no recibe— ni
persiste nada; quien orquesta (`AplicadorIngenieriaLote`) resuelve la
etapa y decide qué hacer con el resultado.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.cargadores.ingenieria_lote import FilaInsumoIngenieria
from obractrl.domain.cargadores.reporte import PendientePropuesto, TipoPendiente
from obractrl.domain.catalogos.apu import Componente
from obractrl.domain.ingenieria.reversion import rendimiento_profundo

__all__ = ["ReconstruccionConcepto", "reconstruir_con_concepto"]


@dataclass(frozen=True, slots=True)
class ReconstruccionConcepto:
    """Una fila de insumo de un bloque `CON_CONCEPTO`, ya dividida entre el
    rendimiento de su clave dentro del concepto nombrado por
    `fila.agrupador`.

    Misma forma que necesita `ReversionDestajo` (mismos nombres de campo
    que relevantes a `cantidad_real`/`reparto`) para que quien orquesta
    pueda alimentar el mismo flujo de `Desviacion`/reclasificación sin un
    camino paralelo — ver `AplicadorIngenieriaLote`.
    """

    concepto: str
    clave_insumo: str
    descripcion: str
    precio: Decimal | None
    cantidad_insumo: Decimal
    """La cantidad cruda que trae la fila del archivo (p. ej. 18 BTS de
    `ADH-00005`) — nunca la cantidad reconstruida del concepto."""

    rendimiento: Decimal
    cantidad_real: Decimal
    """``cantidad_insumo / rendimiento``: la cantidad reconstruida del
    CONCEPTO (`agrupador`), no del insumo."""


def reconstruir_con_concepto(
    filas_insumo: Sequence[FilaInsumoIngenieria],
    composiciones: Mapping[str, Sequence[Componente]],
) -> tuple[tuple[ReconstruccionConcepto, ...], tuple[PendientePropuesto, ...]]:
    """Reconstruye, fila por fila, la cantidad real del concepto que cada
    insumo de un archivo `CON_CONCEPTO` evidencia.

    Filas sin `agrupador` (no debería pasar en un archivo ya detectado
    como `CON_CONCEPTO` — `detectar_estructura` exige al menos un
    agrupador— pero una fila antes del primer agrupador del bloque, si
    existiera, no tendría concepto contra el cual reconstruir) se omiten
    en silencio, igual que `reversion.revertir_destajos` omite las filas
    sin ``etapa`` conocida.
    """
    resultados: list[ReconstruccionConcepto] = []
    pendientes: list[PendientePropuesto] = []
    cache: dict[str, tuple] = {}

    for f in filas_insumo:
        concepto = f.agrupador
        if concepto is None:
            continue
        rendimiento = rendimiento_profundo(concepto, f.clave, composiciones, cache)
        if rendimiento <= 0:
            pendientes.append(
                PendientePropuesto(
                    tipo=TipoPendiente.RENDIMIENTO_NO_ENCONTRADO,
                    entidad="reconstruccion_con_concepto",
                    valor_origen=f.clave,
                    propuesta={
                        "concepto": concepto,
                        "descripcion": f.descripcion,
                        "cantidad": str(f.cantidad),
                        "motivo": (
                            "La clave no aparece en la matriz del concepto "
                            "(ni directa ni en profundidad de un compuesto): "
                            "no hay rendimiento con el que dividir (§3.3)."
                        ),
                    },
                    origen_ref=f"fila {f.fila}",
                )
            )
            continue
        resultados.append(
            ReconstruccionConcepto(
                concepto=concepto,
                clave_insumo=f.clave,
                descripcion=f.descripcion,
                precio=f.precio,
                cantidad_insumo=f.cantidad,
                rendimiento=rendimiento,
                cantidad_real=f.cantidad / rendimiento,
            )
        )

    return tuple(resultados), tuple(pendientes)
