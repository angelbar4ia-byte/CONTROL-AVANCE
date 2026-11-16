"""Colocar en el plano lo que trae la plantilla de un muro (plan de elementos de muro, Ola 4C; M-4, Q5).

Una plantilla de muro (0133) lleva instancias de elementos: castillos —**estimados** (un muro confinado) o **ubicados** (un
muro con cadena)— y cadenas. Al trazar un muro con plantilla el plano coloca esas instancias:

- Un **castillo ubicado** se cuenta con las reglas del mockup: distribución «extremos» = 2 piezas; con una separación,
  ⌈largo ÷ separación⌉ + 1. Se coloca como un vano `castillo` por pieza (instancia del elemento, `vano.elemento_uid`, 0135):
  sube lo alto del muro **menos su arranque** (z) y resta de los m² del muro lo que ya restaba un castillo (ancho × alto × caras).
- Un **castillo estimado** se cuenta igual pero **no se resta** de la mampostería ni se coloca: es solo una cantidad.
- Una **cadena** son los metros del largo del muro.

Las posiciones van **a lo largo del muro** (centro de cada castillo, en metros desde el inicio), repartidas del primero, pegado al
inicio, al último, pegado al final. Todo es aritmética con `Decimal`; no hay precios ni destajos. Funciones puras.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from obractrl.domain.cuantificacion.conceptos_de_elemento import (
    UBICACIONES as UBICACIONES_DE_CONCEPTO,
)
from obractrl.domain.cuantificacion.conceptos_de_elemento import (
    ConceptoDeElemento,
    resolver,
)
from obractrl.domain.cuantificacion.enlaces_de_ranura import (
    UBICACIONES as UBICACIONES_DE_RANURA,
)
from obractrl.domain.cuantificacion.enlaces_de_ranura import (
    Contexto as ContextoDeRanura,
)
from obractrl.domain.cuantificacion.enlaces_de_ranura import (
    EnlaceDeRanura,
    Partida,
    partida_en_capa,
    resolver_ranura,
)
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "ALTO_MINIMO_M",
    "Colocacion",
    "ConceptoColocado",
    "ErrorDeColocacion",
    "Instancia",
    "alto_de_castillo",
    "colocar_plantilla",
    "conceptos_de_instancia",
    "piezas_de_castillo",
    "posiciones_de_castillos",
]

ALTO_MINIMO_M = Decimal("0.10")
_MILI = Decimal("0.001")


class ErrorDeColocacion(ErrorDeCuantificacion):
    """La plantilla no cabe en el muro (más castillos que largo) o el elemento no se puede colocar."""


def _d(valor: Any) -> Decimal:
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def piezas_de_castillo(largo_m: Decimal, sep_m: Decimal | None) -> int:
    """Cuántos castillos lleva un muro: «extremos» (sin separación) son 2; con separación, ⌈largo ÷ separación⌉ + 1."""
    if largo_m <= 0:
        raise ErrorDeColocacion("El largo del muro debe ser mayor que cero.")
    if sep_m is None:
        return 2
    if sep_m <= 0:
        raise ErrorDeColocacion("La separación de los castillos debe ser mayor que cero.")
    return max(2, math.ceil(largo_m / sep_m) + 1)


def alto_de_castillo(altura_m: Decimal, z_m: Decimal = Decimal(0)) -> Decimal:
    """Lo alto de un castillo: la altura del muro menos su altura de arranque (los castillos arrancan por defecto en 0)."""
    alto = altura_m - z_m
    if alto < ALTO_MINIMO_M:
        raise ErrorDeColocacion(f"Un castillo que arranca a {z_m:g} m no cabe en un muro de {altura_m:g} m de alto.")
    return alto


def posiciones_de_castillos(largo_m: Decimal, piezas: int, ancho_m: Decimal) -> list[Decimal]:
    """El centro de cada castillo a lo largo del muro (m desde el inicio): el primero pegado al inicio, el último pegado al final y
    los demás repartidos parejo. Con una sola pieza va a la mitad."""
    if piezas < 1:
        raise ErrorDeColocacion("Un muro lleva al menos un castillo.")
    if ancho_m <= 0:
        raise ErrorDeColocacion("El ancho del castillo debe ser mayor que cero.")
    if piezas == 1:
        return [(largo_m / 2).quantize(_MILI, ROUND_HALF_UP)]
    if piezas * ancho_m > largo_m:
        raise ErrorDeColocacion(
            f"{piezas} castillos de {ancho_m:g} m no caben en un muro de {largo_m:g} m: separa más los castillos o alarga el muro."
        )
    primero, ultimo = ancho_m / 2, largo_m - ancho_m / 2
    paso = (ultimo - primero) / (piezas - 1)
    return [(primero + paso * i).quantize(_MILI, ROUND_HALF_UP) for i in range(piezas)]


@dataclass(frozen=True, slots=True)
class Instancia:
    """Un uso de un elemento de la plantilla ya resuelto en este muro."""

    uid: str
    ref: str
    clase: str  # castillo | cadena
    modo: str | None  # castillo: estimado | ubicado
    piezas: int
    """Castillos: cuántos. Cadena: 1 (su cantidad son los metros)."""
    alto_m: Decimal | None
    """Castillo: lo alto de cada uno (altura del muro − arranque)."""
    ancho_m: Decimal | None
    """Castillo: lo que ocupa a lo largo del muro."""
    metros: Decimal
    """Castillo: piezas × alto (lo que cuenta un concepto por metro). Cadena: el largo del muro."""
    posiciones_m: tuple[Decimal, ...] = ()
    z_m: Decimal = Decimal(0)
    se_coloca: bool = False
    """Es un castillo ubicado: se coloca en el plano como vanos y resta de la mampostería."""
    descuento_m2_por_cara: Decimal = Decimal(0)


@dataclass(frozen=True, slots=True)
class Colocacion:
    largo_m: Decimal
    altura_m: Decimal
    instancias: list[Instancia] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def colocar_plantilla(
    elementos: Iterable[Mapping[str, Any]],
    *,
    largo_m: Decimal,
    altura_m: Decimal,
    anchos_m: Mapping[str, Decimal],
    separacion_m: Decimal | None = None,
) -> Colocacion:
    """Lo que la plantilla coloca en un muro de este largo y esta altura.

    `elementos` son las instancias guardadas en la plantilla (`uid`, `ref`, `clase`, `modo`, `sep_m`, `z_m`); `anchos_m` da, por clave del
    elemento, cuánto ocupa un castillo a lo largo del muro. Los elementos de otra clase (el muro de tabique) no se colocan aquí.

    `separacion_m` es el driver `separacion_castillos` de la obra: la separación de un castillo que la plantilla no fija (su `sep_m`
    vacío). La separación propia del castillo en la plantilla manda sobre el driver. Sin driver (`None`), un castillo sin separación
    sigue siendo «extremos» (2 piezas), como antes.
    """
    if largo_m <= 0:
        raise ErrorDeColocacion("El largo del muro debe ser mayor que cero.")
    if altura_m <= 0:
        raise ErrorDeColocacion("La altura del muro debe ser mayor que cero.")
    salida = Colocacion(largo_m=largo_m, altura_m=altura_m)
    for e in elementos:
        clase = str(e.get("clase") or "")
        uid, ref = str(e.get("uid") or e.get("ref") or ""), str(e.get("ref") or "")
        z = _d(e.get("z_m") or 0)
        if clase == "castillo":
            sep = _d(e["sep_m"]) if e.get("sep_m") not in (None, "") else separacion_m
            ancho = anchos_m.get(ref)
            if ancho is None or ancho <= 0:
                raise ErrorDeColocacion(f"El castillo {ref} no trae el ancho con que se coloca en el muro.")
            n = piezas_de_castillo(largo_m, sep)
            alto = alto_de_castillo(altura_m, z)
            ubicado = e.get("modo") == "ubicado"
            posiciones = tuple(posiciones_de_castillos(largo_m, n, ancho)) if ubicado else ()
            salida.instancias.append(
                Instancia(
                    uid=uid, ref=ref, clase="castillo", modo=str(e.get("modo") or "") or None, piezas=n, alto_m=alto, ancho_m=ancho,
                    metros=alto * n, posiciones_m=posiciones, z_m=z, se_coloca=ubicado,
                    descuento_m2_por_cara=ancho * alto * n if ubicado else Decimal(0),
                )
            )
            if not ubicado:
                salida.avisos.append(
                    f"Los castillos {ref} son estimados ({n} piezas): se cuentan pero no se restan de la mampostería."
                )
        elif clase == "cadena":
            salida.instancias.append(
                Instancia(uid=uid, ref=ref, clase="cadena", modo=None, piezas=1, alto_m=None, ancho_m=None, metros=largo_m, z_m=z)
            )
    return salida



# --- A qué conceptos alimenta lo colocado ----------------------------------------------------------------------------------

UNIDADES_DE_CASTILLO = ("pza", "ml")
"""Un castillo se cuenta en piezas o en metros (D-630)."""


@dataclass(frozen=True, slots=True)
class ConceptoColocado:
    """Un concepto que paga una parte de lo colocado en este contexto y lo que le toca, o por qué no cuenta."""

    ranura: str | None
    """acero, colado o completo: qué parte del elemento paga."""
    concepto_id: UUID | None
    clave: str
    unidad: str
    cantidad: Decimal
    cuenta: bool
    """Solo con el concepto autorizado, su unidad admitida y su partida en el árbol: lo demás avisa y no cuenta."""
    origen: str
    """`contexto`: lo eligió el nivel y el alto (2A). `ranura`: lo enlazó el Paramétrico a esa ranura (4B)."""
    estado: str
    """cuenta, falta_partida, propuesto, unidad_no_admitida."""
    aviso: str | None = None
    partida_id: UUID | None = None


def _cantidad(unidad: str, piezas: int, alto_m: Decimal) -> Decimal | None:
    if unidad == "pza":
        return Decimal(piezas)
    if unidad == "ml":
        return alto_m * piezas
    return None


def conceptos_de_instancia(
    conceptos: Sequence[ConceptoDeElemento],
    *,
    ref: str,
    nivel: int | None,
    ubicacion: str | None,
    alto_m: Decimal,
    piezas: int,
    enlaces: Sequence[EnlaceDeRanura],
    partidas: Sequence[Partida],
    nivel_id: UUID | None,
    etapa_id: UUID | None,
    unidades: Mapping[UUID, str],
) -> tuple[list[ConceptoColocado], list[str]]:
    """Los conceptos que paga un castillo colocado (`piezas` de `alto_m`) en este nivel y esta ubicación.

    1. El concepto lo eligen el nivel, la ubicación y el alto (2A): `resolver` da uno por parte (acero, concreto, cimbra), con el
       escalón de altura que alcanza.
    2. Si el Paramétrico enlazó esa ranura (`elemento:{ref}:{acero|colado|completo}`, 4B) en la capa donde se mide, manda el enlace.
    3. El concepto solo **cuenta** si está en el árbol de la obra en ese nivel y etapa; si falta la partida, **avisa y no cuenta**. Un
       concepto propuesto (sin autorizar) tampoco cuenta.

    `unidades` da la unidad de los conceptos enlazados (un concepto ligado a una ranura puede medirse distinto del que trae el elemento).
    """
    ubic_concepto = ubicacion if ubicacion in UBICACIONES_DE_CONCEPTO else None
    ubic_ranura = ubicacion if ubicacion in UBICACIONES_DE_RANURA else None
    ctx = ContextoDeRanura(nivel_id, etapa_id, ubic_ranura)
    r = resolver(conceptos, nivel=nivel, ubicacion=ubic_concepto, alto_m=alto_m)
    avisos = list(r.avisos)
    salida: list[ConceptoColocado] = []
    for c in r.elegidos:
        ranura = c.ranura
        if c.concepto_id is None:
            salida.append(
                ConceptoColocado(
                    ranura, None, c.clave, c.unidad, Decimal(0), False, "contexto", "propuesto",
                    f"El concepto {c.clave} aún está pendiente de autorizar: no cuenta.",
                )
            )
            continue
        concepto_id, clave, unidad, origen = UUID(str(c.concepto_id)), c.clave, c.unidad, "contexto"
        if ranura is not None:
            res = resolver_ranura(enlaces, partidas, f"elemento:{ref}:{ranura}", ctx)
            if res.estado == "falta_partida":
                assert res.enlace is not None
                salida.append(
                    ConceptoColocado(
                        ranura, res.enlace.concepto_id, res.enlace.concepto_clave, unidades.get(res.enlace.concepto_id, c.unidad),
                        Decimal(0), False, "ranura", "falta_partida", res.aviso,
                    )
                )
                continue
            if res.estado == "enlazado":
                assert res.enlace is not None and res.partida is not None
                concepto_id, clave, origen = res.enlace.concepto_id, res.enlace.concepto_clave, "ranura"
                unidad = unidades.get(concepto_id, c.unidad)
        cantidad = _cantidad(unidad, piezas, alto_m)
        if cantidad is None:
            salida.append(
                ConceptoColocado(
                    ranura, concepto_id, clave, unidad, Decimal(0), False, origen, "unidad_no_admitida",
                    f"El concepto {clave} se mide en {unidad}: un castillo se cuenta en pza o ml, así que no cuenta.",
                )
            )
            continue
        partida = partida_en_capa(partidas, concepto_id, ctx)
        if partida is None:
            salida.append(
                ConceptoColocado(
                    ranura, concepto_id, clave, unidad, cantidad, False, origen, "falta_partida",
                    f"El concepto {clave} no está en el árbol de la obra en este nivel: agrégalo; mientras tanto no cuenta.",
                )
            )
            continue
        salida.append(
            ConceptoColocado(ranura, concepto_id, clave, unidad, cantidad, True, origen, "cuenta", None, partida.id)
        )
    return salida, list(dict.fromkeys(avisos + [x.aviso for x in salida if x.aviso]))
