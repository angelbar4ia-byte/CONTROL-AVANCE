"""Cargadores concretos del §10.6.

Spec §10.6 (cabeceras canónicas: el contrato) · §9.1 (inventario de
cargadores) · §12.11 (`adapters/excel`: cargadores por archivo).

Cada clase implementa el puerto `LectorDeCarga`
(`application.puertos.cargadores`) y no hace más que atar un archivo del
§10.6 con su especificación de columnas y su validador de dominio. Toda la
regla vive en `domain.cargadores`; aquí solo se recorre el `.xlsx`.

Los cargadores del §10.6 que **no** están implementados —obras/lotes,
contratistas y estimaciones— no tienen entrada en `CARGADORES`: pedir uno
de esos tipos falla explícito en vez de cargar cualquier cosa.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial

from obractrl.adapters.excel.lector import LIMITES, ErrorDeArchivo, Limites
from obractrl.adapters.excel.pipeline import (
    leer_filas,
    leer_filas_crudas,
    leer_por_nombre,
)
from obractrl.domain.cargadores import cabeceras
from obractrl.domain.cargadores.almacen import validar_movimiento
from obractrl.domain.cargadores.cabeceras import ErrorDeCabecera, resolver_encabezados
from obractrl.domain.cargadores.conceptos_base import validar_concepto_base
from obractrl.domain.cargadores.cpu import agrupar_conceptos
from obractrl.domain.cargadores.cuadrillas import agrupar_cuadrillas
from obractrl.domain.cargadores.etapas_constructivas import validar_etapa_constructiva
from obractrl.domain.cargadores.mano_de_obra import validar_mano_obra
from obractrl.domain.cargadores.materiales import validar_material
from obractrl.domain.cargadores.niveles import validar_nivel
from obractrl.domain.cargadores.presupuesto import construir_arboles
from obractrl.domain.cargadores.prototipos import validar_prototipo
from obractrl.domain.cargadores.reporte import ErrorEnFila, LecturaCarga
from obractrl.domain.shared.diccionario import TipoCarga, TipoInsumo
from obractrl.domain.shared.normalizacion import canonizar_encabezado

__all__ = [
    "CARGADORES",
    "CargadorAlmacen",
    "CargadorCPU",
    "CargadorConceptosAuxiliares",
    "CargadorConceptosBase",
    "CargadorCuadrillas",
    "CargadorEtapasConstructivas",
    "CargadorManoObra",
    "CargadorMateriales",
    "CargadorNiveles",
    "CargadorPresupuesto",
    "CargadorPrototipos",
    "CargadorSubcontratos",
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


class CargadorManoObra:
    """Mano de obra / destajos — `CABECERAS_MANO_DE_OBRA.xlsx`, hoja
    `DESTAJOS` (§10.6)."""

    tipo = TipoCarga.MANO_DE_OBRA
    especificacion = cabeceras.MANO_DE_OBRA

    def __init__(self, *, limites: Limites = LIMITES) -> None:
        self._limites = limites

    def leer(self, contenido: bytes) -> LecturaCarga:
        return leer_por_nombre(
            contenido,
            self.especificacion,
            validar_mano_obra,
            limites=self._limites,
        )


class CargadorSubcontratos:
    """Subcontratos — `catalogo_de_SUBCONTRATOS.xlsx` (§10.6).

    Mismas cabeceras que `CABECERAS_MANO_DE_OBRA.xlsx` pero su propia hoja
    (`cabeceras.SUBCONTRATOS`, §10.6): reusa el mismo validador, fijando
    ``tipo=SUBCONTRATO`` vía `functools.partial` en vez de duplicarlo.
    """

    tipo = TipoCarga.SUBCONTRATOS
    especificacion = cabeceras.SUBCONTRATOS

    def __init__(self, *, limites: Limites = LIMITES) -> None:
        self._limites = limites

    def leer(self, contenido: bytes) -> LecturaCarga:
        return leer_por_nombre(
            contenido,
            self.especificacion,
            partial(validar_mano_obra, tipo=TipoInsumo.SUBCONTRATO),
            limites=self._limites,
        )


class CargadorCuadrillas:
    """Composición y PU de cuadrillas — `CABECERAS_CUADRILLAS.xlsx` (§10.6).

    Headers por nombre, no posicional (a diferencia de `CargadorCPU`): el
    archivo real no fija columnas por letra. Usa `leer_filas` +
    `agrupar_cuadrillas` en vez de `leer_por_nombre`: cada fila ya trae la
    llave del bloque (`Clave cuadrilla`), así que agrupar es cosa del
    dominio, no de un validador fila por fila.
    """

    tipo = TipoCarga.CUADRILLAS
    especificacion = cabeceras.CUADRILLAS

    def __init__(self, *, limites: Limites = LIMITES) -> None:
        self._limites = limites

    def leer(self, contenido: bytes) -> LecturaCarga:
        mapa, filas = leer_filas(contenido, self.especificacion, limites=self._limites)
        cuadrillas, errores, omitidos = agrupar_cuadrillas(filas, mapa)
        return LecturaCarga(
            registros=tuple(cuadrillas),
            errores=errores,
            filas_leidas=len(filas),
            omitidos=omitidos,
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


class CargadorConceptosBase:
    """Catálogo base de conceptos — `CABECERAS_CONCEPTOS.xlsx` (§8.7).

    Identidad únicamente: clave, descripción, unidad. La composición del
    concepto (qué lleva y con qué costo) es CPU (`CargadorCPU`, más abajo),
    un cargador y un archivo distintos.
    """

    tipo = TipoCarga.CATALOGO_CONCEPTOS
    especificacion = cabeceras.CONCEPTOS_BASE

    def __init__(self, *, limites: Limites = LIMITES) -> None:
        self._limites = limites

    def leer(self, contenido: bytes) -> LecturaCarga:
        return leer_por_nombre(
            contenido,
            self.especificacion,
            validar_concepto_base,
            limites=self._limites,
        )


class CargadorConceptosAuxiliares:
    """Catálogo base de conceptos auxiliares —
    `CABECERAS_CONCEPTOS_AUXILIARES.xlsx` (§8.7, §7.3).

    Mismo validador que `CargadorConceptosBase`: un concepto auxiliar es un
    `concepto` más, solo que `AplicadorConceptosBase` lo da de alta con
    `tipo=auxiliar` en vez de `tipo=concepto` (ver `casos_uso.py`).
    """

    tipo = TipoCarga.CONCEPTOS_AUXILIARES
    especificacion = cabeceras.CONCEPTOS_AUXILIARES

    def __init__(self, *, limites: Limites = LIMITES) -> None:
        self._limites = limites

    def leer(self, contenido: bytes) -> LecturaCarga:
        return leer_por_nombre(
            contenido,
            self.especificacion,
            validar_concepto_base,
            limites=self._limites,
        )


class CargadorNiveles:
    """Catálogo base de niveles de construcción — `CATALOGO_DE_NIVELES.xlsx`
    (§10.1)."""

    tipo = TipoCarga.NIVELES
    especificacion = cabeceras.NIVELES

    def __init__(self, *, limites: Limites = LIMITES) -> None:
        self._limites = limites

    def leer(self, contenido: bytes) -> LecturaCarga:
        return leer_por_nombre(
            contenido,
            self.especificacion,
            validar_nivel,
            limites=self._limites,
        )


class CargadorEtapasConstructivas:
    """Catálogo base de etapas de construcción —
    `CATALOGO_DE_ETAPAS_DE_CONSTRUCCION.xlsx` (§10.1)."""

    tipo = TipoCarga.ETAPAS_CONSTRUCTIVAS
    especificacion = cabeceras.ETAPAS_CONSTRUCTIVAS

    def __init__(self, *, limites: Limites = LIMITES) -> None:
        self._limites = limites

    def leer(self, contenido: bytes) -> LecturaCarga:
        return leer_por_nombre(
            contenido,
            self.especificacion,
            validar_etapa_constructiva,
            limites=self._limites,
        )


class CargadorCPU:
    """CPU / Conceptos — `CABECERAS_CPU.xlsx`, hoja `EXPORTADOR` (§10.6).

    Único cargador **posicional**: el §10.6 fija sus columnas por letra
    (A, B, C, D, E, F, H, I) y no por nombre, así que mapear por encabezado
    sería suponer un contrato que el spec no da.
    """

    tipo = TipoCarga.CPU
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
    TipoCarga.MANO_DE_OBRA: CargadorManoObra,
    TipoCarga.SUBCONTRATOS: CargadorSubcontratos,
    TipoCarga.CUADRILLAS: CargadorCuadrillas,
    TipoCarga.CATALOGO_CONCEPTOS: CargadorConceptosBase,
    TipoCarga.CONCEPTOS_AUXILIARES: CargadorConceptosAuxiliares,
    TipoCarga.NIVELES: CargadorNiveles,
    TipoCarga.ETAPAS_CONSTRUCTIVAS: CargadorEtapasConstructivas,
    TipoCarga.CPU: CargadorCPU,
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
