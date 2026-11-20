"""Las propuestas de versión de concepto del muro de sillar amarillo BAP-01010.

Usa la misma tabla de propuestas de la 3A (`propuesta_de_estructura`, migración 0131): ya guarda el elemento, el concepto, la clase
(`version_de_concepto`), quién propuso, quién autorizó y la versión que nace; el ciclo de autorización
(`/propuestas-de-estructura/{id}/autorizar`) es el mismo. Costos o Control de obra proponen y solo Control de obra autoriza (lo que
propone Control de obra se registra ya autorizado). Nada toca el catálogo ni pone precios ni destajos. El elemento se liga al concepto
BAP-01010, que ya es una matriz del catálogo (regla F7): por eso no hay «concepto nuevo» que proponer.
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
from obractrl.domain.cuantificacion.correcciones_de_catalogo import numero_de_version
from obractrl.domain.cuantificacion.muro_sillar import (
    ElementoDeSillarNoEncontrado,
    EntradaMuroDeSillar,
    calcular_muro_de_sillar,
    elemento_de_sillar,
    propuestas_de_actualizacion_de_apu,
)

__all__ = ["GestionarPropuestasDeSillar"]


def _elemento(clave: str) -> Any:
    try:
        return elemento_de_sillar(clave)
    except ElementoDeSillarNoEncontrado as e:
        raise ElementoParametricoNoEncontrado(str(e)) from e


class GestionarPropuestasDeSillar:
    def __init__(self, *, propuestas: Any, uow: UnidadDeTrabajo) -> None:
        self._propuestas = propuestas
        self._uow = uow

    async def listar(self, elemento_clave: str) -> list[dict[str, Any]]:
        e = _elemento(elemento_clave)
        return list(await self._propuestas.del_elemento(e.clave))

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

    async def proponer_actualizacion_de_apu(
        self, elemento_clave: str, entrada: EntradaMuroDeSillar, *, usuario_id: UUID, rol: str
    ) -> dict[str, Any]:
        """«Confirmar cálculo → actualizar APU»: una versión propuesta de BAP-01010 si sus coeficientes difieren del cálculo. Idempotente:
        no repite una propuesta mientras haya una vigente (pendiente o autorizada) del mismo concepto y clase."""
        validar_que_propone(rol)
        e = _elemento(elemento_clave)
        calculo = calcular_muro_de_sillar(e.clave, entrada)
        creadas: list[UUID] = []
        omitidas: list[str] = []
        async with self._uow:
            for p in propuestas_de_actualizacion_de_apu(calculo):
                vigentes = [v for v in await self._propuestas.vigentes_del_concepto(p["concepto_clave"]) if v["clase"] == p["clase"]]
                if vigentes:
                    omitidas.append(p["concepto_clave"])
                    continue
                creadas.append(await self._registrar(p, usuario_id=usuario_id, rol=rol))
            await self._uow.commit()
        return {"creadas": creadas, "omitidas": omitidas}
