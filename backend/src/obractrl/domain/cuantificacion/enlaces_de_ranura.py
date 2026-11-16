"""El enlace de ranuras con las partidas del árbol de la obra (plan de elementos de muro, fase F; Ola 4B).

Una **ranura** es un concepto que un elemento o una plantilla de muro necesita:

- `elemento:{clave}:{acero|colado|completo}`: lo que se paga de un elemento (el acero, el colado y la cimbra, o todo junto);
- `mamposteria:{material}`: el muro de ese material (`tabique_rojo`, `block_hueco`, `sillar_amarillo`);
- `acabado:{capa}:{ubicacion}`: un acabado (`gris`, `blanca`, `pintura`) en cara `exterior` o `interior`.

El Paramétrico **no inventa conceptos**: enlaza cada ranura, **en una obra**, con un concepto del Presupuesto. El enlace tiene una
**capa** (nivel, etapa y ubicación, todas opcionales) que dice dónde aplica; si varios enlaces de la misma ranura aplican, gana
el **más específico** (la ubicación pesa más que la etapa y esta más que el nivel, como en el mockup). La **partida** es el nodo
del árbol de la obra que contiene ese concepto en el nivel y la etapa donde se mide; **si falta, la ranura avisa y no cuenta**.

Una ranura sin enlace no cuenta tampoco, pero un elemento sigue con sus conceptos por defecto (`por_defecto`). Funciones puras.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "ROLES_QUE_ENLAZAN",
    "UBICACIONES",
    "Capa",
    "Contexto",
    "EnlaceDeRanura",
    "ErrorDeEnlaceDeRanura",
    "Partida",
    "RanuraConocida",
    "Resolucion",
    "elegir_enlace",
    "partida_en_capa",
    "puntaje_de_la_capa",
    "ranuras_de_plantilla",
    "resolver_ranura",
    "validar_que_enlaza",
    "validar_ranura",
    "validar_ubicacion",
]

ROLES_QUE_ENLAZAN = ("costos", "control_obra")
UBICACIONES: tuple[str, ...] = ("interior", "fachada_a", "fachada_b", "pretil", "barda")
"""Las ubicaciones de un muro (`trazo.muro_ubicacion` del mockup); `personalizada` no es una capa donde enlazar."""
MATERIALES_DE_MURO: tuple[str, ...] = ("tabique_rojo", "block_hueco", "sillar_amarillo")
CAPAS_DE_ACABADO: tuple[str, ...] = ("gris", "blanca", "pintura")
UBICACIONES_DE_ACABADO: tuple[str, ...] = ("exterior", "interior")

_FORMA = re.compile(
    r"^(?:mamposteria:[a-z_0-9]+|acabado:[a-z_0-9]+:[a-z_0-9]+|elemento:[A-Za-z0-9._-]+:(?:acero|colado|completo))$"
)

Estado = Literal["enlazado", "falta_partida", "sin_enlace"]

_PESO_UBICACION, _PESO_ETAPA, _PESO_NIVEL = 10, 2, 1


class ErrorDeEnlaceDeRanura(ErrorDeCuantificacion):
    """Una ranura, una capa o un permiso que no valen."""


@dataclass(frozen=True, slots=True)
class Capa:
    nivel_id: UUID | None = None
    etapa_id: UUID | None = None
    ubicacion: str | None = None


@dataclass(frozen=True, slots=True)
class Contexto:
    """Dónde se mide: el nivel y la etapa del plano o del trazo y la ubicación del muro."""

    nivel_id: UUID | None = None
    etapa_id: UUID | None = None
    ubicacion: str | None = None


@dataclass(frozen=True, slots=True)
class EnlaceDeRanura:
    id: UUID
    ranura: str
    capa: Capa
    concepto_id: UUID
    concepto_clave: str


@dataclass(frozen=True, slots=True)
class Partida:
    """Un nodo de concepto del árbol de la obra, con el nivel y la etapa que le dan sus ancestros."""

    id: UUID
    concepto_id: UUID
    nivel_id: UUID | None
    etapa_id: UUID | None
    nombre: str
    orden: int = 0


@dataclass(frozen=True, slots=True)
class Resolucion:
    estado: Estado
    cuenta: bool
    """`True` solo con el concepto enlazado Y su partida en el árbol: lo demás avisa y no cuenta."""
    enlace: EnlaceDeRanura | None
    partida: Partida | None
    por_defecto: bool
    """Una ranura de elemento sin enlace conserva los conceptos por defecto del elemento."""
    aviso: str | None


@dataclass(frozen=True, slots=True)
class RanuraConocida:
    ranura: str
    nombre: str
    grupo: Literal["mamposteria", "acabado"]
    sugerido_clave: str | None = None
    """Un concepto del catálogo que la especificación propone para la ranura (verificado contra el catálogo); nunca se aplica solo."""


def ranuras_de_plantilla() -> list[RanuraConocida]:
    """Las ranuras de una plantilla de muro: la mampostería por material y los acabados por capa y cara."""
    nombres = {"tabique_rojo": "Tabique rojo", "block_hueco": "Block hueco", "sillar_amarillo": "Sillar amarillo"}
    salida = [
        RanuraConocida(
            f"mamposteria:{m}", f"Mampostería · {nombres[m]}", "mamposteria",
            # Verificado contra CATALOGO_DE_PRESUPUESTO.csv: EST-02010 es el muro de tabique de 14 cm. Los demás materiales
            # no tienen concepto propuesto: los conceptos EJ-* del mockup son de ejemplo y no existen en el catálogo.
            "EST-02010" if m == "tabique_rojo" else None,
        )
        for m in MATERIALES_DE_MURO
    ]
    salida += [
        RanuraConocida(f"acabado:{c}:{u}", f"Acabado {c} · cara {u}", "acabado")
        for c in CAPAS_DE_ACABADO
        for u in UBICACIONES_DE_ACABADO
    ]
    return salida


def validar_que_enlaza(rol: str) -> None:
    if rol not in ROLES_QUE_ENLAZAN:
        raise ErrorDeEnlaceDeRanura("Solo Costos y Control de obra enlazan las ranuras con el Presupuesto.")


def validar_ranura(ranura: str) -> str:
    limpia = (ranura or "").strip()
    if not _FORMA.match(limpia):
        raise ErrorDeEnlaceDeRanura(
            "La ranura debe ser «elemento:{clave}:{acero|colado|completo}», «mamposteria:{material}» o «acabado:{capa}:{cara}»."
        )
    return limpia


def validar_ubicacion(ubicacion: str | None) -> str | None:
    if ubicacion in (None, ""):
        return None
    if ubicacion not in UBICACIONES:
        raise ErrorDeEnlaceDeRanura(f"La ubicación debe ser una de: {', '.join(UBICACIONES)}.")
    return ubicacion


def puntaje_de_la_capa(capa: Capa, ctx: Contexto) -> int | None:
    """Qué tan específica es la capa para donde se mide, o `None` si no aplica. Cada dato que la capa fija debe coincidir:
    ubicación 10, etapa 2, nivel 1; una capa vacía aplica a todo con 0."""
    puntos = 0
    if capa.ubicacion is not None:
        if capa.ubicacion != ctx.ubicacion:
            return None
        puntos += _PESO_UBICACION
    if capa.etapa_id is not None:
        if capa.etapa_id != ctx.etapa_id:
            return None
        puntos += _PESO_ETAPA
    if capa.nivel_id is not None:
        if capa.nivel_id != ctx.nivel_id:
            return None
        puntos += _PESO_NIVEL
    return puntos


def elegir_enlace(enlaces: Sequence[EnlaceDeRanura], ranura: str, ctx: Contexto) -> EnlaceDeRanura | None:
    """El enlace más específico de la ranura para donde se mide. Con el mismo puntaje gana el primero de la lista."""
    mejor: EnlaceDeRanura | None = None
    mejor_puntaje = -1
    for e in enlaces:
        if e.ranura != ranura:
            continue
        p = puntaje_de_la_capa(e.capa, ctx)
        if p is not None and p > mejor_puntaje:
            mejor, mejor_puntaje = e, p
    return mejor


def partida_en_capa(partidas: Sequence[Partida], concepto_id: UUID, ctx: Contexto) -> Partida | None:
    """La partida del árbol que contiene el concepto en el nivel y la etapa donde se mide. Sin nivel (o sin etapa) en el
    contexto, vale cualquiera. Con varias, la de menor orden."""
    candidatas = [
        p
        for p in partidas
        if p.concepto_id == concepto_id
        and (ctx.nivel_id is None or p.nivel_id == ctx.nivel_id)
        and (ctx.etapa_id is None or p.etapa_id == ctx.etapa_id)
    ]
    return min(candidatas, key=lambda p: (p.orden, p.nombre), default=None)


def resolver_ranura(
    enlaces: Sequence[EnlaceDeRanura], partidas: Sequence[Partida], ranura: str, ctx: Contexto
) -> Resolucion:
    """Lo que cuenta una ranura donde se mide: el concepto enlazado y su partida, o el aviso de lo que falta."""
    por_defecto = ranura.startswith("elemento:")
    e = elegir_enlace(enlaces, ranura, ctx)
    if e is None:
        aviso = (
            "La ranura no tiene concepto enlazado: se usan los conceptos por defecto del elemento."
            if por_defecto
            else "La ranura no tiene concepto enlazado: no cuenta."
        )
        return Resolucion("sin_enlace", False, None, None, por_defecto, aviso)
    p = partida_en_capa(partidas, e.concepto_id, ctx)
    if p is None:
        return Resolucion(
            "falta_partida", False, e, None, False,
            f"El concepto {e.concepto_clave} no está en el árbol de la obra en esa capa: agrégalo al árbol; mientras tanto no cuenta.",
        )
    return Resolucion("enlazado", True, e, p, False, None)
