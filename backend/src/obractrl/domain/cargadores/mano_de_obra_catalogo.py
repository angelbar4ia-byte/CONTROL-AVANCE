"""Catálogo de mano de obra de OPUS: validación de fila (D-616).

`CATALOGO_DE_MANO_DE_OBRA.csv`: 97 filas y 36 columnas. 58 puestos (insumos
de mano de obra, MOCA-xxx) y las 39 cuadrillas (columna C = «+»: CUAD-001 y
MOCU-xxx). Ninguna columna se ignora: las 36 se leen aquí.

Módulo puro (§12.11): recibe la fila como celdas y devuelve la entidad
validada o levanta :class:`ErrorEnFila`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from obractrl.domain.cargadores.cabeceras import MapaColumnas
from obractrl.domain.cargadores.reporte import ErrorEnFila
from obractrl.domain.shared.normalizacion import (
    ValorNoConvertible,
    a_booleano,
    a_decimal,
    a_fecha,
    esta_vacio,
    texto_limpio,
)
from obractrl.domain.shared.valores import Clave

__all__ = ["CAMPOS_DE_CALCULO", "FilaManoDeObraOpus", "validar_mano_de_obra_opus"]

CAMPOS_DE_CALCULO: tuple[str, ...] = (
    "costo_unitario",
    "salario_tabulado",
    "salario_nominal_mn",
    "fsr",
    "salario_nominal_me",
    "salario_real",
    "factor_salario_base",
    "sbc",
    "excedente_tres_salarios",
    "aplicacion_imss",
    "cuota_fija",
    "prestaciones_en_especie",
    "prestaciones_en_dinero",
    "invalidez_y_vida",
    "cesantia_en_edad_avanzada",
    "riesgos_de_trabajo",
    "guarderias",
    "sar",
    "suma_prestaciones_imss",
    "factor_cuota_patronal_imss",
    "infonavit",
    "impuesto_sobre_nomina",
    "suma_prestaciones",
    "obligacion_obrero_patronal",
    "factor_de_salario_gravable",
    "salario_gravable",
)
"""Las 26 columnas numéricas del cálculo del salario real, en el orden del
archivo. `costo_unitario` es el costo del puesto (el jornal) o de la
cuadrilla; las demás, el desglose que llega a `salario_real`."""


@dataclass(frozen=True, slots=True)
class FilaManoDeObraOpus:
    """Un puesto o una cuadrilla del catálogo de mano de obra."""

    clave: Clave
    descripcion: str
    es_cuadrilla: bool
    """Columna C = «+»: la fila es una cuadrilla (se abre en sus puestos)."""
    unidad: str | None = None
    familia: str | None = None
    subfamilia: str | None = None
    tipo_opus: str | None = None
    fecha: date | None = None
    utilizar_hoja_fsr: bool = False
    categoria_fsr: str | None = None
    calculo: dict[str, Decimal | None] = field(default_factory=dict)
    fila: int = 0

    @property
    def llave(self) -> str:
        return str(self.clave)


def _decimal(fila: Sequence[object], mapa: MapaColumnas, campo: str) -> Decimal | None:
    celda = mapa.valor(fila, campo)
    if esta_vacio(celda):
        return None
    try:
        return a_decimal(celda, campo=campo)
    except ValorNoConvertible as exc:
        raise ErrorEnFila(str(exc), columna=campo, valor=celda) from exc


def validar_mano_de_obra_opus(
    fila: Sequence[object], mapa: MapaColumnas, numero: int = 0
) -> FilaManoDeObraOpus:
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
        raise ErrorEnFila("descripcion: es obligatoria.", columna="descripcion")

    celda_fecha = mapa.valor(fila, "fecha_costo")
    fecha: date | None = None
    if not esta_vacio(celda_fecha):
        try:
            fecha = a_fecha(celda_fecha, campo="fecha")
        except ValorNoConvertible as exc:
            raise ErrorEnFila(str(exc), columna="fecha", valor=celda_fecha) from exc

    celda_fsr = mapa.valor(fila, "utilizar_hoja_fsr")
    utilizar_hoja_fsr = False
    if not esta_vacio(celda_fsr):
        try:
            utilizar_hoja_fsr = a_booleano(celda_fsr, campo="utilizar_hoja_fsr")
        except ValorNoConvertible as exc:
            raise ErrorEnFila(
                str(exc), columna="utilizar_hoja_fsr", valor=celda_fsr
            ) from exc

    return FilaManoDeObraOpus(
        clave=clave,
        descripcion=descripcion,
        es_cuadrilla=texto_limpio(mapa.valor(fila, "desglosable")) == "+",
        unidad=texto_limpio(mapa.valor(fila, "unidad")) or None,
        familia=texto_limpio(mapa.valor(fila, "familia")) or None,
        subfamilia=texto_limpio(mapa.valor(fila, "subfamilia")) or None,
        tipo_opus=texto_limpio(mapa.valor(fila, "tipo_opus")) or None,
        fecha=fecha,
        utilizar_hoja_fsr=utilizar_hoja_fsr,
        categoria_fsr=texto_limpio(mapa.valor(fila, "categoria_fsr")) or None,
        calculo={campo: _decimal(fila, mapa, campo) for campo in CAMPOS_DE_CALCULO},
        fila=numero,
    )
