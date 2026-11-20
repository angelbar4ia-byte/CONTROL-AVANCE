"""Las propuestas de concepto nuevo de la losa (fase 2): el concepto de la losa por m² (regla F7) y el colado y cimbra por ml de las trabes con su
destajo por ml sin importe (D8).

Usa la misma tabla de propuestas de la 3A (`propuesta_de_estructura`, migración 0131): ya guarda el elemento, el concepto, la clase
(`concepto_nuevo`), quién propuso, quién autorizó y la versión que nace; el ciclo de autorización (`/propuestas-de-estructura/{id}/autorizar`)
es el mismo. Costos o Control de obra proponen y solo Control de obra autoriza (lo que propone Control de obra se registra ya autorizado). Nada
toca el catálogo ni pone precios ni destajos con importe. Un concepto que ya está propuesto o autorizado no se vuelve a proponer (idempotente).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.elementos_parametricos import (
    ElementoParametricoNoEncontrado,
)
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.cuantificacion.autorizacion_de_elementos import (
    estado_de_alta,
    validar_que_propone,
)
from obractrl.domain.cuantificacion.colado_por_ml import concepto_nuevo_de_colado
from obractrl.domain.cuantificacion.correcciones_de_catalogo import numero_de_version
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)
from obractrl.domain.cuantificacion.matriz_de_losa import (
    CLAVES_DE_LOSA,
    concepto_nuevo_de_losa,
    elemento_de_losa,
)

__all__ = ["GestionarPropuestasDeLosa"]


class GestionarPropuestasDeLosa:
    def __init__(self, *, propuestas: Any, uow: UnidadDeTrabajo) -> None:
        self._propuestas = propuestas
        self._uow = uow

    async def listar(self, elemento_clave: str) -> list[dict[str, Any]]:
        if elemento_de_losa(elemento_clave) is None:
            raise ElementoParametricoNoEncontrado(f"No hay un elemento de losa «{elemento_clave}» en la biblioteca.")
        return list(await self._propuestas.del_elemento(elemento_clave))

    async def estado_de(self, concepto_clave: str) -> dict[str, Any] | None:
        """La propuesta vigente (pendiente o autorizada) de un concepto: `{id, estado, version, elemento_clave}`, o `None` si nadie lo ha propuesto."""
        vigentes = [v for v in await self._propuestas.vigentes_del_concepto(concepto_clave) if v["clase"] == "concepto_nuevo"]
        if not vigentes:
            return None
        v = sorted(vigentes, key=lambda x: (x["estado"] != "autorizada", x["propuesto_en"]))[0]
        return {"id": v["id"], "estado": v["estado"], "version": v["version"], "elemento_clave": v["elemento_clave"]}

    async def _registrar(self, p: dict[str, Any], *, usuario_id: UUID, rol: str) -> UUID:
        """Costos deja la propuesta pendiente; la de Control de obra nace autorizada con su número de versión."""
        autorizada = estado_de_alta(rol) == "autorizado"
        numero = numero_de_version(p["clase"], await self._propuestas.autorizadas(p["concepto_clave"], p["clase"])) if autorizada else None
        return await self._propuestas.registrar(  # type: ignore[no-any-return]
            elemento_clave=p["elemento_clave"], concepto_clave=p["concepto_clave"], clase=p["clase"],
            estado="autorizada" if autorizada else "pendiente", version=numero, resumen=p["resumen"], detalle=p["detalle"],
            propuso_id=usuario_id, propuso_rol=rol,
            decidio_id=usuario_id if autorizada else None, decidio_rol=rol if autorizada else None,
        )

    async def proponer(self, propuestas: list[dict[str, Any]], *, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """Registra las propuestas que aún no están propuestas ni autorizadas. Idempotente. Una clave provisional que ya está propuesta para OTRO
        elemento se rechaza: dos elementos no pueden compartir el concepto."""
        validar_que_propone(rol)
        creadas: list[UUID] = []
        omitidas: list[str] = []
        async with self._uow:
            for p in propuestas:
                vigentes = [v for v in await self._propuestas.vigentes_del_concepto(p["concepto_clave"]) if v["clase"] == p["clase"]]
                ajenas = [v for v in vigentes if v["elemento_clave"] != p["elemento_clave"]]
                if ajenas:
                    raise ErrorDeElementoParametrico(
                        f"La clave provisional {p['concepto_clave']} ya está propuesta para {ajenas[0]['elemento_clave']}: no puede ser también de {p['elemento_clave']}."
                    )
                if vigentes:
                    omitidas.append(p["concepto_clave"])
                    continue
                creadas.append(await self._registrar(p, usuario_id=usuario_id, rol=rol))
            await self._uow.commit()
        return {"creadas": creadas, "omitidas": omitidas}

    async def proponer_concepto_de_losa(self, elemento_clave: str, *, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """El concepto nuevo de la losa por m² (regla F7), con clave provisional, sin destajo ni precio."""
        tipo = elemento_de_losa(elemento_clave)
        if tipo is None or CLAVES_DE_LOSA[tipo] != elemento_clave:
            raise ElementoParametricoNoEncontrado(f"No hay un elemento de losa «{elemento_clave}» en la biblioteca.")
        return await self.proponer([concepto_nuevo_de_losa(tipo)], usuario_id=usuario_id, rol=rol)

    async def proponer_colado_por_ml(self, elemento_clave: str, *, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """D8: el concepto nuevo de colado y cimbra por ml de una trabe, contratrabe o nervadura, con su destajo por ml sin importe."""
        p = concepto_nuevo_de_colado(elemento_clave)
        if p is None:
            raise ElementoParametricoNoEncontrado(f"«{elemento_clave}» no es una trabe, contratrabe ni nervadura de la biblioteca.")
        return await self.proponer([p], usuario_id=usuario_id, rol=rol)
