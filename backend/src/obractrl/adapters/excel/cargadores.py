"""Cargadores concretos del §10.6.

Spec §10.6 (cabeceras canónicas: el contrato) · §9.1 (inventario de
cargadores) · §12.11 (`adapters/excel`: cargadores por archivo).

Cada clase implementa el puerto `LectorDeCarga`
(`application.puertos.cargadores`) y no hace más que atar un archivo del
§10.6 con su especificación de columnas y su validador de dominio. Toda la
regla vive en `domain.cargadores`; aquí solo se recorre el `.xlsx`.

Los cargadores del §10.6 que **no** están implementados —mano de obra,
subcontratos, obras/lotes, contratistas, niveles, etapas, presupuesto
jerárquico y estimaciones— no tienen entrada en `CARGADORES`: pedir uno de
esos tipos falla explícito en vez de cargar cualquier cosa.
"""

from __future__ import annotations

from obractrl.adapters.excel.lector import LIMITES, Limites
from obractrl.adapters.excel.pipeline import leer_filas_crudas, leer_por_nombre
from obractrl.domain.cargadores import cabeceras
from obractrl.domain.cargadores.almacen import validar_movimiento
from obractrl.domain.cargadores.cpu import agrupar_conceptos
from obractrl.domain.cargadores.materiales import validar_material
from obractrl.domain.cargadores.prototipos import validar_prototipo
from obractrl.domain.cargadores.reporte import LecturaCarga
from obractrl.domain.shared.diccionario import TipoCarga
from obractrl.domain.shared.normalizacion import canonizar_encabezado

__all__ = [
    "CARGADORES",
    "CargadorAlmacen",
    "CargadorCPU",
    "CargadorMateriales",
    "CargadorPrototipos",
    "TipoDeCargaSinCargador",
    "cargador_para",
]


class TipoDeCargaSinCargador(LookupError):
    """El tipo de carga existe en el §8.2 pero aún no tiene cargador escrito."""


class CargadorMateriales:
    """Catálogo de materiales — `CABECERAS_MATERIALES.xlsx` (§10.6)."""

    tipo = TipoCarga.MATERIALES
    especificacion = cabeceras.MATERIALES

    def __init__(self, *, limites: Limites = LIMITES) -> None:
        self._limites = limites

    def leer(self, contenido: bytes) -> LecturaCarga:
        return leer_por_nombre(
            contenido,
            self.especificacion,
            validar_material,
            limites=self._limites,
        )


class CargadorAlmacen:
    """Movimientos de almacén — `IMPORTAADOR_ALMACEN.xlsx`, hoja `Consulta` (§10.6)."""

    tipo = TipoCarga.ALMACEN
    especificacion = cabeceras.ALMACEN

    def __init__(self, *, limites: Limites = LIMITES) -> None:
        self._limites = limites

    def leer(self, contenido: bytes) -> LecturaCarga:
        return leer_por_nombre(
            contenido,
            self.especificacion,
            validar_movimiento,
            limites=self._limites,
        )


class CargadorCPU:
    """CPU / Conceptos — `CABECERAS_CPU.xlsx`, hoja `EXPORTADOR` (§10.6).

    Único cargador **posicional**: el §10.6 fija sus columnas por letra
    (A, B, C, D, E, F, H, I) y no por nombre, así que mapear por encabezado
    sería suponer un contrato que el spec no da.
    """

    tipo = TipoCarga.CATALOGO_CONCEPTOS
    especificacion = cabeceras.CPU

    def __init__(self, *, limites: Limites = LIMITES) -> None:
        self._limites = limites

    def leer(self, contenido: bytes) -> LecturaCarga:
        # Se leen **todas** las filas: aquí no hay encabezado que consumir
        # —las columnas van por letra—, y descartar la primera a ciegas se
        # comería un concepto real si el archivo no trae fila de títulos.
        crudas = leer_filas_crudas(
            contenido, self.especificacion.hoja, limites=self._limites
        )
        filas = [
            (numero, fila)
            for numero, fila in crudas
            if not _es_fila_de_encabezados(fila)
        ]
        conceptos, errores, pendientes, omitidos = agrupar_conceptos(
            filas, cabeceras.MAPA_CPU
        )
        return LecturaCarga(
            registros=tuple(conceptos),
            errores=errores,
            pendientes=pendientes,
            filas_leidas=len(filas),
            omitidos=omitidos,
        )


class CargadorPrototipos:
    """Prototipos — `CABECERAS_PROTOTIPOS.xlsx` (extensión propia, §7.2)."""

    tipo = TipoCarga.PROTOTIPOS
    especificacion = cabeceras.PROTOTIPOS

    def __init__(self, *, limites: Limites = LIMITES) -> None:
        self._limites = limites

    def leer(self, contenido: bytes) -> LecturaCarga:
        return leer_por_nombre(
            contenido,
            self.especificacion,
            validar_prototipo,
            limites=self._limites,
        )


def _es_fila_de_encabezados(fila: object) -> bool:
    """¿Esta fila es la de títulos y no un dato?

    Se decide por el contenido de la columna I: si dice literalmente ``TIPO``
    es el rótulo de la columna; si dice ``Concepto``/``Material``/… es dato.
    No se salta "la fila 1" a ciegas —el §10.6 no promete que exista— ni se
    descarta una fila por parecer rara: una fila con TIPO desconocido va a la
    bandeja (§10.3), no a la basura.
    """
    if not isinstance(fila, list | tuple):
        return False
    celda = cabeceras.MAPA_CPU.valor(fila, "tipo")
    return canonizar_encabezado(celda) == "tipo"


CARGADORES: dict[TipoCarga, type] = {
    TipoCarga.MATERIALES: CargadorMateriales,
    TipoCarga.CATALOGO_CONCEPTOS: CargadorCPU,
    TipoCarga.ALMACEN: CargadorAlmacen,
    TipoCarga.PROTOTIPOS: CargadorPrototipos,
}
"""Tipos del §8.2 que hoy tienen cargador. Los demás no se inventan."""


def cargador_para(tipo: TipoCarga, *, limites: Limites = LIMITES):
    """Cargador del tipo pedido, o :class:`TipoDeCargaSinCargador`."""
    clase = CARGADORES.get(tipo)
    if clase is None:
        raise TipoDeCargaSinCargador(
            f"El tipo de carga {tipo!r} todavía no tiene cargador. Implementados: "
            f"{', '.join(sorted(str(t) for t in CARGADORES))} (§10.6)."
        )
    return clase(limites=limites)
