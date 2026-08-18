"""Pipeline de carga: archivo → mapeo → validación → reporte (§9.2).

Spec §9.2 (`Archivo → Mapeo de columnas → Validación → Previsualización →
Commit + versión → Reporte`) · §9.3 (reporte de errores por fila/columna) ·
§10.2 (dedup por clave) · §12.11 (el borde parsea; el dominio valida).

Este módulo hace los dos primeros pasos y delega el tercero: recorre la hoja,
resuelve las columnas contra el contrato del §10.6 y llama al validador de
dominio **fila por fila**. Una fila mala se anota y la lectura sigue — es la
garantía del §9.3, y por eso el `try/except` está dentro del bucle y no
alrededor.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from obractrl.adapters.excel.lector import (
    LIMITES,
    ErrorDeArchivo,
    Limites,
    abrir_libro,
    filas_de_hoja,
)
from obractrl.domain.cargadores.cabeceras import (
    EspecificacionArchivo,
    MapaColumnas,
    resolver_encabezados,
)
from obractrl.domain.cargadores.reporte import (
    ErrorDeFila,
    ErrorEnFila,
    LecturaCarga,
    PendientePropuesto,
)

__all__ = [
    "ErrorDeArchivo",
    "RegistroConLlave",
    "leer_filas",
    "leer_filas_crudas",
    "leer_por_nombre",
]


class RegistroConLlave(Protocol):
    """Registro validado que sabe cuál es su identidad (§3.3)."""

    @property
    def llave(self) -> str: ...


def leer_filas_crudas(
    contenido: bytes,
    hoja: str | None,
    *,
    limites: Limites = LIMITES,
) -> list[tuple[int, Sequence[object]]]:
    """Todas las filas no vacías de la hoja, **sin** consumir encabezado.

    Lo usa el cargador de CPU, que resuelve sus columnas por posición (§10.6)
    y por tanto no puede dar por hecho que la primera fila sea de títulos:
    tragársela descartaría un concepto real.
    """
    libro = abrir_libro(contenido, limites=limites)
    try:
        return list(filas_de_hoja(libro, hoja, limites=limites))
    finally:
        libro.close()


def leer_filas(
    contenido: bytes,
    especificacion: EspecificacionArchivo,
    *,
    limites: Limites = LIMITES,
) -> tuple[MapaColumnas, list[tuple[int, Sequence[object]]]]:
    """Abre el libro, resuelve encabezados y devuelve las filas de datos.

    La **primera fila no vacía** es el encabezado: el §10.6 describe archivos
    con cabecera, y adivinar dónde empieza el dato con heurísticas sería
    inventar contrato.
    """
    libro = abrir_libro(contenido, limites=limites)
    try:
        iterador = filas_de_hoja(libro, especificacion.hoja, limites=limites)
        primera = next(iterador, None)
        if primera is None:
            raise ErrorDeArchivo(
                f"{especificacion.archivo}: la hoja "
                f"{especificacion.hoja or '(activa)'} no trae ninguna fila."
            )
        mapa = resolver_encabezados(primera[1], especificacion)
        return mapa, list(iterador)
    finally:
        libro.close()


def leer_por_nombre(
    contenido: bytes,
    especificacion: EspecificacionArchivo,
    validar: Callable[[Sequence[object], MapaColumnas, int], RegistroConLlave],
    *,
    limites: Limites = LIMITES,
) -> LecturaCarga:
    """Pipeline completo para un archivo con cabeceras por nombre (§10.6).

    Deduplica por **clave** dentro del archivo: si la misma clave aparece dos
    veces, gana la última y la anterior cuenta como omitida — que es lo que
    significa "deduplica por clave" del modo Actualizar (§10.2).
    """
    mapa, filas = leer_filas(contenido, especificacion, limites=limites)

    registros: dict[str, RegistroConLlave] = {}
    errores: list[ErrorDeFila] = []
    pendientes: list[PendientePropuesto] = []
    omitidos = 0

    for numero, fila in filas:
        try:
            registro = validar(fila, mapa, numero)
        except ErrorEnFila as exc:
            errores.append(exc.con_fila(numero))
            continue
        if registro.llave in registros:
            omitidos += 1
        registros[registro.llave] = registro

    return LecturaCarga(
        registros=tuple(registros.values()),
        errores=tuple(errores),
        pendientes=tuple(pendientes),
        filas_leidas=len(filas),
        omitidos=omitidos,
    )
