"""Los conceptos que paga un elemento paramétrico, por contexto y por escalón de altura (plan de elementos de muro, fase C).

Un elemento (castillo K-1, muro de tabique…) no se paga con un solo concepto. Cada **parte** de su receta —acero, concreto,
cimbra— la toma un concepto, y cuál depende del **contexto** en que se coloca y, en el acero de un castillo, de su **alto**:

- **Contexto**: nivel mínimo y máximo del edificio (1 = planta baja) y ubicación del muro (pretil, barda). El mismo elemento
  paga EST-02010 en los niveles 1 y 2 y EST-02011 desde el nivel 3 (M-106). Sin límites, el concepto sirve en todo contexto.
- **Escalón**: `alto_hasta_m`. El acero de K-1 se paga por pieza con EST-10013 hasta 1.00 m, EST-10012 hasta 1.50 m, EST-10010
  hasta 4.00 m y EST-10011 hasta 6.00 m. Se elige el primer escalón cuyo «hasta» alcanza el alto; si el alto lo rebasa se usa
  el último y se **avisa**. La clave y el «hasta» de un escalón son fijos; solo su descripción se edita.
- **Ranura**: acero, colado (concreto y cimbra) o completo, según lo que toma.
- **Estado**: `autorizado` si enlaza un concepto del catálogo; `propuesto` si es un concepto NUEVO que aún no autoriza Control
  de obra (lleva clave y descripción propuestas, nunca precio).

La regla central: **cada parte la toma un solo concepto por contexto**. Dos conceptos que toman la misma parte en contextos que
se traslapan se rechazan al guardar, salvo que los dos sean escalones de una misma escalera (alto distinto). Y un alto sin
escalón avisa.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from obractrl.domain.cuantificacion.elementos_parametricos import (
    MATERIALES_DE_UN_ELEMENTO,
    ErrorDeElementoParametrico,
)

__all__ = [
    "ESTADOS",
    "GRUPOS_DE_PARTES",
    "RANURAS",
    "UBICACIONES",
    "ConceptoDeElemento",
    "Contexto",
    "ResolucionDeContexto",
    "avisos_de_altura",
    "describir_contexto",
    "normalizar_clave_propuesta",
    "normalizar_descripcion",
    "normalizar_toma",
    "ranura_de",
    "resolver",
    "validar_alta",
    "validar_contexto",
]

ESTADOS = ("propuesto", "autorizado")
RANURAS = ("acero", "colado", "completo")
UBICACIONES = ("pretil", "barda")
"""Las ubicaciones del muro que cambian el concepto (las del mockup). Sin ubicación, el concepto sirve en cualquiera."""

_PARTES_DEL_ACERO = ("acero", "estribos", "alambre")
_PARTES_DEL_COLADO = ("concreto", "cimbra")
GRUPOS_DE_PARTES: dict[str, frozenset[str]] = {
    "acero": frozenset(_PARTES_DEL_ACERO),
    "concreto": frozenset({"concreto"}),
    "cimbra": frozenset({"cimbra"}),
}
"""Los tres grupos del mockup: el acero de refuerzo (varillas, anillos, alambre de amarre), el concreto y la cimbra."""
_CLAVE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{1,19}$")
_TOLERANCIA_M = Decimal("0.0005")


@dataclass(frozen=True, slots=True)
class Contexto:
    """Dónde aplica un concepto del elemento. Un límite nulo significa «sin límite»."""

    nivel_min: int | None = None
    nivel_max: int | None = None
    ubicacion: str | None = None

    def abarca(self, nivel: int | None, ubicacion: str | None) -> bool:
        """Si el concepto sirve para un muro de ese nivel y esa ubicación (un dato que falta no descarta)."""
        if nivel is not None:
            if self.nivel_min is not None and nivel < self.nivel_min:
                return False
            if self.nivel_max is not None and nivel > self.nivel_max:
                return False
        return not (ubicacion is not None and self.ubicacion is not None and self.ubicacion != ubicacion)

    def se_traslapa_con(self, otro: Contexto) -> bool:
        """Si existe algún nivel y ubicación donde los dos conceptos aplican a la vez."""
        minimo = max(self.nivel_min or 1, otro.nivel_min or 1)
        maximo = min(self.nivel_max if self.nivel_max is not None else 10**6, otro.nivel_max if otro.nivel_max is not None else 10**6)
        if minimo > maximo:
            return False
        return self.ubicacion is None or otro.ubicacion is None or self.ubicacion == otro.ubicacion


@dataclass(frozen=True, slots=True)
class ConceptoDeElemento:
    """Una fila de `elemento_concepto`: un concepto, la parte que toma, en qué contexto y con qué escalón."""

    id: Any
    clave: str
    descripcion: str
    unidad: str
    toma: dict[str, bool]
    contexto: Contexto
    alto_hasta_m: Decimal | None
    estado: str
    concepto_id: Any | None = None

    @property
    def partes(self) -> frozenset[str]:
        return frozenset(m for m, v in self.toma.items() if v and m in MATERIALES_DE_UN_ELEMENTO)

    @property
    def ranura(self) -> str | None:
        return ranura_de(self.toma)

    @property
    def es_escalon(self) -> bool:
        return self.alto_hasta_m is not None

    @property
    def es_nuevo(self) -> bool:
        return self.concepto_id is None


def ranura_de(toma: dict[str, bool]) -> str | None:
    """acero, colado o completo según lo que toma; `None` si no toma nada. La base calcula lo mismo (columna `ranura`, 0128)."""
    acero = any(toma.get(m) for m in _PARTES_DEL_ACERO)
    colado = any(toma.get(m) for m in _PARTES_DEL_COLADO)
    if acero and colado:
        return "completo"
    return "acero" if acero else "colado" if colado else None


def normalizar_toma(toma: dict[str, bool]) -> dict[str, bool]:
    limpia = {m: True for m in MATERIALES_DE_UN_ELEMENTO if toma.get(m)}
    if not limpia:
        raise ErrorDeElementoParametrico("El concepto debe tomar al menos un material del elemento.")
    return limpia


def validar_contexto(nivel_min: int | None, nivel_max: int | None, ubicacion: str | None) -> Contexto:
    for nombre, valor in (("nivel mínimo", nivel_min), ("nivel máximo", nivel_max)):
        if valor is not None and valor < 1:
            raise ErrorDeElementoParametrico(f"El {nombre} es 1 (planta baja) o más.")
    if nivel_min is not None and nivel_max is not None and nivel_min > nivel_max:
        raise ErrorDeElementoParametrico("El nivel mínimo no puede pasar del máximo.")
    if ubicacion is not None and ubicacion not in UBICACIONES:
        raise ErrorDeElementoParametrico(f"La ubicación es una de {', '.join(UBICACIONES)}.")
    return Contexto(nivel_min, nivel_max, ubicacion)


def describir_contexto(c: Contexto) -> str:
    """El contexto en palabras: «niveles 1 y 2», «nivel 3 en adelante», «barda»… `Todo contexto` si no limita nada."""
    if c.nivel_min is None and c.nivel_max is None:
        niveles = ""
    elif c.nivel_max is None:
        niveles = f"nivel {c.nivel_min} en adelante"
    elif c.nivel_min is None:
        niveles = f"hasta el nivel {c.nivel_max}"
    elif c.nivel_min == c.nivel_max:
        niveles = f"nivel {c.nivel_min}"
    else:
        niveles = f"niveles {c.nivel_min} a {c.nivel_max}"
    partes = [p for p in (niveles, c.ubicacion) if p]
    return ", ".join(partes) if partes else "Todo contexto"


def normalizar_clave_propuesta(clave: str) -> str:
    limpia = clave.strip().upper()
    if not _CLAVE.match(limpia):
        raise ErrorDeElementoParametrico("La clave del concepto nuevo lleva letras, números, punto, guion o guion bajo (2 a 20 caracteres).")
    return limpia


def normalizar_descripcion(descripcion: str, *, maximo: int = 600) -> str:
    limpia = " ".join(descripcion.split())
    if not limpia:
        raise ErrorDeElementoParametrico("El concepto necesita una descripción.")
    if len(limpia) > maximo:
        raise ErrorDeElementoParametrico(f"La descripción no puede pasar de {maximo} caracteres.")
    return limpia


def _mismo_alto(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= _TOLERANCIA_M


def validar_alta(existentes: Sequence[ConceptoDeElemento], nuevo: ConceptoDeElemento) -> None:
    """La regla «cada parte la toma un solo concepto por contexto».

    Rechaza el concepto si una de sus partes ya la toma otro en un contexto que se traslapa, salvo que ambos sean escalones
    (con alto distinto): así se arma la escalera de acero de un castillo. Un escalón nuevo con el mismo alto que otro, o un
    escalón junto a un concepto sin escalón que toma la misma parte, se rechazan. El mismo concepto no se repite en un mismo
    contexto y escalón.
    """
    for otro in existentes:
        mismo_escalon = nuevo.es_escalon == otro.es_escalon and (
            not nuevo.es_escalon or _mismo_alto(nuevo.alto_hasta_m or Decimal(0), otro.alto_hasta_m or Decimal(0))
        )
        if nuevo.clave == otro.clave and nuevo.contexto == otro.contexto and mismo_escalon:
            raise ErrorDeElementoParametrico(f"{nuevo.clave} ya está en este contexto y escalón.")
        compartidas = nuevo.partes & otro.partes
        if not compartidas or not nuevo.contexto.se_traslapa_con(otro.contexto):
            continue
        parte = ", ".join(sorted(compartidas))
        donde = describir_contexto(otro.contexto).lower()
        if nuevo.es_escalon and otro.es_escalon:
            if _mismo_alto(nuevo.alto_hasta_m or Decimal(0), otro.alto_hasta_m or Decimal(0)):
                raise ErrorDeElementoParametrico(
                    f"Ya hay un escalón hasta {otro.alto_hasta_m:g} m que toma {parte} ({otro.clave}; {donde}): cada parte la toma un solo concepto por contexto."
                )
            if nuevo.unidad != otro.unidad:
                raise ErrorDeElementoParametrico(f"Los escalones de {parte} se cuentan en la misma unidad ({otro.unidad}, como {otro.clave}).")
            continue
        raise ErrorDeElementoParametrico(
            f"{otro.clave} ya toma {parte} ({donde}): cada parte la toma un solo concepto por contexto."
        )


@dataclass(frozen=True, slots=True)
class ResolucionDeContexto:
    """Qué concepto paga cada parte para un nivel, una ubicación y un alto dados, y lo que conviene avisar."""

    por_parte: dict[str, ConceptoDeElemento]
    elegidos: list[ConceptoDeElemento]
    avisos: list[str]


def _escalon_para(escalera: list[ConceptoDeElemento], alto_m: Decimal) -> tuple[ConceptoDeElemento, bool]:
    ordenada = sorted(escalera, key=lambda c: c.alto_hasta_m or Decimal(0))
    for c in ordenada:
        if alto_m <= (c.alto_hasta_m or Decimal(0)) + _TOLERANCIA_M:
            return c, False
    return ordenada[-1], True


def resolver(
    conceptos: Iterable[ConceptoDeElemento],
    *,
    nivel: int | None = None,
    ubicacion: str | None = None,
    alto_m: Decimal | None = None,
    grupos: Iterable[str] = ("acero", "concreto", "cimbra"),
) -> ResolucionDeContexto:
    """Los conceptos que pagan el elemento en este contexto.

    Para cada grupo de partes (acero, concreto, cimbra): los conceptos que la toman y aplican al nivel y la ubicación; si son escalones, el primero cuyo «hasta»
    alcanza el alto (o el último, con aviso, si lo rebasa; sin alto, avisa que no se puede elegir); si son varios sin escalón,
    avisa que la parte se tomaría dos veces; si no hay ninguno, avisa que se perdería del presupuesto.
    """
    aplicables = [c for c in conceptos if c.contexto.abarca(nivel, ubicacion)]
    por_parte: dict[str, ConceptoDeElemento] = {}
    avisos: list[str] = []
    for parte in grupos:
        toman = [c for c in aplicables if c.partes & GRUPOS_DE_PARTES[parte]]
        if not toman:
            avisos.append(f"Sin concepto: {parte} no lo toma ningún concepto en este contexto y se perdería del presupuesto.")
            continue
        escalones = [c for c in toman if c.es_escalon]
        fijos = [c for c in toman if not c.es_escalon]
        if escalones and fijos:
            avisos.append(f"{parte} lo toman {fijos[0].clave} y una escalera de escalones: cada parte la toma un solo concepto por contexto.")
        if len(fijos) > 1:
            avisos.append(f"{parte} lo toman {' y '.join(c.clave for c in fijos)}: se contaría dos veces.")
        if escalones:
            if alto_m is None:
                avisos.append(f"El acero se paga por escalones de altura y no se dio el alto: no se puede elegir el concepto de {parte}.")
                por_parte[parte] = sorted(escalones, key=lambda c: c.alto_hasta_m or Decimal(0))[0]
            else:
                elegido, rebasa = _escalon_para(escalones, alto_m)
                por_parte[parte] = elegido
                if rebasa:
                    avisos.append(
                        f"Un alto de {alto_m:g} m no tiene escalón: el último llega a {elegido.alto_hasta_m:g} m ({elegido.clave}). Falta un concepto nuevo para ese alto."
                    )
        else:
            por_parte[parte] = fijos[0]
    elegidos: list[ConceptoDeElemento] = []
    for c in por_parte.values():
        if c not in elegidos:
            elegidos.append(c)
    return ResolucionDeContexto(por_parte=por_parte, elegidos=elegidos, avisos=list(dict.fromkeys(avisos)))


def avisos_de_altura(conceptos: Sequence[ConceptoDeElemento], alto_m: Decimal) -> list[str]:
    """Los avisos de «alto sin escalón» para todos los contextos que el elemento tiene escalonados (sin elegir un contexto)."""
    avisos: list[str] = []
    contextos = {c.contexto for c in conceptos if c.es_escalon}
    for ctx in sorted(contextos, key=lambda x: (x.nivel_min or 0, x.ubicacion or "")):
        escalonados = [c for c in conceptos if c.es_escalon and c.contexto == ctx]
        if not escalonados:
            continue
        ultimo = max(escalonados, key=lambda c: c.alto_hasta_m or Decimal(0))
        if alto_m > (ultimo.alto_hasta_m or Decimal(0)) + _TOLERANCIA_M:
            avisos.append(
                f"Un alto de {alto_m:g} m no tiene escalón ({describir_contexto(ctx).lower()}): el último llega a {ultimo.alto_hasta_m:g} m ({ultimo.clave}). Falta un concepto nuevo para ese alto."
            )
    return list(dict.fromkeys(avisos))
