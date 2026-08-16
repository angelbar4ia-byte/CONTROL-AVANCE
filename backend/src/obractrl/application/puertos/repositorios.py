"""Puertos de persistencia.

Spec §12.11 (inversión de dependencias) · §11.1 (fachadas).

Los puertos se **declaran aquí** (lado de la aplicación) y se **implementan en
el borde** (`adapters/repos`). El dominio y los casos de uso solo conocen estas
interfaces; nunca a SQLModel ni a la sesión de base de datos.

Un módulo **nunca** toca las tablas ni el repositorio de otro: la comunicación
entre contextos es por fachada o por evento de dominio (§11.1).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

from obractrl.domain.programacion.cpm import NodoCPM
from obractrl.domain.shared.diccionario import TipoSemana

__all__ = [
    "RegistroNoEncontrado",
    "RepositorioActividades",
    "RepositorioCalendario",
    "RepositorioCierres",
    "RepositorioClusters",
    "RepositorioConfiguracion",
    "RepositorioEstimaciones",
    "RepositorioEvaluaciones",
    "RepositorioFrentes",
    "RepositorioIncidencias",
    "RepositorioMateriales",
    "RepositorioObras",
    "RepositorioPrototipos",
    "RepositorioProyectos",
    "UnidadDeTrabajo",
]


class RegistroNoEncontrado(LookupError):
    """Una escritura scoped (`UPDATE ... WHERE id = ...`) no afectó ninguna fila.

    Cualquier implementación de un puerto que haga una escritura acotada bajo
    RLS debe levantar esto —o una subclase propia— cuando el `rowcount` es 0:
    la fila ya no existe, o salió del alcance del rol entre la lectura y la
    escritura (§12.4). Se declara aquí, en el puerto, y no en el adaptador
    concreto, para que los casos de uso puedan atraparla sin importar de
    `adapters/` —eso violaría la regla de dependencia que exige
    `import-linter` (§12.11): la aplicación no toca la infraestructura
    directamente, solo sus propias abstracciones.
    """


@runtime_checkable
class RepositorioActividades(Protocol):
    """Acceso a actividades. Siempre scoped por RLS (`org_id`) — §12.11."""

    async def obtener(self, actividad_id: UUID) -> dict | None: ...

    async def actualizar_avance(
        self,
        actividad_id: UUID,
        *,
        cant_programada: Decimal,
        estatus: str,
    ) -> None: ...
    # `cant_ejecutada` y `avance_pct` no viajan: se derivan de la bitácora
    # (`registrar_captura`) en la BD. Ver D5 en `MD/ROADMAP.md`.

    async def registrar_captura(
        self,
        actividad_id: UUID,
        *,
        fecha: date,
        delta_ejecutado: Decimal,
        usuario_id: UUID,
        evidencias: list[str],
    ) -> UUID: ...

    async def nodos_cpm_de_obra(self, obra_id: UUID) -> list[NodoCPM]:
        """Actividades de la obra como grafo para el motor CPM (§6)."""
        ...

    async def guardar_resultado_cpm(
        self,
        obra_id: UUID,
        resultados: dict[str, dict],
    ) -> None: ...

    async def marcar_bloqueadas(
        self, obra_id: UUID, refs: set[str], bloqueada: bool
    ) -> None: ...

    async def marcar_estatus(self, actividad_id: UUID, estatus: str) -> None:
        """Fija un estatus de flujo (``pendiente_cierre``, ``concluida``…)
        sin tocar cantidades — lo usa el caso de uso de cierres (§11.3 C), no
        el motor de avance (§6)."""
        ...


@runtime_checkable
class RepositorioCierres(Protocol):
    """Acceso a solicitudes de cierre. Siempre scoped por RLS — §12.11, §12.4."""

    async def obtener(self, cierre_id: UUID) -> dict | None: ...

    async def crear(
        self,
        *,
        actividad_id: UUID,
        solicitada_por: UUID,
        cantidad: Decimal,
        monto: Decimal,
        checklist: list[dict],
        adjuntos: list[str],
    ) -> UUID: ...

    async def actualizar(
        self,
        cierre_id: UUID,
        *,
        estatus: str,
        autorizada_por: UUID | None = None,
        validada_por: UUID | None = None,
        comentarios: str | None = None,
    ) -> None: ...

    async def listar(self, *, estatus: str | None = None) -> list[dict]:
        """Bandeja por rol: RLS ya acota el alcance (§11.2)."""
        ...


@runtime_checkable
class RepositorioProyectos(Protocol):
    """Proyectos (§7.2). Alcance por rol vía `app.proyecto_visible` (§12.4)."""

    async def crear(self, datos: dict) -> UUID:
        """Alta de proyecto ya validada por el dominio (§11.2, roles C y SI)."""
        ...

    async def obtener(self, proyecto_id: UUID) -> dict | None: ...

    async def listar(self) -> list[dict]:
        """Proyectos visibles para el rol actual: RLS ya acota el alcance."""
        ...


@runtime_checkable
class RepositorioClusters(Protocol):
    """Clusters —manzanas— de un proyecto (§7.2). Alcance del Supervisor (§4)."""

    async def crear(self, datos: dict) -> UUID: ...

    async def obtener(self, cluster_id: UUID) -> dict | None: ...

    async def listar(self, proyecto_id: UUID | None = None) -> list[dict]: ...


@runtime_checkable
class RepositorioPrototipos(Protocol):
    """Prototipos —modelos de vivienda— del proyecto (§7.2)."""

    async def crear(self, datos: dict) -> UUID: ...

    async def obtener(self, prototipo_id: UUID) -> dict | None: ...

    async def listar(self, proyecto_id: UUID | None = None) -> list[dict]: ...


@runtime_checkable
class RepositorioFrentes(Protocol):
    """Catálogo de frentes (§8.3). Semilla editable de organización (§8.7):
    lo lee cualquier rol (§11.2 `GET /frentes`), lo escribe Configuración."""

    async def listar(self, *, solo_activos: bool = True) -> list[dict]: ...


@runtime_checkable
class RepositorioObras(Protocol):
    async def obtener(self, obra_id: UUID) -> dict | None: ...

    async def actualizar_avance(self, obra_id: UUID, avance_pct: Decimal) -> None: ...

    async def arbol_prototipo(self, prototipo_id: UUID) -> list[dict]:
        """Nodos WBS del prototipo, ordenados (§7.4). Alimenta el workflow A."""
        ...

    async def crear(self, datos: dict) -> UUID:
        """Alta de obra ya validada por el dominio (§11.2 `POST /obras`)."""
        ...

    async def crear_en_lote(self, obras: list[dict]) -> list[UUID]:
        """Alta masiva (§11.2 `POST /obras/bulk`), en una sola transacción."""
        ...

    async def actualizar(self, obra_id: UUID, cambios: dict) -> None:
        """Edición parcial (§11.2 `PATCH /obras/{id}`). Solo las claves
        presentes en `cambios` se escriben."""
        ...

    async def listar(
        self,
        *,
        proyecto_id: UUID | None = None,
        cluster_id: UUID | None = None,
        residente_id: UUID | None = None,
        estatus: str | None = None,
    ) -> list[dict]:
        """Obras visibles para el rol actual: RLS ya acota el alcance (§11.2)."""
        ...

    async def tiene_actividades(self, obra_id: UUID) -> bool:
        """Si la obra ya se generó, volver a generarla la duplicaría (§11.3 A)."""
        ...

    async def precios_vigentes(self, concepto_ids: list[UUID]) -> dict[str, dict]:
        """CPU vigente por concepto (§7.3) para el workflow A.

        Devuelve ``{concepto_id: {"precio_unitario", "precio_destajo"}}``; los
        conceptos sin CPU vigente simplemente no aparecen —el dominio decide
        qué hacer con los faltantes (§11.3 A.2).
        """
        ...

    async def items_programa_base(self, prototipo_id: UUID) -> list[dict]:
        """Items del `ProgramaBase` vigente del prototipo (§7.5). Lista vacía
        si el prototipo aún no tiene plantilla de duraciones."""
        ...

    async def instanciar_programa(self, obra_id: UUID) -> UUID:
        """Crea el `ProgramaObra` vigente de la obra (§7.5, §11.3 A.2)."""
        ...

    async def crear_actividades(
        self, obra_id: UUID, programa_obra_id: UUID, actividades: list[dict]
    ) -> None:
        """Persiste las `Actividad` ya planeadas por el dominio (§11.3 A.2)."""
        ...


@runtime_checkable
class RepositorioEstimaciones(Protocol):
    async def ultimo_consecutivo(self, semana: int, anio: int) -> int:
        """Último consecutivo de la semana.

        El contador es compartido entre ERP y no-ERP (§3.2), así que la
        implementación **no** debe filtrar por origen.
        """
        ...

    async def crear(self, datos: dict) -> UUID: ...

    async def actividades_estimables(
        self, obra_id: UUID, semana: int, anio: int
    ) -> list[dict]:
        """Actividades con avance validado de la semana (§11.3 E.2)."""
        ...

    async def agregar_conceptos(
        self, estimacion_id: UUID, conceptos: list[dict]
    ) -> None:
        """Persiste las líneas `EstimacionConcepto` ya calculadas por el
        dominio (§11.3 E.2)."""
        ...

    async def obtener(self, estimacion_id: UUID) -> dict | None:
        """Cabecera de la estimación, sin sus conceptos (§11.3 E.3-4)."""
        ...

    async def actualizar_estatus(
        self,
        estimacion_id: UUID,
        *,
        estatus: str,
        validada_por: UUID | None = None,
    ) -> None: ...

    async def listar(self, obra_id: UUID) -> list[dict]:
        """Bandeja de estimaciones de una obra: RLS ya acota el alcance."""
        ...


@runtime_checkable
class RepositorioCalendario(Protocol):
    """La tabla `calendario` es la única fuente de la base temporal (§3.1)."""

    async def semana_de(self, fecha: date, tipo: TipoSemana) -> tuple[int, int]: ...

    async def rango_de_semana(
        self, semana: int, anio: int, tipo: TipoSemana
    ) -> tuple[date, date]: ...

    async def semana_activa(self, tipo: TipoSemana) -> tuple[int, int]:
        """Ancla fijada por el admin (§3.1)."""
        ...


@runtime_checkable
class RepositorioConfiguracion(Protocol):
    """Configurables (§8.7).

    En runtime el sistema lee **primero** de aquí; el default canónico del
    código es solo el fallback. Nunca se clava un configurable como constante.
    """

    async def obtener(
        self, clave: str, *, ambito: str = "global", ambito_id: UUID | None = None
    ) -> object | None: ...

    async def decimal(
        self, clave: str, default: Decimal, *, ambito_id: UUID | None = None
    ) -> Decimal: ...


@runtime_checkable
class RepositorioMateriales(Protocol):
    """Movimientos de almacén y su cruce contra presupuesto (§7.7, §10.5).

    `salida_almacen` entra al alcance por obra (política `salida_almacen_scope`,
    `database/migrations/20260814000012`, vía `obra_visible`); `motivo_almacen`
    es semilla editable de organización (§8.7), visible a cualquier usuario de
    la org. `v_consumo_vs_presupuesto` no trae RLS propia —hereda la de las
    tablas que consulta—, así que la implementación debe acotarla por
    `obra_id` explícitamente (no acota sola por org/obra).
    """

    async def obtener_motivo(self, motivo_id: UUID) -> dict | None:
        """Motivo de almacén con su `signo` y `bucket` (§10.5)."""
        ...

    async def crear_salida(self, datos: dict) -> UUID:
        """Inserta el movimiento ya validado por el caso de uso (§10.5)."""
        ...

    async def consumo_vs_presupuesto(self, obra_id: UUID) -> list[dict]:
        """Consumo real vs teórico por insumo de una obra (§7.7, §10.5),
        sobre `v_consumo_vs_presupuesto`."""
        ...

    async def listar_salidas(self, obra_id: UUID | None = None) -> list[dict]:
        """Bandeja de movimientos; RLS ya acota el alcance (§11.2)."""
        ...


@runtime_checkable
class UnidadDeTrabajo(Protocol):
    """Transacción. El commit de una carga es atómico (§9.2)."""

    async def __aenter__(self) -> UnidadDeTrabajo: ...

    async def __aexit__(self, *exc_info: object) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


@runtime_checkable
class RepositorioIncidencias(Protocol):
    """Acceso a incidencias. Siempre scoped por RLS — §12.11, §12.4, §7.8."""

    async def obtener(self, incidencia_id: UUID) -> dict | None: ...

    async def crear(
        self,
        *,
        obra_id: UUID,
        creada_por: UUID,
        tipo: str,
        impacto: str,
        titulo: str,
        descripcion: str | None = None,
        frente_id: UUID | None = None,
        evidencias: list[str] | None = None,
        bloquea_actividades: list[str] | None = None,
        fecha_limite: date | None = None,
    ) -> UUID: ...

    async def actualizar(
        self,
        incidencia_id: UUID,
        *,
        estatus: str,
        asignada_a: UUID | None = None,
    ) -> None: ...

    async def registrar_evento(
        self,
        incidencia_id: UUID,
        *,
        usuario_id: UUID,
        accion: str,
        estatus_previo: str,
        estatus_nuevo: str,
        comentario: str | None = None,
    ) -> UUID:
        """Bitácora de la incidencia (`incidencia_evento`, §7.8)."""
        ...

    async def listar(self, *, estatus: str | None = None) -> list[dict]:
        """Bandeja por rol: RLS ya acota el alcance (§11.2)."""
        ...


@runtime_checkable
class RepositorioEvaluaciones(Protocol):
    """Acceso a evaluaciones de desempeño. Siempre scoped por RLS — §12.11, §12.4."""

    async def obtener(self, evaluacion_id: UUID) -> dict | None: ...

    async def crear(
        self,
        *,
        sujeto_tipo: str,
        sujeto_id: UUID,
        evaluador_id: UUID,
        nivel: str,
        periodo: str,
        obra_id: UUID | None = None,
    ) -> UUID: ...

    async def respuestas_de(self, evaluacion_id: UUID) -> list[dict]:
        """Respuestas ya registradas, para reconstruir la entidad antes de
        agregar nuevas (evita repetir criterio, §7.8)."""
        ...

    async def pesos_de_criterios(self, criterio_ids: list[UUID]) -> dict[UUID, Decimal]:
        """Pesos vigentes del catálogo (`criterio_evaluacion.peso`, semilla
        editable, §8.7) para los criterios que se están respondiendo."""
        ...

    async def agregar_respuestas(
        self,
        evaluacion_id: UUID,
        *,
        respuestas: list[dict],
        puntaje: Decimal | None,
    ) -> None: ...

    async def listar(
        self, *, nivel: str | None = None, sujeto_tipo: str | None = None
    ) -> list[dict]:
        """Bandeja por rol: RLS ya acota el alcance (§11.2)."""
        ...

    async def listar_criterios(self, *, aplica_a: str | None = None) -> list[dict]:
        """Catálogo `criterio_evaluacion` vigente (§11.2 `GET /criterios-evaluacion`)."""
        ...
