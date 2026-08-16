"""Caso de uso: alta y edición de obras (§11.2 "Proyecto · Obra").

Spec §7.2 · §12.11 (capa de aplicación).

Tres comandos, misma forma que el resto: el dominio valida —`Obra.crear` y
los métodos de edición de la entidad—, el caso de uso ordena la secuencia y
el repositorio persiste. El alta masiva es el mismo `Obra.crear` aplicado
fila por fila: **todas** se validan antes de tocar la base, para que un lote
con una fila mala no deje media alta hecha (§11.2 `POST /obras/bulk`).

Quién puede ejecutarlos es RBAC del borde (Control de obra, §11.2) reforzado
por RLS (§12.4); por eso ningún comando de aquí carga un `rol`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from obractrl.application.casos_uso.generar_obra_desde_prototipo import (
    ObraNoEncontrada,
    reconstruir_obra,
)
from obractrl.application.puertos.repositorios import (
    RegistroNoEncontrado,
    RepositorioObras,
    UnidadDeTrabajo,
)
from obractrl.domain.obras.reglas import ErrorDeObra, Obra

__all__ = [
    "SIN_CAMBIO",
    "ActualizarObra",
    "ComandoActualizarObra",
    "ComandoCrearObra",
    "ComandoCrearObrasEnLote",
    "CrearObra",
    "CrearObrasEnLote",
    "ErrorDeObra",
    "ObraCreada",
    "ObraNoEncontrada",
    "ObrasCreadas",
]


class _SinCambio:
    """Centinela de `PATCH`: distingue "no lo mandaron" de "mándalo a null".

    Sin él, `residente_id=None` sería ambiguo y no habría forma de **liberar**
    una obra de su residente (§11.2 `PATCH /obras/{id}`).
    """

    def __repr__(self) -> str:  # pragma: no cover - solo para depurar
        return "SIN_CAMBIO"


SIN_CAMBIO = _SinCambio()


@dataclass(frozen=True, slots=True)
class ComandoCrearObra:
    cluster_id: UUID
    clave: str
    prototipo_id: UUID | None = None
    residente_id: UUID | None = None
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    m2: Decimal | None = None
    es_urba: bool = False


@dataclass(frozen=True, slots=True)
class ComandoCrearObrasEnLote:
    obras: list[ComandoCrearObra] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ComandoActualizarObra:
    obra_id: UUID
    clave: str | None = None
    residente_id: UUID | _SinCambio | None = SIN_CAMBIO
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    m2: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ObraCreada:
    id: UUID
    obra: Obra


@dataclass(frozen=True, slots=True)
class ObrasCreadas:
    ids: list[UUID]
    obras: list[Obra]


def _a_registro(obra: Obra) -> dict:
    """Aplana la entidad a lo que espera el repositorio."""
    return {
        "cluster_id": obra.cluster_id,
        "clave": str(obra.clave),
        "prototipo_id": obra.prototipo_id,
        "residente_id": obra.residente_id,
        "fecha_inicio": obra.fecha_inicio,
        "fecha_fin": obra.fecha_fin,
        "m2": obra.m2,
        "es_urba": obra.es_urba,
    }


def _construir(cmd: ComandoCrearObra) -> Obra:
    return Obra.crear(
        cluster_id=str(cmd.cluster_id),
        clave=cmd.clave,
        prototipo_id=str(cmd.prototipo_id) if cmd.prototipo_id else None,
        residente_id=str(cmd.residente_id) if cmd.residente_id else None,
        fecha_inicio=cmd.fecha_inicio,
        fecha_fin=cmd.fecha_fin,
        m2=cmd.m2,
        es_urba=cmd.es_urba,
    )


class CrearObra:
    """`POST /obras` (Control de obra, §11.2)."""

    def __init__(self, *, obras: RepositorioObras, uow: UnidadDeTrabajo) -> None:
        self._obras = obras
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearObra) -> ObraCreada:
        obra = _construir(cmd)
        async with self._uow:
            obra_id = await self._obras.crear(_a_registro(obra))
            await self._uow.commit()
        return ObraCreada(id=obra_id, obra=obra)


class CrearObrasEnLote:
    """`POST /obras/bulk` — alta masiva (Control de obra, §11.2)."""

    def __init__(self, *, obras: RepositorioObras, uow: UnidadDeTrabajo) -> None:
        self._obras = obras
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearObrasEnLote) -> ObrasCreadas:
        if not cmd.obras:
            raise ErrorDeObra("El lote no trae ninguna obra que dar de alta.")

        # Se valida el lote completo ANTES de abrir la transacción: así el
        # error de la fila 40 no depende de que las 39 anteriores ya hubieran
        # entrado, y el mensaje sale de una sola pasada.
        entidades = [_construir(uno) for uno in cmd.obras]

        async with self._uow:
            ids = await self._obras.crear_en_lote(
                [_a_registro(obra) for obra in entidades]
            )
            await self._uow.commit()
        return ObrasCreadas(ids=ids, obras=entidades)


class ActualizarObra:
    """`PATCH /obras/{id}` (Control de obra, §11.2).

    Solo los campos presentes en el comando se tocan. El estatus **no** es
    editable por aquí: lo deriva el avance y lo cierra el cierre de obra
    (§6, §11.3 D), no un `PATCH`.
    """

    def __init__(self, *, obras: RepositorioObras, uow: UnidadDeTrabajo) -> None:
        self._obras = obras
        self._uow = uow

    async def ejecutar(self, cmd: ComandoActualizarObra) -> Obra:
        fila = await self._obras.obtener(cmd.obra_id)
        if fila is None:
            raise ObraNoEncontrada(f"Obra {cmd.obra_id} no encontrada en tu alcance.")

        obra = reconstruir_obra(fila)
        cambios: dict = {}

        if cmd.clave is not None:
            obra.renombrar(cmd.clave)
            cambios["clave"] = str(obra.clave)

        if not isinstance(cmd.residente_id, _SinCambio):
            obra.asignar_residente(
                str(cmd.residente_id) if cmd.residente_id else None
            )
            cambios["residente_id"] = obra.residente_id

        if cmd.fecha_inicio is not None or cmd.fecha_fin is not None:
            obra.programar_fechas(inicio=cmd.fecha_inicio, fin=cmd.fecha_fin)
            if cmd.fecha_inicio is not None:
                cambios["fecha_inicio"] = obra.fecha_inicio
            if cmd.fecha_fin is not None:
                cambios["fecha_fin"] = obra.fecha_fin

        if cmd.m2 is not None:
            obra.redimensionar(cmd.m2)
            cambios["m2"] = obra.m2

        if not cambios:
            return obra

        async with self._uow:
            try:
                await self._obras.actualizar(cmd.obra_id, cambios)
            except RegistroNoEncontrado as exc:
                raise ObraNoEncontrada(
                    f"Obra {cmd.obra_id} ya no está en tu alcance."
                ) from exc
            await self._uow.commit()

        return obra
