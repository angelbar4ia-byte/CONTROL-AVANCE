"""Hallazgos de desviación candidatos, de comparar la ingeniería del lote
reconstruida contra lo que el prototipo predice — ANTES de construir
(CONOCIMIENTO.md §11.7: "la comparación usa el mecanismo que ya existe").

**Solo lo que esta fase puede saber de verdad.** La reversión por destajo
(`domain.ingenieria.reversion`) reconstruye, para cada concepto resuelto,
una CANTIDAD — nunca un precio observado de mercado: la ingeniería del
lote no trae una factura, trae lo que se planeó comprar. Por eso este
módulo genera **solo** `TipoDesviacion.CONSUMO` (CONOCIMIENTO.md §13.6:
``(cantidad_real - cantidad_plan) × precio_plan``, el precio se queda fijo
en el del catálogo) — nunca `TipoDesviacion.PRECIO`, que necesitaría un
precio real que esta fase no tiene. Comparar por INSUMO (material) en vez
de por concepto —la reconciliación de 519 claves de §11.11— es una
extensión mayor que esta fase no construye (ver el docstring del paquete y
el reporte de la tarea): lo que sí construye es exactamente lo que la
reversión por destajo entrega, concepto por concepto.

**Nunca decide la causa.** Cada `Desviacion` sale con ``causa=None``
(MODELO.md §5g: "causa IS NULL es un estado válido") — asignar una de las
nueve causas raíz (`domain.desviacion.nueve_causas`) es trabajo de quien
use este resultado después, con el contexto de obra que esta fase no
tiene (si el cliente lo pidió, si hubo control de cambio...).

**Nunca persiste.** Devuelve las instancias, no las escribe (§12.11,
ningún módulo de dominio toca la base) — y, como `Desviacion` exige
``concepto_id``/``obra_id`` (identificadores de catálogo, no claves,
§3.3), este módulo los recibe ya resueltos de quien llama (``obra_id``,
``concepto_id_de_clave``): no inventa un cruce contra el catálogo que no
le corresponde hacer a un dataclass puro.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal

from obractrl.domain.cargadores.reporte import PendientePropuesto, TipoPendiente
from obractrl.domain.desviacion.desviacion import Desviacion
from obractrl.domain.ingenieria.reversion import ReversionDestajo
from obractrl.domain.presupuesto.rendimiento import UMBRAL_DESVIACION, desviacion_de
from obractrl.domain.shared.diccionario import TipoDesviacion

__all__ = ["generar_desviaciones_candidatas"]


def generar_desviaciones_candidatas(
    resultados_reversion: Sequence[ReversionDestajo],
    presupuesto_por_etapa: Mapping[str, Mapping[str, Decimal]],
    precio_concepto: Mapping[str, Decimal],
    *,
    obra_id: str,
    concepto_id_de_clave: Mapping[str, str],
    detectada_en: datetime,
    umbral: Decimal = UMBRAL_DESVIACION,
) -> tuple[tuple[Desviacion, ...], tuple[PendientePropuesto, ...]]:
    """Compara, concepto por concepto, lo que la reversión reconstruyó
    contra lo que el presupuesto del prototipo ya decía, y devuelve las
    `Desviacion` candidatas (``causa=None``) más allá del umbral de
    `rendimiento.desviacion_de` — sin persistir nada.

    - ``precio_concepto``: clave de concepto → su precio unitario en el
      prototipo ya identificado (el CPU de `apu.explotar`, ``.precio.
      total``). Un concepto resuelto que no aparece aquí no genera
      `Desviacion` —sin precio no hay monto que calcular— y tampoco
      pendiente: es una precondición de la llamada, no un dato de la obra.
    - ``concepto_id_de_clave``: clave → id de catálogo (`concepto.id`).
      Un concepto resuelto sin id aquí no puede construir una `Desviacion`
      válida (exige ``concepto_id``, §3.3 lo resuelve el borde, no este
      módulo) — se reporta como `TipoPendiente.MAPEO_NO_RECONOCIDO` en vez
      de perderse en silencio.
    - Solo entran los `ReversionDestajo` **resueltos** (``reparto is not
      None``): `VARIOS` sin cierre exacto y `SIN` ya quedaron como
      `PendientePropuesto` en `reversion.revertir_destajos` — repetirlos
      aquí como `Desviacion` inventaría una cantidad que nadie confirmó.
    - Cuando ``reparto[concepto] == cantidad_plan`` no hay nada que
      reportar: es justo el caso `VARIOS` que cerró exacto (§11.9, D-489)
      o un `UNICO` que confirmó el presupuesto — la ausencia de
      `Desviacion` para ese concepto **es** el resultado correcto.
    """
    # Un mismo concepto puede resolverse desde DOS destajos distintos —p.
    # ej. `EST-01053` desde `MOC-01010` (directo) y, en profundidad, desde
    # `MOC-12010` (vía el compuesto `ZA1-000001`, §11.9)— con estimaciones
    # de cantidad que no tienen por qué coincidir. CONOCIMIENTO.md §11.13
    # ya trae la regla y un caso real verificado ("dos destajos de un
    # mismo concepto en desacuerdo se resuelven por el de mayor costo"):
    # se usa el de mayor ``precio × cantidad_real`` observado en la
    # ingeniería, nunca un promedio ni "el que llegó primero".
    por_concepto: dict[str, list[tuple[Decimal, Decimal, str]]] = {}
    for resultado in resultados_reversion:
        if resultado.reparto is None:
            continue
        costo_destajo = (resultado.precio or Decimal(0)) * resultado.cantidad_real
        for concepto, cantidad_real in resultado.reparto.items():
            por_concepto.setdefault(concepto, []).append((costo_destajo, cantidad_real, resultado.etapa))

    desviaciones: list[Desviacion] = []
    pendientes: list[PendientePropuesto] = []

    for concepto, estimaciones in por_concepto.items():
        costo_destajo, cantidad_real, etapa = max(estimaciones, key=lambda e: e[0])
        cantidades_plan = presupuesto_por_etapa.get(etapa, {})

        precio_plan = precio_concepto.get(concepto)
        if precio_plan is None:
            continue

        cantidad_plan = cantidades_plan.get(concepto, Decimal(0))
        if cantidad_real == cantidad_plan:
            continue

        concepto_id = concepto_id_de_clave.get(concepto)
        if concepto_id is None:
            pendientes.append(
                PendientePropuesto(
                    tipo=TipoPendiente.MAPEO_NO_RECONOCIDO,
                    entidad="desviacion_candidata",
                    valor_origen=concepto,
                    propuesta={
                        "motivo": (
                            "La reversión reconstruyó una cantidad para este "
                            "concepto, pero no hay id de catálogo con el que "
                            "construir la Desviacion (§3.3)."
                        ),
                        "cantidad_real": str(cantidad_real),
                        "cantidad_plan": str(cantidad_plan),
                    },
                )
            )
            continue

        medida = desviacion_de(
            importe_presupuestado=cantidad_plan * precio_plan,
            importe_ejecutado=cantidad_real * precio_plan,
            umbral=umbral,
        )
        if not medida.relevante:
            continue

        desviaciones.append(
            Desviacion(
                insumo_id=None,
                concepto_id=concepto_id,
                obra_id=obra_id,
                tipo=TipoDesviacion.CONSUMO,
                monto=medida.importe,
                cantidad_plan=cantidad_plan,
                cantidad_real=cantidad_real,
                precio_plan=None,
                precio_real=None,
                detectada_en=detectada_en,
                causa=None,
            )
        )

    return tuple(desviaciones), tuple(pendientes)
