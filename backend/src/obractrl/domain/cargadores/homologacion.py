"""Homologación: alias del archivo → registro oficial del catálogo (§10.3).

Spec §10.3 (mapeos y homologaciones) · §3.3 (prioridad de CLAVE) · §3.4
(jerarquía de fuentes: el catálogo es la fuente de verdad) · §10.1 (los
catálogos traen alias a homologar).

El orden de resolución no es arbitrario, es el §3.3 y el §3.4 juntos:

1. **CLAVE** — "todo análisis, mapeo, homologación y cruce prioriza la
   comparación por CLAVE".
2. **Mapeo confirmado** (`mapeo`, §10.3) — un humano ya dijo que ese alias es
   ese registro; vale más que un parecido de texto, pero no más que la clave.
3. **Sinónimo del catálogo** — los que trae `unidad.sinonimos` (§3.5:
   ``pza→PZ``).
4. **Descripción** — solo desempata, y solo si es **única**: dos registros con
   la misma descripción no resuelven a ninguno. Adivinar ahí es exactamente
   lo que el §3.3 evita.

Módulo puro (§12.11).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from obractrl.domain.shared.normalizacion import normalizar

__all__ = ["Homologador"]

_AMBIGUO = object()
"""Marca interna: ese texto apunta a más de un registro y por tanto a ninguno."""


@dataclass(slots=True)
class Homologador:
    """Índice de un catálogo para cruzar contra lo que trae un archivo."""

    por_clave: dict[str, str] = field(default_factory=dict)
    por_alias: dict[str, str] = field(default_factory=dict)
    por_sinonimo: dict[str, object] = field(default_factory=dict)
    por_descripcion: dict[str, object] = field(default_factory=dict)

    @classmethod
    def desde(
        cls,
        registros: Iterable[Mapping[str, object]],
        *,
        campos_descripcion: Sequence[str] = ("descripcion", "nombre", "razon_social"),
        campo_sinonimos: str = "sinonimos",
        mapeos: Mapping[str, str] | None = None,
    ) -> Homologador:
        """Arma el índice desde las filas del catálogo y los mapeos confirmados."""
        homologador = cls()

        for registro in registros:
            clave = str(registro.get("clave") or "").strip()
            if not clave:
                continue
            homologador.por_clave[normalizar(clave)] = clave

            for sinonimo in registro.get(campo_sinonimos) or ():
                _indexar(homologador.por_sinonimo, normalizar(sinonimo), clave)

            for campo in campos_descripcion:
                texto = registro.get(campo)
                if texto:
                    _indexar(homologador.por_descripcion, normalizar(texto), clave)

        for alias, canonica in (mapeos or {}).items():
            homologador.por_alias[normalizar(alias)] = str(canonica)

        return homologador

    def resolver(self, valor: object) -> str | None:
        """Clave canónica del registro que corresponde a ``valor``, o ``None``.

        ``None`` significa "no lo sé": el caso de uso lo manda a la bandeja
        (§10.3) en vez de inventar un cruce.
        """
        llave = normalizar(valor)
        if not llave:
            return None

        directo = self.por_clave.get(llave)
        if directo is not None:
            return directo

        confirmado = self.por_alias.get(llave)
        if confirmado is not None:
            return confirmado

        for indice in (self.por_sinonimo, self.por_descripcion):
            candidato = indice.get(llave)
            if candidato is _AMBIGUO or candidato is None:
                continue
            return str(candidato)

        return None


def _indexar(indice: dict[str, object], llave: str, clave: str) -> None:
    """Guarda ``llave → clave``, marcando como ambiguo si ya apuntaba a otra."""
    if not llave:
        return
    existente = indice.get(llave)
    if existente is None:
        indice[llave] = clave
    elif existente != clave:
        indice[llave] = _AMBIGUO
