"""Cargador del catálogo base de etapas de construcción: validación de
fila (§10.1).

Spec: catálogo base de identidad de etapas — clave, descripción, nada más
(orden/ponderación/importe quedan en su default; `nivel_id` queda sin
resolver — el archivo real no trae a qué nivel pertenece cada etapa, y
adivinarlo por la columna "TIPO" del archivo original sería inventar una
relación que el archivo no da: esa columna es la clasificación propia de
la herramienta de origen, no una referencia a nuestro catálogo de
niveles). Mismo criterio que `domain.cargadores.conceptos_base`: la clave
es la identidad (§3.3); si la fila no la trae, se numera sola
(`AplicadorEtapasConstructivas`, prefijo ``ECO``).

Módulo puro (§12.11): recibe la fila ya leída como celdas y devuelve la
entidad validada o levanta :class:`ErrorEnFila`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import ErrorEnFila
from obractrl.domain.shared.normalizacion import esta_vacio, texto_limpio
from obractrl.domain.shared.valores import Clave

__all__ = ["FilaEtapaConstructiva", "validar_etapa_constructiva"]


@dataclass(frozen=True, slots=True)
class FilaEtapaConstructiva:
    """Una fila válida del catálogo base de etapas de construcción (§10.1)."""

    clave: Clave | None
    descripcion: str

    fila: int = 0
    """Renglón del archivo. Viaja con el registro para que un pendiente
    pueda ligar al origen (§10.3), y le da una `llave` estable a una fila
    sin clave (ver abajo)."""

    @property
    def llave(self) -> str:
        """Identidad para dedup y diff dentro del archivo (§3.3, §10.2).

        Mismo criterio que `FilaConceptoBase.llave`: sin clave, el número
        de renglón evita que el pipeline confunda dos filas distintas con
        "la misma fila repetida" — `AplicadorEtapasConstructivas` reemplaza
        esto por la clave real (dada o generada) antes de tocar el
        catálogo.
        """
        return str(self.clave) if self.clave is not None else f"__sin_clave__{self.fila}"


def validar_etapa_constructiva(
    fila: Sequence[object], mapa: MapaColumnas, numero: int = 0
) -> FilaEtapaConstructiva:
    """Fila del archivo → `FilaEtapaConstructiva`, o :class:`ErrorEnFila`.

    La clave, si viene, se normaliza con `Clave` (§3.3); si no viene, la
    fila igual se acepta (ver `FilaEtapaConstructiva.clave`). La
    descripción es obligatoria — una etapa sin nombre no es identificable
    ni con clave propia ni con una generada.
    """
    celda_clave = mapa.valor(fila, "clave")
    clave: Clave | None = None
    if not esta_vacio(celda_clave):
        try:
            clave = Clave(str(celda_clave))
        except ValueError as exc:
            raise ErrorEnFila(str(exc), columna="clave", valor=celda_clave) from exc

    descripcion = texto_limpio(mapa.valor(fila, "descripcion"))
    if not descripcion:
        raise ErrorEnFila(
            "descripcion: una etapa sin descripción no es identificable (§10.1).",
            columna="descripcion",
            valor=mapa.valor(fila, "descripcion"),
        )

    return FilaEtapaConstructiva(clave=clave, descripcion=descripcion, fila=numero)
