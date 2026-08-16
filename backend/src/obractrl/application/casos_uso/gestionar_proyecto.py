"""Caso de uso: alta de la estructura de proyecto (§11.2 "Proyecto · Obra").

Spec §7.2 · §12.11 (capa de aplicación).

Tres altas —proyecto, cluster y prototipo— con la misma forma que el resto:
el dominio valida (`domain.proyectos.reglas`), el caso de uso ordena la
secuencia y el repositorio persiste. Quién puede ejecutarlas es RBAC del
borde (Control de obra y Super intendente, §11.2) reforzado por RLS (§12.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from obractrl.application.puertos.repositorios import (
    RepositorioClusters,
    RepositorioPrototipos,
    RepositorioProyectos,
    UnidadDeTrabajo,
)
from obractrl.domain.proyectos.reglas import Cluster, ErrorDeProyecto, Prototipo, Proyecto

__all__ = [
    "ClusterCreado",
    "ComandoCrearCluster",
    "ComandoCrearPrototipo",
    "ComandoCrearProyecto",
    "CrearCluster",
    "CrearPrototipo",
    "CrearProyecto",
    "ErrorDeProyecto",
    "PrototipoCreado",
    "ProyectoCreado",
]


@dataclass(frozen=True, slots=True)
class ComandoCrearProyecto:
    clave: str
    nombre: str
    ubicacion: str | None = None
    inicio: date | None = None
    fin_estimado: date | None = None


@dataclass(frozen=True, slots=True)
class ComandoCrearCluster:
    proyecto_id: UUID
    clave: str
    nombre: str


@dataclass(frozen=True, slots=True)
class ComandoCrearPrototipo:
    proyecto_id: UUID
    clave: str
    nombre: str
    m2: Decimal | None = None
    niveles: int | None = None
    recamaras: int | None = None


@dataclass(frozen=True, slots=True)
class ProyectoCreado:
    id: UUID
    proyecto: Proyecto


@dataclass(frozen=True, slots=True)
class ClusterCreado:
    id: UUID
    cluster: Cluster


@dataclass(frozen=True, slots=True)
class PrototipoCreado:
    id: UUID
    prototipo: Prototipo


class CrearProyecto:
    """`POST /proyectos` (Control de obra y Super intendente, §11.2)."""

    def __init__(
        self, *, proyectos: RepositorioProyectos, uow: UnidadDeTrabajo
    ) -> None:
        self._proyectos = proyectos
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearProyecto) -> ProyectoCreado:
        proyecto = Proyecto.crear(
            clave=cmd.clave,
            nombre=cmd.nombre,
            ubicacion=cmd.ubicacion,
            inicio=cmd.inicio,
            fin_estimado=cmd.fin_estimado,
        )
        async with self._uow:
            proyecto_id = await self._proyectos.crear(
                {
                    "clave": str(proyecto.clave),
                    "nombre": proyecto.nombre,
                    "ubicacion": proyecto.ubicacion,
                    "inicio": proyecto.inicio,
                    "fin_estimado": proyecto.fin_estimado,
                }
            )
            await self._uow.commit()
        return ProyectoCreado(id=proyecto_id, proyecto=proyecto)


class CrearCluster:
    """`POST /clusters` (Control de obra y Super intendente, §11.2)."""

    def __init__(self, *, clusters: RepositorioClusters, uow: UnidadDeTrabajo) -> None:
        self._clusters = clusters
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearCluster) -> ClusterCreado:
        cluster = Cluster.crear(
            proyecto_id=str(cmd.proyecto_id),
            clave=cmd.clave,
            nombre=cmd.nombre,
        )
        async with self._uow:
            cluster_id = await self._clusters.crear(
                {
                    "proyecto_id": cluster.proyecto_id,
                    "clave": str(cluster.clave),
                    "nombre": cluster.nombre,
                }
            )
            await self._uow.commit()
        return ClusterCreado(id=cluster_id, cluster=cluster)


class CrearPrototipo:
    """`POST /prototipos` (Control de obra y Super intendente, §11.2)."""

    def __init__(
        self, *, prototipos: RepositorioPrototipos, uow: UnidadDeTrabajo
    ) -> None:
        self._prototipos = prototipos
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearPrototipo) -> PrototipoCreado:
        prototipo = Prototipo.crear(
            proyecto_id=str(cmd.proyecto_id),
            clave=cmd.clave,
            nombre=cmd.nombre,
            m2=cmd.m2,
            niveles=cmd.niveles,
            recamaras=cmd.recamaras,
        )
        async with self._uow:
            prototipo_id = await self._prototipos.crear(
                {
                    "proyecto_id": prototipo.proyecto_id,
                    "clave": str(prototipo.clave),
                    "nombre": prototipo.nombre,
                    "m2": prototipo.m2,
                    "niveles": prototipo.niveles,
                    "recamaras": prototipo.recamaras,
                }
            )
            await self._uow.commit()
        return PrototipoCreado(id=prototipo_id, prototipo=prototipo)
