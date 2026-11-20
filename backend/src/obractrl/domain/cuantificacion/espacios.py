"""La capa «espacio» (D-565, D-566, D-640; migración 0143): el cuarto o área donde se asignan zonas de losa, muros y elementos.

Un **espacio** (recámara 1, baño, cochera…) es el nivel de agrupación entre el nivel/etapa y la partida del árbol del presupuesto. Su único dato
capturado son los m² (opcionales). No es una zona de losa (una zona puede cubrir varios cuartos) ni una medición (la capa sombra de 0088).

Qué resuelve este módulo (funciones puras, sin base de datos):

- **Quién edita**: solo Control de obra edita la estructura de los espacios (la misma regla de las zonas de losa).
- **Muro compartido** (D-566): un muro que separa dos espacios se traza **una vez** y su cantidad se **reparte**: se asigna a un espacio (100 %) o se
  reparte entre dos (por omisión mitad y mitad). `reparto_de_muro` siempre devuelve fracciones que suman **exactamente 1** y `repartir` reparte una
  cantidad sin perder ni agregar un solo decimal: **no hay doble conteo**. Si uno de los dos espacios se borra, el que queda recibe todo.
- **Repartir una cantidad** por partes con el residuo en la última, para que la suma de las partidas sea igual a la medida.

Lo que NO resuelve (valor conservador, queda como pregunta): el **excedente de altura** de un muro compartido (la banda por encima de lo que cubre un
espacio, D-566) todavía no se manda a un «área» propia; el muro se reparte entero.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, TypeVar
from uuid import UUID

from obractrl.domain.cuantificacion.enlaces_de_ranura import (
    Contexto,
    Partida,
    partida_en_capa,
)
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "ROLES_QUE_EDITAN",
    "TIPOS_DE_ESPACIO",
    "ErrorDeEspacio",
    "repartir",
    "reparto_de_muro",
    "resolver_matriz_por_espacio",
    "validar_asignacion_de_muro",
    "validar_espacio",
    "validar_que_edita",
]

ROLES_QUE_EDITAN: tuple[str, ...] = ("control_obra",)

TIPOS_DE_ESPACIO: tuple[str, ...] = (
    "recamara", "bano", "cocina", "sala", "comedor", "estancia", "cochera", "pasillo", "escalera", "patio", "azotea", "bodega", "otro",
)
"""Los tipos de espacio que se ofrecen (los mismos del check de la base). Solo clasifican: no cambian ningún cálculo."""

_MICRO = Decimal("0.000001")
_UNO = Decimal(1)
_CIEN = Decimal(100)
_MITAD = Decimal(50)
_AREA_MAXIMA = Decimal(100000)
K = TypeVar("K", bound=Hashable)


class ErrorDeEspacio(ErrorDeCuantificacion):
    """Un espacio, una asignación o un permiso que no valen."""


def validar_que_edita(rol: str) -> None:
    if rol not in ROLES_QUE_EDITAN:
        raise ErrorDeEspacio("Solo Control de obra edita los espacios.")


def validar_espacio(*, nombre: str, tipo: str | None, area_m2: Any) -> dict[str, Any]:
    """El espacio normalizado: nombre sin espacios sobrantes (1 a 60), tipo conocido (por omisión «otro») y m² positivos si vienen."""
    limpio = " ".join((nombre or "").split())
    if not 1 <= len(limpio) <= 60:
        raise ErrorDeEspacio("El nombre del espacio va de 1 a 60 caracteres.")
    t = tipo or "otro"
    if t not in TIPOS_DE_ESPACIO:
        raise ErrorDeEspacio(f"El tipo de espacio debe ser uno de: {', '.join(TIPOS_DE_ESPACIO)}.")
    area: Decimal | None = None
    if area_m2 is not None:
        area = Decimal(str(area_m2))
        if not Decimal(0) < area <= _AREA_MAXIMA:
            raise ErrorDeEspacio("Los m² del espacio van de más de 0 a 100000.")
        area = area.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"nombre": limpio, "tipo": t, "area_m2": area}


def validar_asignacion_de_muro(
    *, espacio_id: UUID | None, comparte_id: UUID | None, reparto_pct: Any
) -> tuple[UUID | None, UUID | None, Decimal | None]:
    """La asignación de un muro: sin espacio, a uno, o compartido entre dos con su reparto (1 a 99 % para el principal; sin él, mitad y mitad).

    Se rechaza compartir sin un espacio principal, compartir un espacio consigo mismo y un reparto sin segundo espacio o fuera de rango. El reparto
    de un muro de un solo espacio no existe: el espacio se lleva todo."""
    if comparte_id is not None and espacio_id is None:
        raise ErrorDeEspacio("Un muro compartido lleva un espacio principal: asigna primero el espacio.")
    if comparte_id is not None and comparte_id == espacio_id:
        raise ErrorDeEspacio("Un muro no se comparte con el mismo espacio.")
    pct: Decimal | None = None
    if reparto_pct is not None:
        if comparte_id is None:
            raise ErrorDeEspacio("El reparto solo aplica a un muro compartido entre dos espacios.")
        pct = Decimal(str(reparto_pct))
        if not Decimal(0) < pct < _CIEN:
            raise ErrorDeEspacio("El reparto del espacio principal va de más de 0 a menos de 100 %.")
        pct = pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return espacio_id, comparte_id, pct


def reparto_de_muro(
    espacio_id: UUID | None, comparte_id: UUID | None, reparto_pct: Decimal | float | None
) -> list[tuple[UUID, Decimal]]:
    """Las fracciones de un muro por espacio, que suman **exactamente 1** (sin doble conteo).

    - Sin espacio: lista vacía (el muro cuenta como siempre, sin espacio).
    - Un solo espacio (o el otro se borró): ese espacio, 1.
    - Compartido: el principal recibe `reparto_pct` % (por omisión 50) y el otro, el resto.
    """
    if espacio_id is None and comparte_id is None:
        return []
    if comparte_id is None or espacio_id is None or comparte_id == espacio_id:
        unico = espacio_id if espacio_id is not None else comparte_id
        assert unico is not None
        return [(unico, _UNO)]
    pct = Decimal(str(reparto_pct)) if reparto_pct is not None else _MITAD
    principal = (pct / _CIEN).quantize(_MICRO, rounding=ROUND_HALF_UP)
    return [(espacio_id, principal), (comparte_id, _UNO - principal)]


def repartir(cantidad: Decimal | float | int, partes: Sequence[tuple[K, Decimal]]) -> list[tuple[K, Decimal]]:
    """Reparte una cantidad según las fracciones de `partes`, a seis decimales y con el residuo en la última, de modo que la suma de lo repartido es
    **igual** a la cantidad. Las fracciones deben sumar 1."""
    if not partes:
        return []
    total = sum((f for _, f in partes), Decimal(0))
    if total != _UNO:
        raise ErrorDeEspacio("Las fracciones del reparto deben sumar 1.")
    cantidad = Decimal(str(cantidad)).quantize(_MICRO, rounding=ROUND_HALF_UP)
    salida: list[tuple[K, Decimal]] = []
    asignado = Decimal(0)
    for clave, fraccion in partes[:-1]:
        parte = (cantidad * fraccion).quantize(_MICRO, rounding=ROUND_HALF_UP)
        salida.append((clave, parte))
        asignado += parte
    salida.append((partes[-1][0], cantidad - asignado))
    return salida


def resolver_matriz_por_espacio(
    grupos: Sequence[Mapping[str, Any]],
    *,
    partidas: Sequence[Partida],
    concepto_id_de: Mapping[str, UUID],
    nombres: Mapping[UUID, str] | None = None,
) -> list[dict[str, Any]]:
    """En qué partida del árbol se mide cada concepto de la matriz de una zona de losa, por espacio.

    `grupos` es `por_espacio` de la matriz (cada grupo: `espacio_id` o `None`, y sus `conceptos` con la clave y la cantidad). Cada concepto recibe una
    `resolucion` con el `estado` y, si cuenta, la partida:

    - ``cuenta``: el concepto existe en el catálogo y tiene partida en el árbol en ese espacio (o una general): la cantidad se escribe en ella.
    - ``sin_espacio``: lo que no está asignado a un espacio no se escribe (la losa solo alimenta el presupuesto por espacio; lo ya guardado no cambia).
    - ``propuesto`` / ``sin_concepto``: el concepto aún no está en el catálogo (un concepto nuevo propuesto no cuenta hasta autorizarse).
    - ``falta_partida``: el concepto existe pero el árbol no lo trae en ese espacio: avisa y no cuenta.
    - ``sin_cantidad``: la cantidad es cero.

    Cada polígono y cada elemento está en un solo grupo, así que lo que se escribe en las partidas suma lo de la matriz: no hay doble conteo.
    """
    salida: list[dict[str, Any]] = []
    for g in grupos:
        espacio = g.get("espacio_id")
        espacio_id = UUID(str(espacio)) if espacio else None
        conceptos: list[dict[str, Any]] = []
        for c in g["conceptos"]:
            clave = c["concepto"]["clave"]
            cantidad = Decimal(str(c["cantidad"]))
            concepto_id = concepto_id_de.get(clave)
            partida = partida_en_capa(partidas, concepto_id, Contexto(espacio_id=espacio_id)) if concepto_id is not None else None
            if cantidad <= 0:
                estado, aviso = "sin_cantidad", None
            elif espacio_id is None:
                estado = "sin_espacio"
                aviso = "Sin espacio: asigna el polígono o el elemento a un espacio para que su cantidad alimente una partida."
            elif concepto_id is None:
                propuesto = c["concepto"].get("estado") == "propuesto"
                estado = "propuesto" if propuesto else "sin_concepto"
                aviso = (
                    f"El concepto {clave} aún es una propuesta (clave provisional): no cuenta hasta que Control de obra lo autorice y esté en el catálogo."
                    if propuesto
                    else f"El concepto {clave} no está en el catálogo: no cuenta."
                )
            elif partida is None:
                estado = "falta_partida"
                aviso = f"El concepto {clave} no está en el árbol de la obra en este espacio: agrégalo al árbol; mientras tanto no cuenta."
            else:
                estado, aviso = "cuenta", None
            conceptos.append(
                {
                    **c,
                    "resolucion": {
                        "estado": estado,
                        "cuenta": estado == "cuenta",
                        "aviso": aviso,
                        "concepto_id": concepto_id,
                        "partida_id": partida.id if estado == "cuenta" and partida is not None else None,
                        "partida_nombre": partida.nombre if estado == "cuenta" and partida is not None else None,
                    },
                }
            )
        salida.append(
            {
                **g,
                "espacio_nombre": (nombres or {}).get(espacio_id) if espacio_id is not None else None,
                "conceptos": conceptos,
            }
        )
    return salida
