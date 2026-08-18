"""Diff entre el archivo y lo vigente — versionado y reversa (§10.8).

Spec §10.8 (cada carga es una versión; si es idéntico, no crea versión) ·
§10.2 (los tres modos) · §12.3 (idempotencia por clave) · §3.3 (la CLAVE
manda).

El §10.8 lo dice con un ejemplo: se carga `materiales.xlsx` → v1; se sube
otro `materiales.xlsx`, el sistema detecta que **3 precios cambiaron y 2
claves son nuevas** → v2 con ese diff; v1 queda en el historial. Y si el
archivo no cambia nada, **no se crea versión**.

Este módulo calcula exactamente ese diff, sobre diccionarios: quién lo llene
—el repositorio con lo vigente, el cargador con lo entrante— es problema del
caso de uso. Módulo puro (§12.11).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.shared.diccionario import ModoCarga

__all__ = ["Cambio", "Diff", "comparable", "diferenciar"]


def comparable(valores: Mapping[str, object]) -> dict[str, str]:
    """Forma canónica de un registro para compararlo con otro.

    Sin esto el diff mentiría: ``Decimal('250.00')`` y ``Decimal('250')`` son
    el mismo precio pero distintos objetos, y una carga idéntica generaría
    versión nueva —justo lo que el §10.8 prohíbe.
    """
    normalizado: dict[str, str] = {}
    for campo, valor in valores.items():
        if valor is None:
            normalizado[campo] = ""
        elif isinstance(valor, Decimal):
            # `normalize()` iguala 250.00 y 250; el `+ 0` deshace la notación
            # exponencial que `normalize` produce para enteros grandes.
            normalizado[campo] = str(valor.normalize() + Decimal(0))
        elif isinstance(valor, bool):
            normalizado[campo] = "si" if valor else "no"
        else:
            normalizado[campo] = str(valor)
    return normalizado


@dataclass(frozen=True, slots=True)
class Cambio:
    """Un registro que la carga toca, con su estado antes y después (§10.8)."""

    clave: str
    despues: Mapping[str, object]
    antes: Mapping[str, object] | None = None

    @property
    def campos_cambiados(self) -> tuple[str, ...]:
        """Qué cambió exactamente — el "diff" que el §10.8 manda guardar."""
        if self.antes is None:
            return tuple(sorted(self.despues))
        viejo = comparable(self.antes)
        nuevo = comparable(self.despues)
        return tuple(
            sorted(campo for campo, valor in nuevo.items() if viejo.get(campo) != valor)
        )


@dataclass(frozen=True, slots=True)
class Diff:
    """Resultado de comparar el archivo contra la versión vigente (§10.8)."""

    altas: tuple[Cambio, ...] = ()
    cambios: tuple[Cambio, ...] = ()
    bajas: tuple[Cambio, ...] = ()
    sin_cambio: tuple[str, ...] = ()

    @property
    def hay_cambios(self) -> bool:
        """Si es ``False`` **no se crea versión**: es idéntico (§10.8, §12.3)."""
        return bool(self.altas or self.cambios or self.bajas)

    @property
    def omitidos(self) -> int:
        """Registros que la carga dejó tal cual estaban."""
        return len(self.sin_cambio)

    def como_dict(self) -> dict[str, object]:
        """Diff serializable para `carga_datos.resumen` (§9.4)."""
        return {
            "altas": [c.clave for c in self.altas],
            "cambios": {c.clave: list(c.campos_cambiados) for c in self.cambios},
            "bajas": [c.clave for c in self.bajas],
            "sin_cambio": len(self.sin_cambio),
        }


def diferenciar(
    *,
    vigentes: Mapping[str, Mapping[str, object]],
    entrantes: Mapping[str, Mapping[str, object]],
    modo: ModoCarga = ModoCarga.ACTUALIZAR,
) -> Diff:
    """Compara lo entrante contra lo vigente según el modo del §10.2.

    - **Actualizar** (default) — deduplica por clave, actualiza existentes,
      agrega nuevos. No borra nada.
    - **Acumular** — solo agrega nuevos, sin tocar lo actual: lo que ya existe
      cuenta como omitido aunque el archivo traiga otro valor.
    - **Reemplazar** — sustituye todo el conjunto: lo que no viene en el
      archivo se da de baja.

    Ambos lados se indexan por **clave** (§3.3): es lo que hace la carga
    idempotente (§12.3).
    """
    altas: list[Cambio] = []
    cambios: list[Cambio] = []
    bajas: list[Cambio] = []
    sin_cambio: list[str] = []

    for clave, nuevo in entrantes.items():
        viejo = vigentes.get(clave)
        if viejo is None:
            altas.append(Cambio(clave=clave, despues=nuevo))
            continue
        if modo is ModoCarga.ACUMULAR:
            sin_cambio.append(clave)
            continue
        if comparable(viejo) == comparable(nuevo):
            sin_cambio.append(clave)
            continue
        cambios.append(Cambio(clave=clave, despues=nuevo, antes=viejo))

    if modo is ModoCarga.REEMPLAZAR:
        for clave, viejo in vigentes.items():
            if clave not in entrantes:
                bajas.append(Cambio(clave=clave, despues={}, antes=viejo))

    return Diff(
        altas=tuple(altas),
        cambios=tuple(cambios),
        bajas=tuple(bajas),
        sin_cambio=tuple(sin_cambio),
    )
