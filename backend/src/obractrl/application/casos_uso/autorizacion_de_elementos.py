"""Costos propone, Control de obra autoriza: el historial, lo pendiente y las decisiones (plan de elementos de muro, fase I).

Lo que Costos propone queda pendiente y Control de obra lo autoriza o lo rechaza; cada autorización crea la versión siguiente del
elemento o de su concepto, con quién propuso, quién autorizó y cuándo. Esta clase junta lo que decide: autorizar un elemento
nuevo, un cambio propuesto, un concepto nuevo (que entra al catálogo **sin precio**: Costos lo asigna) o la actualización de un
APU. Los cambios de Control de obra no pasan por aquí: se aplican al momento y quedan como versión.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.apu_desde_elemento import ActualizarApuDesdeElemento
from obractrl.application.casos_uso.elementos_parametricos import (
    ElementoParametricoNoEncontrado,
    GestionarElementosParametricos,
)
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.cuantificacion.autorizacion_de_elementos import (
    siguiente_version,
    validar_que_autoriza,
)
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)

__all__ = ["AutorizarElementos"]

_UNIDAD_EN_LA_BASE = {"m²": "m2"}
"""Cómo se llama en el catálogo de unidades la unidad con que el elemento cuenta un concepto."""


class AutorizarElementos:
    def __init__(
        self,
        *,
        elementos: Any,
        versiones: Any,
        conceptos: Any,
        insumos: Any,
        uow: UnidadDeTrabajo,
        elementos_uc: GestionarElementosParametricos,
        apu_uc: ActualizarApuDesdeElemento,
        sincronizador: Any | None = None,
    ) -> None:
        self._elementos = elementos
        self._versiones = versiones
        self._conceptos = conceptos
        self._insumos = insumos
        self._uow = uow
        self._elementos_uc = elementos_uc
        self._apu_uc = apu_uc
        self._sincronizador = sincronizador

    async def _elemento(self, elemento_id: UUID) -> dict[str, Any]:
        e = await self._elementos.obtener(elemento_id)
        if e is None:
            raise ElementoParametricoNoEncontrado(f"El elemento {elemento_id} no existe o está fuera de tu alcance.")
        return e  # type: ignore[no-any-return]

    # --- Lectura ------------------------------------------------------------------------------------------------

    async def historial(self, elemento_id: UUID) -> dict[str, Any]:
        """El estado de autorización del elemento y todas sus propuestas y versiones, las suyas y las de sus conceptos."""
        elemento = await self._elemento(elemento_id)
        raiz = await self._versiones.raiz_de(elemento_id)
        filas = await self._versiones.historial(raiz)
        propias = [f["version"] for f in filas if f["fila_id"] is None and f["estado"] == "autorizada"]
        return {
            "elemento_id": elemento_id,
            "estado": elemento.get("estado_autorizacion", "autorizado"),
            "version": max(propias, default=None),
            "versiones": filas,
        }

    async def pendientes(self) -> list[dict[str, Any]]:
        """Todo lo que espera la autorización de Control de obra."""
        return await self._versiones.pendientes()  # type: ignore[no-any-return]

    # --- Decisiones de Control de obra --------------------------------------------------------------------------

    async def autorizar_elemento(self, elemento_id: UUID, *, usuario_id: UUID, rol: str) -> int:
        """Un elemento nuevo que propuso Costos deja de ser provisional: queda autorizado y es su versión 1."""
        validar_que_autoriza(rol)
        elemento = await self._elemento(elemento_id)
        if elemento.get("estado_autorizacion", "autorizado") != "pendiente":
            raise ErrorDeElementoParametrico(f"{elemento['clave']} ya está autorizado.")
        raiz = await self._versiones.raiz_de(elemento_id)
        async with self._uow:
            await self._elementos.fijar_estado_de_autorizacion(elemento_id, "autorizado")
            numero = siguiente_version(await self._versiones.autorizadas(raiz, None))
            await self._versiones.registrar(
                elemento_id=elemento_id, raiz_id=raiz, fila_id=None, clase="elemento", estado="autorizada", version=numero,
                resumen=f"Alta autorizada del elemento {elemento['clave']}", detalle={}, propuso_id=elemento.get("autor_id"),
                propuso_rol="costos", decidio_id=usuario_id, decidio_rol=rol,
            )
            await self._uow.commit()
        return numero

    async def _pendiente(self, revision_id: UUID) -> dict[str, Any]:
        r = await self._versiones.obtener(revision_id)
        if r is None:
            raise ElementoParametricoNoEncontrado(f"La propuesta {revision_id} no existe o está fuera de tu alcance.")
        if r["estado"] != "pendiente":
            raise ErrorDeElementoParametrico("Esta propuesta ya fue decidida.")
        return r  # type: ignore[no-any-return]

    async def autorizar_revision(self, revision_id: UUID, *, usuario_id: UUID, rol: str) -> int:
        """Autoriza la propuesta de Costos: se aplica el cambio del elemento o la actualización del APU y queda la versión siguiente."""
        validar_que_autoriza(rol)
        r = await self._pendiente(revision_id)
        if r["clase"] == "apu":
            return await self._apu_uc.autorizar(r, usuario_id=usuario_id, rol=rol)
        if r["clase"] != "elemento":
            raise ErrorDeElementoParametrico("Esta propuesta no se autoriza aquí: autoriza el concepto desde su fila.")
        vigente = await self._versiones.vigente_de(r["raiz_id"])
        if vigente is None:
            raise ElementoParametricoNoEncontrado("El elemento de esta propuesta ya no existe.")
        cambio = dict(dict(r["detalle"]).get("cambio") or {})
        # Si el cambio ya no es válido (otro elemento quedó igual, la clave se ocupó), falla aquí y la propuesta sigue pendiente.
        await self._elementos_uc.actualizar(
            vigente, clave=cambio.get("clave"), nombre=cambio.get("nombre"), parametros=cambio.get("parametros"),
            autor_id=usuario_id, categoria=cambio.get("categoria"), subcategoria=cambio.get("subcategoria"),
            materiales=cambio.get("materiales"),
        )
        async with self._uow:
            numero = siguiente_version(await self._versiones.autorizadas(r["raiz_id"], None))
            await self._versiones.decidir(revision_id, estado="autorizada", version=numero, decidio_id=usuario_id, decidio_rol=rol)
            await self._uow.commit()
        return numero

    async def rechazar_revision(self, revision_id: UUID, *, usuario_id: UUID, rol: str, motivo: str | None) -> None:
        validar_que_autoriza(rol)
        await self._pendiente(revision_id)
        limpio = " ".join((motivo or "").split())[:300] or None
        async with self._uow:
            await self._versiones.decidir(revision_id, estado="rechazada", version=None, decidio_id=usuario_id, decidio_rol=rol, motivo=limpio)
            await self._uow.commit()

    async def autorizar_concepto(self, elemento_id: UUID, fila_id: UUID, *, usuario_id: UUID, rol: str) -> int:
        """Un concepto nuevo propuesto entra al catálogo **sin precio** (Costos lo asigna) y deja de ser pendiente: desde aquí cuenta
        en el presupuesto. Queda como su versión 1."""
        validar_que_autoriza(rol)
        await self._elemento(elemento_id)
        fila = await self._elementos.concepto_por_contexto(elemento_id, fila_id)
        if fila is None:
            raise ElementoParametricoNoEncontrado(f"El concepto {fila_id} no es de este elemento.")
        if fila["estado"] != "propuesto" or fila["concepto_id"] is not None:
            raise ErrorDeElementoParametrico(f"{fila['clave']} ya está autorizado.")
        if await self._conceptos.obtener_por_clave(fila["clave"]) is not None:
            raise ErrorDeElementoParametrico(f"{fila['clave']} ya está en el catálogo: enlázalo en lugar de autorizarlo como nuevo.")
        unidad = await self._insumos.unidad_id(_UNIDAD_EN_LA_BASE.get(fila["unidad"], fila["unidad"]))
        if unidad is None:
            raise ErrorDeElementoParametrico(f"La unidad «{fila['unidad']}» no existe en el catálogo de unidades.")
        raiz = await self._versiones.raiz_de(elemento_id)
        async with self._uow:
            concepto_id = await self._conceptos.crear(
                {"tipo": "concepto", "clave": fila["clave"], "descripcion": fila["descripcion"], "unidad_id": unidad}
            )
            await self._elementos.autorizar_concepto(fila_id, concepto_id)
            numero = siguiente_version(await self._versiones.autorizadas(raiz, fila_id))
            await self._versiones.registrar(
                elemento_id=elemento_id, raiz_id=raiz, fila_id=fila_id, clase="concepto", estado="autorizada", version=numero,
                resumen=f"Concepto nuevo {fila['clave']} autorizado, sin precio: Costos define su APU y su destajo",
                detalle={"clave": fila["clave"], "unidad": fila["unidad"]}, propuso_id=fila.get("autor_id"), propuso_rol=None,
                decidio_id=usuario_id, decidio_rol=rol,
            )
            general = (
                fila["nivel_min"] is None and fila["nivel_max"] is None and fila["ubicacion"] is None
                and fila["alto_hasta_m"] in (None, Decimal(0))
            )
            if general and self._sincronizador is not None:
                await self._sincronizador.de_las_obras_con(elemento_id)
            await self._uow.commit()
        return numero
