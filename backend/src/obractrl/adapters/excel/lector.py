"""Lectura defensiva de un `.xlsx` subido por un usuario.

Spec §9.2 (pipeline de carga) · §10.6 (hoja por archivo) · §12.11 (el parseo
vive en el borde, no en el dominio).

**Un archivo subido es entrada no confiable.** Todo lo de aquí existe por eso:

- Se abre **desde memoria** (`BytesIO`), nunca desde una ruta que venga del
  usuario: no hay forma de que un nombre de archivo apunte al disco del
  servidor.
- `data_only=True` toma el **valor cacheado** que Excel dejó en la celda.
  openpyxl no evalúa fórmulas —ni aquí ni en ningún modo—, y una celda que
  solo trae la fórmula sin valor cacheado se rechaza en vez de colarse como
  el texto ``"=A1*B1"``.
- Límites de **bytes**, **filas** y **columnas** antes de recorrer nada: un
  libro de 2 GB o de un millón de filas no debe poder tumbar el proceso.
- `read_only=True` recorre en streaming en vez de materializar el libro.

El dominio (`domain.cargadores`) recibe celdas ya leídas y no sabe que
existió un `.xlsx` (§12.11).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from io import BytesIO

from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook

__all__ = [
    "LIMITES",
    "ErrorDeArchivo",
    "Limites",
    "abrir_libro",
    "filas_de_hoja",
]


class ErrorDeArchivo(ValueError):
    """El archivo no se puede leer: no es un `.xlsx`, no trae la hoja, excede
    los límites o vino corrupto.

    Es un error del archivo entero, no de una fila: no hay nada que reportar
    renglón por renglón si el libro no abre (§9.3).
    """


@dataclass(frozen=True, slots=True)
class Limites:
    """Topes de una carga. Existen para acotar el daño de un archivo hostil."""

    bytes_maximos: int = 20 * 1024 * 1024
    filas_maximas: int = 100_000
    columnas_maximas: int = 256


LIMITES = Limites()
"""Límites por defecto.

20 MB y 100 000 filas cubren con holgura los archivos reales del §10.6 —el de
almacén es el más grande, con 46 columnas— y siguen siendo un tope duro.
256 columnas es el doble largo de ese mismo archivo.
"""


def abrir_libro(contenido: bytes, *, limites: Limites = LIMITES) -> Workbook:
    """Abre el libro desde memoria, con los límites ya aplicados."""
    if not contenido:
        raise ErrorDeArchivo("El archivo llegó vacío.")
    if len(contenido) > limites.bytes_maximos:
        raise ErrorDeArchivo(
            f"El archivo pesa {len(contenido) / 1024 / 1024:.1f} MB y el máximo "
            f"es {limites.bytes_maximos / 1024 / 1024:.0f} MB."
        )
    try:
        return load_workbook(
            BytesIO(contenido),
            read_only=True,
            data_only=True,
            keep_links=False,
            rich_text=False,
        )
    except Exception as exc:  # noqa: BLE001 — openpyxl levanta de todo ante basura
        raise ErrorDeArchivo(
            f"No se pudo abrir el archivo como .xlsx ({type(exc).__name__}). "
            f"Los cargadores del §10.6 leen Excel; un .xls antiguo o un CSV "
            f"renombrado no sirve."
        ) from exc


def _celda_segura(valor: object) -> object:
    """Rechaza una celda que llegó como fórmula sin valor cacheado.

    Con `data_only=True` openpyxl devuelve el valor que Excel guardó; si el
    libro se generó sin cachear resultados, lo que queda en la celda es el
    texto de la fórmula. Tomarlo como dato metería ``"=B2*1.16"`` al catálogo.
    """
    if isinstance(valor, str) and valor.startswith("="):
        raise ErrorDeArchivo(
            f"La celda trae una fórmula sin resultado calculado ({valor[:40]!r}). "
            f"Guarda el archivo desde Excel —que cachea los resultados— o pega "
            f"los valores; este cargador no evalúa fórmulas."
        )
    return valor


def filas_de_hoja(
    libro: Workbook, hoja: str | None, *, limites: Limites = LIMITES
) -> Iterator[tuple[int, Sequence[object]]]:
    """Itera ``(numero_de_fila, celdas)`` de la hoja, saltando las vacías.

    El número es el **del archivo** (base 1, el encabezado es la fila 1) para
    que el reporte de errores del §9.3 mande al usuario al renglón exacto.
    """
    if hoja is None:
        pagina = libro.active
        if pagina is None:
            raise ErrorDeArchivo("El libro no tiene ninguna hoja.")
    elif hoja in libro.sheetnames:
        pagina = libro[hoja]
    else:
        raise ErrorDeArchivo(
            f"El libro no trae la hoja {hoja!r} que exige el §10.6. "
            f"Hojas encontradas: {', '.join(libro.sheetnames) or '(ninguna)'}."
        )

    columnas = pagina.max_column or 0
    if columnas > limites.columnas_maximas:
        raise ErrorDeArchivo(
            f"La hoja {pagina.title!r} trae {columnas} columnas y el máximo es "
            f"{limites.columnas_maximas}."
        )

    leidas = 0
    for numero, celdas in enumerate(pagina.iter_rows(values_only=True), start=1):
        leidas += 1
        if leidas > limites.filas_maximas:
            raise ErrorDeArchivo(
                f"La hoja {pagina.title!r} excede las {limites.filas_maximas} "
                f"filas permitidas por carga. Pártela en varios archivos: las "
                f"cargas son multi-archivo (§10.2)."
            )
        if len(celdas) > limites.columnas_maximas:
            raise ErrorDeArchivo(
                f"La fila {numero} trae {len(celdas)} columnas y el máximo es "
                f"{limites.columnas_maximas}."
            )
        if all(c is None or (isinstance(c, str) and not c.strip()) for c in celdas):
            # Las filas vacías del final son normales en un .xlsx y no son un
            # error de datos: no cuentan ni como fila leída ni como error.
            continue
        yield numero, [_celda_segura(c) for c in celdas]
