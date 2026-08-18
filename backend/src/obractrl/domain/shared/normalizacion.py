"""Normalización de encabezados y valores externos.

Spec §8.6 (mapa de sinónimos) · §3.3 (prioridad de CLAVE) · §3.4 (jerarquía de
fuentes) · §9.2 (mapeo de columnas → campos canónicos).

Los archivos externos escriben lo mismo de mil maneras: ``Descripción``,
``DESCRIPCION``, ``  Descripcion ``. Este módulo colapsa esas variantes a una
forma única **antes** de compararlas contra el mapa de sinónimos del §8.6, y
convierte los valores de celda a los tipos del dominio con errores legibles.

Es el complemento de `diccionario.ALIAS_ENCABEZADOS`, cuyas llaves ya están
guardadas en esta misma forma normalizada.

Módulo puro: sin FastAPI, SQLModel, pandas ni openpyxl (§12.11). Recibe
valores ya leídos por el adaptador; no sabe de dónde salieron.
"""

from __future__ import annotations

import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from obractrl.domain.shared.diccionario import ALIAS_ENCABEZADOS

__all__ = [
    "ValorNoConvertible",
    "a_booleano",
    "a_decimal",
    "a_entero",
    "a_fecha",
    "canonizar_encabezado",
    "esta_vacio",
    "normalizar",
    "texto_limpio",
]


class ValorNoConvertible(ValueError):
    """Una celda no se puede leer como el tipo que el campo canónico exige.

    La levanta el validador de fila, no el lector: el lector solo trae la
    celda tal cual (§12.11). Quien la atrapa la convierte en un renglón del
    reporte de errores por fila/columna (§9.3), sin abortar el archivo.
    """


def normalizar(valor: object) -> str:
    """Forma comparable de un texto: minúsculas, sin acentos, sin dobles espacios.

    **No** quita puntuación: las llaves del §8.6 la conservan (``p.u.``,
    ``no.``, ``# parte``) y quitarla haría chocar alias distintos.
    """
    if valor is None:
        return ""
    crudo = " ".join(str(valor).split()).lower()
    # NFKD separa la tilde de su letra; descartar los diacríticos deja
    # "descripción" y "descripcion" en la misma cadena.
    descompuesto = unicodedata.normalize("NFKD", crudo)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def canonizar_encabezado(
    encabezado: object, alias: dict[str, str] | None = None
) -> str | None:
    """Encabezado externo → nombre canónico del §8.6, o ``None`` si no mapea.

    ``alias`` permite a un cargador concreto extender el mapa global con las
    cabeceras literales de **su** archivo (§10.6) sin ensuciar el diccionario
    compartido; lo propio del archivo gana sobre el mapa global.

    >>> canonizar_encabezado("  Descripción ")
    'descripcion'
    >>> canonizar_encabezado("P.U.")
    'precio_unitario'
    >>> canonizar_encabezado("Columna rara")
    """
    llave = normalizar(encabezado)
    if not llave:
        return None
    if alias and llave in alias:
        return alias[llave]
    return ALIAS_ENCABEZADOS.get(llave)


def esta_vacio(valor: object) -> bool:
    """Celda sin dato: ``None`` o solo espacios."""
    return valor is None or (isinstance(valor, str) and not valor.strip())


def texto_limpio(valor: object) -> str:
    """Texto con espacios internos colapsados, conservando mayúsculas/acentos."""
    if valor is None:
        return ""
    return " ".join(str(valor).split())


def a_decimal(valor: object, *, campo: str) -> Decimal:
    """Celda → `Decimal`, tolerando el formato con el que Excel exporta números.

    Acepta separador de miles, símbolo de moneda, porcentaje y el paréntesis
    contable (``(1,250.00)`` = −1250.00): los tres aparecen en los archivos
    reales del §10.6 cuando la columna quedó formateada como texto.

    Nunca pasa por ``float``: el §3.5 exige importes en DECIMAL y un
    ``float`` intermedio ya perdió precisión.
    """
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, bool):
        raise ValorNoConvertible(f"{campo}: se esperaba un número, no un booleano.")
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        # openpyxl entrega los numéricos como float; `str()` da la forma
        # decimal más corta que reproduce ese float, que es lo que el usuario
        # escribió en la celda.
        return Decimal(str(valor))

    crudo = texto_limpio(valor)
    if not crudo:
        raise ValorNoConvertible(f"{campo}: valor vacío donde se esperaba un número.")

    negativo = crudo.startswith("(") and crudo.endswith(")")
    if negativo:
        crudo = crudo[1:-1]

    limpio = (
        crudo.replace("$", "")
        .replace("%", "")
        .replace(",", "")
        .replace(" ", "")
        .strip()
    )
    try:
        numero = Decimal(limpio)
    except (InvalidOperation, ValueError) as exc:
        raise ValorNoConvertible(
            f"{campo}: {valor!r} no es un número."
        ) from exc
    return -numero if negativo else numero


def a_entero(valor: object, *, campo: str) -> int:
    """Celda → ``int``. Un decimal con parte fraccionaria es un error, no un
    redondeo silencioso."""
    numero = a_decimal(valor, campo=campo)
    if numero != numero.to_integral_value():
        raise ValorNoConvertible(
            f"{campo}: {valor!r} tiene decimales donde se esperaba un entero."
        )
    return int(numero)


_FORMATOS_FECHA = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%y")
"""Formatos aceptados cuando la columna vino como texto.

``%d/%m/%Y`` primero que ``%m/%d/%Y`` —que no está— porque el origen es
mexicano (§3.5, moneda única MXN): interpretar ``03/04/2026`` como abril
sería inventar una fecha.
"""


def a_fecha(valor: object, *, campo: str) -> date:
    """Celda → `date` (§3.1: la fecha es la que clasifica la semana de obra)."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    crudo = texto_limpio(valor)
    if not crudo:
        raise ValorNoConvertible(f"{campo}: valor vacío donde se esperaba una fecha.")
    # Excel a veces deja la hora pegada aunque la celda se vea como fecha.
    solo_fecha = crudo.split(" ")[0]
    for formato in _FORMATOS_FECHA:
        try:
            return datetime.strptime(solo_fecha, formato).date()
        except ValueError:
            continue
    raise ValorNoConvertible(
        f"{campo}: {valor!r} no es una fecha reconocible "
        f"({', '.join(_FORMATOS_FECHA)})."
    )


# Ya normalizados (sin acentos, minúsculas): `normalizar` deja "Sí" en "si".
_VERDADEROS = frozenset({"1", "si", "true", "verdadero", "x", "s"})
_FALSOS = frozenset({"0", "no", "false", "falso", "n", "-"})


def a_booleano(valor: object, *, campo: str) -> bool:
    """Celda → ``bool``. La casilla de IVA del §3.5 llega como ``SI``/``X``/``1``."""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, int | float | Decimal):
        return bool(valor)
    llave = normalizar(valor)
    if llave in _VERDADEROS:
        return True
    if llave in _FALSOS:
        return False
    raise ValorNoConvertible(
        f"{campo}: {valor!r} no es un sí/no reconocible."
    )
