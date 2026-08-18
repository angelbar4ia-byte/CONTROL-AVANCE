"""Plantillas descargables por cargador (§9.3, §11.2 `GET /cargas/plantillas/{tipo}`).

Spec §9.3 ("plantillas descargables — un Excel template por cargador,
alineado al diccionario") · §10.6 (las cabeceras que la plantilla escribe).

La plantilla se genera **desde la misma especificación** que valida la carga
(`domain.cargadores.cabeceras`), no desde una lista paralela: si el contrato
cambia, la plantilla cambia con él y no hay forma de que se desincronicen.
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook

from obractrl.adapters.excel.cargadores import CARGADORES, TipoDeCargaSinCargador
from obractrl.domain.cargadores import cabeceras
from obractrl.domain.shared.diccionario import TipoCarga

__all__ = ["nombre_de_plantilla", "plantilla_de"]

_ETIQUETAS_CPU: dict[str, str] = {
    "clave": "CLAVE",
    "clave_insumo": "CLAVE INSUMO",
    "descripcion": "DESCRIPCION",
    "unidad": "UNIDAD",
    "cantidad": "CANTIDAD",
    "precio_unitario": "P.U.",
    "familia": "FAMILIA",
    "tipo": "TIPO",
}
"""Rótulos del archivo de CPU. El §10.6 fija sus columnas por **letra**, así
que la plantilla las coloca en su letra y solo pone un título legible encima."""


def nombre_de_plantilla(tipo: TipoCarga) -> str:
    """Nombre del archivo tal como lo cita el §10.6."""
    return _especificacion(tipo).archivo


def _especificacion(tipo: TipoCarga) -> cabeceras.EspecificacionArchivo:
    clase = CARGADORES.get(tipo)
    if clase is None:
        raise TipoDeCargaSinCargador(
            f"El tipo de carga {tipo!r} todavía no tiene cargador ni plantilla "
            f"(§10.6)."
        )
    return clase.especificacion


def plantilla_de(tipo: TipoCarga) -> bytes:
    """`.xlsx` vacío con las cabeceras del §10.6 del cargador pedido."""
    especificacion = _especificacion(tipo)
    libro = Workbook()
    hoja = libro.active
    assert hoja is not None  # noqa: S101 — Workbook() siempre crea una hoja
    hoja.title = especificacion.hoja or "Datos"

    if tipo is TipoCarga.CATALOGO_CONCEPTOS:
        # Posicional: cada rótulo va en su letra, incluida la G que el §10.6
        # no usa y que por eso queda en blanco.
        for columna in cabeceras.COLUMNAS_CPU:
            hoja.cell(row=1, column=columna.indice + 1, value=_ETIQUETAS_CPU[columna.campo])
    else:
        titulos = _titulos(especificacion)
        for posicion, titulo in enumerate(titulos, start=1):
            hoja.cell(row=1, column=posicion, value=titulo)

    memoria = BytesIO()
    libro.save(memoria)
    libro.close()
    return memoria.getvalue()


def _titulos(especificacion: cabeceras.EspecificacionArchivo) -> list[str]:
    """Cabecera literal por campo canónico, obligatorias primero.

    Se prefiere el alias propio del archivo (§10.6: ``# Parte``, ``Efecto
    Qty``) sobre el nombre canónico, para que la plantilla se vea como el
    archivo real que el usuario ya conoce.
    """
    literal: dict[str, str] = {}
    for alias, campo in especificacion.alias.items():
        literal.setdefault(campo, alias)
    return [
        literal.get(campo, campo)
        for campo in (*especificacion.obligatorias, *especificacion.opcionales)
    ]
