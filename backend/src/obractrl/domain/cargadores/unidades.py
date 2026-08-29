"""Cargador del catálogo base de unidades: validación de fila (§7.3, §3.5).

Spec: identidad del catálogo de unidades — clave, nombre, nada más
(sinónimos/factor quedan en su default y Control los ajusta a mano, mismo
criterio que `domain.cargadores.niveles`). El archivo real trae "CLAVE
UNIDAD" (un consecutivo numérico del sistema de origen, sin dónde vivir
aquí) y dos columnas de texto: "UNIDAD" (la clave corta, `KG`/`PZ`/...) y
"SINONIMO" (el nombre descriptivo completo, `Kilogramo`/`Pieza`/...) —
confirmado con el usuario: pese al nombre de la columna, es el ``nombre``
obligatorio de la unidad, no un alias de clave; el catálogo real no trae
otra columna con claves alternas. El mapeo vive en `cabeceras.UNIDADES.alias`
(``unidad`` → ``clave``, ``sinonimo`` → ``nombre``).

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

__all__ = ["FilaUnidad", "validar_unidad"]


@dataclass(frozen=True, slots=True)
class FilaUnidad:
    """Una fila válida del catálogo base de unidades (§3.5)."""

    clave: Clave | None
    nombre: str

    fila: int = 0
    """Renglón del archivo. Viaja con el registro para que un pendiente
    pueda ligar al origen (§10.3), y le da una `llave` estable a una fila
    sin clave (ver abajo)."""

    @property
    def llave(self) -> str:
        """Identidad para dedup y diff dentro del archivo (§3.3, §10.2).

        Mismo criterio que `FilaNivel.llave`: sin clave, el número de
        renglón evita que el pipeline confunda dos filas distintas con "la
        misma fila repetida" — `AplicadorUnidades` la reemplaza por la
        clave real (dada o generada) antes de tocar el catálogo.
        """
        return str(self.clave) if self.clave is not None else f"__sin_clave__{self.fila}"


def validar_unidad(
    fila: Sequence[object], mapa: MapaColumnas, numero: int = 0
) -> FilaUnidad:
    """Fila del archivo → `FilaUnidad`, o :class:`ErrorEnFila`.

    La clave, si viene, se normaliza con `Clave` (§3.3); si no viene, la
    fila igual se acepta (ver `FilaUnidad.clave`). El nombre sí es
    obligatorio — una unidad sin nombre no es identificable ni con clave
    propia ni con una generada.
    """
    celda_clave = mapa.valor(fila, "clave")
    clave: Clave | None = None
    if not esta_vacio(celda_clave):
        try:
            clave = Clave(str(celda_clave))
        except ValueError as exc:
            raise ErrorEnFila(str(exc), columna="clave", valor=celda_clave) from exc

    nombre = texto_limpio(mapa.valor(fila, "nombre"))
    if not nombre:
        raise ErrorEnFila(
            "nombre: una unidad sin nombre no es identificable (§3.5).",
            columna="nombre",
            valor=mapa.valor(fila, "nombre"),
        )

    return FilaUnidad(clave=clave, nombre=nombre, fila=numero)
