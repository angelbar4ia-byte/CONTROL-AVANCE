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
    "RepositorioAsignaciones",
    "RepositorioCalendario",
    "RepositorioCierres",
    "RepositorioCierresDeObra",
    "RepositorioClusters",
    "RepositorioConceptos",
    "RepositorioConfiguracion",
    "RepositorioContratistas",
    "RepositorioCuadrillas",
    "RepositorioEstimaciones",
    "RepositorioEvaluaciones",
    "RepositorioExpediente",
    "RepositorioFamilias",
    "RepositorioFrentes",
    "RepositorioIncidencias",
    "RepositorioInsumos",
    "RepositorioMateriales",
    "RepositorioNivelesEtapas",
    "RepositorioObras",
    "RepositorioPresupuestos",
    "RepositorioProgramas",
    "RepositorioPrototipoNodo",
    "RepositorioPrototipos",
    "RepositorioProyectos",
    "RepositorioRevisiones",
    "RepositorioTorre",
    "RepositorioUnidades",
    "RepositorioUsuarios",
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

    async def obtener_para_captura(self, actividad_id: UUID) -> dict | None:
        """Como `obtener`, pero bloqueando la fila hasta el commit.

        Lo necesita `CapturarAvance`, que deriva un delta de un absoluto (D6)
        mientras el móvil escribe deltas por su lado (D5). Sin bloqueo, la
        carrera deja el total en un valor que nadie capturó.
        """
        ...

    async def crear_extra(self, datos: dict) -> UUID:
        """Alta extra-catálogo (§11.2 `POST /actividades`). Devuelve su id."""
        ...

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

    # --- Programación · CPM (§7.5, §11.2) --------------------------------
    #
    # Los campos de programación (`duracion_dias`, `dependencias`,
    # `fecha_inicio`, `fecha_termino`, `es_critica`, `holgura`, `desfase`)
    # viven en `actividad` por el §7.6, así que el contexto Programación los
    # lee y escribe **por este puerto**, nunca tocando la tabla desde su
    # propio repositorio (§11.1: ningún módulo toca las tablas de otro).

    async def programacion_de_obra(self, obra_id: UUID) -> list[dict]:
        """Cronograma completo de la obra: lo que el CPM y el Gantt necesitan
        de cada actividad (§7.6, §11.2 `GET /obras/{id}/ruta-critica`)."""
        ...

    async def programacion_de(self, actividad_id: UUID) -> dict | None:
        """Programación de una sola actividad, con su `obra_id` (§11.2
        `PATCH /actividades/{id}/programacion`)."""
        ...

    async def aplicar_programacion(
        self,
        obra_id: UUID,
        *,
        programa_obra_id: UUID,
        programaciones: list[dict],
    ) -> None:
        """Baja el cronograma instanciado a las actividades y las ata a la
        versión de `ProgramaObra` que las programó (§7.5, §11.2)."""
        ...

    async def actualizar_programacion(
        self, actividad_id: UUID, cambios: dict
    ) -> None:
        """Ajuste manual de una actividad; solo las claves presentes se
        escriben (§11.2 `PATCH /actividades/{id}/programacion`)."""
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

    async def listar_de_obra(self, obra_id: UUID) -> list[dict]:
        """Cierres de una obra, con fechas y adjuntos, para el expediente
        (§7.9, §11.2 `GET /obras/{id}/expediente`).

        Método aparte de `listar` y no un filtro más: la bandeja del §11.2
        pagina por estatus y no necesita los adjuntos, mientras que el
        expediente los necesita todos y con sus fechas. `solicitud_cierre` no
        tiene `obra_id` propio —llega a la obra por su actividad (§7.8)—, así
        que la implementación resuelve el vínculo; el expediente no toca la
        tabla de otro contexto (§11.1).
        """
        ...


@runtime_checkable
class RepositorioCierresDeObra(Protocol):
    """Cierre de obra **final** (§11.3 D), distinto del de actividad (§11.3 C).

    Comparten la palabra y nada más: otro flujo, otros roles, otra tabla. Por
    eso son dos puertos y no uno con métodos que significan cosas distintas
    según cuál se llame.
    """

    async def abrir(self, *, obra_id: UUID, abierto_por: UUID) -> UUID:
        """Abre el acta en `en_proceso`. Idempotente: una obra tiene un cierre."""
        ...

    async def obtener(self, cierre_id: UUID) -> dict | None: ...

    async def obtener_de_obra(self, obra_id: UUID) -> dict | None: ...

    async def listar(self, *, estatus: str | None = None) -> list[dict]: ...

    async def cerrar(self, cierre_id: UUID, *, fecha: date, acta: str | None) -> None:
        """Firma el acta. Levanta `RegistroNoEncontrado` si ya estaba cerrada:
        es lo que impide cerrarla dos veces desde dos peticiones."""
        ...

    async def participar(
        self,
        *,
        cierre_obra_id: UUID,
        usuario_id: UUID,
        rol: str,
        comentario: str | None,
        evidencias: list[str],
    ) -> UUID: ...

    async def participaciones(self, cierre_obra_id: UUID) -> list[dict]: ...

    async def estado_de_obra(self, obra_id: UUID) -> dict | None:
        """Lo que `evaluar_pendientes` necesita para decidir si se puede
        entregar: avance, actividades, cierres, estimaciones, incidencias,
        expediente y evaluaciones — en una sola consulta."""
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

    # Solo la usa el cargador masivo (§7.2): la edición individual no tiene
    # endpoint PATCH todavía, así que este método no tiene otro llamador.
    async def actualizar(self, prototipo_id: UUID, campos: dict) -> None: ...


@runtime_checkable
class RepositorioPrototipoNodo(Protocol):
    """Árbol WBS del prototipo (§7.4): nivel/etapa/concepto.

    Hasta el cargador de presupuesto jerárquico (§10.6) nadie escribía esta
    tabla — `RepositorioObras.arbol_prototipo` solo la lee (§11.1, otra
    fachada, otro contexto). La clave de un nodo (`NIV-`, `ECO-`) no es
    única por organización: se repite igual en cada prototipo, así que la
    identidad natural es `(prototipo_id, clave)` (`uq_prototipo_nodo_clave`,
    migración 0030).
    """

    async def por_prototipo(self, prototipo_id: UUID) -> list[dict]:
        """Nodos vigentes del árbol de un prototipo, con clave.

        La usa el aplicador para capturar el ``antes`` de cada nodo que va a
        tocar —antes de llamar `upsert`— porque el `id` que conserva un
        upsert no basta para revertir: la reversa necesita los valores
        previos, no solo saber que la fila ya existía (§10.8).
        """
        ...

    async def arbol(self, prototipo_id: UUID) -> list[dict]:
        """Los mismos nodos que `por_prototipo`, en recorrido en profundidad
        padre-antes-que-hijos (mismo criterio que
        `RepositorioObras.arbol_prototipo`, §11.1): lo que pinta la pantalla
        de Prototipos y, con los `programa_base_item` superpuestos por
        `prototipo_nodo_id`, la de Programas base.
        """
        ...

    async def upsert(
        self, prototipo_id: UUID, *, clave: str | None, datos: dict
    ) -> tuple[UUID, bool]:
        """Inserta o actualiza por `(org_id, prototipo_id, clave)`.

        Conserva el `id` existente en una recarga —a propósito: lo
        referencian por igualdad literal `programa_base_item.
        prototipo_nodo_id` y `actividad.prototipo_nodo_id`
        (`domain.programacion.reglas`); regenerar ids en cada carga
        rompería esas referencias en silencio. `clave=None` (si algún nodo
        no trae una) siempre inserta: sin identidad natural no hay con qué
        hacer match. Devuelve `(id, es_alta)`.
        """
        ...


@runtime_checkable
class RepositorioNivelesEtapas(Protocol):
    """Catálogo de niveles y etapas de construcción (§10.1), compartido por
    toda la organización — no por prototipo, `uq_nivel_clave`/
    `uq_etapa_clave` son `(org_id, clave)`.

    Sin escritor hasta el cargador de presupuesto jerárquico. La primera
    carga que trae una clave define su descripción; una carga posterior con
    la misma clave y otra descripción **no la sobreescribe** (es texto, no
    afecta ningún cálculo — a diferencia de una composición de concepto en
    conflicto, que si se sobreescribiera silenciosamente sí distorsionaría
    un precio).
    """

    async def upsert_nivel(self, *, clave: str, descripcion: str, orden: int) -> UUID: ...

    async def upsert_etapa(
        self, *, clave: str, descripcion: str, nivel_id: UUID | None, orden: int
    ) -> UUID: ...


@runtime_checkable
class RepositorioPresupuestos(Protocol):
    """Presupuesto de un prototipo y sus partidas (§7.3, §7.4).

    Solo lectura hasta el cargador de presupuesto jerárquico — `presupuesto`
    entra por carga de Excel y se versiona ahí (§10.8); un endpoint que lo
    dejara capturar a mano abriría un segundo camino de alta con otro
    versionado (`adapters/api/v1/presupuesto.py`, docstring del router).
    """

    async def vigente_de_prototipo(self, prototipo_id: UUID) -> dict | None: ...

    async def presupuesto_de_obra(self, obra_id: UUID) -> dict | None: ...

    async def partidas(self, presupuesto_id: UUID) -> list[dict]: ...

    async def otros_prototipos_con_partida_vigente(
        self, concepto_id: UUID, *, excluir_prototipo_id: UUID
    ) -> list[UUID]:
        """Prototipos (distintos del excluido) cuyo presupuesto **vigente**
        tiene una partida para este concepto.

        La usa el cargador de presupuesto jerárquico para distinguir un
        conflicto real (otro prototipo ya depende de la composición vigente)
        de un prototipo recargando su propia corrección: si nadie más
        vigente usa el concepto, no hay a quién dejarle una composición
        vieja — la carga puede actualizarlo sin pedir permiso."""
        ...

    async def versiones_de_prototipo(self, prototipo_id: UUID) -> list[dict]: ...

    async def rendimiento_por_concepto(self, obra_id: UUID) -> list[dict]: ...

    async def rendimiento_por_cuadrilla(self, obra_id: UUID) -> list[dict]: ...

    async def resumen_por_obra(self, *, proyecto_id: UUID | None = None) -> list[dict]: ...

    async def crear_version(
        self, prototipo_id: UUID, *, origen: str, carga_id: UUID | None
    ) -> dict:
        """Retira el vigente anterior (si hay) e inserta la versión
        siguiente como vigente (§10.8). Mismo orden que
        `RepositorioConceptos.publicar_version_cpu`: `uq_presupuesto_vigente`
        es un índice único parcial y no diferible, así que primero se retira
        y luego se inserta. El resultado incluye ``anterior_id`` —el `id`
        de la versión que quedó en `vigente=false`, o `None` si no había
        ninguna— para que el aplicador pueda registrar esa operación y la
        reversa la restaure."""
        ...

    async def agregar_partidas(
        self, presupuesto_id: UUID, partidas: list[dict]
    ) -> list[dict]:
        """Inserta las partidas y devuelve las filas persistidas, completas,
        para el snapshot del lote (§10.8)."""
        ...

    async def actualizar_monto_total(self, presupuesto_id: UUID, monto_total: Decimal) -> None: ...


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
class RepositorioProgramas(Protocol):
    """Programación: plantilla del prototipo y cronograma de la obra (§7.5).

    Cubre las tres tablas del contexto —`programa_base`, `programa_base_item`
    y `programa_obra`— y **solo** esas: los campos de programación de la
    `Actividad` (§7.6) se tocan por `RepositorioActividades`, que es su puerto
    (§11.1).

    Alcance: `programa_base` y `programa_base_item` entran al bloque de
    catálogo de `rls_policies` (lectura para la org, escritura para
    `app.es_config()`); `programa_obra` entra al bloque por obra
    (`app.obra_visible(obra_id)`). Ninguna implementación filtra `org_id` a
    mano.
    """

    async def crear_base(self, datos: dict) -> UUID:
        """Alta de `ProgramaBase` con su versión (§11.2 `POST /programas-base`).

        La implementación resuelve la versión siguiente del prototipo y retira
        el vigente anterior: `uq_programa_base_vigente` deja un solo vigente
        por prototipo.
        """
        ...

    async def obtener_base(self, programa_base_id: UUID) -> dict | None: ...

    async def listar_bases(
        self, *, prototipo_id: UUID | None = None, solo_vigentes: bool = False
    ) -> list[dict]:
        """Programas base visibles (§11.2 `GET /programas-base`)."""
        ...

    async def agregar_items_base(
        self, programa_base_id: UUID, items: list[dict]
    ) -> None:
        """Renglones ya validados por el dominio (`validar_item_base`)."""
        ...

    async def listar_items_base(self, programa_base_id: UUID) -> list[dict]:
        """§11.2 `GET /programas-base/{id}/items`."""
        ...

    async def items_base_vigente(self, prototipo_id: UUID) -> list[dict]:
        """Renglones del programa base **vigente** del prototipo (§7.5).
        Lista vacía si el prototipo aún no tiene plantilla."""
        ...

    async def programa_vigente(self, obra_id: UUID) -> dict | None:
        """`ProgramaObra` vigente de la obra (§11.2 `GET /obras/{id}/programa`)."""
        ...

    async def listar_programas(self, obra_id: UUID) -> list[dict]:
        """Historial de versiones del cronograma de la obra (§7.5)."""
        ...

    async def instanciar(self, obra_id: UUID, *, fecha_corte: date | None) -> dict:
        """Crea la siguiente versión vigente de `ProgramaObra` y retira la
        anterior (§7.5, §11.2 `POST /obras/{id}/programa`)."""
        ...

    async def fijar_fecha_corte(self, programa_obra_id: UUID, fecha: date) -> None:
        """Deja constancia de contra qué fecha se midió el último recálculo
        (§7.5 `ProgramaObra.fecha_corte`, §6 desfase)."""
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

    async def conceptos_de(self, estimacion_id: UUID) -> list[dict]:
        """Renglones de la estimación, listos para exportar (§11.2 `GET
        /estimaciones/{id}/export`).

        Trae la línea de `estimacion_concepto` ya acompañada de lo que el
        Excel necesita rotular —clave y descripción del concepto, unidad— tal
        como `actividades_estimables` acompaña la actividad con su precio: el
        renglón de una estimación no se entiende sin el concepto que estima.
        """
        ...

    # --- Bloqueo del periodo (§11.3 E.5) ---------------------------------

    async def bloquear_periodo(
        self,
        *,
        obra_id: UUID,
        tipo_semana: str,
        semana: int,
        anio: int,
        estimacion_id: UUID,
        usuario_id: UUID,
    ) -> None:
        """Cierra la semana de la obra al validar (§11.3 E.5 "bloquear
        periodo").

        Idempotente: validar dos veces la misma estimación —o dos
        estimaciones de modos distintos de la misma semana— no puede reventar
        con un choque de índice único; el periodo ya bloqueado sigue
        bloqueado.
        """
        ...

    async def periodo_bloqueado(
        self, *, obra_id: UUID, tipo_semana: str, semana: int, anio: int
    ) -> bool:
        """¿La semana de esa obra ya está cerrada? (§11.3 E.5)"""
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

    async def listar_motivos(self, *, solo_activos: bool = True) -> list[dict]:
        """Catálogo vivo de motivos (§8.7, semilla editable).

        El cargador de almacén cruza por la columna `Motivo` del archivo
        (§10.6) y un motivo no catalogado va a la bandeja (§10.3, §10.5), así
        que necesita la lista completa, no un motivo a la vez.
        """
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

    async def listar(
        self, *, estatus: str | None = None, obra_id: UUID | None = None
    ) -> list[dict]:
        """Bandeja por rol: RLS ya acota el alcance (§11.2).

        `obra_id` lo usa el expediente (§7.9), que reúne las evidencias de la
        obra sin leer la tabla de incidencias por su cuenta (§11.1).
        """
        ...


@runtime_checkable
class RepositorioRevisiones(Protocol):
    """Revisiones físicas de campo (§7.8). Scoped por RLS — §12.4.

    `revision_fisica` entra al loop `por_obra` de
    `database/migrations/20260814000012_rls_policies.sql` (vía `obra_visible`),
    así que ninguna implementación filtra por `org_id` u `obra_id` a mano: eso
    lo impone la base, igual que en `cierres` e `incidencias`.
    """

    async def crear(
        self,
        *,
        obra_id: UUID,
        usuario_id: UUID,
        fecha: date,
        fotos: list[str],
        comentario: str | None = None,
        calidad: int | None = None,
        actividad_id: UUID | None = None,
        incidencia_id: UUID | None = None,
    ) -> UUID:
        """Alta ya validada por el dominio (§11.2 `POST /obras/{id}/revisiones`)."""
        ...

    async def listar(self, *, obra_id: UUID | None = None) -> list[dict]:
        """Bandeja `GET /revisiones`: RLS ya acota el alcance (§11.2)."""
        ...


# --- Catálogos · APU (§7.3, §11.2) ---------------------------------------
#
# Los catálogos entran al bloque A de `rls_policies` (migración
# 20260814000012): **lectura** para cualquier usuario de la organización,
# **escritura** solo para `app.es_config()` —Control de obra y Super
# intendente (§5.1)—. Ninguna implementación filtra por `org_id` a mano.
#
# La CLAVE es única por catálogo y es la que manda en todo cruce (§3.3), así
# que el alta de cualquiera de estos puertos puede chocar con su índice único
# (`uq_unidad_clave`, `uq_insumo_clave`…): eso es correcto, es el §3.3 en la
# base.


@runtime_checkable
class RepositorioUnidades(Protocol):
    """Catálogo de unidades con sinónimos y factor (§7.3, §3.5).

    Semilla editable (§8.7): el front la lee directo de Supabase (§10.7) y la
    escribe por aquí.
    """

    async def crear(self, datos: dict) -> UUID: ...

    async def obtener(self, unidad_id: UUID) -> dict | None: ...

    async def listar(self, *, solo_activos: bool = True) -> list[dict]: ...


@runtime_checkable
class RepositorioFamilias(Protocol):
    """Árbol de familias (§7.3). En materiales define el IVA (§3.5)."""

    async def crear(self, datos: dict) -> UUID: ...

    async def obtener(self, familia_id: UUID) -> dict | None: ...

    async def listar(
        self, *, aplica_a: str | None = None, solo_activos: bool = True
    ) -> list[dict]: ...


@runtime_checkable
class RepositorioCuadrillas(Protocol):
    """Cuadrillas (§7.3, §10.6): grupos de trabajadores a los que se les
    asigna un destajo.

    Hasta el cargador de mano de obra (§10.6) nadie escribía esta tabla
    (migración 0005) — solo se leía para reportes (`rendimiento_por_
    cuadrilla`, Torre de control). Sin pantalla de alta propia todavía: el
    único escritor es este cargador, que la da de alta con lo mínimo
    (clave, nombre) igual que unidad/familia — `contratista_id`/
    `frente_id`/`lider`/`integrantes` quedan para cuando exista esa
    pantalla.
    """

    async def crear(self, datos: dict) -> UUID: ...

    async def listar(self, *, solo_activos: bool = True) -> list[dict]: ...

    async def actualizar_rendimiento(self, cuadrilla_id: UUID, rendimiento: Decimal) -> None:
        """La cuadrilla "asume" el rendimiento teórico de la mano de obra
        que se le asigna (§10.6) — no se toca si el archivo no lo trae."""
        ...


@runtime_checkable
class RepositorioInsumos(Protocol):
    """Recursos base del APU (§7.3).

    `Material` **no** es otra tabla: es un insumo con ``tipo = 'material'``
    (§7.3), así que `GET /materiales` (§11.2) es este mismo puerto con el
    filtro puesto. Duplicarlo partiría la clave única del catálogo (§3.3).
    """

    async def crear(self, datos: dict) -> UUID: ...

    async def obtener(self, insumo_id: UUID) -> dict | None: ...

    async def actualizar(self, insumo_id: UUID, cambios: dict) -> None:
        """Edición parcial; solo las claves presentes se escriben.

        La `clave` no es editable: es la identidad del registro (§3.3). La
        usan el cargador de materiales (modo Actualizar, §10.2) y el de
        almacén para bajar la valuación del §10.5.
        """
        ...

    async def listar(
        self,
        *,
        tipo: str | None = None,
        familia_id: UUID | None = None,
        solo_activos: bool = True,
    ) -> list[dict]:
        """Insumos visibles; `tipo='material'` da el catálogo de materiales."""
        ...


@runtime_checkable
class RepositorioContratistas(Protocol):
    """Contratistas oficiales (§7.3, §10.1)."""

    async def crear(self, datos: dict) -> UUID: ...

    async def obtener(self, contratista_id: UUID) -> dict | None: ...

    async def listar(self, *, solo_activos: bool = True) -> list[dict]: ...


@runtime_checkable
class RepositorioConceptos(Protocol):
    """Conceptos, su explosión y sus versiones de CPU (§7.3)."""

    async def crear(self, datos: dict) -> UUID: ...

    async def obtener(self, concepto_id: UUID) -> dict | None: ...

    async def listar(
        self,
        *,
        tipo: str | None = None,
        familia_id: UUID | None = None,
        solo_activos: bool = True,
    ) -> list[dict]: ...

    async def composicion_recursiva(self, concepto_id: UUID) -> list[dict]:
        """Filas de `Explosion` de **todo** concepto alcanzable desde la raíz.

        El dominio explota por CLAVE (§3.3), así que cada fila trae ya
        resueltas ``concepto_clave``, ``insumo_clave`` y
        ``concepto_hijo_clave`` además de ``categoria``, ``cantidad``,
        ``costo_unitario`` y ``costo_insumo_vigente`` (§10.1).

        Devuelve el conjunto **completo**, incluida la arista que cierra un
        ciclo: detectarlo es del dominio (`CicloEnExplosion`, §7.3), no del
        SQL — la base solo impide el ciclo directo.
        """
        ...

    async def actualizar(self, concepto_id: UUID, cambios: dict) -> None:
        """Edición parcial; la `clave` no es editable (§3.3). La usa el
        cargador de CPU en modo Actualizar (§10.2)."""
        ...

    async def explosion_directa(self, concepto_id: UUID) -> list[dict]:
        """Filas de `Explosion` propias del concepto, sin recursión (§7.3).

        Es lo que el cargador de CPU necesita para guardar el ``antes`` de la
        composición que va a sustituir (§10.8).
        """
        ...

    async def eliminar_explosion(self, concepto_id: UUID) -> None:
        """Borra la composición vigente del concepto (§10.6, §10.8)."""
        ...

    async def agregar_explosion(
        self, concepto_id: UUID, *, cpu_id: UUID | None, filas: list[dict]
    ) -> list[dict]:
        """Inserta la composición nueva y devuelve las filas persistidas,
        completas, para el snapshot del lote (§10.8)."""
        ...

    async def versiones_cpu(self, concepto_id: UUID) -> list[dict]:
        """Historial de CPU del concepto, todas las variantes (§7.3, §10.8)."""
        ...

    async def publicar_version_cpu(
        self,
        concepto_id: UUID,
        *,
        version: int,
        precio_unitario: Decimal,
        precio_destajo: Decimal,
        variante: str | None,
        retirar: list[int],
    ) -> UUID:
        """Inserta la versión nueva como vigente y retira las de ``retirar``.

        Retirar y luego insertar es **una sola operación** a propósito:
        `uq_cpu_vigente` es un índice único parcial y no es diferible, así que
        insertar el nuevo vigente antes de bajar el anterior violaría la
        restricción. Quién retira a quién ya lo decidió el dominio
        (`apu.publicar_version`).
        """
        ...


@runtime_checkable
class RepositorioExpediente(Protocol):
    """Acervo documental de la obra (`expediente_doc`, §7.9).

    `expediente_doc` entra al loop `por_obra` de
    `database/migrations/20260814000012_rls_policies.sql` (vía
    `obra_visible`), así que ninguna implementación filtra por `org_id` u
    `obra_id` a mano: eso lo impone la base, igual que en `revisiones`.
    """

    async def crear(
        self,
        *,
        obra_id: UUID,
        tipo: str,
        nombre: str,
        url: str,
        subido_por: UUID,
    ) -> UUID:
        """Alta ya validada por el dominio (§11.2, roles C y SI)."""
        ...

    async def listar(
        self, obra_id: UUID, *, tipo: str | None = None
    ) -> list[dict]:
        """Documentos visibles de la obra (§11.2 `GET /obras/{id}/expediente`)."""
        ...


@runtime_checkable
class RepositorioUsuarios(Protocol):
    """Identidad, solo para lo que otro contexto necesita de ella (§11.1).

    Existe para que Notificaciones pueda resolver a quién le escribe sin
    consultar `usuario` desde su propio repositorio: la tabla es del contexto
    Identidad/Org (§11.1) y se accede por esta fachada. La política
    `usuario_select` (migración 0012) da lectura a cualquier usuario de la
    organización, así que el alcance sigue siendo el del token.
    """

    async def correos_de(self, usuario_ids: list[UUID]) -> list[dict]:
        """`{id, nombre, email}` de los usuarios pedidos que existan y estén
        en el alcance. Los que no, simplemente no aparecen."""
        ...

    async def tokens_push_de(self, usuario_ids: list[UUID]) -> list[str]:
        """Tokens de Expo Push activos de esos usuarios (§12.2).

        Vive junto a `correos_de` porque resuelve la misma pregunta —a qué
        canal le hablo a esta persona— y así Notificaciones sigue sin conocer
        la tabla `dispositivo_push`, igual que no conoce `usuario` (§11.1).

        Devuelve **solo tokens**, sin decir de quién es cada uno: el emisor no
        necesita saberlo y un token es una capacidad sobre la pantalla ajena.
        La política RLS ni siquiera deja leer el dispositivo de otro; la
        excepción es una función `security definer` con nombre propio
        (migración 0028).
        """
        ...

    async def crear(self, datos: dict) -> UUID:
        """Alta de usuario (§11.2, roles C y SI). Devuelve su id."""
        ...

    async def obtener(self, usuario_id: UUID) -> dict | None: ...

    async def obtener_auth_user_id(self, usuario_id: UUID) -> UUID | None:
        """La cuenta ligada del proveedor de auth, para resetear su contraseña."""
        ...

    async def listar(self, *, rol: str | None = None) -> list[dict]:
        """El equipo de la organización, activos e inactivos (§5.1)."""
        ...

    async def actualizar(self, usuario_id: UUID, cambios: dict) -> None:
        """Edita perfil, rol o estatus. Levanta `RegistroNoEncontrado` si el
        `UPDATE` no tocó ninguna fila."""
        ...

    async def marcar_contrasena_temporal(
        self, usuario_id: UUID, *, temporal: bool
    ) -> None:
        """Enciende o apaga `debe_cambiar_password` (§5.1)."""
        ...

    async def borrar(self, usuario_id: UUID) -> None:
        """Solo para deshacer un alta a medio camino. Dar de baja es
        `estatus = 'inactivo'`, no esto."""
        ...


@runtime_checkable
class RepositorioAsignaciones(Protocol):
    """Los puentes de alcance del §4: quién ve qué.

    Dos tablas con permisos distintos, y a propósito: `supervisor_cluster` lo
    escribe Control de obra; `control_proyecto` **solo** el Super intendente,
    porque decide el alcance de quien administra. El residente no lleva puente:
    llega a su obra por `obra.residente_id`.
    """

    async def asignar_cluster(
        self, *, supervisor_id: UUID, cluster_id: UUID
    ) -> None: ...

    async def retirar_cluster(self, *, supervisor_id: UUID, cluster_id: UUID) -> None:
        """Levanta `RegistroNoEncontrado` si no había nada que retirar."""
        ...

    async def clusters_de(self, supervisor_id: UUID) -> list[dict]: ...

    async def asignar_proyecto(
        self, *, usuario_id: UUID, proyecto_id: UUID
    ) -> None: ...

    async def retirar_proyecto(self, *, usuario_id: UUID, proyecto_id: UUID) -> None:
        """Levanta `RegistroNoEncontrado` si no había nada que retirar."""
        ...

    async def proyectos_de(self, usuario_id: UUID) -> list[dict]: ...


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


@runtime_checkable
class RepositorioTorre(Protocol):
    """Estado agregado de las obras visibles (§5.1, §11.2 `/torre`).

    Lo declara la aplicación porque el **reporte de avance** lo necesita
    (`ArmarReporteDeAvance`), no porque la Torre lo use: su endpoint consulta
    el repositorio directo, como toda lectura sin orquestación de dominio.

    Existe un solo método aquí —el que el caso de uso usa— y no la superficie
    completa de `RepositorioTorreSQL`. Un puerto es lo que el interior
    necesita, no el espejo del adaptador.
    """

    async def estado_de_obras(
        self,
        *,
        proyecto_id: UUID | None = None,
        cluster_id: UUID | None = None,
        solo_con_pendientes: bool = False,
    ) -> list[dict]:
        """Una fila por obra visible con sus contadores. RLS acota el alcance."""
        ...
