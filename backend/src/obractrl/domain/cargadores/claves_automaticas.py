"""Clave automática para una fila que no trae identidad (§8.7).

Spec §3.3 (la clave manda) · §8.7 (catálogos base: mínimo clave, descripción,
unidad). Cuando un catálogo base se alimenta de pasada —CPU o el árbol
referenciando una unidad/familia/concepto por descripción, sin clave— no hay
con qué homologar ni con qué dar de alta (§3.3: todo cruce empieza por
clave). En vez de bloquear la fila, se numera sola: prefijo del catálogo +
consecutivo, como el ejemplo que dio el usuario (``FAM-00001``).

Módulo puro (§12.11).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

__all__ = ["generar_clave_automatica"]


def generar_clave_automatica(prefijo: str, existentes: Iterable[str]) -> str:
    """Siguiente clave libre de la forma ``{prefijo}-NNNNN``.

    Busca en ``existentes`` las claves que ya siguen este patrón, toma el
    consecutivo más alto y devuelve el que sigue, con cero a la izquierda a 5
    dígitos. Si ninguna clave existente lo sigue, empieza en ``00001`` — no en
    ``00000``, para que la primera generada ya sea la 1, como se contaría a
    mano.
    """
    patron = re.compile(rf"^{re.escape(prefijo)}-(\d+)$", re.IGNORECASE)
    maximo = 0
    for clave in existentes:
        coincidencia = patron.match(clave)
        if coincidencia:
            maximo = max(maximo, int(coincidencia.group(1)))
    return f"{prefijo}-{maximo + 1:05d}"
