"""Lo común de los cálculos de elementos que leen los drivers de la obra (Ola 4, «drivers conectados»).

Cada petición de cálculo acepta un `obra_id` opcional. Con él, el cálculo toma los drivers vigentes de esa obra (petición > obra >
defecto); sin él, vale lo de siempre. La respuesta dice qué drivers usó y de dónde salió cada valor (`drivers_usados`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from obractrl.domain.cuantificacion.drivers_de_elementos import DriverUsado

__all__ = ["DriverUsadoRespuesta", "a_respuesta", "explicitos_de_receta"]


class DriverUsadoRespuesta(BaseModel):
    clave: str = Field(description="La clave del driver del Paramétrico.")
    nombre: str
    unidad: str
    valor: float = Field(description="El valor con que se calculó.")
    fuente: Literal["peticion", "obra", "global", "defecto"] = Field(
        description="`peticion`: lo mandó la petición; `obra`: el driver propio de la obra; `global`: el driver global de la "
        "organización; `defecto`: el valor por defecto del cálculo."
    )


def a_respuesta(usados: list[DriverUsado]) -> list[dict[str, object]]:
    return [{"clave": u.clave, "nombre": u.nombre, "unidad": u.unidad, "valor": u.valor, "fuente": u.fuente} for u in usados]


def explicitos_de_receta(p: BaseModel) -> dict[str, float]:
    """Solo lo que la petición mandó (los campos sin mandar no son explícitos: pueden salir del driver de la obra)."""
    return {k: float(v) for k, v in p.model_dump(include=set(p.model_fields_set)).items()}
