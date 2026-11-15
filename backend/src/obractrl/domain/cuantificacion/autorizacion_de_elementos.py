"""Quién propone y quién autoriza los elementos y sus conceptos, y cómo se numeran las versiones (plan de elementos de muro,
fase I; D-647, D-648).

**Costos propone y Control de obra autoriza.** Lo que Costos da de alta (un elemento nuevo, un cambio a un elemento
autorizado, un concepto nuevo del elemento, los coeficientes de un APU) queda *pendiente* y no cuenta hasta que Control de
obra lo autorice; los cambios de Control de obra no piden autorización. Siempre se guarda versión: cada autorización crea la
versión siguiente del elemento o del concepto, con quién propuso, quién autorizó y cuándo.

Un elemento nuevo que propone Costos se puede usar como **provisional** (queda `pendiente`), pero sus conceptos nuevos y sus
cambios no cuentan en el presupuesto hasta autorizarse. Nada de esto pone precios ni destajos. Funciones puras, sin base de datos.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)

__all__ = [
    "CLASES_DE_REVISION",
    "ESTADOS_DEL_ELEMENTO",
    "ESTADOS_DE_LA_REVISION",
    "ROLES_QUE_AUTORIZAN",
    "ROLES_QUE_PROPONEN",
    "diferencias",
    "estado_de_alta",
    "puede_autorizar",
    "requiere_autorizacion_el_cambio",
    "siguiente_version",
    "validar_que_autoriza",
    "validar_que_propone",
]

ROL_CONTROL_DE_OBRA = "control_obra"
ROL_COSTOS = "costos"
ROLES_QUE_PROPONEN = (ROL_COSTOS, ROL_CONTROL_DE_OBRA)
ROLES_QUE_AUTORIZAN = (ROL_CONTROL_DE_OBRA,)
ESTADOS_DEL_ELEMENTO = ("pendiente", "autorizado")
ESTADOS_DE_LA_REVISION = ("pendiente", "autorizada", "rechazada")
CLASES_DE_REVISION = ("elemento", "concepto", "apu")

_ETIQUETAS = {
    "clave": "Clave",
    "nombre": "Nombre",
    "categoria": "Categoría",
    "subcategoria": "Subcategoría",
    "parametros": "Parámetro",
    "materiales": "Material",
}


def puede_autorizar(rol: str) -> bool:
    """Solo Control de obra autoriza."""
    return rol in ROLES_QUE_AUTORIZAN


def validar_que_propone(rol: str) -> None:
    if rol not in ROLES_QUE_PROPONEN:
        raise ErrorDeElementoParametrico("Solo Costos y Control de obra proponen elementos y conceptos.")


def validar_que_autoriza(rol: str) -> None:
    if not puede_autorizar(rol):
        raise ErrorDeElementoParametrico("Solo Control de obra autoriza.")


def estado_de_alta(rol: str) -> str:
    """El estado con que nace un elemento nuevo: el de Control de obra ya está autorizado; el de Costos queda pendiente."""
    validar_que_propone(rol)
    return "autorizado" if puede_autorizar(rol) else "pendiente"


def requiere_autorizacion_el_cambio(rol: str, estado_del_elemento: str) -> bool:
    """Un cambio pide autorización si lo propone Costos sobre un elemento **ya autorizado**. Control de obra nunca la pide, y
    sobre un elemento aún pendiente (provisional) Costos sigue afinando su propia propuesta."""
    validar_que_propone(rol)
    return not puede_autorizar(rol) and estado_del_elemento == "autorizado"


def siguiente_version(versiones_autorizadas: Iterable[int]) -> int:
    """El número de la versión que se crea al autorizar: una más que la mayor ya autorizada (la primera es la 1)."""
    return max((int(v) for v in versiones_autorizadas), default=0) + 1


def _plano(valor: Any) -> Any:
    return float(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else valor


def diferencias(antes: Mapping[str, Any], despues: Mapping[str, Any]) -> list[str]:
    """Lo que cambia entre dos estados de un elemento, en palabras (`Nombre: A → B`, `Parámetro alto: 3 → 4`). Solo cuenta lo
    que viene en `despues` y es distinto; los parámetros y los materiales se comparan uno por uno."""
    cambios: list[str] = []
    for campo, etiqueta in _ETIQUETAS.items():
        if campo not in despues:
            continue
        nuevo, previo = despues[campo], antes.get(campo)
        if isinstance(nuevo, Mapping):
            previo = previo if isinstance(previo, Mapping) else {}
            # Los parámetros vienen parciales (solo los que cambian); los materiales reemplazan a todos los anteriores.
            claves = nuevo if campo == "parametros" else {*previo, *nuevo}
            for k in sorted(claves, key=str):
                a, b = _plano(previo.get(k)), _plano(nuevo.get(k))
                if a != b:
                    cambios.append(f"{etiqueta} {k}: {'—' if a is None else a} → {'—' if b is None else b}")
        elif _plano(previo) != _plano(nuevo):
            cambios.append(f"{etiqueta}: {'—' if previo is None else previo} → {'—' if nuevo is None else nuevo}")
    return cambios
