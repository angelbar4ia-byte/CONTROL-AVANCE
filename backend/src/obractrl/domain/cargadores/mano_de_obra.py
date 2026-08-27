"""Cargador de mano de obra / destajos: validación de fila
(§10.6 `CABECERAS_MANO_DE_OBRA.xlsx`, hoja `DESTAJOS`).

Spec §10.6 ("Mano de obra (Destajos): clave, clave_usuario, descripción,
unidad, cuadrilla, rendimiento_teórico/real, costo_unitario, familia") ·
§3.3 (la CLAVE manda).

Un renglón de mano de obra es un `Insumo` con ``tipo = 'mano_obra'`` (§7.3),
igual que un material lo es con ``tipo = 'material'``: este cargador
alimenta el mismo catálogo de insumos, no una tabla aparte.

``rendimiento_real`` del §10.6 **no** se lee aquí a propósito: sale de
cruzar contra la duración real de la obra, un cálculo posterior — este
archivo solo trae el teórico.

Módulo puro (§12.11): recibe la fila ya leída como celdas y devuelve la
entidad validada o levanta :class:`ErrorEnFila`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import ErrorEnFila
from obractrl.domain.shared.diccionario import TipoInsumo
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_decimal,
    esta_vacio,
    texto_limpio,
)
from obractrl.domain.shared.valores import Clave

__all__ = ["FilaManoObra", "validar_mano_obra"]


@dataclass(frozen=True, slots=True)
class FilaManoObra:
    """Una fila válida del catálogo de mano de obra / destajos (§10.6)."""

    clave: Clave
    descripcion: str
    unidad: str | None = None
    clave_unidad: str | None = None
    """Código de la unidad en su propio catálogo (§3.3) — distinto de
    ``unidad`` (el texto libre). Mismo criterio que en materiales."""

    familia: str | None = None
    cuadrilla: str | None = None
    """Clave de la cuadrilla que ejecuta este destajo — no texto libre: se
    homologa contra el catálogo de cuadrillas, dándola de alta si no
    existe (mismo criterio que unidad/familia, §8.7)."""

    rendimiento_teorico: Decimal | None = None
    costo_base: Decimal | None = None
    """``None`` = **la columna no vino** en esta fila — igual que en
    materiales, quien aplica la carga trata el ``None`` como "conserva lo
    vigente" (§10.2, modo Actualizar)."""

    tipo: TipoInsumo = TipoInsumo.MANO_OBRA

    fila: int = 0
    """Renglón del archivo. Viaja con el registro para que un pendiente
    pueda ligar al origen (§10.3) sin volver a abrir el libro."""

    @property
    def llave(self) -> str:
        """Identidad para dedup y diff: la CLAVE (§3.3, §10.2)."""
        return str(self.clave)


def _decimal_opcional(
    fila: Sequence[object], mapa: MapaColumnas, campo: str
) -> Decimal | None:
    celda = mapa.valor(fila, campo)
    if esta_vacio(celda):
        return None
    try:
        valor = a_decimal(celda, campo=campo)
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna=campo, valor=celda) from exc
    if valor < 0:
        raise ErrorEnFila(
            f"{campo}: no puede ser negativo ({valor}).", columna=campo, valor=celda
        )
    return valor


def validar_mano_obra(
    fila: Sequence[object],
    mapa: MapaColumnas,
    numero: int = 0,
    *,
    tipo: TipoInsumo = TipoInsumo.MANO_OBRA,
) -> FilaManoObra:
    """Fila del archivo → `FilaManoObra`, o :class:`ErrorEnFila`.

    La **clave** es obligatoria y se normaliza con `Clave` (§3.3): sin ella
    no hay con qué deduplicar ni contra qué cruzar.

    ``tipo`` distingue mano de obra de subcontratos (§10.6): mismas
    cabeceras, mismo validador — lo fija `CargadorSubcontratos` vía
    `functools.partial`.
    """
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

    descripcion = texto_limpio(mapa.valor(fila, "descripcion"))
    if not descripcion:
        raise ErrorEnFila(
            "descripcion: es obligatoria (§10.1).",
            columna="descripcion",
            valor=mapa.valor(fila, "descripcion"),
        )

    return FilaManoObra(
        clave=clave,
        descripcion=descripcion,
        unidad=texto_limpio(mapa.valor(fila, "unidad")) or None,
        clave_unidad=texto_limpio(mapa.valor(fila, "clave_unidad")) or None,
        familia=texto_limpio(mapa.valor(fila, "familia")) or None,
        cuadrilla=texto_limpio(mapa.valor(fila, "cuadrilla")) or None,
        rendimiento_teorico=_decimal_opcional(fila, mapa, "rendimiento_teorico"),
        costo_base=_decimal_opcional(fila, mapa, "costo_base"),
        tipo=tipo,
        fila=numero,
    )
