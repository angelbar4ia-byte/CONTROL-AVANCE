"""Endpoints de programación y ruta crítica.

Spec §11.2 ("Programación · CPM") · §7.5 · §7.6 · §6 (ruta crítica) ·
§11.3 A.3 y C.4.

Controladores delgados: validan el DTO, delegan en el caso de uso y mapean el
resultado. **Cero lógica de negocio aquí** (§12.11) — las reglas viven en
`domain.programacion.reglas` y el cálculo en `domain.programacion.cpm`.

Roles (§11.2):

* `GET/POST /programas-base` y `GET /programas-base/{id}/items` — Control de
  obra: la plantilla de duraciones es configuración del prototipo (§5.1).
* `GET/POST /obras/{id}/programa` — Control de obra y Supervisor.
* `GET /obras/{id}/ruta-critica` — todos: el Residente ve la de su obra y RLS
  se encarga de que sea solo esa (§4, §12.4).
* `POST /obras/{id}/ruta-critica/recalcular` y
  `PATCH /actividades/{id}/programacion` — Supervisor y Control de obra.

Las lecturas simples consultan el repositorio directo, como `GET /obras`
(`adapters/api/v1/obras.py`): no hay orquestación de dominio que hacer y RLS
ya acota el alcance (§12.4).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from obractrl.adapters.api.casos_uso import (
    ConsultarRutaCriticaDep,
    CrearProgramaBaseDep,
    EditarProgramacionActividadDep,
    InstanciarProgramaObraDep,
    RecalcularRutaCriticaDep,
)
from obractrl.adapters.api.dependencias import SesionRLS, exigir_rol
from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.programas_sql import RepositorioProgramasSQL
from obractrl.application.casos_uso.gestionar_programacion import (
    ActividadEnRuta,
    ComandoCrearProgramaBase,
    ComandoEditarProgramacion,
    ComandoInstanciarPrograma,
    ComandoRecalcularRutaCritica,
    ProgramaBaseNoEncontrado,
    ProgramaInstanciadoEnObra,
    RutaCritica,
)
from obractrl.domain.programacion.cpm import Dependencia, TipoDependencia, Tramo
from obractrl.domain.programacion.reglas import ItemProgramaBase
from obractrl.domain.shared.diccionario import Rol

router = APIRouter(tags=["programacion"])

CONFIGURA_PROGRAMA = Depends(exigir_rol(Rol.CONTROL_OBRA))
"""Programas base: Control de obra (§11.2, §5.1 "Configuración")."""

PROGRAMA_DE_OBRA = Depends(exigir_rol(Rol.CONTROL_OBRA, Rol.SUPERVISOR))
"""Instanciar el cronograma, recalcular y ajustar actividades (§11.2)."""

_NO_ENCONTRADA: dict[int | str, dict[str, Any]] = {
    404: {"description": "No existe o está fuera de tu alcance (§12.4)."}
}

_CICLO: dict[int | str, dict[str, Any]] = {
    422: {
        "description": (
            "El cronograma tiene dependencias circulares o la programación es "
            "inválida; nada se escribió (§6, §7.5)."
        )
    }
}


# --- DTOs ----------------------------------------------------------------


class DependenciaDTO(BaseModel):
    """Precedencia entre actividades (§7.5, §6)."""

    ref: str = Field(
        min_length=1,
        description=(
            "En un programa base, el `prototipo_nodo_id` de la predecesora; "
            "en una actividad, el id de la actividad predecesora."
        ),
    )
    tipo: str = Field(
        default=TipoDependencia.FIN_INICIO,
        description=(
            "FS (fin→inicio), SS (inicio→inicio), FF (fin→fin) o SF "
            "(inicio→fin), como en MS Project."
        ),
    )
    lag_dias: float = Field(default=0.0, description="Días de desfase de la relación.")

    def a_dominio(self) -> Dependencia:
        return Dependencia(ref=self.ref, tipo=self.tipo, lag_dias=self.lag_dias)

    @classmethod
    def desde_dominio(cls, dep: Dependencia) -> DependenciaDTO:
        return cls(ref=dep.ref, tipo=dep.tipo, lag_dias=dep.lag_dias)


class TramoDTO(BaseModel):
    """Un segmento de una actividad interrumpida (§7.6).

    Lista vacía = actividad continua, el caso normal. Con tramos, la
    `duracion_dias` de la actividad es la **suma** de sus tramos —los días de
    trabajo— y lo que ocupa en el calendario es
    `max(offset_dias + duracion_dias)`, que es lo que el CPM encadena.
    """

    duracion_dias: float = Field(
        gt=0, description="Días de trabajo de este tramo (§7.6)."
    )
    offset_dias: float = Field(
        default=0.0,
        ge=0,
        description=(
            "Días desde el inicio de la actividad en que arranca el tramo. El "
            "primero arranca en 0."
        ),
    )

    def a_dominio(self) -> Tramo:
        return Tramo(duracion_dias=self.duracion_dias, offset_dias=self.offset_dias)

    @classmethod
    def desde_dominio(cls, tramo: Tramo) -> TramoDTO:
        return cls(
            duracion_dias=tramo.duracion_dias, offset_dias=tramo.offset_dias
        )

    @classmethod
    def lista_desde_jsonb(cls, dato: list | None) -> list[TramoDTO]:
        return [cls.desde_dominio(Tramo.desde_jsonb(t)) for t in (dato or [])]


class ItemProgramaBasePeticion(BaseModel):
    """Renglón de la plantilla de duraciones (§7.5 `ProgramaBaseItem`)."""

    duracion_dias: Decimal = Field(gt=0, description="Días de la actividad (§7.5).")
    prototipo_nodo_id: UUID | None = Field(
        default=None, description="Nodo exacto del árbol WBS al que aplica (§7.4)."
    )
    etapa_id: UUID | None = Field(
        default=None,
        description="Plantilla gruesa: aplica a toda la etapa constructiva.",
    )
    frente_id: UUID | None = Field(default=None, description="Frente del §8.3.")
    dependencias: list[DependenciaDTO] = Field(default_factory=list)
    tramos: list[TramoDTO] = Field(
        default_factory=list,
        description=(
            "Interrupción de la actividad; vacío = continua. La interrupción "
            "vive en la plantilla porque es de la secuencia constructiva del "
            "prototipo (§7.6)."
        ),
    )
    orden: int = 0

    def a_dominio(self) -> ItemProgramaBase:
        return ItemProgramaBase(
            duracion_dias=self.duracion_dias,
            prototipo_nodo_id=str(self.prototipo_nodo_id)
            if self.prototipo_nodo_id
            else None,
            etapa_id=str(self.etapa_id) if self.etapa_id else None,
            frente_id=str(self.frente_id) if self.frente_id else None,
            dependencias=tuple(dep.a_dominio() for dep in self.dependencias),
            tramos=tuple(tramo.a_dominio() for tramo in self.tramos),
            orden=self.orden,
        )


class CrearProgramaBasePeticion(BaseModel):
    """§11.2 `POST /programas-base`. Cada alta es una versión nueva (§7.5)."""

    prototipo_id: UUID
    nombre: str | None = None
    items: list[ItemProgramaBasePeticion] = Field(default_factory=list)


class ProgramaBaseRespuesta(BaseModel):
    id: UUID
    prototipo_id: UUID
    version: int
    vigente: bool
    nombre: str | None

    @classmethod
    def desde_fila(cls, fila: dict) -> ProgramaBaseRespuesta:
        return cls(
            id=fila["id"],
            prototipo_id=fila["prototipo_id"],
            version=fila["version"],
            vigente=fila["vigente"],
            nombre=fila["nombre"],
        )


class ProgramaBaseCreadoRespuesta(BaseModel):
    id: UUID
    version: int
    n_items: int


class ItemProgramaBaseRespuesta(BaseModel):
    id: UUID
    programa_base_id: UUID
    prototipo_nodo_id: UUID | None
    etapa_id: UUID | None
    frente_id: UUID | None
    duracion_dias: Decimal
    dependencias: list[DependenciaDTO]
    tramos: list[TramoDTO]
    orden: int

    @classmethod
    def desde_fila(cls, fila: dict) -> ItemProgramaBaseRespuesta:
        return cls(
            id=fila["id"],
            programa_base_id=fila["programa_base_id"],
            prototipo_nodo_id=fila["prototipo_nodo_id"],
            etapa_id=fila["etapa_id"],
            frente_id=fila["frente_id"],
            duracion_dias=fila["duracion_dias"],
            dependencias=[
                DependenciaDTO.desde_dominio(Dependencia.desde_jsonb(dep))
                for dep in (fila["dependencias"] or [])
            ],
            tramos=TramoDTO.lista_desde_jsonb(fila["tramos"]),
            orden=fila["orden"],
        )


class ActividadProgramadaRespuesta(BaseModel):
    """Fila del Gantt: lo capturado más lo que derivó el motor (§7.6, §6)."""

    id: UUID
    descripcion: str | None
    frente_id: UUID | None
    etapa_id: UUID | None
    nivel_id: UUID | None
    duracion_dias: Decimal
    dependencias: list[DependenciaDTO]
    tramos: list[TramoDTO]
    fecha_inicio: date | None
    fecha_termino: date | None
    avance_pct: Decimal
    estatus: str
    bloqueada: bool
    es_critica: bool
    holgura: Decimal | None
    desfase: Decimal | None

    @classmethod
    def desde_fila(cls, fila: dict) -> ActividadProgramadaRespuesta:
        return cls(
            id=fila["id"],
            descripcion=fila["descripcion"],
            frente_id=fila["frente_id"],
            etapa_id=fila["etapa_id"],
            nivel_id=fila["nivel_id"],
            duracion_dias=fila["duracion_dias"],
            dependencias=[
                DependenciaDTO.desde_dominio(Dependencia.desde_jsonb(dep))
                for dep in (fila["dependencias"] or [])
            ],
            tramos=TramoDTO.lista_desde_jsonb(fila["tramos"]),
            fecha_inicio=fila["fecha_inicio"],
            fecha_termino=fila["fecha_termino"],
            avance_pct=fila["avance_pct"],
            estatus=fila["estatus"],
            bloqueada=fila["bloqueada"],
            es_critica=fila["es_critica"],
            holgura=fila["holgura"],
            desfase=fila["desfase"],
        )


class ProgramaObraRespuesta(BaseModel):
    """§11.2 `GET /obras/{id}/programa`: el cronograma vigente y su historial."""

    obra_id: UUID
    programa_obra_id: UUID | None
    version: int | None
    fecha_corte: date | None
    versiones: list[int]
    actividades: list[ActividadProgramadaRespuesta]


class InstanciarProgramaPeticion(BaseModel):
    fecha_corte: date | None = Field(
        default=None,
        description="Fecha contra la que se mide el desfase; por defecto hoy (§6).",
    )


class ActividadEnRutaRespuesta(BaseModel):
    """Una actividad con su cálculo de CPM (§6)."""

    actividad_id: UUID
    descripcion: str | None
    frente_id: UUID | None
    duracion_dias: Decimal
    dependencias: list[DependenciaDTO]
    tramos: list[TramoDTO]
    inicio_temprano: date
    fin_temprano: date
    inicio_tardio: date
    fin_tardio: date
    holgura: float
    desfase: float
    es_critica: bool
    bloqueada: bool
    avance_pct: Decimal

    @classmethod
    def desde_dominio(cls, actividad: ActividadEnRuta) -> ActividadEnRutaRespuesta:
        return cls(
            actividad_id=actividad.actividad_id,
            descripcion=actividad.descripcion,
            frente_id=actividad.frente_id,
            duracion_dias=actividad.duracion_dias,
            dependencias=[
                DependenciaDTO.desde_dominio(dep) for dep in actividad.dependencias
            ],
            tramos=[TramoDTO.desde_dominio(t) for t in actividad.tramos],
            inicio_temprano=actividad.inicio_temprano,
            fin_temprano=actividad.fin_temprano,
            inicio_tardio=actividad.inicio_tardio,
            fin_tardio=actividad.fin_tardio,
            holgura=actividad.holgura,
            desfase=actividad.desfase,
            es_critica=actividad.es_critica,
            bloqueada=actividad.bloqueada,
            avance_pct=actividad.avance_pct,
        )


class RutaCriticaRespuesta(BaseModel):
    obra_id: UUID
    fecha_inicio: date
    fecha_corte: date
    fin_programado: date | None
    programa_obra_id: UUID | None
    version: int | None
    actividades: list[ActividadEnRutaRespuesta]

    @classmethod
    def desde_dominio(cls, ruta: RutaCritica) -> RutaCriticaRespuesta:
        return cls(
            obra_id=ruta.obra_id,
            fecha_inicio=ruta.fecha_inicio,
            fecha_corte=ruta.fecha_corte,
            fin_programado=ruta.fin_programado,
            programa_obra_id=ruta.programa_obra_id,
            version=ruta.version,
            actividades=[
                ActividadEnRutaRespuesta.desde_dominio(a) for a in ruta.actividades
            ],
        )


class ProgramaInstanciadoRespuesta(BaseModel):
    """§11.2 `POST /obras/{id}/programa`."""

    programa_obra_id: UUID
    version: int
    n_actividades: int
    sin_item: list[str] = Field(
        description=(
            "Actividades para las que el programa base no trae renglón: "
            "conservaron su programación anterior (§7.5)."
        )
    )
    refs_no_resueltas: list[str] = Field(
        description=(
            "Dependencias del programa base que no corresponden a ninguna "
            "actividad de la obra; el motor las ignora (§6)."
        )
    )
    ruta: RutaCriticaRespuesta

    @classmethod
    def desde_dominio(
        cls, instanciado: ProgramaInstanciadoEnObra
    ) -> ProgramaInstanciadoRespuesta:
        return cls(
            programa_obra_id=instanciado.programa_obra_id,
            version=instanciado.version,
            n_actividades=instanciado.n_actividades,
            sin_item=list(instanciado.sin_item),
            refs_no_resueltas=list(instanciado.refs_no_resueltas),
            ruta=RutaCriticaRespuesta.desde_dominio(instanciado.ruta),
        )


class ProgramacionActividadPeticion(BaseModel):
    """§11.2 `PATCH /actividades/{id}/programacion`.

    Solo se cambia lo que llega. Una lista vacía de `dependencias` **sí** es un
    cambio: deja la actividad sin predecesoras; una de `tramos`, sin
    interrupción.
    """

    duracion_dias: Decimal | None = Field(default=None, gt=0)
    dependencias: list[DependenciaDTO] | None = None
    tramos: list[TramoDTO] | None = Field(
        default=None,
        description=(
            "Interrupción de la actividad. Una lista vacía le quita la "
            "interrupción; mandarla sin `duracion_dias` **deriva** la duración "
            "de la suma de los tramos (§7.6)."
        ),
    )
    frente_id: UUID | None = None
    fecha_inicio: date | None = None
    fecha_termino: date | None = None


# --- Programas base (§11.2) ---------------------------------------------


@router.get(
    "/programas-base",
    response_model=list[ProgramaBaseRespuesta],
    summary="Programas base de duraciones",
    dependencies=[CONFIGURA_PROGRAMA],
)
async def listar_programas_base(
    sesion: SesionRLS,
    prototipo_id: Annotated[
        UUID | None, Query(description="Acota al prototipo (§7.2).")
    ] = None,
    solo_vigentes: Annotated[
        bool, Query(description="Solo la versión vigente de cada prototipo (§7.5).")
    ] = False,
) -> list[ProgramaBaseRespuesta]:
    filas = await RepositorioProgramasSQL(sesion).listar_bases(
        prototipo_id=prototipo_id, solo_vigentes=solo_vigentes
    )
    return [ProgramaBaseRespuesta.desde_fila(fila) for fila in filas]


@router.post(
    "/programas-base",
    response_model=ProgramaBaseCreadoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Alta de un programa base (nueva versión)",
    dependencies=[CONFIGURA_PROGRAMA],
    responses=_CICLO,
)
async def crear_programa_base(
    peticion: CrearProgramaBasePeticion, caso_uso: CrearProgramaBaseDep
) -> ProgramaBaseCreadoRespuesta:
    """Cada alta versiona y retira la vigente anterior (§7.5, §10.8)."""
    creado = await caso_uso.ejecutar(
        ComandoCrearProgramaBase(
            prototipo_id=peticion.prototipo_id,
            nombre=peticion.nombre,
            items=tuple(item.a_dominio() for item in peticion.items),
        )
    )
    return ProgramaBaseCreadoRespuesta(
        id=creado.id, version=creado.version, n_items=creado.n_items
    )


@router.get(
    "/programas-base/{programa_base_id}/items",
    response_model=list[ItemProgramaBaseRespuesta],
    summary="Renglones de un programa base",
    dependencies=[CONFIGURA_PROGRAMA],
    responses=_NO_ENCONTRADA,
)
async def listar_items_programa_base(
    programa_base_id: UUID, sesion: SesionRLS
) -> list[ItemProgramaBaseRespuesta]:
    repo = RepositorioProgramasSQL(sesion)
    if await repo.obtener_base(programa_base_id) is None:
        # Una lista vacía no distingue "no existe" de "no tiene renglones";
        # el 404 sí, y RLS ya hace indistinguible "no existe" de "no la puedes
        # ver" (§12.4).
        raise ProgramaBaseNoEncontrado(
            f"Programa base {programa_base_id} no encontrado en tu alcance."
        )
    return [
        ItemProgramaBaseRespuesta.desde_fila(fila)
        for fila in await repo.listar_items_base(programa_base_id)
    ]


# --- Cronograma de la obra (§11.2) --------------------------------------


@router.get(
    "/obras/{obra_id}/programa",
    response_model=ProgramaObraRespuesta,
    summary="Cronograma vigente de la obra",
    dependencies=[PROGRAMA_DE_OBRA],
)
async def obtener_programa_de_obra(
    obra_id: UUID, sesion: SesionRLS
) -> ProgramaObraRespuesta:
    """El `ProgramaObra` vigente, su historial de versiones y las actividades
    con su programación (§7.5, §7.6). Sin programa instanciado devuelve las
    actividades igual: es lo que alimenta el Gantt desde el día uno."""
    programas = RepositorioProgramasSQL(sesion)
    vigente = await programas.programa_vigente(obra_id)
    versiones = await programas.listar_programas(obra_id)
    filas = await RepositorioActividadesSQL(sesion).programacion_de_obra(obra_id)

    return ProgramaObraRespuesta(
        obra_id=obra_id,
        programa_obra_id=vigente["id"] if vigente else None,
        version=vigente["version"] if vigente else None,
        fecha_corte=vigente["fecha_corte"] if vigente else None,
        versiones=[fila["version"] for fila in versiones],
        actividades=[
            ActividadProgramadaRespuesta.desde_fila(fila) for fila in filas
        ],
    )


@router.post(
    "/obras/{obra_id}/programa",
    response_model=ProgramaInstanciadoRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Instanciar / versionar el cronograma desde el programa base",
    dependencies=[PROGRAMA_DE_OBRA],
    responses={**_NO_ENCONTRADA, **_CICLO},
)
async def instanciar_programa_de_obra(
    obra_id: UUID,
    peticion: InstanciarProgramaPeticion,
    caso_uso: InstanciarProgramaObraDep,
) -> ProgramaInstanciadoRespuesta:
    """Baja la plantilla del prototipo a las actividades, resuelve las
    dependencias a ids de actividad y recalcula la ruta (§7.5, §11.2)."""
    instanciado = await caso_uso.ejecutar(
        ComandoInstanciarPrograma(obra_id=obra_id, fecha_corte=peticion.fecha_corte)
    )
    return ProgramaInstanciadoRespuesta.desde_dominio(instanciado)


# --- Ruta crítica (§6, §11.2) -------------------------------------------


@router.get(
    "/obras/{obra_id}/ruta-critica",
    response_model=RutaCriticaRespuesta,
    summary="Ruta crítica, holgura y desfase de la obra",
    responses={**_NO_ENCONTRADA, **_CICLO},
)
async def obtener_ruta_critica(
    obra_id: UUID,
    caso_uso: ConsultarRutaCriticaDep,
    fecha_corte: Annotated[
        date | None,
        Query(description="Fecha contra la que se mide el desfase; por defecto hoy."),
    ] = None,
) -> RutaCriticaRespuesta:
    """Todos los roles, cada uno con su alcance (§4, §11.2): el Residente ve
    la de su obra porque RLS no le deja ver otra."""
    return RutaCriticaRespuesta.desde_dominio(
        await caso_uso.ejecutar(obra_id, fecha_corte=fecha_corte)
    )


@router.post(
    "/obras/{obra_id}/ruta-critica/recalcular",
    response_model=RutaCriticaRespuesta,
    summary="Recalcular y persistir la ruta crítica",
    dependencies=[PROGRAMA_DE_OBRA],
    responses={**_NO_ENCONTRADA, **_CICLO},
)
async def recalcular_ruta_critica(
    obra_id: UUID,
    caso_uso: RecalcularRutaCriticaDep,
    fecha_corte: Annotated[
        date | None, Query(description="Fecha de corte del desfase (§6).")
    ] = None,
) -> RutaCriticaRespuesta:
    """Recálculo on-demand (§6). Es idempotente: con el mismo cronograma y la
    misma fecha de corte deja exactamente los mismos valores."""
    return RutaCriticaRespuesta.desde_dominio(
        await caso_uso.ejecutar(
            ComandoRecalcularRutaCritica(obra_id=obra_id, fecha_corte=fecha_corte)
        )
    )


@router.patch(
    "/actividades/{actividad_id}/programacion",
    response_model=ActividadEnRutaRespuesta,
    summary="Ajustar fechas, duración y dependencias de una actividad",
    dependencies=[PROGRAMA_DE_OBRA],
    responses={**_NO_ENCONTRADA, **_CICLO},
)
async def editar_programacion_actividad(
    actividad_id: UUID,
    peticion: ProgramacionActividadPeticion,
    caso_uso: EditarProgramacionActividadDep,
) -> ActividadEnRutaRespuesta:
    """Supervisor y Control de obra ajustan el cronograma (§11.2). El recálculo
    de la ruta va en la misma transacción."""
    return ActividadEnRutaRespuesta.desde_dominio(
        await caso_uso.ejecutar(
            ComandoEditarProgramacion(
                actividad_id=actividad_id,
                duracion_dias=peticion.duracion_dias,
                dependencias=(
                    tuple(dep.a_dominio() for dep in peticion.dependencias)
                    if peticion.dependencias is not None
                    else None
                ),
                tramos=(
                    tuple(tramo.a_dominio() for tramo in peticion.tramos)
                    if peticion.tramos is not None
                    else None
                ),
                frente_id=peticion.frente_id,
                fecha_inicio=peticion.fecha_inicio,
                fecha_termino=peticion.fecha_termino,
            )
        )
    )
