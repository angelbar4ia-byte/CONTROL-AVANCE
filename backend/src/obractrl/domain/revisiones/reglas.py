"""Reglas de la revisión física en campo.

Spec §2 (glosario: "Revisión física — captura en campo de **Control de obra**
(fotos, comentarios, calidad)") · §7.8 (`RevisionFisica`) · §11.2 ("Revisión
física (móvil · Control de obra)": `POST /obras/{id}/revisiones` — fotos +
comentario + calidad **(C)**).

Como en `domain.evaluaciones.reglas`, aquí **no hay máquina de transición**:
la revisión se registra una vez y no cambia de estatus —el §7.8 no le define
ciclo de vida, a diferencia de `Incidencia` o `SolicitudCierre`—. Las dos
únicas invariantes son las que el spec sí fija:

    quién  → solo Control de obra registra (§2, §11.2).
    calidad → 1 a 5, y es opcional.

El rango de `calidad` se define **aquí** y la base lo repite como `CHECK
(calidad between 1 and 5)` (`database/migrations/20260814000009`), que es la
invariante 2 del roadmap: la regla vive una vez en el dominio y la BD la
espeja. Sin la validación de dominio, una calidad de 9 solo reventaría como
`IntegrityError` opaco del driver en vez de como un error de negocio legible.

Nada obliga a traer fotos ni comentario: el §7.8 los declara opcionales
(`fotos` default `[]`, `comentario` nullable) y una revisión que solo
califica es una captura válida en campo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "CALIDAD_MAXIMA",
    "CALIDAD_MINIMA",
    "ErrorDeRevision",
    "RevisionFisica",
]

CALIDAD_MINIMA = 1
CALIDAD_MAXIMA = 5
"""Escala de calidad (§7.8). La BD la repite como `CHECK` en la migración 0009."""


class ErrorDeRevision(ValueError):
    """Permiso o dato inválido al registrar una revisión física (§7.8, §11.2)."""


@dataclass(slots=True)
class RevisionFisica:
    """Entidad de dominio de una revisión física (§7.8).

    Entidad propia que además **puede** ligarse a una actividad o a una
    incidencia (§7.8): los dos vínculos son opcionales y no se excluyen entre
    sí —el spec los enumera con `?` y sin condición—, así que el dominio no
    inventa una regla de exclusividad que nadie escribió.
    """

    obra_id: str
    usuario_id: str
    fecha: date
    fotos: list[str] = field(default_factory=list)
    comentario: str | None = None
    calidad: int | None = None
    actividad_id: str | None = None
    incidencia_id: str | None = None

    @classmethod
    def registrar(
        cls,
        *,
        obra_id: str,
        usuario_id: str,
        rol: Rol,
        fecha: date,
        fotos: list[str] | None = None,
        comentario: str | None = None,
        calidad: int | None = None,
        actividad_id: str | None = None,
        incidencia_id: str | None = None,
    ) -> RevisionFisica:
        """Control de obra registra la revisión en campo (§2, §11.2).

        El rol se valida puertas adentro, como `SolicitudCierre.solicitar`
        valida `rol=Residente`, aunque el router también lleve su
        `exigir_rol`: la guarda HTTP da un 403 legible y esta deja la regla
        escrita una sola vez, donde vive el §6.
        """
        if rol is not Rol.CONTROL_OBRA:
            raise ErrorDeRevision(
                f"Solo Control de obra registra una revisión física; el rol "
                f"{rol.value!r} no puede (§11.2)."
            )
        if calidad is not None and not CALIDAD_MINIMA <= calidad <= CALIDAD_MAXIMA:
            raise ErrorDeRevision(
                f"La calidad va de {CALIDAD_MINIMA} a {CALIDAD_MAXIMA}; "
                f"{calidad} está fuera de la escala (§7.8)."
            )

        comentario_limpio = comentario.strip() if comentario else None
        return cls(
            obra_id=obra_id,
            usuario_id=usuario_id,
            fecha=fecha,
            fotos=list(fotos or []),
            comentario=comentario_limpio or None,
            calidad=calidad,
            actividad_id=actividad_id,
            incidencia_id=incidencia_id,
        )
