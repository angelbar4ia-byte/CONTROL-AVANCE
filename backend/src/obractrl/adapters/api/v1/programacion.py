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
* `GET /programas-base/{id}/obras` y `POST /programas-base/{id}/replicar` —
  los mismos que la instanciación individual: replicar es esa operación
  repetida sobre varias obras, no una facultad nueva (§7.5).
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
    ConsultarArbolProgramaDep,
    ConsultarRutaCriticaDep,
    CrearProgramaBaseDep,
    EditarProgramacionActividadDep,
    InstanciarProgramaObraDep,
    ProgramarNodoDelArbolDep,
    RecalcularRutaCriticaDep,
    ReplicarProgramaEnObrasDep,
)
from obractrl.adapters.api.dependencias import SesionRLS, exigir_rol
from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.programas_sql import RepositorioProgramasSQL
from obractrl.application.casos_uso.gestionar_programacion import (
    ActividadEnRuta,
    ArbolDePrograma,
    ComandoCrearProgramaBase,
    ComandoEditarProgramacion,
    ComandoInstanciarPrograma,
    ComandoProgramarNodo,
    ComandoRecalcularRutaCritica,
    ComandoReplicarPrograma,
    NodoProgramado,
    ProgramaBaseNoEncontrado,
    ProgramaInstanciadoEnObra,
    ReplicaDePrograma,
    ReplicaEnObra,
    ResumenNodo,
    RutaCritica,
)
from obractrl.domain.programacion.calendario import (
    DIAS_DE_LA_SEMANA,
    SEMANA_LABORAL,
    CalendarioInvalidoError,
    CalendarioLaboral,
)
from obractrl.domain.programacion.cpm import Dependencia, TipoDependencia, Tramo
from obractrl.domain.programacion.reglas import ItemProgramaBase
from obractrl.domain.shared.diccionario import ClaseNodo, Rol

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


CALENDARIO_NATURAL = "natural"
CALENDARIO_LABORAL = "laboral"
"""Las dos etiquetas de `CalendarioRespuesta.tipo`, que es lo que el usuario elige en
pantalla: "semana laboral o semana natural" (§5.1, Control de obra)."""


_DIAS_HABILES_KW: dict[str, Any] = {
    "min_length": 1,
    "max_length": 7,
    "description": (
        "Días de la semana que se trabajan, ISO 1 = lunes … 7 = domingo. "
        f"{list(DIAS_DE_LA_SEMANA)} es semana natural (default) y "
        f"{SEMANA_LABORAL.a_lista()} la semana laboral típica de obra."
    ),
    "examples": [list(DIAS_DE_LA_SEMANA), SEMANA_LABORAL.a_lista()],
}
"""Mismo campo en la petición y en la respuesta: es el único dato del
calendario, y describirlo dos veces distinto sería la primera forma de que las
dos caras del contrato se desfasen. Va como kwargs y no como un `Field` ya
construido porque cada modelo le pone su propio default."""


class CalendarioPeticion(BaseModel):
    """Calendario de trabajo del cronograma (§7.5, migración 0040).

    Qué días de la semana cuentan como trabajo, en numeración ISO: 1 = lunes …
    7 = domingo. Los siete son la **semana natural** —días corridos, el
    comportamiento de siempre y el default—; cualquier subconjunto es semana
    laboral y hace que el motor salte los días que no están al convertir
    duraciones, holguras, lags y tramos a fechas (§6).

    Se captura el **conjunto de días** y no un `tipo`: "laboral" no es lunes a
    viernes en este giro —en obra en México lo normal es lunes a sábado, y hay
    frentes que trabajan domingo—, así que un `tipo` capturable obligaría a
    decidir por el usuario cuál de las variantes es "la laboral". El `tipo` que
    ve la pantalla se deriva (`CalendarioRespuesta`), no se manda.
    """

    dias_habiles: list[Annotated[int, Field(ge=1, le=7)]] = Field(
        default_factory=lambda: list(DIAS_DE_LA_SEMANA), **_DIAS_HABILES_KW
    )

    def a_dominio(self) -> CalendarioLaboral:
        """Normaliza y valida. Un conjunto imposible es un 422, no un 500.

        Los `ge`/`le` de pydantic ya acotan cada día; lo que queda —ordenar y
        quitar repetidos— lo hace el dominio, que es donde está definido qué es
        un calendario válido (§12.11).
        """
        try:
            return CalendarioLaboral.de(self.dias_habiles)
        except CalendarioInvalidoError as exc:
            raise ValueError(str(exc)) from exc


class CalendarioRespuesta(BaseModel):
    """El calendario tal como quedó, con su lectura para la pantalla.

    `tipo` es **derivado** de `dias_habiles`, no un segundo dato: se calcula al
    construir la respuesta y nunca se captura, así que no hay forma de que los
    dos se contradigan. Existe para que el interruptor "semana laboral / semana
    natural" no obligue a cada cliente a reimplementar la equivalencia.
    """

    dias_habiles: list[Annotated[int, Field(ge=1, le=7)]] = Field(
        **_DIAS_HABILES_KW
    )
    tipo: str = Field(
        description=(
            f"`{CALENDARIO_NATURAL}` si se trabajan los siete días, "
            f"`{CALENDARIO_LABORAL}` si alguno se salta. Derivado de "
            f"`dias_habiles`."
        ),
        examples=[CALENDARIO_NATURAL, CALENDARIO_LABORAL],
    )

    @classmethod
    def desde_dominio(cls, calendario: CalendarioLaboral) -> CalendarioRespuesta:
        return cls(
            dias_habiles=calendario.a_lista(),
            tipo=(
                CALENDARIO_NATURAL if calendario.es_natural else CALENDARIO_LABORAL
            ),
        )

    @classmethod
    def desde_fila(cls, dias_habiles: list[int] | None) -> CalendarioRespuesta:
        """Desde la columna `smallint[]`. `None` —fila sin cronograma— es
        semana natural, el mismo default del motor."""
        return cls.desde_dominio(CalendarioLaboral.de(dias_habiles))


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


_PROFUNDIDAD_KW: dict[str, Any] = {
    "description": (
        "A qué altura del árbol WBS se sugiere capturar este programa (§7.4, "
        "migración 0041): `nivel`, `etapa` o `concepto`. Es el default con el "
        "que abre el editor para que todo el equipo vea lo mismo, **no** una "
        "restricción: cualquiera puede bajar a capturar más fino sin "
        "reversionar la plantilla. `concepto` es renglón por renglón."
    ),
    "examples": [ClaseNodo.ETAPA.value, ClaseNodo.CONCEPTO.value],
}
"""Mismo campo en la petición y en la respuesta, descrito una sola vez —igual
que `_DIAS_HABILES_KW`—, para que las dos caras del contrato no se desfasen."""


class CrearProgramaBasePeticion(BaseModel):
    """§11.2 `POST /programas-base`. Cada alta es una versión nueva (§7.5)."""

    prototipo_id: UUID
    nombre: str | None = None
    items: list[ItemProgramaBasePeticion] = Field(default_factory=list)
    profundidad_captura: ClaseNodo = Field(
        default=ClaseNodo.CONCEPTO, **_PROFUNDIDAD_KW
    )
    calendario: CalendarioPeticion = Field(
        default_factory=CalendarioPeticion,
        description=(
            "Semana laboral o natural del cronograma (§5.1: la elige Control "
            "de obra). Se captura una vez en la plantilla del prototipo y baja "
            "a cada obra que se genere o instancie con ella. Omitirlo es "
            "semana natural, el comportamiento de siempre."
        ),
    )


class ProgramaBaseRespuesta(BaseModel):
    id: UUID
    prototipo_id: UUID
    version: int
    vigente: bool
    nombre: str | None
    calendario: CalendarioRespuesta
    profundidad_captura: ClaseNodo = Field(**_PROFUNDIDAD_KW)

    @classmethod
    def desde_fila(cls, fila: dict) -> ProgramaBaseRespuesta:
        return cls(
            id=fila["id"],
            prototipo_id=fila["prototipo_id"],
            version=fila["version"],
            vigente=fila["vigente"],
            nombre=fila["nombre"],
            calendario=CalendarioRespuesta.desde_fila(fila["dias_habiles"]),
            profundidad_captura=ClaseNodo(
                str(fila.get("profundidad_captura") or ClaseNodo.CONCEPTO)
            ),
        )


class ProgramaBaseCreadoRespuesta(BaseModel):
    id: UUID
    version: int
    n_items: int
    calendario: CalendarioRespuesta
    profundidad_captura: ClaseNodo = Field(**_PROFUNDIDAD_KW)


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
    calendario: CalendarioRespuesta = Field(
        description=(
            "Calendario con el que se programó esta obra (0040). El Gantt lo "
            "necesita para dibujar: sin él, una actividad de cinco días "
            "laborales se pintaría como cinco casillas corridas."
        )
    )


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
    calendario: CalendarioRespuesta = Field(
        description=(
            "Con qué calendario se calcularon estas fechas (0040). Fija además "
            "en qué unidad están `holgura` y `desfase`: días hábiles con "
            "semana laboral, días corridos con semana natural (§6)."
        )
    )

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
            calendario=CalendarioRespuesta.desde_dominio(ruta.calendario),
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


class ObraCandidataRespuesta(BaseModel):
    """Una obra a la que este programa base se puede replicar (§11.2).

    Lo que la pantalla de replicación necesita saber **antes** de elegir: qué
    casa es, si ya se generó desde su prototipo —sin actividades no hay nada
    que programar (§11.3 A.2)— y si ya trae cronograma, porque replicar sobre
    una obra programada le crea una **versión nueva** y eso el usuario lo tiene
    que saber antes, no después (§7.5).
    """

    obra_id: UUID
    clave: str
    estatus: str
    residente_id: UUID | None
    fecha_inicio: date | None
    version_cronograma: int | None = Field(
        description=(
            "Versión del `ProgramaObra` vigente de la obra, o `null` si nunca "
            "se le instanció uno. Replicar sobre una obra con versión crea la "
            "siguiente (§7.5)."
        )
    )
    fecha_corte: date | None = Field(
        description="Fecha de corte con la que se calculó esa versión (§6)."
    )

    @classmethod
    def desde_filas(
        cls, obra: dict, programa: dict | None
    ) -> ObraCandidataRespuesta:
        return cls(
            obra_id=obra["id"],
            clave=obra["clave"],
            estatus=obra["estatus"],
            residente_id=obra["residente_id"],
            fecha_inicio=obra["fecha_inicio"],
            version_cronograma=programa["version"] if programa else None,
            fecha_corte=programa["fecha_corte"] if programa else None,
        )


class ReplicarProgramaPeticion(BaseModel):
    """§11.2 `POST /programas-base/{id}/replicar`.

    Las obras van explícitas y no se asume "todas las del prototipo": replicar
    reprograma casas que pueden llevar avance, así que cuáles entran es una
    decisión del usuario, no un default.
    """

    obras: list[UUID] = Field(
        min_length=1,
        description=(
            "Obras destino. Deben ser del mismo prototipo que el programa "
            "base; las que no lo sean se reportan como no replicadas en vez de "
            "abortar el lote."
        ),
    )
    fecha_corte: date | None = Field(
        default=None,
        description="Fecha contra la que se mide el desfase; por defecto hoy (§6).",
    )


class ReplicaEnObraRespuesta(BaseModel):
    """El parte de **una** obra del lote (§11.2)."""

    obra_id: UUID
    clave: str | None
    programada: bool = Field(
        description=(
            "`true` si la obra quedó con cronograma nuevo. `false` trae el "
            "`motivo` y significa que esa obra no se tocó: su transacción no "
            "se confirmó."
        )
    )
    programa_obra_id: UUID | None
    version: int | None
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
    motivo: str | None = Field(
        description=(
            "Por qué esta obra no quedó programada, redactado para quien lee "
            "el reporte. `null` en las que sí."
        )
    )

    @classmethod
    def desde_dominio(cls, replica: ReplicaEnObra) -> ReplicaEnObraRespuesta:
        return cls(
            obra_id=replica.obra_id,
            clave=replica.clave,
            programada=replica.programada,
            programa_obra_id=replica.programa_obra_id,
            version=replica.version,
            n_actividades=replica.n_actividades,
            sin_item=list(replica.sin_item),
            refs_no_resueltas=list(replica.refs_no_resueltas),
            motivo=replica.motivo,
        )


class ReplicaDeProgramaRespuesta(BaseModel):
    """§11.2 `POST /programas-base/{id}/replicar`.

    Responde **200 y no 201** aunque cree cronogramas: un lote de mejor
    esfuerzo no tiene un recurso creado que anunciar —puede haber creado 39 de
    40, o ninguno— y el resultado real es el parte por obra, no una ubicación.
    """

    programa_base_id: UUID
    prototipo_id: UUID
    version_base: int
    n_programadas: int
    n_fallidas: int
    obras: list[ReplicaEnObraRespuesta] = Field(
        description="Un renglón por obra pedida, en el orden en que se pidieron."
    )

    @classmethod
    def desde_dominio(cls, replica: ReplicaDePrograma) -> ReplicaDeProgramaRespuesta:
        return cls(
            programa_base_id=replica.programa_base_id,
            prototipo_id=replica.prototipo_id,
            version_base=replica.version_base,
            n_programadas=len(replica.programadas),
            n_fallidas=len(replica.fallidas),
            obras=[
                ReplicaEnObraRespuesta.desde_dominio(obra) for obra in replica.obras
            ],
        )


# --- Programación jerárquica sobre el árbol WBS (§7.4, §11.2) -----------


class ConflictoJerarquiaRespuesta(BaseModel):
    """Un nodo cuya ventana capturada no cuadra con la de sus conceptos (§7.5).

    **No es un error: es la pregunta.** Las dos cifras viajan las dos porque lo
    que el usuario tiene que decidir es cuál conservar, y darle sólo una lo
    obligaría a ir a buscar la otra a otra pantalla.
    """

    nodo_id: UUID
    nombre: str
    dias_capturados: Decimal = Field(
        description="Días que el programa base declara para este nodo (§7.5)."
    )
    dias_derivados: Decimal = Field(
        description="Días que hoy ocupan sus conceptos ya programados (§6)."
    )
    actividades: list[UUID] = Field(
        description=(
            "Los conceptos programados a mano que están en desacuerdo: es lo "
            "que se perdería al conservar la cifra del nodo."
        )
    )


class NodoDelArbolRespuesta(BaseModel):
    """Un renglón del Gantt jerárquico (§7.4, §6).

    Los nodos `nivel` y `etapa` son **barras resumen derivadas**, no
    actividades: el residente sigue capturando sólo en conceptos y estas se
    recalculan de sus hojas en cada lectura (§7.6). Por eso no traen id de
    actividad ni estatus — no son una fila de `actividad` y no deben poder
    editarse como si lo fueran.
    """

    nodo_id: UUID
    tipo: ClaseNodo = Field(
        description="`etapa`, `nivel` o `concepto`, del árbol WBS (§7.4)."
    )
    nombre: str
    parent_id: UUID | None
    profundidad: int = Field(
        description=(
            "Cuántos ancestros tiene, la raíz en 0. Es con lo que el cliente "
            "colapsa o expande por niveles de profundidad."
        )
    )
    actividades: list[UUID] = Field(
        description="Los conceptos que cuelgan del nodo, a cualquier distancia."
    )
    fecha_inicio: date | None
    fecha_termino: date | None
    duracion_dias: Decimal = Field(
        description=(
            "**Span** de la barra: días de calendario entre el inicio más "
            "temprano y el fin más tardío de sus conceptos, en la escala del "
            "calendario del cronograma. No es la suma de sus duraciones."
        )
    )
    duracion_hojas_dias: Decimal = Field(
        description=(
            "Suma de los días de **trabajo** de sus conceptos. Coincide con el "
            "span cuando van uno tras otro y es menor cuando se traslapan."
        )
    )
    avance_pct: Decimal = Field(
        description=(
            "Avance **ponderado por importe** de sus conceptos (§6), no el "
            "promedio simple: el muro de $122k en cero y el castillo de $10k "
            "terminado no son 50 %."
        )
    )
    importe: Decimal
    conflicto: ConflictoJerarquiaRespuesta | None

    @classmethod
    def desde_dominio(cls, nodo: ResumenNodo) -> NodoDelArbolRespuesta:
        return cls(
            nodo_id=UUID(nodo.nodo_id),
            tipo=nodo.tipo,
            nombre=nodo.nombre,
            parent_id=UUID(nodo.parent_id) if nodo.parent_id else None,
            profundidad=nodo.profundidad,
            actividades=[UUID(a) for a in nodo.actividades],
            fecha_inicio=nodo.fecha_inicio,
            fecha_termino=nodo.fecha_termino,
            duracion_dias=nodo.duracion_dias,
            duracion_hojas_dias=nodo.duracion_hojas_dias,
            avance_pct=nodo.avance_pct,
            importe=nodo.importe,
            conflicto=(
                None
                if nodo.conflicto is None
                else ConflictoJerarquiaRespuesta(
                    nodo_id=UUID(nodo.conflicto.nodo_id),
                    nombre=nodo.conflicto.nombre,
                    dias_capturados=nodo.conflicto.dias_capturados,
                    dias_derivados=nodo.conflicto.dias_derivados,
                    actividades=[UUID(a) for a in nodo.conflicto.actividades],
                )
            ),
        )


class ArbolDeProgramaRespuesta(BaseModel):
    """§11.2 `GET /obras/{id}/programa/arbol`: el cronograma como árbol WBS."""

    obra_id: UUID
    prototipo_id: UUID
    profundidad_captura: ClaseNodo = Field(**_PROFUNDIDAD_KW)
    calendario: CalendarioRespuesta
    nodos: list[NodoDelArbolRespuesta] = Field(
        description=(
            "Un renglón por nodo con conceptos debajo, en recorrido en "
            "profundidad —padre antes que hijos—, que es el orden del Gantt. "
            "Los nodos sin conceptos no aparecen: no hay nada que resumir."
        )
    )
    n_conflictos: int = Field(
        description=(
            "Cuántos nodos traen `conflicto`. Es un aviso no bloqueante: la "
            "pantalla lo marca y el usuario decide caso por caso (§7.5)."
        )
    )

    @classmethod
    def desde_dominio(cls, arbol: ArbolDePrograma) -> ArbolDeProgramaRespuesta:
        return cls(
            obra_id=arbol.obra_id,
            prototipo_id=arbol.prototipo_id,
            profundidad_captura=arbol.profundidad_captura,
            calendario=CalendarioRespuesta.desde_dominio(arbol.calendario),
            nodos=[NodoDelArbolRespuesta.desde_dominio(n) for n in arbol.nodos],
            n_conflictos=len(arbol.conflictos),
        )


class ProgramarNodoPeticion(BaseModel):
    """§11.2 `POST /obras/{id}/programa/nodos/{prototipo_nodo_id}`."""

    duracion_dias: Decimal = Field(
        gt=0,
        description=(
            "Ventana del nodo. Los conceptos que cuelgan de él se acomodan uno "
            "tras otro dentro de ella, repartidos en proporción a su importe "
            "(§7.4)."
        ),
    )
    fecha_inicio: date | None = Field(
        default=None,
        description=(
            "Ancla de la ventana. Sin ella se conserva el inicio que los "
            "conceptos ya tenían y, si ninguno lo tiene, el arranque de la "
            "obra: cambiar una duración no debería mover el nodo de lugar."
        ),
    )
    forzar: bool = Field(
        default=False,
        description=(
            "La respuesta al conflicto padre-hijo: `true` conserva la cifra "
            "del nodo y pisa lo que los conceptos traían. Sin él, un conflicto "
            "responde 409 sin escribir nada y el usuario decide (§7.5)."
        ),
    )


class NodoProgramadoRespuesta(BaseModel):
    """§11.2 `POST /obras/{id}/programa/nodos/{prototipo_nodo_id}`."""

    obra_id: UUID
    prototipo_nodo_id: UUID
    duracion_dias: Decimal
    fecha_inicio: date
    fecha_termino: date
    actividades: list[UUID] = Field(
        description="Conceptos reprogramados, en el orden en que se acomodaron."
    )
    omitidas: list[UUID] = Field(
        description=(
            "Conceptos que el reparto no tocó por estar interrumpidos en "
            "tramos (§7.6): una ventana gruesa no tiene con qué decidir cómo "
            "volver a partirlos, y reescalarlos o borrarlos destruiría la "
            "secuencia constructiva del prototipo. Prográmalos con el `PATCH`."
        )
    )
    ruta: RutaCriticaRespuesta

    @classmethod
    def desde_dominio(cls, nodo: NodoProgramado) -> NodoProgramadoRespuesta:
        return cls(
            obra_id=nodo.obra_id,
            prototipo_nodo_id=nodo.prototipo_nodo_id,
            duracion_dias=nodo.duracion_dias,
            fecha_inicio=nodo.fecha_inicio,
            fecha_termino=nodo.fecha_termino,
            actividades=list(nodo.actividades),
            omitidas=list(nodo.omitidas),
            ruta=RutaCriticaRespuesta.desde_dominio(nodo.ruta),
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
            calendario=peticion.calendario.a_dominio(),
            profundidad_captura=peticion.profundidad_captura,
        )
    )
    return ProgramaBaseCreadoRespuesta(
        id=creado.id,
        version=creado.version,
        n_items=creado.n_items,
        calendario=CalendarioRespuesta.desde_dominio(creado.calendario),
        profundidad_captura=creado.profundidad_captura,
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


# --- Replicación a las obras del prototipo (§11.2, §7.5) ----------------
#
# Las dos rutas cuelgan del **programa base** y no de las obras porque el gesto
# es "este programa, a estas casas": el sujeto es la plantilla y las obras son
# el destino. Colgarlas de `/obras` obligaría a mandar el programa en el cuerpo
# y dejaría la operación sin dueño claro en el contrato.


@router.get(
    "/programas-base/{programa_base_id}/obras",
    response_model=list[ObraCandidataRespuesta],
    summary="Obras a las que este programa base se puede replicar",
    dependencies=[PROGRAMA_DE_OBRA],
    responses=_NO_ENCONTRADA,
)
async def listar_obras_candidatas(
    programa_base_id: UUID, sesion: SesionRLS
) -> list[ObraCandidataRespuesta]:
    """Las obras del prototipo del programa, con el estado de su cronograma.

    Lectura simple, así que consulta los repos directo como
    `obtener_programa_de_obra` (§11.2). Son **dos** repositorios y no uno a
    propósito: la obra la sirve `RepositorioObras` y el `ProgramaObra` vigente
    `RepositorioProgramas`, cada contexto por su puerto (§11.1). Componerlos
    aquí es lo que evita un join entre `obra` y `programa_obra` dentro de un
    repositorio que no es dueño de las dos tablas.
    """
    programas = RepositorioProgramasSQL(sesion)
    base = await programas.obtener_base(programa_base_id)
    if base is None:
        raise ProgramaBaseNoEncontrado(
            f"Programa base {programa_base_id} no encontrado en tu alcance."
        )

    obras = await RepositorioObrasSQL(sesion).listar(
        prototipo_id=base["prototipo_id"]
    )
    vigentes = await programas.programas_vigentes([obra["id"] for obra in obras])

    return [
        ObraCandidataRespuesta.desde_filas(obra, vigentes.get(str(obra["id"])))
        for obra in obras
    ]


@router.post(
    "/programas-base/{programa_base_id}/replicar",
    response_model=ReplicaDeProgramaRespuesta,
    summary="Replicar el programa base a varias obras del prototipo",
    dependencies=[PROGRAMA_DE_OBRA],
    responses={**_NO_ENCONTRADA, **_CICLO},
)
async def replicar_programa_base(
    programa_base_id: UUID,
    peticion: ReplicarProgramaPeticion,
    caso_uso: ReplicarProgramaEnObrasDep,
) -> ReplicaDeProgramaRespuesta:
    """Instancia el cronograma de varias obras en una sola llamada (§7.5).

    Mismos roles que la instanciación individual (`PROGRAMA_DE_OBRA`): repetir
    una operación no la vuelve más privilegiada, y RLS ya acota a qué obras
    llega cada quien (§12.4).

    Es de **mejor esfuerzo**: una obra que falla no cancela el lote, y el 422
    documentado arriba solo aparece cuando lo inválido es el programa —una
    versión retirada—, no cuando lo es una obra. Lo que pase con cada casa va
    en `obras[].motivo`.
    """
    return ReplicaDeProgramaRespuesta.desde_dominio(
        await caso_uso.ejecutar(
            ComandoReplicarPrograma(
                programa_base_id=programa_base_id,
                obras=tuple(peticion.obras),
                fecha_corte=peticion.fecha_corte,
            )
        )
    )


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
        # Sin cronograma instanciado, semana natural: es el default de la
        # columna y el del motor, y las actividades que se devuelven abajo se
        # calculan con ese mismo criterio (`_calendario_de`).
        calendario=CalendarioRespuesta.desde_fila(
            vigente["dias_habiles"] if vigente else None
        ),
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


# --- Árbol WBS del cronograma (§7.4, §11.2) -----------------------------
#
# Las dos rutas cuelgan de `/obras/{id}/programa` y no de `/actividades` porque
# el sujeto es el **nodo del árbol**, que no es una actividad: `nivel` y `etapa`
# son estructura y su barra es derivada (§11.3 A.2). Colgarlas de `/actividades`
# habría sugerido que existe una actividad de resumen que se puede editar.


@router.get(
    "/obras/{obra_id}/programa/arbol",
    response_model=ArbolDeProgramaRespuesta,
    summary="Cronograma de la obra como árbol WBS, con barras resumen",
    responses={**_NO_ENCONTRADA, **_CICLO},
)
async def obtener_arbol_del_programa(
    obra_id: UUID,
    caso_uso: ConsultarArbolProgramaDep,
    fecha_corte: Annotated[
        date | None,
        Query(description="Fecha contra la que se mide el desfase; por defecto hoy."),
    ] = None,
) -> ArbolDeProgramaRespuesta:
    """El Gantt jerárquico: nivel y etapa con su barra derivada y su avance
    ponderado (§7.4, §6).

    Todos los roles, como `GET /obras/{id}/ruta-critica` y por la misma razón:
    el Residente ve la de su obra porque RLS no le deja ver otra (§12.4). La
    barra resumen es de **lectura**; capturar sigue siendo en conceptos.

    No escribe nada: el resumen se deriva de las actividades que ya se leyeron.
    Persistirlo sería un segundo lugar donde vive la misma cifra.
    """
    return ArbolDeProgramaRespuesta.desde_dominio(
        await caso_uso.ejecutar(obra_id, fecha_corte=fecha_corte)
    )


@router.post(
    "/obras/{obra_id}/programa/nodos/{prototipo_nodo_id}",
    response_model=NodoProgramadoRespuesta,
    summary="Programar un nodo del árbol y repartir sus días a los conceptos",
    dependencies=[PROGRAMA_DE_OBRA],
    responses={
        **_NO_ENCONTRADA,
        **_CICLO,
        409: {
            "description": (
                "La ventana del nodo choca con lo que sus conceptos ya traen "
                "programado y nadie ha decidido cuál cifra conservar. No se "
                "escribió nada; el cuerpo trae las dos cifras y las actividades "
                "en desacuerdo. Repetir con `forzar: true` conserva la del nodo "
                "(§7.5)."
            )
        },
    },
)
async def programar_nodo_del_arbol(
    obra_id: UUID,
    prototipo_nodo_id: UUID,
    peticion: ProgramarNodoPeticion,
    caso_uso: ProgramarNodoDelArbolDep,
) -> NodoProgramadoRespuesta:
    """Captura gruesa: 20 días en una etapa acomodan a sus conceptos uno tras
    otro dentro de esa ventana, repartidos por importe (§7.4, §11.2).

    **No crea una actividad de resumen**: escribe la duración y las fechas de
    los conceptos que ya existen. Una fila de resumen duplicaría cantidad,
    avance y costo sobre los de sus hijos (§6, §7.6).
    """
    return NodoProgramadoRespuesta.desde_dominio(
        await caso_uso.ejecutar(
            ComandoProgramarNodo(
                obra_id=obra_id,
                prototipo_nodo_id=prototipo_nodo_id,
                duracion_dias=peticion.duracion_dias,
                fecha_inicio=peticion.fecha_inicio,
                forzar=peticion.forzar,
            )
        )
    )


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
