"""Correcciones propuestas a un dato del catálogo, como nueva versión del concepto (Ola 3B; migración 0132).

Costos propone y Control de obra autoriza. Una corrección **no edita el catálogo**: se guarda como versión del concepto
(propuesta → autorizada o rechazada) y la conciliación muestra la diferencia contra el catálogo vigente. Solo se proponen las
correcciones **conocidas** (`correcciones_de_catalogo`), con el valor que respalda el catálogo; nada se inventa. Si la propone Control
de obra, queda autorizada al momento (como en el resto de los cambios de Control de obra).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.elementos_parametricos import (
    ElementoParametricoNoEncontrado,
)
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.cuantificacion.autorizacion_de_elementos import puede_autorizar
from obractrl.domain.cuantificacion.correcciones_de_unidad import (
    CORRECCIONES_CONOCIDAS,
    correccion_conocida,
    siguiente_version,
    validar_que_autoriza,
    validar_que_propone,
)
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)

__all__ = ["GestionarCorreccionesDeCatalogo"]

_CAMPOS_PUBLICOS = (
    "id", "estado", "version", "propuso_nombre", "propuso_rol", "propuesto_en", "decidio_nombre", "decidio_rol", "decidido_en", "motivo_rechazo",
    "valor_propuesto",
)


class GestionarCorreccionesDeCatalogo:
    def __init__(self, *, correcciones: Any, uow: UnidadDeTrabajo) -> None:
        self._correcciones = correcciones
        self._uow = uow

    async def listar(self) -> list[dict[str, Any]]:
        """Cada corrección conocida con su estado: sin proponer, pendiente, o la última decidida, y todo su historial."""
        historial = await self._correcciones.historial()
        salida: list[dict[str, Any]] = []
        for c in CORRECCIONES_CONOCIDAS:
            propias = [h for h in historial if h["concepto_clave"].upper() == c["concepto_clave"] and h["campo"] == c["campo"]]
            vigente = next((h for h in sorted(propias, key=lambda h: h["version"] or 0, reverse=True) if h["estado"] == "autorizada"), None)
            pendiente = next((h for h in propias if h["estado"] == "pendiente"), None)
            salida.append(
                {
                    **{k: v for k, v in c.items() if k != "preguntas"},
                    "preguntas": list(c["preguntas"]),
                    "estado": "pendiente" if pendiente else ("autorizada" if vigente else "sin_proponer"),
                    "version_vigente": vigente["version"] if vigente else None,
                    "valor_vigente": vigente["valor_propuesto"] if vigente else c["valor_catalogo"],
                    "pendiente_id": pendiente["id"] if pendiente else None,
                    "historial": [{k: h[k] for k in _CAMPOS_PUBLICOS if k in h} for h in propias],
                }
            )
        return salida

    async def proponer(self, concepto_clave: str, campo: str, *, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """Costos propone la versión nueva del concepto (queda pendiente); Control de obra la deja autorizada al momento."""
        validar_que_propone(rol)
        c = correccion_conocida(concepto_clave, campo)
        existentes = await self._correcciones.historial()
        propias = [h for h in existentes if h["concepto_clave"].upper() == c["concepto_clave"] and h["campo"] == c["campo"]]
        if any(h["estado"] == "autorizada" and h["valor_propuesto"] == c["valor_propuesto"] for h in propias):
            raise ErrorDeElementoParametrico(f"{c['concepto_clave']} ya tiene autorizada esta corrección.")
        directa = puede_autorizar(rol)
        async with self._uow:
            numero = siguiente_version(await self._correcciones.autorizadas(c["concepto_clave"], c["campo"])) if directa else None
            nuevo = await self._correcciones.registrar(
                concepto_clave=c["concepto_clave"], campo=c["campo"], valor_catalogo=c["valor_catalogo"], valor_propuesto=c["valor_propuesto"],
                motivo=c["motivo"], fuente=c["fuente"], estado="autorizada" if directa else "pendiente", version=numero,
                propuso_id=usuario_id, propuso_rol=rol,
            )
            await self._uow.commit()
        return {"id": nuevo, "estado": "autorizada" if directa else "pendiente", "version": numero}

    async def _pendiente(self, correccion_id: UUID) -> dict[str, Any]:
        r = await self._correcciones.obtener(correccion_id)
        if r is None:
            raise ElementoParametricoNoEncontrado(f"La corrección {correccion_id} no existe o está fuera de tu alcance.")
        if r["estado"] != "pendiente":
            raise ErrorDeElementoParametrico("Esta propuesta ya fue decidida.")
        return r  # type: ignore[no-any-return]

    async def autorizar(self, correccion_id: UUID, *, usuario_id: UUID, rol: str) -> int:
        """Control de obra autoriza: nace la versión siguiente del concepto. El catálogo no se edita."""
        validar_que_autoriza(rol)
        r = await self._pendiente(correccion_id)
        async with self._uow:
            numero = siguiente_version(await self._correcciones.autorizadas(r["concepto_clave"], r["campo"]))
            await self._correcciones.decidir(correccion_id, estado="autorizada", version=numero, decidio_id=usuario_id, decidio_rol=rol)
            await self._uow.commit()
        return numero

    async def rechazar(self, correccion_id: UUID, *, usuario_id: UUID, rol: str, motivo: str | None) -> None:
        validar_que_autoriza(rol)
        await self._pendiente(correccion_id)
        limpio = " ".join((motivo or "").split())[:300] or None
        async with self._uow:
            await self._correcciones.decidir(correccion_id, estado="rechazada", version=None, decidio_id=usuario_id, decidio_rol=rol, motivo=limpio)
            await self._uow.commit()
