"""Reglas del expediente técnico de la obra.

Spec §7.9 (`ExpedienteDoc` — `obra_id`, `tipo`, `nombre`, `url`, `subido_por`,
`fecha`) · §11.2 ("**Expediente** — `GET/POST /obras/{id}/expediente` — todos
lectura / **(C, SI)** subida") · §11.1 (contexto Expediente).

Como en `domain.revisiones.reglas`, aquí **no hay máquina de transición**: el
§7.9 no le define ciclo de vida al documento —se agrega y queda—. Las
invariantes son las tres que el spec sí fija:

    quién   → solo Control de obra y Super intendente suben (§11.2).
    tipo    → del enum canónico `tipo_expediente_doc` (§8.2).
    nombre  → obligatorio, igual que `url` (§7.9: ambos `not null`).

`url` **no es una URL firmada** sino la *clave* del objeto en R2, que es lo
que persiste: la firma caduca, la clave no
(`infrastructure/storage/r2.SubidaFirmada.clave`). El binario nunca viaja por
la API (§12.2), así que el documento llega aquí cuando el cliente ya lo subió.

Módulo puro: sin BD, sin FastAPI, 100% testeable (§12.11).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from obractrl.domain.shared.diccionario import Rol, TipoExpedienteDoc

__all__ = ["ROLES_QUE_SUBEN", "DocumentoExpediente", "ErrorDeExpediente"]

ROLES_QUE_SUBEN = (Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE)
"""§11.2: la lectura es de todos, la **subida** es de C y SI."""


class ErrorDeExpediente(ValueError):
    """Permiso o dato inválido al agregar un documento al expediente (§7.9)."""


@dataclass(slots=True)
class DocumentoExpediente:
    """Entidad de dominio de `ExpedienteDoc` (§7.9)."""

    obra_id: str
    tipo: TipoExpedienteDoc
    nombre: str
    url: str
    subido_por: str
    fecha: datetime | None = None

    @classmethod
    def subir(
        cls,
        *,
        obra_id: str,
        tipo: TipoExpedienteDoc,
        nombre: str,
        url: str,
        subido_por: str,
        rol: Rol,
    ) -> DocumentoExpediente:
        """Control de obra o Super intendente agregan un documento (§11.2).

        El rol se valida puertas adentro —como `RevisionFisica.registrar`—
        aunque el router también lleve su `exigir_rol`: la guarda HTTP da un
        403 legible y esta deja la regla escrita una sola vez, donde vive el
        §6.
        """
        if rol not in ROLES_QUE_SUBEN:
            permitidos = ", ".join(r.value for r in ROLES_QUE_SUBEN)
            raise ErrorDeExpediente(
                f"Solo {permitidos} suben documentos al expediente; el rol "
                f"{rol.value!r} no puede (§11.2)."
            )

        nombre_limpio = nombre.strip()
        if not nombre_limpio:
            raise ErrorDeExpediente(
                "El documento necesita un nombre: `expediente_doc.nombre` es "
                "`not null` (§7.9)."
            )

        url_limpia = url.strip()
        if not url_limpia:
            raise ErrorDeExpediente(
                "El documento necesita la clave del objeto ya subido a R2; "
                "`expediente_doc.url` es `not null` (§7.9, §12.2)."
            )

        return cls(
            obra_id=obra_id,
            tipo=tipo,
            nombre=nombre_limpio,
            url=url_limpia,
            subido_por=subido_por,
        )
