"""Reglas de la estructura de proyecto.

Spec §7.2 (Proyecto · Cluster · Prototipo) · §2.1 (glosario) · §3.3 (clave) ·
§11.2 (Proyecto · Obra).

El árbol del §2.1 es **Proyecto → Cluster → Obra**; el **Prototipo** cuelga
del proyecto y es el modelo de vivienda que la obra instancia (§7.4). Aquí
viven las tres entidades de arriba; la Obra tiene su propio módulo
(`domain.obras.reglas`) porque es la unidad mínima de control y arrastra
avance, estatus y el flujo de generación (§11.3 A).

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11). El alcance por rol —quién
ve qué proyecto— **no** se decide aquí: es frontera de la base (§12.4,
`app.proyecto_visible`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from obractrl.domain.shared.valores import Clave

__all__ = [
    "Cluster",
    "ErrorDeProyecto",
    "Prototipo",
    "Proyecto",
]


class ErrorDeProyecto(ValueError):
    """Invariante rota en la estructura de proyecto (§7.2)."""


def _exigir_texto(valor: str, campo: str) -> str:
    limpio = " ".join(str(valor).split())
    if not limpio:
        raise ErrorDeProyecto(f"El campo {campo!r} es obligatorio.")
    return limpio


def _exigir_referencia(valor: str, campo: str) -> str:
    if not str(valor).strip():
        raise ErrorDeProyecto(f"El campo {campo!r} es obligatorio.")
    return str(valor)


def _exigir_positivo(valor: Decimal | None, campo: str) -> Decimal | None:
    if valor is None:
        return None
    if valor <= 0:
        raise ErrorDeProyecto(f"El campo {campo!r} debe ser mayor que cero: {valor}.")
    return valor


@dataclass(slots=True)
class Proyecto:
    """Desarrollo completo: el tope del árbol (§7.2)."""

    clave: Clave
    nombre: str
    ubicacion: str | None = None
    inicio: date | None = None
    fin_estimado: date | None = None
    activo: bool = True

    @classmethod
    def crear(
        cls,
        *,
        clave: str,
        nombre: str,
        ubicacion: str | None = None,
        inicio: date | None = None,
        fin_estimado: date | None = None,
    ) -> Proyecto:
        """Alta de proyecto (§11.2, Control de obra y Super intendente)."""
        try:
            clave_canonica = Clave(clave)
        except ValueError as exc:
            raise ErrorDeProyecto(str(exc)) from exc

        if inicio is not None and fin_estimado is not None and fin_estimado < inicio:
            raise ErrorDeProyecto(
                f"El fin estimado ({fin_estimado}) no puede ser anterior al "
                f"inicio ({inicio})."
            )

        return cls(
            clave=clave_canonica,
            nombre=_exigir_texto(nombre, "nombre"),
            ubicacion=" ".join(ubicacion.split()) if ubicacion else None,
            inicio=inicio,
            fin_estimado=fin_estimado,
        )


@dataclass(slots=True)
class Cluster:
    """Manzana dentro de un proyecto (§2.1). Es el alcance del Supervisor (§4)."""

    proyecto_id: str
    clave: Clave
    nombre: str

    @classmethod
    def crear(cls, *, proyecto_id: str, clave: str, nombre: str) -> Cluster:
        try:
            clave_canonica = Clave(clave)
        except ValueError as exc:
            raise ErrorDeProyecto(str(exc)) from exc

        return cls(
            proyecto_id=_exigir_referencia(proyecto_id, "proyecto_id"),
            clave=clave_canonica,
            nombre=_exigir_texto(nombre, "nombre"),
        )


@dataclass(slots=True)
class Prototipo:
    """Modelo de vivienda del proyecto (§7.2). Clave con prefijo ``CAS`` (§10.1).

    El prefijo es **semilla editable** (§8.7), así que el dominio no lo exige:
    lo normaliza y lo deja disponible en `Clave.prefijo` para quien lo valide
    contra la lista viva de Configuración.
    """

    proyecto_id: str | None
    """``None`` = prototipo de todos los proyectos de la organización (D-614)."""
    clave: Clave
    nombre: str
    m2: Decimal | None = None
    niveles: int | None = None
    recamaras: int | None = None

    @classmethod
    def crear(
        cls,
        *,
        proyecto_id: str | None = None,
        clave: str,
        nombre: str,
        m2: Decimal | None = None,
        niveles: int | None = None,
        recamaras: int | None = None,
    ) -> Prototipo:
        try:
            clave_canonica = Clave(clave)
        except ValueError as exc:
            raise ErrorDeProyecto(str(exc)) from exc

        if niveles is not None and niveles < 1:
            raise ErrorDeProyecto(
                f"Un prototipo tiene al menos un nivel: {niveles}."
            )
        if recamaras is not None and recamaras < 0:
            raise ErrorDeProyecto(
                f"Las recámaras no pueden ser negativas: {recamaras}."
            )

        return cls(
            proyecto_id=(
                _exigir_referencia(proyecto_id, "proyecto_id") if proyecto_id is not None else None
            ),
            clave=clave_canonica,
            nombre=_exigir_texto(nombre, "nombre"),
            m2=_exigir_positivo(m2, "m2"),
            niveles=niveles,
            recamaras=recamaras,
        )
