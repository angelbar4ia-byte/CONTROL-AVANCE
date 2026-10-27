"""Escenario «Nuevo» (cerebro WORKFLOWS.md §8.9; D-571, D-574): se entra por el cuantificador y
se crea la obra desde ahí, sin prototipo de dónde copiar.

Se elige el **catálogo base de 1 o de 2 plantas** —los dos tipos de prototipo— y se forma
tomando la estructura y los conceptos de ese prototipo, **sin cantidades**: llegan midiendo. Es
un prototipo de un solo uso (`de_una_obra`): exclusivo de su obra, y ahí lo que se mide es el
presupuesto. Crear la obra y su presupuesto es un solo acto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.puertos.partes import RepositorioPartes
from obractrl.application.puertos.repositorios import (
    RepositorioClusters,
    RepositorioObras,
    RepositorioPrototipoNodo,
    RepositorioPrototipos,
    UnidadDeTrabajo,
)
from obractrl.domain.obras.reglas import Obra
from obractrl.domain.proyectos.reglas import Prototipo

# El número de plantas ya fija el plazo base (D-419): 28 semanas una planta, 30 dos.
PLAZO_BASE_SEMANAS = {1: 28, 2: 30}


class ErrorDeCatalogoBase(ValueError):
    """No hay con qué formar el catálogo base pedido."""


@dataclass(frozen=True, slots=True)
class ComandoCrearObraDesdeCatalogoBase:
    cluster_id: UUID
    clave: str
    plantas: int
    residente_id: UUID | None = None


class ConsultarCatalogosBase:
    """`GET /catalogos-base`: de qué prototipo sale el catálogo de 1 y el de 2 plantas."""

    def __init__(self, *, partes: RepositorioPartes) -> None:
        self._partes = partes

    async def ejecutar(self) -> list[dict[str, Any]]:
        por_plantas = {f["plantas"]: f for f in await self._partes.catalogos_base()}
        return [
            {
                "plantas": n,
                "plazo_base_semanas": PLAZO_BASE_SEMANAS[n],
                "prototipo_clave": por_plantas[n]["clave"] if n in por_plantas else None,
                "prototipo_nombre": por_plantas[n]["nombre"] if n in por_plantas else None,
                "n_nodos": int(por_plantas[n]["n_nodos"]) if n in por_plantas else 0,
                "disponible": n in por_plantas and int(por_plantas[n]["n_nodos"]) > 0,
            }
            for n in (1, 2)
        ]


class CrearObraDesdeCatalogoBase:
    """`POST /obras/desde-catalogo-base` (Control de obra): la obra «Nueva» y su catálogo."""

    def __init__(
        self,
        *,
        obras: RepositorioObras,
        clusters: RepositorioClusters,
        prototipos: RepositorioPrototipos,
        prototipo_nodos: RepositorioPrototipoNodo,
        partes: RepositorioPartes,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._obras = obras
        self._clusters = clusters
        self._prototipos = prototipos
        self._prototipo_nodos = prototipo_nodos
        self._partes = partes
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearObraDesdeCatalogoBase) -> dict[str, Any]:
        if cmd.plantas not in PLAZO_BASE_SEMANAS:
            raise ErrorDeCatalogoBase("Una casa tiene 1 o 2 plantas.")
        cluster = await self._clusters.obtener(cmd.cluster_id)
        if cluster is None:
            raise ObraNoEncontrada(f"Cluster {cmd.cluster_id} no encontrado en tu alcance.")
        base = {f["plantas"]: f for f in await self._partes.catalogos_base()}.get(cmd.plantas)
        if base is None or int(base["n_nodos"]) == 0:
            raise ErrorDeCatalogoBase(
                f"No hay un prototipo de {cmd.plantas} "
                f"{'planta' if cmd.plantas == 1 else 'plantas'} con estructura de dónde formar el catálogo."
            )

        # Se validan los datos como en el alta normal, antes de escribir nada.
        prototipo = Prototipo.crear(
            proyecto_id=str(cluster["proyecto_id"]),
            clave=cmd.clave,
            nombre=cmd.clave,
            m2=base.get("m2"),
            niveles=base.get("niveles"),
            recamaras=base.get("recamaras"),
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
                    "plantas": cmd.plantas,
                    "de_una_obra": True,
                }
            )
            nodos = await self._prototipo_nodos.clonar_estructura(
                origen_prototipo_id=UUID(str(base["id"])),
                destino_prototipo_id=prototipo_id,
                sin_cantidades=True,
            )
            obra = Obra.crear(
                cluster_id=str(cmd.cluster_id),
                clave=cmd.clave,
                prototipo_id=str(prototipo_id),
                residente_id=str(cmd.residente_id) if cmd.residente_id else None,
            )
            obra_id = await self._obras.crear(
                {
                    "cluster_id": obra.cluster_id,
                    "clave": str(obra.clave),
                    "prototipo_id": obra.prototipo_id,
                    "residente_id": obra.residente_id,
                    "fecha_inicio": obra.fecha_inicio,
                    "fecha_fin": obra.fecha_fin,
                    "m2": obra.m2,
                    "es_urba": obra.es_urba,
                }
            )
            await self._uow.commit()
        return {
            "obra_id": obra_id,
            "prototipo_id": prototipo_id,
            "plantas": cmd.plantas,
            "plazo_base_semanas": PLAZO_BASE_SEMANAS[cmd.plantas],
            "base_clave": str(base["clave"]),
            "nodos": nodos,
        }


@dataclass(frozen=True, slots=True)
class ComandoCrearObraDesdeCero:
    cluster_id: UUID
    clave: str
    plantas: int | None = None
    residente_id: UUID | None = None


class CrearObraDesdeCero:
    """`POST /obras/desde-cero` (Control de obra): la obra del escenario 4 (D-578).

    *«El paramétrico primero y luego se mide.»* Es el único caso en que no hay obra anterior de
    dónde copiar: nace con un prototipo de un solo uso **vacío** y su presupuesto, donde los
    ensambles —uno por tipo de espacio, D-579— componen la estructura con cantidades estimadas.
    Después se mide por partes y lo medido sustituye a lo estimado.
    """

    def __init__(
        self,
        *,
        obras: RepositorioObras,
        clusters: RepositorioClusters,
        prototipos: RepositorioPrototipos,
        partes: RepositorioPartes,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._obras = obras
        self._clusters = clusters
        self._prototipos = prototipos
        self._partes = partes
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearObraDesdeCero) -> dict[str, Any]:
        if cmd.plantas is not None and cmd.plantas not in PLAZO_BASE_SEMANAS:
            raise ErrorDeCatalogoBase("Una casa tiene 1 o 2 plantas.")
        cluster = await self._clusters.obtener(cmd.cluster_id)
        if cluster is None:
            raise ObraNoEncontrada(f"Cluster {cmd.cluster_id} no encontrado en tu alcance.")
        prototipo = Prototipo.crear(
            proyecto_id=str(cluster["proyecto_id"]), clave=cmd.clave, nombre=cmd.clave
        )
        async with self._uow:
            prototipo_id = await self._prototipos.crear(
                {
                    "proyecto_id": prototipo.proyecto_id,
                    "clave": str(prototipo.clave),
                    "nombre": prototipo.nombre,
                    "plantas": cmd.plantas,
                    "de_una_obra": True,
                }
            )
            presupuesto_id = await self._partes.crear_presupuesto_parametrico(prototipo_id)
            obra = Obra.crear(
                cluster_id=str(cmd.cluster_id),
                clave=cmd.clave,
                prototipo_id=str(prototipo_id),
                residente_id=str(cmd.residente_id) if cmd.residente_id else None,
            )
            obra_id = await self._obras.crear(
                {
                    "cluster_id": obra.cluster_id,
                    "clave": str(obra.clave),
                    "prototipo_id": obra.prototipo_id,
                    "residente_id": obra.residente_id,
                    "fecha_inicio": obra.fecha_inicio,
                    "fecha_fin": obra.fecha_fin,
                    "m2": obra.m2,
                    "es_urba": obra.es_urba,
                }
            )
            await self._uow.commit()
        return {
            "obra_id": obra_id,
            "prototipo_id": prototipo_id,
            "presupuesto_id": presupuesto_id,
            "plantas": cmd.plantas,
        }
