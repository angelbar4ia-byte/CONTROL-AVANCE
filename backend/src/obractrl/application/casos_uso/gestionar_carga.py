"""Casos de uso de cargas de datos — workflow G (§11.3).

Spec §11.3 G (subir → validar → aplicar) · §9.2 (pipeline) · §9.4
(`CargaDatos`) · §10.2 (lote reversible, tres modos) · §10.3 (bandeja) ·
§10.8 (versionado y reversa) · §12.3 (idempotencia por clave).

Tres operaciones:

- :class:`EjecutarCarga` — sube un archivo y lo **previsualiza** o lo
  **aplica**. Los dos caminos corren exactamente el mismo pipeline; la
  diferencia es si se escribe (§9.3: "dry-run obligatorio", y por eso la vista
  previa tiene que dar los mismos números que el commit).
- :class:`RevertirCarga` — deshace el lote completo (§10.8), nunca registro
  por registro.
- :class:`ConsultarCarga` — estado del lote y su bandeja de pendientes.

**Idempotencia (§10.8, §12.3).** Antes de aplicar se busca una carga del
mismo tipo, ya aplicada y no revertida, con el mismo hash de archivo: si
existe, no se crea versión ni se toca el catálogo. Y aunque el hash difiera,
si el diff sale vacío tampoco se genera versión — "si es idéntico, no crea
versión" es sobre el **contenido**, no sobre el archivo.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.aplicar_carga import AplicadorDeCarga
from obractrl.application.puertos.cargadores import LectorDeCarga, RepositorioCargas
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.cargadores.reporte import ErrorDeFila, ResumenCarga
from obractrl.domain.shared.diccionario import EstatusCarga, ModoCarga, TipoCarga

__all__ = [
    "CargaNoEliminable",
    "CargaNoEncontrada",
    "CargaNoRevertible",
    "ComandoEjecutarCarga",
    "ConsultarCarga",
    "EjecutarCarga",
    "EliminarCarga",
    "ResultadoCarga",
    "RevertirCarga",
]


class CargaNoEncontrada(LookupError):
    """El lote no existe o está fuera del alcance del usuario (§12.4)."""


class CargaNoRevertible(RuntimeError):
    """El lote no se puede revertir: no llegó a aplicarse o ya se revirtió."""


class CargaNoEliminable(RuntimeError):
    """El lote se aplicó y no se ha revertido: borrar su registro ahora
    dejaría el catálogo modificado sin ninguna forma de deshacerlo."""


@dataclass(frozen=True, slots=True)
class ComandoEjecutarCarga:
    """Subida de un archivo (§11.3 G.1, §11.2 `POST /cargas`)."""

    tipo: TipoCarga
    contenido: bytes
    archivo_nombre: str
    usuario_id: UUID | None = None
    modo: ModoCarga = ModoCarga.ACTUALIZAR
    dry_run: bool = False
    """``True`` = vista previa (§10.2): valida, cuenta y llena la bandeja, sin
    escribir el catálogo."""


@dataclass(frozen=True, slots=True)
class ResultadoCarga:
    """Lo que ve quien subió el archivo (§9.3, §9.4)."""

    carga_id: UUID
    estatus: EstatusCarga
    resumen: ResumenCarga
    errores: tuple[ErrorDeFila, ...] = ()
    pendientes: int = 0
    version_generada: int | None = None
    diff: dict[str, Any] = field(default_factory=dict)
    reutilizada: bool = False
    """``True`` cuando el archivo ya se había aplicado idéntico: no se creó
    versión ni se tocó nada (§10.8, §12.3)."""


class EjecutarCarga:
    """`POST /cargas` — workflow G completo sobre un archivo (§11.3 G)."""

    def __init__(
        self,
        *,
        cargas: RepositorioCargas,
        lector: LectorDeCarga,
        aplicador: AplicadorDeCarga,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._cargas = cargas
        self._lector = lector
        self._aplicador = aplicador
        self._uow = uow

    async def ejecutar(self, cmd: ComandoEjecutarCarga) -> ResultadoCarga:
        huella = hashlib.sha256(cmd.contenido).hexdigest()

        if not cmd.dry_run:
            previa = await self._cargas.buscar_aplicada_por_hash(
                tipo=str(cmd.tipo), archivo_hash=huella
            )
            if previa is not None:
                return _resultado_reutilizado(previa)

        # Parsear **antes** de abrir el lote: si el archivo ni siquiera se
        # puede leer (`ErrorDeArchivo`), no hay nada que registrar.
        lectura = self._lector.leer(cmd.contenido)

        carga_id = await self._cargas.crear(
            tipo=str(cmd.tipo),
            modo=str(cmd.modo),
            archivo_nombre=cmd.archivo_nombre,
            archivo_hash=huella,
            usuario_id=cmd.usuario_id,
        )

        aplicacion = await self._aplicador.aplicar(
            lectura, modo=cmd.modo, dry_run=cmd.dry_run, carga_id=carga_id
        )

        errores = (*lectura.errores, *aplicacion.errores)
        pendientes = (*lectura.pendientes, *aplicacion.pendientes)

        version: int | None = None
        if not cmd.dry_run and aplicacion.diff.hay_cambios:
            # "Cada carga = una versión" (§10.8) — pero solo si algo cambió:
            # un archivo que no mueve nada no genera versión.
            version = await self._cargas.siguiente_version(tipo=str(cmd.tipo))

        estatus = (
            EstatusCarga.PREVISUALIZADO if cmd.dry_run else EstatusCarga.APLICADO
        )
        resumen = ResumenCarga(
            filas=lectura.filas_leidas,
            insertados=aplicacion.insertados,
            actualizados=aplicacion.actualizados,
            omitidos=aplicacion.omitidos,
            errores=len(errores),
            pendientes=len(pendientes),
        )

        async with self._uow:
            if aplicacion.operaciones:
                await self._cargas.registrar_snapshots(
                    carga_id, list(aplicacion.operaciones)
                )
            if pendientes:
                await self._cargas.crear_pendientes(
                    carga_id, [p.como_dict() for p in pendientes]
                )
            await self._cargas.finalizar(
                carga_id,
                estatus=str(estatus),
                resumen={
                    **resumen.como_dict(),
                    "diff": aplicacion.diff.como_dict(),
                    **aplicacion.detalle,
                },
                errores=[e.como_dict() for e in errores],
                version_generada=version,
            )
            await self._uow.commit()

        return ResultadoCarga(
            carga_id=carga_id,
            estatus=estatus,
            resumen=resumen,
            errores=errores,
            pendientes=len(pendientes),
            version_generada=version,
            diff=aplicacion.diff.como_dict(),
        )


def _resultado_reutilizado(previa: dict[str, Any]) -> ResultadoCarga:
    """Respuesta cuando el archivo ya se aplicó idéntico (§10.8, §12.3)."""
    guardado = previa.get("resumen") or {}
    return ResultadoCarga(
        carga_id=previa["id"],
        estatus=EstatusCarga.APLICADO,
        resumen=ResumenCarga(
            filas=int(guardado.get("filas", 0)),
            omitidos=int(guardado.get("filas", 0)),
        ),
        version_generada=previa.get("version_generada"),
        diff=guardado.get("diff") or {},
        reutilizada=True,
    )


class RevertirCarga:
    """Deshace un lote completo (§10.8).

    "Una carga se revierte/elimina **como unidad** (el lote completo),
    dejando los datos como estaban antes de esa carga. No se borra registro
    por registro: se revierte el lote."
    """

    def __init__(self, *, cargas: RepositorioCargas, uow: UnidadDeTrabajo) -> None:
        self._cargas = cargas
        self._uow = uow

    async def ejecutar(
        self, carga_id: UUID, *, usuario_id: UUID | None = None
    ) -> dict[str, Any]:
        carga = await self._cargas.obtener(carga_id)
        if carga is None:
            # RLS hace indistinguible "no existe" de "no la puedes ver" (§12.4).
            raise CargaNoEncontrada(
                f"No existe la carga {carga_id} o está fuera de tu alcance."
            )
        if str(carga["estatus"]) != str(EstatusCarga.APLICADO):
            raise CargaNoRevertible(
                f"La carga está en estatus {carga['estatus']!r}: solo se revierte "
                f"lo que se aplicó (§10.8)."
            )
        if carga.get("revertida_en") is not None:
            raise CargaNoRevertible(
                f"La carga ya se revirtió el {carga['revertida_en']}."
            )

        operaciones = await self._cargas.snapshots(carga_id)

        async with self._uow:
            # En orden inverso: el repositorio ya las devuelve así. Importa —
            # el CPU vigente anterior no se puede volver a marcar vigente
            # antes de borrar el nuevo (`uq_cpu_vigente`).
            for operacion in operaciones:
                await self._cargas.revertir_operacion(operacion)
            await self._cargas.marcar_revertida(carga_id, usuario_id=usuario_id)
            await self._uow.commit()

        return {"carga_id": carga_id, "operaciones_revertidas": len(operaciones)}


class EliminarCarga:
    """Borra el registro de una carga que no tiene nada pendiente de
    revertir: una vista previa que nunca escribió (§9.3), una que falló
    antes de aplicar, o una que ya se revirtió. `carga_snapshot` y
    `pendiente` se van en cascada (`on delete cascade` desde el diseño
    original de estas tablas, §10.8) — no hay nada más que limpiar a mano.

    Una carga aplicada y **sin** revertir no se puede eliminar directo:
    borrar su snapshot sin deshacer los cambios que hizo dejaría el
    catálogo modificado y sin ninguna forma de revertirlo. Revertir
    primero, eliminar después — son dos pasos a propósito, no uno.
    """

    def __init__(self, *, cargas: RepositorioCargas, uow: UnidadDeTrabajo) -> None:
        self._cargas = cargas
        self._uow = uow

    async def ejecutar(self, carga_id: UUID) -> None:
        carga = await self._cargas.obtener(carga_id)
        if carga is None:
            raise CargaNoEncontrada(
                f"No existe la carga {carga_id} o está fuera de tu alcance."
            )
        aplicada_sin_revertir = (
            str(carga["estatus"]) == str(EstatusCarga.APLICADO)
            and carga.get("revertida_en") is None
        )
        if aplicada_sin_revertir:
            raise CargaNoEliminable(
                "Esta carga se aplicó y no se ha revertido: revierte primero "
                "(§10.8), o se perdería la única forma de deshacer sus "
                "cambios."
            )
        async with self._uow:
            await self._cargas.eliminar(carga_id)
            await self._uow.commit()


class ConsultarCarga:
    """`GET /cargas`, `GET /cargas/{id}` y su bandeja (§11.2, §10.3)."""

    def __init__(self, *, cargas: RepositorioCargas) -> None:
        self._cargas = cargas

    async def obtener(self, carga_id: UUID) -> dict[str, Any]:
        carga = await self._cargas.obtener(carga_id)
        if carga is None:
            raise CargaNoEncontrada(
                f"No existe la carga {carga_id} o está fuera de tu alcance."
            )
        return carga

    async def listar(self, *, tipo: TipoCarga | None = None) -> list[dict[str, Any]]:
        return await self._cargas.listar(tipo=str(tipo) if tipo else None)

    async def pendientes(
        self, carga_id: UUID, *, solo_abiertos: bool = True
    ) -> list[dict[str, Any]]:
        await self.obtener(carga_id)
        return await self._cargas.listar_pendientes(
            carga_id=carga_id, solo_abiertos=solo_abiertos
        )
