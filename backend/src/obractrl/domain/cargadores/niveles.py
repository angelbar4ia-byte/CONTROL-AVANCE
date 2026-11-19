"""Cargador del catálogo base de niveles de construcción: validación de
fila (§10.1).

Spec: catálogo base de identidad de niveles — clave, descripción, nada más
(orden/importe quedan en su default y Control los ajusta a mano). Mismo
criterio que `domain.cargadores.conceptos_base`: la clave es la identidad
(§3.3); si la fila no la trae, se numera sola (`AplicadorNiveles`, prefijo
``NIV``).

Módulo puro (§12.11): recibe la fila ya leída como celdas y devuelve la
entidad validada o levanta :class:`ErrorEnFila`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import ErrorEnFila
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_entero,
    esta_vacio,
    texto_limpio,
)
from obractrl.domain.shared.valores import Clave

__all__ = ["FilaNivel", "validar_nivel"]


@dataclass(frozen=True, slots=True)
class FilaNivel:
    """Una fila válida del catálogo base de niveles de construcción (§10.1)."""

    clave: Clave | None
    descripcion: str

    numero_de_nivel: int | None = None
    """Número de nivel explícito (PB = 1, 1 a 99) o ``None`` si el archivo no lo trae (no se toca el guardado)."""

    fila: int = 0
    """Renglón del archivo. Viaja con el registro para que un pendiente
    pueda ligar al origen (§10.3), y le da una `llave` estable a una fila
    sin clave (ver abajo)."""

    @property
    def llave(self) -> str:
        """Identidad para dedup y diff dentro del archivo (§3.3, §10.2).

        Mismo criterio que `FilaConceptoBase.llave`: sin clave, el número
        de renglón evita que el pipeline confunda dos filas distintas con
        "la misma fila repetida" — `AplicadorNiveles` reemplaza esto por la
        clave real (dada o generada) antes de tocar el catálogo.
        """
        return str(self.clave) if self.clave is not None else f"__sin_clave__{self.fila}"


def validar_nivel(
    fila: Sequence[object], mapa: MapaColumnas, numero: int = 0
) -> FilaNivel:
    """Fila del archivo → `FilaNivel`, o :class:`ErrorEnFila`.

    La clave, si viene, se normaliza con `Clave` (§3.3); si no viene, la
    fila igual se acepta (ver `FilaNivel.clave`). La descripción es
    obligatoria — un nivel sin nombre no es identificable ni con clave
    propia ni con una generada.
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
            "descripcion: un nivel sin descripción no es identificable (§10.1).",
            columna="descripcion",
            valor=mapa.valor(fila, "descripcion"),
        )

    celda_numero = mapa.valor(fila, "numero_de_nivel")
    numero_de_nivel: int | None = None
    if not esta_vacio(celda_numero):
        try:
            numero_de_nivel = a_entero(celda_numero, campo="numero_de_nivel")
        except ValorNoConvertible as exc:
            raise ErrorEnFila(str(exc), columna="numero_de_nivel", valor=celda_numero) from exc
        if not 1 <= numero_de_nivel <= 99:
            raise ErrorEnFila(
                "numero_de_nivel: el número de nivel va de 1 (PB) a 99.",
                columna="numero_de_nivel",
                valor=celda_numero,
            )

    return FilaNivel(clave=clave, descripcion=descripcion, numero_de_nivel=numero_de_nivel, fila=numero)
