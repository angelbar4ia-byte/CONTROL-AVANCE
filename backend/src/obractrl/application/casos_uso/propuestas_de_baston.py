"""Las propuestas de versión de concepto de los bastones (Ola 4, 4D).

Usa la misma tabla de propuestas de la 3A (`propuesta_de_estructura`, migración 0131): guarda el elemento, el concepto, la clase
(`version_de_concepto` o `concepto_nuevo`), quién propuso y quién autorizó; el ciclo de autorización
(`/propuestas-de-estructura/{id}/autorizar`) es el mismo. Costos o Control de obra proponen y solo Control de obra autoriza (lo que
propone Control de obra se registra ya autorizado). Nada toca el catálogo ni pone precios ni destajos. No hace falta migración.
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
from obractrl.domain.cuantificacion.baston import (
    CLAVE_ELEMENTO,
    ElementoDeBastonNoEncontrado,
    EntradaDeBaston,
    calcular_baston,
    concepto_nuevo_de,
    propuestas_de_actualizacion_de_apu,
)
from obractrl.domain.cuantificacion.correcciones_de_catalogo import numero_de_version

__all__ = ["GestionarPropuestasDeBaston"]


def _validar_elemento(clave: str) -> str:
    if clave != CLAVE_ELEMENTO:
        raise ElementoParametricoNoEncontrado(str(ElementoDeBastonNoEncontrado(f"No hay un bastón con la clave {clave}.")))
    return clave


class GestionarPropuestasDeBaston:
    def __init__(self, *, propuestas: Any, uow: UnidadDeTrabajo) -> None:
        self._propuestas = propuestas
        self._uow = uow

    async def listar(self, elemento_clave: str) -> list[dict[str, Any]]:
        return list(await self._propuestas.del_elemento(_validar_elemento(elemento_clave)))

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

    async def _registrar_las_que_faltan(self, propuestas: list[dict[str, Any]], *, usuario_id: UUID, rol: str) -> dict[str, Any]:
        creadas: list[UUID] = []
        omitidas: list[str] = []
        async with self._uow:
            for p in propuestas:
                vigentes = [
                    v for v in await self._propuestas.vigentes_del_concepto(p["concepto_clave"]) if v["clase"] == p["clase"]
                ]
                if vigentes:
                    omitidas.append(p["concepto_clave"])
                    continue
                creadas.append(await self._registrar(p, usuario_id=usuario_id, rol=rol))
            await self._uow.commit()
        return {"creadas": creadas, "omitidas": omitidas}

    async def proponer_concepto_nuevo(
        self, elemento_clave: str, entrada: EntradaDeBaston, *, usuario_id: UUID, rol: str
    ) -> dict[str, Any]:
        """El escalón que el catálogo no trae: concepto nuevo con clave provisional, sin destajo ni precio. Idempotente."""
        validar_que_propone(rol)
        _validar_elemento(elemento_clave)
        return await self._registrar_las_que_faltan([concepto_nuevo_de(entrada)], usuario_id=usuario_id, rol=rol)

    async def proponer_actualizacion_de_apu(
        self, elemento_clave: str, entrada: EntradaDeBaston, *, usuario_id: UUID, rol: str
    ) -> dict[str, Any]:
        """«Confirmar cálculo → actualizar APU»: una versión propuesta del escalón cuyos coeficientes difieren del cálculo."""
        validar_que_propone(rol)
        _validar_elemento(elemento_clave)
        return await self._registrar_las_que_faltan(
            propuestas_de_actualizacion_de_apu(calcular_baston(entrada)), usuario_id=usuario_id, rol=rol
        )
