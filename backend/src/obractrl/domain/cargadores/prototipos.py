"""Cargador de prototipos: validación de fila (§7.2, extensión propia).

A diferencia de `materiales.py`/`almacen.py`, este archivo no está descrito
por el §10.6 — es el bulk-load que le faltaba a `POST /prototipos`. Mismo
patrón: módulo puro (§12.11), recibe la fila ya leída y devuelve la entidad
validada o levanta :class:`ErrorEnFila`.

Las reglas de rango (niveles ≥ 1, recámaras ≥ 0, m² positivo) **no** viven
aquí: las vuelve a aplicar `domain.proyectos.reglas.Prototipo.crear()`, que
el aplicador llama por fila. Duplicarlas aquí sería una tercera copia que se
desincroniza (mismo motivo que documenta `usuarios_sql.py` para sus reglas).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import ErrorEnFila
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_decimal,
    a_entero,
    esta_vacio,
    texto_limpio,
)
from obractrl.domain.shared.valores import Clave

__all__ = ["FilaPrototipo", "validar_prototipo"]


@dataclass(frozen=True, slots=True)
class FilaPrototipo:
    """Una fila válida del archivo de prototipos."""

    proyecto_clave: str
    clave: Clave
    nombre: str
    m2: Decimal | None = None
    niveles: int | None = None
    recamaras: int | None = None

    fila: int = 0
    """Renglón del archivo. Viaja con el registro para que un error de fila
    pueda ligar al origen (§10.3) sin volver a abrir el libro."""

    @property
    def llave(self) -> str:
        """Identidad para dedup y diff: la CLAVE (§3.3, §10.2).

        Igual que en materiales: `uq_prototipo_clave` es único por
        `(org_id, clave)`, sin `proyecto_id` — dos proyectos no pueden
        compartir clave, así que la clave sola ya identifica la fila.
        """
        return str(self.clave)


def _entero_opcional(
    fila: Sequence[object], mapa: MapaColumnas, campo: str
) -> int | None:
    celda = mapa.valor(fila, campo)
    if esta_vacio(celda):
        return None
    try:
        return a_entero(celda, campo=campo)
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna=campo, valor=celda) from exc


def validar_prototipo(
    fila: Sequence[object], mapa: MapaColumnas, numero: int = 0
) -> FilaPrototipo:
    """Fila del archivo → `FilaPrototipo`, o :class:`ErrorEnFila`.

    `proyecto_clave` y `clave` son obligatorias y no se homologan (§3.3): un
    proyecto o una clave que no cruzan exacto son un error de fila, no algo
    que adivinar.
    """
    celda_proyecto = mapa.valor(fila, "proyecto_clave")
    proyecto_clave = texto_limpio(celda_proyecto)
    if not proyecto_clave:
        raise ErrorEnFila(
            "proyecto_clave: la fila no trae el proyecto al que pertenece.",
            columna="proyecto_clave",
            valor=celda_proyecto,
        )

    celda_clave = mapa.valor(fila, "clave")
    if esta_vacio(celda_clave):
        raise ErrorEnFila(
            "clave: la fila no trae clave y la clave es única por catálogo (§3.3).",
            columna="clave",
        )
    try:
        clave = Clave(str(celda_clave))
    except ValueError as exc:
        raise ErrorEnFila(str(exc), columna="clave", valor=celda_clave) from exc

    celda_nombre = mapa.valor(fila, "nombre")
    nombre = texto_limpio(celda_nombre)
    if not nombre:
        raise ErrorEnFila(
            "nombre: es obligatorio (§7.2).",
            columna="nombre",
            valor=celda_nombre,
        )

    celda_m2 = mapa.valor(fila, "m2")
    m2: Decimal | None = None
    if not esta_vacio(celda_m2):
        try:
            m2 = a_decimal(celda_m2, campo="m2")
        except ValorNoConvertible as exc:
            raise ErrorEnFila(str(exc), columna="m2", valor=celda_m2) from exc

    return FilaPrototipo(
        proyecto_clave=proyecto_clave,
        clave=clave,
        nombre=nombre,
        m2=m2,
        niveles=_entero_opcional(fila, mapa, "niveles"),
        recamaras=_entero_opcional(fila, mapa, "recamaras"),
        fila=numero,
    )
