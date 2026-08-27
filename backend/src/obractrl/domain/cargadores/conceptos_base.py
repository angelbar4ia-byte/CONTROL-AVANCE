"""Cargador del catálogo base de conceptos: validación de fila (§8.7).

Spec: catálogo base de identidad de conceptos — clave, descripción, unidad
(y opcionalmente la clave de esa unidad en su propio catálogo, igual que
`domain.cargadores.materiales`). Sin composición ni costo: eso es CPU
(`domain.cargadores.cpu`), un cargador distinto que analiza un concepto ya
identificado aquí — el archivo real de conceptos auxiliares trae costo y
familia (mismas columnas que `MATERIALES`) y se ignoran a propósito,
confirmado con el usuario. Mismo criterio que `domain.cargadores.
materiales`: la clave es la identidad (§3.3), lo demás puede llenarse
después a mano desde el catálogo.

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

__all__ = ["FilaConceptoBase", "validar_concepto_base"]


@dataclass(frozen=True, slots=True)
class FilaConceptoBase:
    """Una fila válida del catálogo base de conceptos (§8.7).

    ``clave`` puede venir vacía: la fila no se rechaza por eso —el usuario
    dio el ejemplo de un catálogo base sin clave que se auto-numera
    (``FAM-00001``)—, pero numerar hace falta un catálogo completo para no
    repetir un consecutivo, y este módulo es puro (§12.11, sin acceso a
    datos). Quien numera es `AplicadorConceptosBase`, con el catálogo
    vigente a la vista.
    """

    clave: Clave | None
    descripcion: str
    unidad: str | None = None
    clave_unidad: str | None = None
    """Código de la unidad en su propio catálogo (§3.3) — distinto de
    ``unidad`` (el texto libre). Mismo criterio que en materiales/mano de
    obra: el archivo real de conceptos auxiliares trae las dos columnas
    por separado."""

    fila: int = 0
    """Renglón del archivo. Viaja con el registro para que un pendiente
    pueda ligar al origen (§10.3) sin volver a abrir el libro, y para darle
    una `llave` estable a una fila sin clave (ver abajo)."""

    @property
    def llave(self) -> str:
        """Identidad para dedup y diff dentro del archivo (§3.3, §10.2).

        Sin clave, dos filas nunca son "la misma fila que se repite" —cada
        una es candidata a su propio consecutivo—, así que la `llave` usa el
        número de renglón: único dentro del archivo, y suficiente para que
        el pipeline (`adapters.excel.pipeline.leer_por_nombre`) no las
        deduplique entre sí. `AplicadorConceptosBase` la reemplaza por la
        clave real (dada o generada) antes de tocar el catálogo.
        """
        return str(self.clave) if self.clave is not None else f"__sin_clave__{self.fila}"


def validar_concepto_base(
    fila: Sequence[object], mapa: MapaColumnas, numero: int = 0
) -> FilaConceptoBase:
    """Fila del archivo → `FilaConceptoBase`, o :class:`ErrorEnFila`.

    La clave, si viene, se normaliza con `Clave` (§3.3); si no viene, la fila
    igual se acepta (ver `FilaConceptoBase.clave`). La **descripción** sí es
    obligatoria — un concepto sin nombre no es identificable ni con clave
    propia ni con una generada. La unidad es lo único opcional.
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
            "descripcion: un concepto sin descripción no es identificable (§10.1).",
            columna="descripcion",
            valor=mapa.valor(fila, "descripcion"),
        )

    return FilaConceptoBase(
        clave=clave,
        descripcion=descripcion,
        unidad=texto_limpio(mapa.valor(fila, "unidad")) or None,
        clave_unidad=texto_limpio(mapa.valor(fila, "clave_unidad")) or None,
        fila=numero,
    )
