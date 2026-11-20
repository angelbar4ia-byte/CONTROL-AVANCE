"""A qué conceptos alimenta lo que un muro con plantilla coloca en el plano (Ola 4C).

Junta lo que ya existe sin duplicarlo: los **conceptos del elemento por contexto** (2A: el nivel, la ubicación y el alto eligen el
concepto y su escalón) y los **enlaces de ranura** del Paramétrico (4B: la partida del árbol donde se mide). Lo usan el reporte de
lo colocado y la toma de los conceptos (`SincronizarTomas`), así los dos cuentan igual. No escribe nada.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.parametrico import _a_enlace, _a_partida
from obractrl.domain.cuantificacion.colocacion_de_plantilla import (
    ConceptoColocado,
    conceptos_de_instancia,
)
from obractrl.domain.cuantificacion.espacios import repartir, reparto_de_muro

__all__ = ["conceptos_de_lo_colocado", "nivel_para_conceptos", "por_espacio"]


def por_espacio(grupo: dict[str, Any]) -> list[dict[str, Any]]:
    """Un grupo de lo colocado en un muro, repartido por espacio (0143, D-566): sin espacio queda igual; con uno, ese espacio; con un muro
    compartido, una copia por espacio con su parte de las piezas y de los metros. Lo repartido **suma exactamente lo del grupo**: el muro cuenta una
    sola vez entre los dos espacios."""
    partes = reparto_de_muro(grupo.get("espacio_id"), grupo.get("espacio_comparte_id"), grupo.get("espacio_reparto_pct"))
    if not partes:
        return [grupo]
    if len(partes) == 1:
        return [{**grupo, "espacio_id": partes[0][0]}]
    piezas = repartir(Decimal(str(grupo["piezas"])), partes)
    metros = repartir(Decimal(str(grupo["metros"])), partes) if grupo.get("metros") is not None else None
    return [
        {**grupo, "espacio_id": espacio, "piezas": cantidad, **({"metros": metros[n][1]} if metros is not None else {})}
        for n, (espacio, cantidad) in enumerate(piezas)
    ]


def nivel_para_conceptos(numero: Any) -> int | None:
    """El número de nivel con que se eligen los conceptos del elemento (PB = 1): el campo EXPLÍCITO `nivel.numero_de_nivel` (F5, 0141) y, sin él,
    el orden del nivel solo mientras los niveles de la organización sean consecutivos (lo resuelve `app.numero_de_nivel`). Con saltos de nivel y sin
    número explícito llega `None`: no se descarta ningún concepto (no se adivina). Un número que no es de nivel (0 o menos) tampoco descarta."""
    return int(numero) if numero is not None and int(numero) >= 1 else None


async def conceptos_de_lo_colocado(
    *, elementos: Any, parametrico: Any, obra_id: UUID, instancias: Iterable[dict[str, Any]]
) -> list[tuple[dict[str, Any], list[ConceptoColocado], list[str]]]:
    """Para cada castillo colocado (dict con `elemento_id`, `ref`, `alto_m`, `piezas`, `numero_de_nivel`, `nivel_id`, `etapa_id`, `ubicacion`)
    o cadena de una plantilla (dict con `metros` y sin alto) los conceptos que paga y los avisos. Con `espacio_id` (y, si el muro es compartido,
    `espacio_comparte_id` y `espacio_reparto_pct`) lo repartido por espacio sale como una entrada por espacio. `instancias` ya viene agrupada: `piezas`
    es cuántos castillos iguales son (con fracción en la regla «por ml» o «total» de un castillo estimado)."""
    # Import aquí: `conceptos_de_elemento` llega a `tomas_de_elemento` (que usa este módulo) y un import arriba cerraría el círculo.
    from obractrl.application.casos_uso.conceptos_de_elemento import _concepto

    filas_enlaces = await parametrico.enlaces(obra_id)
    enlaces = [_a_enlace(f) for f in filas_enlaces]
    partidas = [_a_partida(f) for f in await parametrico.partidas(obra_id)]
    unidades = {UUID(str(f["concepto_id"])): str(f["unidad"]) for f in filas_enlaces if f.get("unidad")}
    cache: dict[Any, list[Any]] = {}
    salida: list[tuple[dict[str, Any], list[ConceptoColocado], list[str]]] = []
    for i in (parte for grupo in instancias for parte in por_espacio(grupo)):
        eid = i["elemento_id"]
        if eid not in cache:
            cache[eid] = [_concepto(f) for f in await elementos.conceptos_por_contexto(eid)]
        conceptos, avisos = conceptos_de_instancia(
            cache[eid],
            ref=str(i["ref"]),
            nivel=nivel_para_conceptos(i.get("numero_de_nivel")),
            ubicacion=i.get("ubicacion"),
            alto_m=Decimal(str(i["alto_m"])) if i.get("alto_m") is not None else None,
            piezas=Decimal(str(i["piezas"])),
            metros=Decimal(str(i["metros"])) if i.get("metros") is not None else None,
            enlaces=enlaces,
            partidas=partidas,
            nivel_id=i.get("nivel_id"),
            etapa_id=i.get("etapa_id"),
            unidades=unidades,
            espacio_id=UUID(str(i["espacio_id"])) if i.get("espacio_id") else None,
        )
        salida.append((i, conceptos, avisos))
    return salida
