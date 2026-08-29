"""Cargador del catálogo base de familias: validación de fila (§7.3, §3.5).

Spec: identidad del catálogo de familias — clave, nombre, nada más
(`parent_id`/`aplica_a`/`iva_aplica` quedan en su default y Control los
ajusta a mano, mismo criterio que `domain.cargadores.niveles`). El archivo
real trae "PREFIJO" (`ACA`/`ADH`/`PET`/...) sin dónde vivir en `familia`
hoy — confirmado con el usuario, mismo criterio que la columna "TIPO" que
ya se ignora en niveles/etapas. El mapeo vive en `cabeceras.FAMILIAS.alias`
(``familia`` → ``nombre``: la columna se llama igual que el campo global de
familia-como-referencia-ajena, así que sin este alias propio el nombre de
CADA fila —la familia que esa fila identifica, no una que referencia—
quedaría descartado en silencio).

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

__all__ = ["FilaFamilia", "validar_familia"]


@dataclass(frozen=True, slots=True)
class FilaFamilia:
    """Una fila válida del catálogo base de familias (§3.5)."""

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
        misma fila repetida" — `AplicadorFamilias` la reemplaza por la
        clave real (dada o generada) antes de tocar el catálogo.
        """
        return str(self.clave) if self.clave is not None else f"__sin_clave__{self.fila}"


def validar_familia(
    fila: Sequence[object], mapa: MapaColumnas, numero: int = 0
) -> FilaFamilia:
    """Fila del archivo → `FilaFamilia`, o :class:`ErrorEnFila`.

    La clave, si viene, se normaliza con `Clave` (§3.3); si no viene, la
    fila igual se acepta (ver `FilaFamilia.clave`). El nombre sí es
    obligatorio — una familia sin nombre no es identificable ni con clave
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
            "nombre: una familia sin nombre no es identificable (§3.5).",
            columna="nombre",
            valor=mapa.valor(fila, "nombre"),
        )

    return FilaFamilia(clave=clave, nombre=nombre, fila=numero)
