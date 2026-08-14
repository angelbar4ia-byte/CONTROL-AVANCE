"""Normalización de FOLIO de estimaciones.

Spec §3.2.

``FOLIO = [E-]WWYY-NNN``
  * ``WW``  semana
  * ``YY``  año a dos dígitos
  * ``NNN`` consecutivo, reinicia por (semana + año) y es **continuo**:
    ERP y no-ERP comparten el contador de la semana.
  * ``E-``  solo si el origen es ERP. ERP es únicamente **metadato**: de qué
    sistema salió el dato. No hay integración en línea (§3.2).

Un solo campo "semana" del archivo puede traer semana suelta (``21``), un
código (``S-2126``) o un folio completo (``2126-003``). Si ya viene con
formato de folio, **se toma como folio** y semana/año se clasifican a partir
de él. Sin año, se asume el año en curso.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

__all__ = ["Folio", "interpretar_campo_semana"]

_RE_FOLIO = re.compile(
    r"^\s*(?P<erp>E-)?(?P<ww>\d{2})(?P<yy>\d{2})-(?P<nnn>\d{1,4})\s*$",
    re.IGNORECASE,
)
_RE_CODIGO = re.compile(r"^\s*S-?(?P<ww>\d{2})(?P<yy>\d{2})\s*$", re.IGNORECASE)
_RE_SEMANA = re.compile(r"^\s*(?P<ww>\d{1,2})\s*$")


def _anio_completo(yy: int) -> int:
    """Expande el año a dos dígitos al siglo en curso."""
    siglo = date.today().year // 100 * 100
    return siglo + yy


@dataclass(frozen=True, slots=True)
class Folio:
    """Folio de estimación, único por fila (§3.2)."""

    semana: int
    anio: int
    consecutivo: int
    es_erp: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.semana <= 53:
            raise ValueError(f"Semana fuera de rango 1–53: {self.semana}")
        if self.consecutivo < 1:
            raise ValueError(f"El consecutivo arranca en 1: {self.consecutivo}")
        if self.anio < 2000 or self.anio > 2999:
            raise ValueError(f"Año fuera de rango: {self.anio}")

    def __str__(self) -> str:
        prefijo = "E-" if self.es_erp else ""
        return f"{prefijo}{self.semana:02d}{self.anio % 100:02d}-{self.consecutivo:03d}"

    @classmethod
    def parsear(cls, texto: str) -> Folio:
        """Lee un folio ya formado. Lanza ``ValueError`` si no lo es."""
        m = _RE_FOLIO.match(texto or "")
        if not m:
            raise ValueError(f"No tiene formato de folio [E-]WWYY-NNN: {texto!r}")
        return cls(
            semana=int(m.group("ww")),
            anio=_anio_completo(int(m.group("yy"))),
            consecutivo=int(m.group("nnn")),
            es_erp=bool(m.group("erp")),
        )

    @classmethod
    def siguiente(
        cls, semana: int, anio: int, ultimo_consecutivo: int, es_erp: bool = False
    ) -> Folio:
        """Emite el folio siguiente de la semana.

        El contador es **compartido** entre ERP y no-ERP (§3.2): quien pida el
        siguiente recibe ``ultimo + 1`` sin importar su origen.
        """
        return cls(
            semana=semana,
            anio=anio,
            consecutivo=ultimo_consecutivo + 1,
            es_erp=es_erp,
        )


def interpretar_campo_semana(
    valor: str | int | None, anio_default: int | None = None
) -> tuple[int, int, Folio | None]:
    """Resuelve el campo ambiguo "semana" de los archivos externos (§3.2).

    Devuelve ``(semana, anio, folio)``. ``folio`` viene poblado solo cuando el
    valor ya traía formato de folio; en ese caso manda sobre cualquier otra
    interpretación.

    >>> interpretar_campo_semana("2126-003")[:2]
    (21, 2026)
    >>> interpretar_campo_semana("S-2126")[:2]
    (21, 2026)
    >>> interpretar_campo_semana(21, anio_default=2026)[:2]
    (21, 2026)
    """
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise ValueError("El campo semana viene vacío.")

    texto = str(valor).strip()
    anio_default = anio_default or date.today().year

    # 1. ¿Ya es un folio? Entonces manda (§3.2).
    try:
        folio = Folio.parsear(texto)
    except ValueError:
        pass
    else:
        return folio.semana, folio.anio, folio

    # 2. ¿Código de semana S-WWYY?
    m = _RE_CODIGO.match(texto)
    if m:
        return int(m.group("ww")), _anio_completo(int(m.group("yy"))), None

    # 3. Semana suelta: sin año, se asume el año en curso.
    m = _RE_SEMANA.match(texto)
    if m:
        semana = int(m.group("ww"))
        if not 1 <= semana <= 53:
            raise ValueError(f"Semana fuera de rango 1–53: {semana}")
        return semana, anio_default, None

    raise ValueError(
        f"No se pudo interpretar el campo semana: {texto!r}. "
        f"Se esperaba una semana (21), un código (S-2126) o un folio (2126-003)."
    )
