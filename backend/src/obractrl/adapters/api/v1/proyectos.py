"""Endpoints de la estructura de proyecto.

Spec §11.2 (Proyecto · Obra) · §7.2 · §8.3 (frentes).

Controladores delgados: validan el DTO, delegan en el caso de uso y mapean el
resultado. **Cero lógica de negocio aquí** (§12.11) — las invariantes viven en
`domain.proyectos.reglas`.

Roles (§11.2): `GET/POST /proyectos`, `/clusters` y `/prototipos` son de
Control de obra y Super intendente; `GET /frentes` es de todos, porque el
catálogo de frentes lo consulta cualquier pantalla (§8.3).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    CrearClusterDep,
    CrearPrototipoDep,
    CrearProyectoDep,
)
from obractrl.adapters.api.dependencias import SesionRLS, exigir_rol
from obractrl.adapters.repos.clusters_sql import RepositorioClustersSQL
from obractrl.adapters.repos.frentes_sql import RepositorioFrentesSQL
from obractrl.adapters.repos.prototipo_nodo_sql import RepositorioPrototipoNodoSQL
from obractrl.adapters.repos.prototipos_sql import RepositorioPrototiposSQL
from obractrl.adapters.repos.proyectos_sql import RepositorioProyectosSQL
from obractrl.application.casos_uso.gestionar_proyecto import (
    ComandoCrearCluster,
    ComandoCrearPrototipo,
    ComandoCrearProyecto,
)
from obractrl.domain.proyectos.reglas import Cluster, Prototipo, Proyecto
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["proyectos"])

CONFIGURA = Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE))
"""Configuración de la estructura de proyecto: C y SI (§5.1, §11.2)."""

FiltroProyecto = Annotated[
    UUID | None, Query(description="Acota al proyecto indicado (§7.2).")
]


# --- Proyectos -----------------------------------------------------------


class CrearProyectoPeticion(BaseModel):
    clave: str = Field(min_length=1, description="Clave única del proyecto (§3.3).")
    nombre: str = Field(min_length=1)
    ubicacion: str | None = None
    inicio: date | None = None
    fin_estimado: date | None = None


class ProyectoRespuesta(BaseModel):
    id: UUID
    clave: str
    nombre: str
    ubicacion: str | None = None
    inicio: date | None = None
    fin_estimado: date | None = None
    estatus: str = "activo"

    @classmethod
    def desde_dominio(cls, proyecto_id: UUID, proyecto: Proyecto) -> ProyectoRespuesta:
        return cls(
            id=proyecto_id,
            clave=str(proyecto.clave),
            nombre=proyecto.nombre,
            ubicacion=proyecto.ubicacion,
            inicio=proyecto.inicio,
            fin_estimado=proyecto.fin_estimado,
            estatus="activo" if proyecto.activo else "inactivo",
        )

    @classmethod
    def desde_fila(cls, fila: dict) -> ProyectoRespuesta:
        return cls(
            id=fila["id"],
            clave=fila["clave"],
            nombre=fila["nombre"],
            ubicacion=fila["ubicacion"],
            inicio=fila["inicio"],
            fin_estimado=fila["fin_estimado"],
            estatus=fila["estatus"],
        )


@router.get(
    "/proyectos",
    response_model=list[ProyectoRespuesta],
    summary="Proyectos dentro del alcance",
    dependencies=[CONFIGURA],
)
async def listar_proyectos(sesion: SesionRLS) -> list[ProyectoRespuesta]:
    """Lectura simple sin orquestación de dominio —como `GET /cierres`— así que
    consulta el repo directo: RLS ya acota el alcance (§12.4)."""
    filas = await RepositorioProyectosSQL(sesion).listar()
    return [ProyectoRespuesta.desde_fila(fila) for fila in filas]


@router.post(
    "/proyectos",
    response_model=ProyectoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de proyecto",
    dependencies=[CONFIGURA],
    responses={422: {"description": "Datos de proyecto inválidos (§7.2)."}},
)
async def crear_proyecto(
    peticion: CrearProyectoPeticion, caso_uso: CrearProyectoDep
) -> ProyectoRespuesta:
    """Control de obra y Super intendente dan de alta un proyecto (§11.2)."""
    creado = await caso_uso.ejecutar(
        ComandoCrearProyecto(
            clave=peticion.clave,
            nombre=peticion.nombre,
            ubicacion=peticion.ubicacion,
            inicio=peticion.inicio,
            fin_estimado=peticion.fin_estimado,
        )
    )
    return ProyectoRespuesta.desde_dominio(creado.id, creado.proyecto)


# --- Clusters ------------------------------------------------------------


class CrearClusterPeticion(BaseModel):
    proyecto_id: UUID
    clave: str = Field(min_length=1)
    nombre: str = Field(min_length=1)


class ClusterRespuesta(BaseModel):
    id: UUID
    proyecto_id: UUID
    clave: str
    nombre: str

    @classmethod
    def desde_dominio(cls, cluster_id: UUID, cluster: Cluster) -> ClusterRespuesta:
        return cls(
            id=cluster_id,
            proyecto_id=UUID(cluster.proyecto_id),
            clave=str(cluster.clave),
            nombre=cluster.nombre,
        )

    @classmethod
    def desde_fila(cls, fila: dict) -> ClusterRespuesta:
        return cls(
            id=fila["id"],
            proyecto_id=fila["proyecto_id"],
            clave=fila["clave"],
            nombre=fila["nombre"],
        )


@router.get(
    "/clusters",
    response_model=list[ClusterRespuesta],
    summary="Clusters (manzanas) dentro del alcance",
    dependencies=[CONFIGURA],
)
async def listar_clusters(
    sesion: SesionRLS, proyecto_id: FiltroProyecto = None
) -> list[ClusterRespuesta]:
    filas = await RepositorioClustersSQL(sesion).listar(proyecto_id)
    return [ClusterRespuesta.desde_fila(fila) for fila in filas]


@router.post(
    "/clusters",
    response_model=ClusterRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de cluster",
    dependencies=[CONFIGURA],
    responses={422: {"description": "Datos de cluster inválidos (§7.2)."}},
)
async def crear_cluster(
    peticion: CrearClusterPeticion, caso_uso: CrearClusterDep
) -> ClusterRespuesta:
    creado = await caso_uso.ejecutar(
        ComandoCrearCluster(
            proyecto_id=peticion.proyecto_id,
            clave=peticion.clave,
            nombre=peticion.nombre,
        )
    )
    return ClusterRespuesta.desde_dominio(creado.id, creado.cluster)


# --- Prototipos ----------------------------------------------------------


class CrearPrototipoPeticion(BaseModel):
    proyecto_id: UUID
    clave: str = Field(min_length=1, description="Clave con prefijo CAS (§10.1).")
    nombre: str = Field(min_length=1)
    m2: Decimal | None = None
    niveles: int | None = None
    recamaras: int | None = None


class PrototipoRespuesta(BaseModel):
    id: UUID
    proyecto_id: UUID
    clave: str
    nombre: str
    m2: Decimal | None = None
    niveles: int | None = None
    recamaras: int | None = None

    @classmethod
    def desde_dominio(
        cls, prototipo_id: UUID, prototipo: Prototipo
    ) -> PrototipoRespuesta:
        return cls(
            id=prototipo_id,
            proyecto_id=UUID(prototipo.proyecto_id),
            clave=str(prototipo.clave),
            nombre=prototipo.nombre,
            m2=prototipo.m2,
            niveles=prototipo.niveles,
            recamaras=prototipo.recamaras,
        )

    @classmethod
    def desde_fila(cls, fila: dict) -> PrototipoRespuesta:
        return cls(
            id=fila["id"],
            proyecto_id=fila["proyecto_id"],
            clave=fila["clave"],
            nombre=fila["nombre"],
            m2=fila["m2"],
            niveles=fila["niveles"],
            recamaras=fila["recamaras"],
        )


@router.get(
    "/prototipos",
    response_model=list[PrototipoRespuesta],
    summary="Prototipos (modelos de vivienda)",
    dependencies=[CONFIGURA],
)
async def listar_prototipos(
    sesion: SesionRLS, proyecto_id: FiltroProyecto = None
) -> list[PrototipoRespuesta]:
    filas = await RepositorioPrototiposSQL(sesion).listar(proyecto_id)
    return [PrototipoRespuesta.desde_fila(fila) for fila in filas]


@router.post(
    "/prototipos",
    response_model=PrototipoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de prototipo",
    dependencies=[CONFIGURA],
    responses={422: {"description": "Datos de prototipo inválidos (§7.2)."}},
)
async def crear_prototipo(
    peticion: CrearPrototipoPeticion, caso_uso: CrearPrototipoDep
) -> PrototipoRespuesta:
    creado = await caso_uso.ejecutar(
        ComandoCrearPrototipo(
            proyecto_id=peticion.proyecto_id,
            clave=peticion.clave,
            nombre=peticion.nombre,
            m2=peticion.m2,
            niveles=peticion.niveles,
            recamaras=peticion.recamaras,
        )
    )
    return PrototipoRespuesta.desde_dominio(creado.id, creado.prototipo)


class NodoPrototipoRespuesta(BaseModel):
    id: UUID
    parent_id: UUID | None = None
    tipo: Literal["nivel", "etapa", "concepto"]
    nombre: str
    clave: str | None = None
    concepto_id: UUID | None = None
    nivel_id: UUID | None = None
    etapa_id: UUID | None = None
    orden: int = 0
    cantidad: Decimal | None = None
    ponderacion: Decimal | None = None

    @classmethod
    def desde_fila(cls, fila: dict) -> NodoPrototipoRespuesta:
        return cls(**fila)


@router.get(
    "/prototipos/{prototipo_id}/nodos",
    response_model=list[NodoPrototipoRespuesta],
    summary="Árbol WBS del prototipo: nivel → etapa → concepto",
    dependencies=[CONFIGURA],
)
async def listar_nodos_de_prototipo(
    prototipo_id: UUID, sesion: SesionRLS
) -> list[NodoPrototipoRespuesta]:
    """Nodos del prototipo en recorrido padre-antes-que-hijos (§7.4), listos
    para anidar en el front sin volver a ordenar. Los da de alta el
    cargador de presupuesto jerárquico (§10.6); un prototipo sin ingeniería
    cargada todavía devuelve una lista vacía, no un error."""
    filas = await RepositorioPrototipoNodoSQL(sesion).arbol(prototipo_id)
    return [NodoPrototipoRespuesta.desde_fila(fila) for fila in filas]


# --- Frentes -------------------------------------------------------------


class FrenteRespuesta(BaseModel):
    id: UUID
    clave: str
    nombre: str
    etapa: str | None = None
    orden: int = 0
    color: str | None = None

    @classmethod
    def desde_fila(cls, fila: dict) -> FrenteRespuesta:
        return cls(
            id=fila["id"],
            clave=fila["clave"],
            nombre=fila["nombre"],
            etapa=fila["etapa"],
            orden=fila["orden"],
            color=fila["color"],
        )


@router.get(
    "/frentes",
    response_model=list[FrenteRespuesta],
    summary="Catálogo de frentes de obra",
)
async def listar_frentes(
    sesion: SesionRLS,
    incluir_inactivos: Annotated[
        bool, Query(description="Incluye los frentes dados de baja (§8.7).")
    ] = False,
) -> list[FrenteRespuesta]:
    """Todos los roles: el catálogo de frentes alimenta filtros y Gantt (§8.3).

    Es semilla editable de organización (§8.7), así que RLS lo acota por org
    y no por alcance de obra.
    """
    filas = await RepositorioFrentesSQL(sesion).listar(
        solo_activos=not incluir_inactivos
    )
    return [FrenteRespuesta.desde_fila(fila) for fila in filas]
