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
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    CrearClusterDep,
    CrearPrototipoDep,
    CrearProyectoDep,
)
from obractrl.adapters.api.dependencias import SesionRLS, exigir_rol
from obractrl.adapters.repos.cargas_sql import RepositorioCargasSQL
from obractrl.adapters.repos.clusters_sql import RepositorioClustersSQL
from obractrl.adapters.repos.especialidades_sql import RepositorioEspecialidadesSQL
from obractrl.adapters.repos.frentes_sql import RepositorioFrentesSQL
from obractrl.adapters.repos.niveles_etapas_sql import RepositorioNivelesEtapasSQL
from obractrl.adapters.repos.prototipo_nodo_sql import RepositorioPrototipoNodoSQL
from obractrl.adapters.repos.prototipos_sql import RepositorioPrototiposSQL
from obractrl.adapters.repos.proyectos_sql import RepositorioProyectosSQL
from obractrl.application.casos_uso.gestionar_proyecto import (
    ComandoCrearCluster,
    ComandoCrearPrototipo,
    ComandoCrearProyecto,
)
from obractrl.domain.proyectos.reglas import Cluster, Prototipo, Proyecto
from obractrl.domain.shared.diccionario import Rol, TipoConcepto

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
    plantas: int | None = Field(
        default=None, description="1 o 2 (planta baja y alta); ver `PUT /prototipos/{id}/plantas`."
    )

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
            plantas=fila.get("plantas"),
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
    tipo: Literal["nivel", "etapa", "agrupador", "concepto"]
    nombre: str
    clave: str | None = None
    concepto_id: UUID | None = None
    nivel_id: UUID | None = None
    etapa_id: UUID | None = None
    orden: int = 0
    cantidad: Decimal | None = None
    ponderacion: Decimal | None = None
    concepto_tipo: TipoConcepto | None = Field(
        default=None,
        description=(
            "`tipo` no distingue concepto de concepto auxiliar —los dos se "
            "guardan como 'concepto', §10.1—; este campo sí, tomado del "
            "catálogo. `null` en nodos sin `concepto_id` (nivel/etapa)."
        ),
    )

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


class CrearFrentePeticion(BaseModel):
    clave: str = Field(min_length=1, description="Clave única del catálogo (§3.3).")
    nombre: str = Field(min_length=1)
    orden: int = Field(default=0, description="Orden de obra en que se listan.")
    color: str | None = Field(
        default=None, description="Token de color para el Gantt; opcional."
    )


class EditarFrentePeticion(BaseModel):
    """Solo lo que cambia. La `clave` no está: es la identidad (§3.3)."""

    nombre: str | None = Field(default=None, min_length=1)
    orden: int | None = None
    color: str | None = None
    estatus: str | None = Field(
        default=None, description="`activo` o `inactivo` (§8.7)."
    )


class EtapasDelFrentePeticion(BaseModel):
    """Las etapas que pertenecen al frente, **completas**.

    Es un reemplazo y no un alta: lo que no venga en la lista se queda sin
    frente. Así mover una etapa de un frente a otro es una llamada y no dos, y
    la pantalla no tiene que llevar la cuenta de lo que quitó.
    """

    etapa_ids: list[UUID] = Field(default_factory=list)


@router.post(
    "/frentes",
    response_model=FrenteRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Dar de alta un frente",
    dependencies=[CONFIGURA],
)
async def crear_frente(
    peticion: CrearFrentePeticion, sesion: SesionRLS
) -> FrenteRespuesta:
    """Los ocho del §8.3 son la semilla, no la lista cerrada (§8.7).

    Una constructora agrupa sus frentes como los trabaja: `INSTALACIONES`
    cubriendo hidráulica, sanitaria, eléctrica y gas es un frente suyo aunque
    el spec liste esos cuatro por separado — el spec nombra gremios y el frente
    es una decisión de cómo se contrata.
    """
    repo = RepositorioFrentesSQL(sesion)
    frente_id = await repo.crear(peticion.model_dump())
    await sesion.commit()
    return FrenteRespuesta(
        id=frente_id,
        clave=peticion.clave,
        nombre=peticion.nombre,
        orden=peticion.orden,
        color=peticion.color,
    )


@router.patch(
    "/frentes/{frente_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Editar un frente",
    dependencies=[CONFIGURA],
)
async def editar_frente(
    frente_id: UUID, peticion: EditarFrentePeticion, sesion: SesionRLS
) -> None:
    cambios = peticion.model_dump(exclude_unset=True, exclude_none=True)
    await RepositorioFrentesSQL(sesion).actualizar(frente_id, cambios)
    await sesion.commit()


@router.put(
    "/frentes/{frente_id}/etapas",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Qué etapas constructivas agrupa el frente",
    dependencies=[CONFIGURA],
)
async def asignar_etapas_al_frente(
    frente_id: UUID, peticion: EtapasDelFrentePeticion, sesion: SesionRLS
) -> None:
    """El mapeo del §8.3 que la migración 0045 hizo posible.

    Una etapa pertenece a **un** frente: tomarla aquí la quita del que tuviera.
    Si estuviera en dos, su trabajo se contaría dos veces al planear cuántas
    cuadrillas hacen falta, que es la cifra para la que existe este mapeo.
    """
    await RepositorioNivelesEtapasSQL(sesion).asignar_frente(
        frente_id=frente_id, etapa_ids=peticion.etapa_ids
    )
    await sesion.commit()


# --- Especialidades: el oficio del concepto (§8.3, migración 0047) ---------


class EspecialidadRespuesta(BaseModel):
    """Un oficio del catálogo: ESTRUCTURA, ACABADOS, CARPINTERIA…

    El segundo eje del trabajo. El **frente** dice qué clase de contratista se
    contrata —OBRA, INSTALACIONES— y cuelga de la etapa; la **especialidad**
    dice qué oficio hace falta y cuelga del concepto. Hacen falta los dos: un
    frente entero es demasiado grueso para contratar, porque en la obra real
    OBRA concentra el 90% de las jornadas.
    """

    id: UUID
    clave: str
    nombre: str
    orden: int = 0
    estatus: str = "activo"

    @classmethod
    def desde_fila(cls, fila: dict[str, Any]) -> EspecialidadRespuesta:
        return cls(
            id=fila["id"],
            clave=fila["clave"],
            nombre=fila["nombre"],
            orden=fila["orden"],
            estatus=str(fila.get("estatus") or "activo"),
        )


class CrearEspecialidadPeticion(BaseModel):
    clave: str = Field(min_length=1, description="Clave única del catálogo (§3.3).")
    nombre: str = Field(min_length=1)
    orden: int = Field(default=0)


class EditarEspecialidadPeticion(BaseModel):
    """Solo lo que cambia. La `clave` no está: es la identidad (§3.3)."""

    nombre: str | None = Field(default=None, min_length=1)
    orden: int | None = None
    estatus: str | None = Field(default=None, description="`activo` o `inactivo`.")


class ConceptosDelOficioPeticion(BaseModel):
    """Los conceptos que se ejecutan con ese oficio, **completos**.

    Reemplazo y no alta, igual que las etapas de un frente: lo que no venga en
    la lista se queda sin oficio. Así mover un concepto de un oficio a otro es
    una llamada y no dos.
    """

    concepto_ids: list[UUID] = Field(default_factory=list)


class FusionarEspecialidadPeticion(BaseModel):
    absorbida_id: UUID = Field(
        description="El oficio que desaparece. Todo lo suyo pasa al de la ruta."
    )


class FusionRespuesta(BaseModel):
    conceptos: int
    contratistas: int
    alias_registrado: str = Field(
        description=(
            "El nombre del oficio absorbido queda homologado (§10.3): la "
            "próxima carga del catálogo no lo vuelve a crear."
        )
    )


@router.get(
    "/especialidades",
    response_model=list[EspecialidadRespuesta],
    summary="Catálogo de oficios",
)
async def listar_especialidades(
    sesion: SesionRLS,
    incluir_inactivos: Annotated[
        bool, Query(description="Incluye los dados de baja (§8.7).")
    ] = False,
) -> list[EspecialidadRespuesta]:
    """Todos los roles: alimenta el desglose de la pantalla de cuadrillas."""
    filas = await RepositorioEspecialidadesSQL(sesion).listar(
        solo_activos=not incluir_inactivos
    )
    return [EspecialidadRespuesta.desde_fila(fila) for fila in filas]


@router.post(
    "/especialidades",
    response_model=EspecialidadRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Dar de alta un oficio",
    dependencies=[CONFIGURA],
)
async def crear_especialidad(
    peticion: CrearEspecialidadPeticion, sesion: SesionRLS
) -> EspecialidadRespuesta:
    repo = RepositorioEspecialidadesSQL(sesion)
    nuevo_id = await repo.crear(peticion.model_dump())
    await sesion.commit()
    return EspecialidadRespuesta(
        id=nuevo_id,
        clave=peticion.clave,
        nombre=peticion.nombre,
        orden=peticion.orden,
    )


@router.patch(
    "/especialidades/{especialidad_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Editar un oficio",
    dependencies=[CONFIGURA],
)
async def editar_especialidad(
    especialidad_id: UUID, peticion: EditarEspecialidadPeticion, sesion: SesionRLS
) -> None:
    cambios = peticion.model_dump(exclude_unset=True, exclude_none=True)
    await RepositorioEspecialidadesSQL(sesion).actualizar(especialidad_id, cambios)
    await sesion.commit()


@router.put(
    "/especialidades/{especialidad_id}/conceptos",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Qué conceptos se ejecutan con este oficio",
    dependencies=[CONFIGURA],
)
async def asignar_conceptos_al_oficio(
    especialidad_id: UUID, peticion: ConceptosDelOficioPeticion, sesion: SesionRLS
) -> None:
    """Con esto se llena a mano lo que el archivo no trajo (§8.3, 0047).

    El catálogo del cliente cubre 461 de 898 conceptos; el resto no tiene
    oficio y sale agrupado como «Sin oficio» al desglosar un frente. Aquí se
    completa sin volver a subir un Excel.

    Un concepto tiene **un** oficio: tomarlo aquí lo quita del que tuviera.
    """
    await RepositorioEspecialidadesSQL(sesion).reemplazar_conceptos(
        especialidad_id, peticion.concepto_ids
    )
    await sesion.commit()


@router.post(
    "/especialidades/{especialidad_id}/fusionar",
    response_model=FusionRespuesta,
    summary="Unir dos oficios que resultaron ser el mismo",
    dependencies=[CONFIGURA],
)
async def fusionar_especialidad(
    especialidad_id: UUID, peticion: FusionarEspecialidadPeticion, sesion: SesionRLS
) -> FusionRespuesta:
    """Todo lo de la absorbida pasa a la de la ruta, y la absorbida desaparece.

    Pasa cuando el catálogo escribe el mismo oficio de dos formas —
    `EQUIPAMIENTO` y `EQUIPAMIENTOS`, con prefijos de clave distintos—:
    separados parten el desglose de un frente en dos renglones que nadie puede
    contratar por separado.

    El nombre de la absorbida queda registrado como alias (§10.3). Sin eso, la
    próxima carga del mismo archivo —que sigue trayendo los dos nombres— la
    volvería a crear y la fusión se desharía sola.
    """
    if peticion.absorbida_id == especialidad_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Un oficio no se puede fusionar consigo mismo.",
        )

    repo = RepositorioEspecialidadesSQL(sesion)
    por_id = {str(f["id"]): f for f in await repo.listar(solo_activos=False)}
    destino = por_id.get(str(especialidad_id))
    absorbida = por_id.get(str(peticion.absorbida_id))
    if destino is None or absorbida is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alguno de los dos oficios no existe en tu organización.",
        )

    movido = await repo.fusionar(
        destino=especialidad_id, absorbida=peticion.absorbida_id
    )
    await RepositorioCargasSQL(sesion).registrar_mapeo(
        entidad="especialidad",
        alias=str(absorbida["nombre"]),
        clave_canonica=str(destino["clave"]),
    )
    await sesion.commit()
    return FusionRespuesta(
        conceptos=movido["conceptos"],
        contratistas=movido["contratistas"],
        alias_registrado=str(absorbida["nombre"]),
    )
