"""El estado de una parte y sus transiciones (cerebro WORKFLOWS.md §8.9, D-571 a D-579).

Cada **parte** (etapa o concepto independiente) recorre su propio camino, a su paso:

    cuantificando ─► enviada a presupuesto ─► por validar ─► autorizada ─► enviada a programa
                                                                       ─► programada ─► asignada

* **Enviar a presupuesto:** quien cuantifica manda lo que ya está (total o por partes).
* **Autorizar** lo realiza **Costos o Control de obra**; **validar** lo hace **Control de obra**
  al final (D-571). «Autorizada» es el nivel que el cerebro llamaba «listo» (D-576).
* **Programar pide autorizada** (D-576), más estricto que el «costeado» de D-532.
* **Asignar** equivale a contratar: de ahí en adelante, cambiar es control de cambio.
* **Devolver** —volver a un paso anterior— es **libre hasta asignar** (D-571); una parte
  asignada ya no se devuelve.

Quién puede cada acción vive en `PERMISOS`: sumar un rol (Costos) es sumar una línea.

Módulo puro: sin BD ni FastAPI (§12.11).
"""

from __future__ import annotations

from enum import StrEnum

from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "ORDEN",
    "PERMISOS",
    "Accion",
    "ErrorDeParte",
    "EstadoDeParte",
    "ParteNoPermitida",
    "aplicar",
    "roles_del_siguiente_paso",
]


class EstadoDeParte(StrEnum):
    """Es el enum de Postgres `estado_parte`."""

    CUANTIFICANDO = "cuantificando"
    ENVIADA_PRESUPUESTO = "enviada_presupuesto"
    POR_VALIDAR = "por_validar"
    AUTORIZADA = "autorizada"
    ENVIADA_PROGRAMA = "enviada_programa"
    PROGRAMADA = "programada"
    ASIGNADA = "asignada"


ORDEN: tuple[EstadoDeParte, ...] = tuple(EstadoDeParte)
"""El orden del camino: lo «anterior» a un estado es lo que va antes aquí."""


class Accion(StrEnum):
    ENVIAR_A_PRESUPUESTO = "enviar_a_presupuesto"
    AUTORIZAR = "autorizar"
    VALIDAR = "validar"
    ENVIAR_A_PROGRAMA = "enviar_a_programa"
    PROGRAMAR = "programar"
    ASIGNAR = "asignar"
    DEVOLVER = "devolver"


class ErrorDeParte(ValueError):
    """La acción no cabe en el estado en que está la parte."""


class ParteNoPermitida(PermissionError):
    """El rol no puede hacer esa acción sobre una parte."""


_C = Rol.CONTROL_OBRA
_K = Rol.COSTOS

PERMISOS: dict[Accion, frozenset[Rol]] = {
    # Quien cuantifica manda lo que ya está; autorizar lo realiza Costos o Control y Control
    # valida al final (D-571). Costos ve todas las obras pero no programa, no asigna ni valida.
    Accion.ENVIAR_A_PRESUPUESTO: frozenset({_C, _K}),
    Accion.AUTORIZAR: frozenset({_C, _K}),
    Accion.VALIDAR: frozenset({_C}),
    Accion.ENVIAR_A_PROGRAMA: frozenset({_C}),
    Accion.PROGRAMAR: frozenset({_C, Rol.SUPERVISOR}),
    Accion.ASIGNAR: frozenset({_C}),
    Accion.DEVOLVER: frozenset({_C}),
}

_DE_A: dict[Accion, tuple[EstadoDeParte, EstadoDeParte]] = {
    Accion.ENVIAR_A_PRESUPUESTO: (EstadoDeParte.CUANTIFICANDO, EstadoDeParte.ENVIADA_PRESUPUESTO),
    Accion.AUTORIZAR: (EstadoDeParte.ENVIADA_PRESUPUESTO, EstadoDeParte.POR_VALIDAR),
    Accion.VALIDAR: (EstadoDeParte.POR_VALIDAR, EstadoDeParte.AUTORIZADA),
    Accion.ENVIAR_A_PROGRAMA: (EstadoDeParte.AUTORIZADA, EstadoDeParte.ENVIADA_PROGRAMA),
    Accion.PROGRAMAR: (EstadoDeParte.ENVIADA_PROGRAMA, EstadoDeParte.PROGRAMADA),
    Accion.ASIGNAR: (EstadoDeParte.PROGRAMADA, EstadoDeParte.ASIGNADA),
}


_SIGUIENTE: dict[EstadoDeParte, Accion] = {
    EstadoDeParte.CUANTIFICANDO: Accion.ENVIAR_A_PRESUPUESTO,
    EstadoDeParte.ENVIADA_PRESUPUESTO: Accion.AUTORIZAR,
    EstadoDeParte.POR_VALIDAR: Accion.VALIDAR,
    EstadoDeParte.AUTORIZADA: Accion.ENVIAR_A_PROGRAMA,
    EstadoDeParte.ENVIADA_PROGRAMA: Accion.PROGRAMAR,
    EstadoDeParte.PROGRAMADA: Accion.ASIGNAR,
}


def roles_del_siguiente_paso(estado: EstadoDeParte) -> frozenset[Rol]:
    """Quiénes pueden dar el paso que sigue a una parte en ese estado: a ellos se les avisa
    («se avisa a quien tiene que dar el siguiente paso», §8.6). Una parte asignada ya no tiene
    paso siguiente."""
    accion = _SIGUIENTE.get(estado)
    return PERMISOS[accion] if accion is not None else frozenset()


def aplicar(
    accion: Accion,
    *,
    estado: EstadoDeParte,
    rol: Rol,
    a: EstadoDeParte | None = None,
) -> EstadoDeParte:
    """El estado al que pasa la parte, o `ParteNoPermitida` / `ErrorDeParte`.

    Primero el permiso: quien no puede hacerlo no debe enterarse de en qué estado está.
    `a` solo lo usa `devolver`: el estado anterior al que se vuelve.
    """
    if rol not in PERMISOS[accion]:
        raise ParteNoPermitida(
            f"El rol {rol.value!r} no puede hacer {accion.value.replace('_', ' ')!r} sobre una parte."
        )

    if accion is Accion.DEVOLVER:
        if estado is EstadoDeParte.ASIGNADA:
            raise ErrorDeParte(
                "Una parte asignada ya no se devuelve: de aquí en adelante, cambiar es control "
                "de cambio."
            )
        if a is None:
            raise ErrorDeParte("Devolver dice a qué estado se vuelve.")
        if ORDEN.index(a) >= ORDEN.index(estado):
            raise ErrorDeParte(
                f"Solo se vuelve a un paso anterior: de {estado.value!r} no se puede ir a {a.value!r}."
            )
        return a

    desde, hacia = _DE_A[accion]
    if estado is not desde:
        raise ErrorDeParte(
            f"No se puede {accion.value.replace('_', ' ')}: la parte está {estado.value!r} y "
            f"hace falta que esté {desde.value!r}."
        )
    return hacia
