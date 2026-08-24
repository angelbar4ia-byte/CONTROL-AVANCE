"""Cargadores concretos del §10.6.

Spec §10.6 (cabeceras canónicas: el contrato) · §9.1 (inventario de
cargadores) · §12.11 (`adapters/excel`: cargadores por archivo).

Cada clase implementa el puerto `LectorDeCarga`
(`application.puertos.cargadores`) y no hace más que atar un archivo del
§10.6 con su especificación de columnas y su validador de dominio. Toda la
regla vive en `domain.cargadores`; aquí solo se recorre el `.xlsx`.

Los cargadores del §10.6 que **no** están implementados —mano de obra,
subcontratos, obras/lotes, contratistas, niveles, etapas y estimaciones— no
tienen entrada en `CARGADORES`: pedir uno de esos tipos falla explícito en
vez de cargar cualquier cosa.
"""

from __future__ import annotations

from collections.abc import Sequence

from obractrl.adapters.excel.lector import LIMITES, ErrorDeArchivo, Limites
from obractrl.adapters.excel.pipeline import (
    leer_filas,
    leer_filas_crudas,
    leer_por_nombre,
)
from obractrl.domain.cargadores import cabeceras
from obractrl.domain.cargadores.almacen import validar_movimiento
from obractrl.domain.cargadores.cabeceras import ErrorDeCabecera, resolver_encabezados
from obractrl.domain.cargadores.cpu import agrupar_conceptos
from obractrl.domain.cargadores.materiales import validar_material
from obractrl.domain.cargadores.presupuesto import construir_arboles
from obractrl.domain.cargadores.prototipos import validar_prototipo
from obractrl.domain.cargadores.reporte import ErrorEnFila, LecturaCarga
from obractrl.domain.shared.diccionario import TipoCarga
from obractrl.domain.shared.normalizacion import canonizar_encabezado

__all__ = [
    "CARGADORES",
    "CargadorAlmacen",
    "CargadorCPU",
    "CargadorMateriales",
    "CargadorPresupuesto",
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
    """Prototipos, en cualquiera de sus **dos formatos** (extensión propia).

    Los dos alimentan lo mismo —el catálogo de prototipos— y por eso son un
    solo tipo de carga en la pantalla, no dos que el usuario tenga que
    distinguir de memoria:

    - **Alta plana** (`CABECERAS_PROTOTIPOS.xlsx`): una fila por prototipo,
      con su proyecto. Da de alta el encabezado (§7.2).
    - **Ingeniería por prototipo** (`CABECERAS_PRESUPUESTO.xlsx`): el árbol
      nivel → etapa → concepto con su APU, que además arma el presupuesto
      del prototipo (§7.4).

    Cuál es cuál lo dice el **archivo**, no el usuario: se resuelven sus
    encabezados contra cada contrato y gana el que cumple. No hay ambigüedad
    posible — el árbol exige `CLAVE HIJO`/`TIPO`, que el plano no trae, y el
    plano exige `Proyecto`/`Nombre`, que el árbol no trae.
    """

    tipo = TipoCarga.PROTOTIPOS
    especificacion = cabeceras.PROTOTIPOS

    def __init__(self, *, limites: Limites = LIMITES) -> None:
        self._limites = limites

    def leer(self, contenido: bytes) -> LecturaCarga:
        crudas = leer_filas_crudas(contenido, None, limites=self._limites)
        if not crudas:
            raise ErrorDeArchivo(
                f"{self.especificacion.archivo}: la hoja no trae ninguna fila."
            )

        (_, encabezados), *filas = crudas
        try:
            mapa_arbol = resolver_encabezados(encabezados, cabeceras.PRESUPUESTO)
        except ErrorDeCabecera:
            # No es el árbol: se exige el contrato plano, y si tampoco
            # cumple, su `ErrorDeCabecera` es el que sube — es el formato
            # que el usuario quiso subir si no traía las columnas del árbol.
            return self._leer_plano(encabezados, filas)

        arboles, errores, pendientes, omitidos = construir_arboles(filas, mapa_arbol)
        return LecturaCarga(
            registros=tuple(arboles),
            errores=errores,
            pendientes=pendientes,
            filas_leidas=len(filas),
            omitidos=omitidos,
        )

    def _leer_plano(
        self, encabezados: Sequence[object], filas: list[tuple[int, Sequence[object]]]
    ) -> LecturaCarga:
        """El pipeline de `leer_por_nombre`, pero sobre filas ya leídas.

        No se puede llamar a `leer_por_nombre` aquí: volvería a abrir el
        libro para re-leer lo que ya está en memoria, y el `.xlsx` real
        pesa miles de filas.
        """
        mapa = resolver_encabezados(encabezados, self.especificacion)
        registros: dict[str, object] = {}
        errores = []
        omitidos = 0

        for numero, fila in filas:
            try:
                registro = validar_prototipo(fila, mapa, numero)
            except ErrorEnFila as exc:
                errores.append(exc.con_fila(numero))
                continue
            if registro.llave in registros:
                omitidos += 1
            registros[registro.llave] = registro

        return LecturaCarga(
            registros=tuple(registros.values()),
            errores=tuple(errores),
            filas_leidas=len(filas),
            omitidos=omitidos,
        )


class CargadorPresupuesto:
    """Presupuesto jerárquico — `CABECERAS_PRESUPUESTO.xlsx` (extensión
    propia). Árbol de un prototipo (nivel → etapa → concepto) por
    `CLAVE PADRE → CLAVE HIJO` entre filas consecutivas — no una tabla plana
    ni bloques de un nivel, así que usa `construir_arboles` en vez de
    `leer_por_nombre`/`agrupar_conceptos`."""

    tipo = TipoCarga.PRESUPUESTO
    especificacion = cabeceras.PRESUPUESTO

    def __init__(self, *, limites: Limites = LIMITES) -> None:
        self._limites = limites

    def leer(self, contenido: bytes) -> LecturaCarga:
        mapa, filas = leer_filas(contenido, self.especificacion, limites=self._limites)
        arboles, errores, pendientes, omitidos = construir_arboles(filas, mapa)
        return LecturaCarga(
            registros=tuple(arboles),
            errores=errores,
            pendientes=pendientes,
            filas_leidas=len(filas),
            omitidos=omitidos,
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
    TipoCarga.PRESUPUESTO: CargadorPresupuesto,
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
