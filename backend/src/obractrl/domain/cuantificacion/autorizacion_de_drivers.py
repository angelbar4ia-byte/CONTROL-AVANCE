"""Quién propone y quién autoriza un cambio a un driver del Paramétrico (F3, 2026-11-19).

Los cambios a drivers pasan por Control de obra: **Costos y Control de obra proponen** (quien tiene permiso de editar drivers) y **solo
Control de obra autoriza**. Lo que propone Control de obra nace ya autorizado, como en `autorizacion_de_elementos` (el patrón de las
propuestas de estructura). Cada propuesta guarda quién propuso, quién decidió, cuándo y el valor anterior: esa es la bitácora de quién y
cuándo. Mientras una propuesta está pendiente **no cambia nada**: los cálculos siguen leyendo el valor vigente.

Una propuesta es una de tres cosas: fijar el valor y/o el modo del driver **global**, fijar el valor de una **obra** o **quitar** el ajuste
de una obra. Funciones puras, sin base de datos.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from obractrl.domain.cuantificacion.drivers import (
    DefinicionDeDriver,
    ErrorDeDriver,
    ModoDeDriver,
    puede_editar_drivers,
    validar_modo,
    validar_que_se_puede_cambiar,
    validar_valor,
)

__all__ = [
    "ESTADOS_DE_PROPUESTA",
    "ROLES_QUE_AUTORIZAN",
    "ROLES_QUE_PROPONEN",
    "PropuestaValidada",
    "armar_propuesta",
    "estado_de_alta",
    "puede_autorizar",
    "validar_que_autoriza",
    "validar_que_propone",
]

ROL_CONTROL_DE_OBRA = "control_obra"
ROLES_QUE_PROPONEN = ("costos", ROL_CONTROL_DE_OBRA)
ROLES_QUE_AUTORIZAN = (ROL_CONTROL_DE_OBRA,)
ESTADOS_DE_PROPUESTA = ("pendiente", "autorizada", "rechazada")

Alcance = Literal["global", "obra"]
Accion = Literal["fijar", "quitar"]


def puede_autorizar(rol: str) -> bool:
    return rol in ROLES_QUE_AUTORIZAN


def validar_que_propone(rol: str) -> None:
    if rol not in ROLES_QUE_PROPONEN or not puede_editar_drivers(rol):
        raise ErrorDeDriver("Solo Costos y Control de obra proponen cambios a los drivers.")


def validar_que_autoriza(rol: str) -> None:
    if not puede_autorizar(rol):
        raise ErrorDeDriver("Solo Control de obra autoriza los cambios a los drivers.")


def estado_de_alta(rol: str) -> str:
    """El estado con que nace una propuesta: la de Control de obra ya está autorizada; la de Costos queda pendiente."""
    validar_que_propone(rol)
    return "autorizada" if puede_autorizar(rol) else "pendiente"


@dataclass(frozen=True, slots=True)
class PropuestaValidada:
    clave: str
    alcance: Alcance
    accion: Accion
    valor: Decimal | None
    modo: ModoDeDriver | None


def armar_propuesta(
    d: DefinicionDeDriver,
    *,
    alcance: Alcance,
    accion: Accion = "fijar",
    valor: object | None = None,
    modo: str | None = None,
    modo_global_actual: ModoDeDriver | None = None,
) -> PropuestaValidada:
    """Revisa una propuesta antes de guardarla (y otra vez al autorizarla). F4: un driver inmutable no se propone.

    `modo_global_actual` es el modo que el global tiene hoy: un ajuste de obra solo cabe en un driver `ajustable`."""
    validar_que_se_puede_cambiar(d)
    if alcance == "global":
        if accion != "fijar":
            raise ErrorDeDriver("Del driver global solo se propone fijar su valor o su modo.")
        if valor is None and modo is None:
            raise ErrorDeDriver("Indica el valor o el modo del driver.")
        return PropuestaValidada(
            d.clave, "global", "fijar", validar_valor(d, valor) if valor is not None else None,
            validar_modo(modo) if modo is not None else None,
        )
    if modo is not None:
        raise ErrorDeDriver("El modo es del driver global: una obra solo tiene su valor.")
    if accion == "quitar":
        if valor is not None:
            raise ErrorDeDriver("Quitar el ajuste de una obra no lleva valor.")
        return PropuestaValidada(d.clave, "obra", "quitar", None, None)
    if (modo_global_actual or d.modo_inicial) != "ajustable":
        raise ErrorDeDriver(f"«{d.nombre}» es fijo: la obra no lo ajusta. Primero se cambia a ajustable en los drivers globales.")
    if valor is None:
        raise ErrorDeDriver("Indica el valor del ajuste de la obra.")
    return PropuestaValidada(d.clave, "obra", "fijar", validar_valor(d, valor), None)
