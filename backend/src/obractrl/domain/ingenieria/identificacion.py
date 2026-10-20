"""Identificación del prototipo de un lote, por contenido y por cantidad
(CONOCIMIENTO.md §11.5, §11.7, §11.11; P-30).

**El contenido dice de qué modelo salió, la etiqueta solo rotula** (§11.5):
un lote llamado "Zafiro Plus" puede ser, en realidad, Diamante con
chimenea. Este módulo compara la ingeniería consolidada del lote contra la
explosión profunda (`domain.catalogos.apu.explotar`, con el volumen real de
cada renglón del presupuesto — igual método que
`backend/core/tests/test_comparacion_alamo18.py` del cerebro, §11.11) de
cada uno de los prototipos candidatos del catálogo, y calcula la razón
``total de la ingeniería ÷ total explotado del prototipo`` — global, que es
la que decide, y por etapa, que es diagnóstico (§11.5: "la dispersión entre
etapas es información, no ruido" — una etapa en 1.00 confirma el
prototipo, una que se sale señala dónde el lote se apartó del modelo, pero
eso no decide la identidad por sí solo).

**Decisión ya tomada, no se reabre (§11.7):** si NINGÚN candidato cae
dentro del umbral (20% por defecto, parámetro de la función —nunca un
número fijo en el código—), no se bloquea nada: se devuelve el candidato
más cercano como SUGERENCIA, con la señal de "identidad dudosa" (P-30) para
que la capa de aplicación la marque como alerta — este módulo nunca
autoasigna en firme.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from obractrl.domain.cargadores.presupuesto import ArbolPrototipoCargado
from obractrl.domain.catalogos.apu import Componente, explotar
from obractrl.domain.ingenieria.arbol_prototipo import renglones_por_etapa

__all__ = [
    "UMBRAL_IDENTIDAD_DEFAULT",
    "CandidatoIdentificacion",
    "ExplosionPrototipo",
    "IdentificacionPrototipo",
    "explotar_prototipo_por_etapa",
    "identificar_prototipo",
]

UMBRAL_IDENTIDAD_DEFAULT = Decimal("20")
"""Porcentaje de desviación tolerado antes de que la identidad quede en
duda (§11.7: "20% por defecto, parámetro, no número fijo en el código").
Quien llame puede pasar el umbral configurado por la organización, igual
que `rendimiento.UMBRAL_DESVIACION`."""


@dataclass(frozen=True, slots=True)
class ExplosionPrototipo:
    """Un prototipo del catálogo, explotado a fondo con el volumen real de
    cada renglón de su presupuesto (§11.11), con el importe partido por la
    etapa (`ECO-...`) que lo contiene."""

    clave_prototipo: str
    total_global: Decimal
    total_por_etapa: dict[str, Decimal] = field(default_factory=dict)


def explotar_prototipo_por_etapa(
    arbol: ArbolPrototipoCargado,
    composiciones: Mapping[str, Sequence[Componente]],
) -> ExplosionPrototipo:
    """Explota todos los `CONCEPTO`/`CONCEPTO AUXILIAR` del árbol de un
    prototipo, cada uno a su propia cantidad de presupuesto, y acumula el
    importe global y por etapa.

    Un concepto fuera de ``composiciones`` no es un error: es una hoja sin
    desglose y cuesta cero (mismo criterio que `apu.explotar`, que a su vez
    sigue el de `core/importacion_opus.py::armar_arbol` del cerebro) — un
    renglón del presupuesto sin matriz en el archivo no debe tumbar la
    comparación.
    """
    total_por_etapa: dict[str, Decimal] = {}
    total_global = Decimal(0)
    for renglon in renglones_por_etapa(arbol):
        importe = explotar(renglon.clave, composiciones=composiciones).precio.total.monto
        importe *= renglon.cantidad
        total_global += importe
        if renglon.etapa is not None:
            total_por_etapa[renglon.etapa] = total_por_etapa.get(renglon.etapa, Decimal(0)) + importe

    return ExplosionPrototipo(
        clave_prototipo=arbol.clave_prototipo,
        total_global=total_global,
        total_por_etapa=total_por_etapa,
    )


@dataclass(frozen=True, slots=True)
class CandidatoIdentificacion:
    """Un prototipo candidato, con la razón que le tocó contra este lote."""

    clave_prototipo: str
    razon_global: Decimal | None
    """``None`` cuando el prototipo no explota a nada (total 0): dividir
    entre cero no da infinito, dice que la pregunta no aplica — mismo
    criterio que `rendimiento.desviacion_de`."""

    razon_por_etapa: dict[str, Decimal]
    dentro_del_umbral: bool


@dataclass(frozen=True, slots=True)
class IdentificacionPrototipo:
    """Resultado de comparar el lote contra todos los candidatos."""

    identificado: str | None
    """La clave del prototipo, SOLO si cayó dentro del umbral. Nunca se
    rellena con el más cercano cuando nadie calificó — para eso está
    ``sugerido``."""

    sugerido: str
    """El candidato más cercano, exista o no un ``identificado`` — es lo
    que se propone cuando la identidad queda en duda (P-30)."""

    candidatos: tuple[CandidatoIdentificacion, ...]
    identidad_dudosa: bool
    """``True`` cuando ningún candidato cayó dentro del umbral (P-30): la
    capa de aplicación la marca como alerta, nunca autoasigna ``sugerido``
    en firme."""


def identificar_prototipo(
    total_ingenieria_por_etapa: Mapping[str, Decimal],
    candidatos: Sequence[ExplosionPrototipo],
    *,
    umbral: Decimal = UMBRAL_IDENTIDAD_DEFAULT,
) -> IdentificacionPrototipo:
    """Compara el lote consolidado (`domain.ingenieria.consolidacion.
    consolidar_lote`) contra cada prototipo ya explotado y decide.

    **Decisión de diseño, no dada por el cerebro de forma literal.** La
    fórmula de §11.7 ("razón = total de la ingeniería cargada ÷ total del
    prototipo que dice la etiqueta") asume que la ingeniería YA cubre el
    prototipo completo (§11.11, las once/doce ingenierías juntas). Pero
    §11.5 identifica el prototipo con una sola de esas ingenierías —la
    cimentación, 5 de ~41 etapas— y ahí comparar contra el total COMPLETO
    del candidato sería absurdo incluso con el candidato correcto: la
    cimentación nunca puede sumar el 100% de una casa. Verificado contra
    los datos reales: con el total completo del candidato en el
    denominador, ``razón_global`` de `CAS-00007` contra solo la
    cimentación de `ALAMO 18` sale en 0.10, no cerca de 1 — rechazaría al
    prototipo correcto.

    La razón global aquí es, por eso, la del **mismo alcance que trae la
    ingeniería**: la suma de `total_ingenieria_por_etapa` (todas las etapas
    que el lote sí trae) contra la suma del total explotado del candidato
    **restringida a esas mismas etapas** — nunca contra TODO el prototipo.
    Con la ingeniería completa de un lote (§11.8, 36 de 41 etapas) esto
    converge al método de §11.11 salvo el 8% de niveles sin ingeniería
    (ausencia de dato, no de identidad); con una sola ingeniería parcial
    (§11.5) sigue siendo comparable, porque los dos lados mi­den el MISMO
    conjunto de etapas. Las etapas que el lote trae sin ``ECO-`` conocido
    (archivos `SUELTA`, §11.8: "el nombre del archivo dice a qué
    corresponde, no el contenido") no entran en ningún lado de la razón —
    esta función nunca ve el nombre del archivo, así que no puede
    ubicarlas; quien consolida el lote con esa información puede, aparte,
    sumarlas al numerador si decide a qué prototipo asignarlas.
    """
    if not candidatos:
        raise ValueError("identificar_prototipo necesita al menos un prototipo candidato.")
    if not total_ingenieria_por_etapa:
        raise ValueError(
            "identificar_prototipo necesita al menos una etapa con ingeniería conocida "
            "(ECO-...); sin eso no hay nada que comparar contra los candidatos."
        )

    total_ingenieria_alcance = sum(total_ingenieria_por_etapa.values(), Decimal(0))

    resultados: list[CandidatoIdentificacion] = []
    for candidato in candidatos:
        total_candidato_alcance = sum(
            (candidato.total_por_etapa.get(etapa, Decimal(0)) for etapa in total_ingenieria_por_etapa),
            Decimal(0),
        )
        razon_global = (
            total_ingenieria_alcance / total_candidato_alcance
            if total_candidato_alcance
            else None
        )
        razon_por_etapa = {
            etapa: total_ingenieria_por_etapa[etapa] / candidato.total_por_etapa[etapa]
            for etapa in total_ingenieria_por_etapa
            if candidato.total_por_etapa.get(etapa)
        }
        dentro = razon_global is not None and abs(razon_global - 1) * 100 <= umbral
        resultados.append(
            CandidatoIdentificacion(
                clave_prototipo=candidato.clave_prototipo,
                razon_global=razon_global,
                razon_por_etapa=razon_por_etapa,
                dentro_del_umbral=dentro,
            )
        )

    def distancia(r: CandidatoIdentificacion) -> Decimal:
        return abs(r.razon_global - 1) if r.razon_global is not None else Decimal("Infinity")

    mas_cercano = min(resultados, key=distancia)
    return IdentificacionPrototipo(
        identificado=mas_cercano.clave_prototipo if mas_cercano.dentro_del_umbral else None,
        sugerido=mas_cercano.clave_prototipo,
        candidatos=tuple(resultados),
        identidad_dudosa=not mas_cercano.dentro_del_umbral,
    )
