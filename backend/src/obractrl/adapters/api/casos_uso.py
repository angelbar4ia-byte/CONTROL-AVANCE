"""Construcción de casos de uso para los endpoints.

Spec §12.11 (el borde ensambla; la aplicación no sabe cómo).

Cada función es una dependencia de FastAPI que arma un caso de uso con
implementaciones concretas de sus puertos, a partir de la sesión con RLS ya
fijado (`SesionRLS`, `adapters/api/dependencias.py`). Los routers dependen de
estas funciones, nunca construyen un repositorio SQL directamente: así el
router solo conoce el caso de uso (aplicación), no `adapters.repos`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from obractrl.adapters.api.avisos import suscribir_avisos
from obractrl.adapters.api.dependencias import ContextoActual, SesionRLS
from obractrl.adapters.excel.cargadores import TipoDeCargaSinCargador, cargador_para
from obractrl.adapters.repos.actividades_sql import RepositorioActividadesSQL
from obractrl.adapters.repos.asignaciones_sql import RepositorioAsignacionesSQL
from obractrl.adapters.repos.calendario_sql import RepositorioCalendarioSQL
from obractrl.adapters.repos.cargas_sql import RepositorioCargasSQL
from obractrl.adapters.repos.cierres_obra_sql import RepositorioCierresDeObraSQL
from obractrl.adapters.repos.cierres_sql import RepositorioCierresSQL
from obractrl.adapters.repos.clusters_sql import RepositorioClustersSQL
from obractrl.adapters.repos.conceptos_sql import RepositorioConceptosSQL
from obractrl.adapters.repos.configuracion_sql import RepositorioConfiguracionSQL
from obractrl.adapters.repos.contratistas_sql import RepositorioContratistasSQL
from obractrl.adapters.repos.control_cambio_sql import RepositorioControlCambioSQL
from obractrl.adapters.repos.cuadrillas_sql import RepositorioCuadrillasSQL
from obractrl.adapters.repos.cuantificacion_sql import (
    RepositorioEnlacesCuantificacionSQL,
    RepositorioNotasPlanoSQL,
    RepositorioPlanosSQL,
    RepositorioTrazosSQL,
)
from obractrl.adapters.repos.desviaciones_sql import RepositorioDesviacionesSQL
from obractrl.adapters.repos.especialidades_sql import (
    RepositorioEspecialidadesSQL,
)
from obractrl.adapters.repos.estimaciones_sql import RepositorioEstimacionesSQL
from obractrl.adapters.repos.evaluaciones_sql import RepositorioEvaluacionesSQL
from obractrl.adapters.repos.expediente_sql import RepositorioExpedienteSQL
from obractrl.adapters.repos.familias_sql import RepositorioFamiliasSQL
from obractrl.adapters.repos.frentes_sql import RepositorioFrentesSQL
from obractrl.adapters.repos.incidencias_sql import RepositorioIncidenciasSQL
from obractrl.adapters.repos.insumos_sql import RepositorioInsumosSQL
from obractrl.adapters.repos.materiales_sql import RepositorioMaterialesSQL
from obractrl.adapters.repos.niveles_etapas_sql import RepositorioNivelesEtapasSQL
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.organizacion_sql import RepositorioOrganizacionSQL
from obractrl.adapters.repos.planeacion_sql import RepositorioPlaneacionSQL
from obractrl.adapters.repos.presupuestos_sql import RepositorioPresupuestosSQL
from obractrl.adapters.repos.programas_sql import RepositorioProgramasSQL
from obractrl.adapters.repos.prototipo_nodo_sql import RepositorioPrototipoNodoSQL
from obractrl.adapters.repos.prototipos_sql import RepositorioPrototiposSQL
from obractrl.adapters.repos.proyectos_sql import RepositorioProyectosSQL
from obractrl.adapters.repos.revisiones_sql import RepositorioRevisionesSQL
from obractrl.adapters.repos.unidad_de_trabajo import UnidadDeTrabajoSQL
from obractrl.adapters.repos.unidades_sql import RepositorioUnidadesSQL
from obractrl.adapters.repos.usuarios_sql import RepositorioUsuariosSQL
from obractrl.application.casos_uso.aplicar_carga import (
    AplicadorAlmacen,
    AplicadorConceptosBase,
    AplicadorContratistas,
    AplicadorCPU,
    AplicadorCuadrillas,
    AplicadorDeCarga,
    AplicadorDePrototipos,
    AplicadorEtapasConstructivas,
    AplicadorFamilias,
    AplicadorIngenieriaLote,
    AplicadorManoObra,
    AplicadorMateriales,
    AplicadorNiveles,
    AplicadorPresupuesto,
    AplicadorPrototipos,
    AplicadorTrabajos,
    AplicadorUnidades,
)
from obractrl.application.casos_uso.calcular_cpu import (
    ExplotarConcepto,
    ObtenerCPU,
    PublicarVersionCPU,
)
from obractrl.application.casos_uso.capturar_avance import CapturarAvance
from obractrl.application.casos_uso.consultar_insumos_programados import (
    ConsultarInsumosProgramados,
)
from obractrl.application.casos_uso.consultar_planeacion import (
    AsignarFrenteDeObra,
    ConsultarPlaneacion,
)
from obractrl.application.casos_uso.cuantificar import (
    ReemplazarEnlace,
    RegistrarNotaPlano,
    RegistrarPlano,
    RegistrarTrazoConEnlaces,
)
from obractrl.application.casos_uso.dar_de_alta_extra import DarDeAltaExtra
from obractrl.application.casos_uso.exportar_estimacion import (
    ArmarReporteDeEstimacion,
)
from obractrl.application.casos_uso.generar_obra_desde_prototipo import (
    GenerarObraDesdePrototipo,
    RevertirGeneracionDeObra,
)
from obractrl.application.casos_uso.gestionar_carga import (
    ConsultarCarga,
    EjecutarCarga,
    EliminarCarga,
    ResolverPendiente,
    RevertirCarga,
    RevertirCargaEnCadena,
)
from obractrl.application.casos_uso.gestionar_catalogos import (
    CrearConcepto,
    CrearContratista,
    CrearCuadrilla,
    CrearFamilia,
    CrearInsumo,
    CrearUnidad,
    EliminarVersionDeCPU,
    EliminarVersionDeCuadrilla,
)
from obractrl.application.casos_uso.gestionar_cierre import (
    AutorizarCierre,
    RechazarCierre,
    SolicitarCierre,
    ValidarCierre,
)
from obractrl.application.casos_uso.gestionar_cierre_de_obra import (
    AbrirCierreDeObra,
    ConsultarCierreDeObra,
    Participar,
)
from obractrl.application.casos_uso.gestionar_control_cambio import (
    ResolverControlDeCambio,
    SolicitarControlDeCambio,
)
from obractrl.application.casos_uso.gestionar_estimacion import (
    EnviarEstimacion,
    GenerarEstimacion,
    ValidarEstimacion,
)
from obractrl.application.casos_uso.gestionar_evaluacion import (
    AgregarRespuestas,
    CrearEvaluacion,
)
from obractrl.application.casos_uso.gestionar_expediente import (
    AgregarDocumento,
    ArmarExpediente,
    ConsultarExpediente,
)
from obractrl.application.casos_uso.gestionar_incidencia import (
    AbrirIncidencia,
    CerrarIncidencia,
    ProgramarIncidencia,
    RechazarIncidencia,
    RegistrarEventoIncidencia,
)
from obractrl.application.casos_uso.gestionar_obra import (
    ActualizarObra,
    CrearObra,
    CrearObrasEnLote,
)
from obractrl.application.casos_uso.gestionar_organizacion import ReiniciarOrganizacion
from obractrl.application.casos_uso.gestionar_programacion import (
    ComandoRecalcularRutaCritica,
    ConsultarArbolPrograma,
    ConsultarRutaCritica,
    CrearProgramaBase,
    EditarProgramacionActividad,
    InstanciarProgramaObra,
    ProgramarNodoDelArbol,
    RecalcularRutaCritica,
    ReplicarProgramaEnObras,
)
from obractrl.application.casos_uso.gestionar_proyecto import (
    CrearCluster,
    CrearPrototipo,
    CrearProyecto,
)
from obractrl.application.casos_uso.gestionar_usuarios import (
    ActualizarUsuario,
    AsignarAlcance,
    CrearUsuario,
    ResetearContrasena,
)
from obractrl.application.casos_uso.notificar_estimacion import (
    NotificarEstimacionValidada,
)
from obractrl.application.casos_uso.registrar_revision_fisica import (
    RegistrarRevisionFisica,
)
from obractrl.application.casos_uso.registrar_salida_almacen import RegistrarSalidaAlmacen
from obractrl.application.eventos import (
    ActividadCerrada,
    BusEnProceso,
    EstimacionValidada,
    IncidenciaDetiene,
)
from obractrl.domain.shared.diccionario import TipoCarga, TipoConcepto, TipoInsumo
from obractrl.infrastructure.auth.supabase_admin import AdminDeSupabase
from obractrl.infrastructure.jobs.cola import ColaDeTrabajos
from obractrl.infrastructure.notificaciones.expo import ClienteExpoPush
from obractrl.infrastructure.notificaciones.resend import ClienteResend
from obractrl.infrastructure.tiempo_real.canal import canal_de_avisos

__all__ = [
    "AbrirCierreDeObraDep",
    "AbrirIncidenciaDep",
    "ActualizarObraDep",
    "ActualizarUsuarioDep",
    "AgregarDocumentoDep",
    "AgregarRespuestasDep",
    "ArmarExpedienteDep",
    "ArmarReporteDeEstimacionDep",
    "AsignarAlcanceDep",
    "AsignarFrenteDeObraDep",
    "AutorizarCierreDep",
    "CapturarAvanceDep",
    "CerrarIncidenciaDep",
    "ColaDeTrabajosDep",
    "ConsultarArbolProgramaDep",
    "ConsultarCargaDep",
    "ConsultarCierreDeObraDep",
    "ConsultarExpedienteDep",
    "ConsultarInsumosProgramadosDep",
    "ConsultarPlaneacionDep",
    "ConsultarRutaCriticaDep",
    "CrearClusterDep",
    "CrearConceptoDep",
    "CrearContratistaDep",
    "CrearCuadrillaDep",
    "CrearEvaluacionDep",
    "CrearFamiliaDep",
    "CrearInsumoDep",
    "CrearObraDep",
    "CrearObrasEnLoteDep",
    "CrearProgramaBaseDep",
    "CrearPrototipoDep",
    "CrearProyectoDep",
    "CrearUnidadDep",
    "CrearUsuarioDep",
    "DarDeAltaExtraDep",
    "EditarProgramacionActividadDep",
    "EliminarCargaDep",
    "EliminarVersionDeCPUDep",
    "EliminarVersionDeCuadrillaDep",
    "EnviarEstimacionDep",
    "ExplotarConceptoDep",
    "FabricaDeCargasDep",
    "GenerarEstimacionDep",
    "GenerarObraDesdePrototipoDep",
    "InstanciarProgramaObraDep",
    "ObtenerCPUDep",
    "ParticiparEnCierreDep",
    "ProgramarIncidenciaDep",
    "ProgramarNodoDelArbolDep",
    "PublicarVersionCPUDep",
    "RecalcularRutaCriticaDep",
    "RechazarCierreDep",
    "RechazarIncidenciaDep",
    "ReemplazarEnlaceDep",
    "RegistrarEventoIncidenciaDep",
    "RegistrarNotaPlanoDep",
    "RegistrarPlanoDep",
    "RegistrarRevisionFisicaDep",
    "RegistrarSalidaAlmacenDep",
    "RegistrarTrazoConEnlacesDep",
    "ReiniciarOrganizacionDep",
    "ReplicarProgramaEnObrasDep",
    "ResetearContrasenaDep",
    "ResolverPendienteDep",
    "RevertirCargaDep",
    "RevertirCargaEnCadenaDep",
    "RevertirGeneracionDeObraDep",
    "SolicitarCierreDep",
    "ValidarCierreDep",
    "ValidarEstimacionDep",
]


def obtener_capturar_avance(sesion: SesionRLS) -> CapturarAvance:
    return CapturarAvance(
        actividades=RepositorioActividadesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


CapturarAvanceDep = Annotated[CapturarAvance, Depends(obtener_capturar_avance)]


def obtener_solicitar_cierre(sesion: SesionRLS) -> SolicitarCierre:
    return SolicitarCierre(
        actividades=RepositorioActividadesSQL(sesion),
        cierres=RepositorioCierresSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_autorizar_cierre(sesion: SesionRLS) -> AutorizarCierre:
    return AutorizarCierre(
        cierres=RepositorioCierresSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_validar_cierre(sesion: SesionRLS, ctx: ContextoActual) -> ValidarCierre:
    """Validar un cierre publica `ActividadCerrada` (§11.3 C.4).

    El **borde** es quien decide que ese evento recalcula el CPM: el caso de
    uso de cierres no conoce el de programación, y viceversa (§11.1). Cambiar
    el transporte a Arq es sustituir el bus aquí, sin tocar ningún caso de uso.
    """
    return ValidarCierre(
        actividades=RepositorioActividadesSQL(sesion),
        cierres=RepositorioCierresSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_cierre(sesion, ctx),
    )


def _bus_de_cierre(sesion: SesionRLS, ctx: ContextoActual) -> BusEnProceso:
    """`ActividadCerrada` → recalcular la ruta crítica de su obra (§11.1) y
    anunciarlo en vivo (§11.2)."""
    recalcular = obtener_recalcular_ruta_critica(sesion)

    async def _recalcular_cpm(evento: ActividadCerrada) -> None:
        await recalcular.ejecutar(
            ComandoRecalcularRutaCritica(obra_id=evento.obra_id)
        )

    bus = BusEnProceso()
    bus.suscribir(ActividadCerrada, _recalcular_cpm)
    return suscribir_avisos(bus, ctx=ctx, canal=canal_de_avisos)


def obtener_rechazar_cierre(sesion: SesionRLS) -> RechazarCierre:
    return RechazarCierre(
        actividades=RepositorioActividadesSQL(sesion),
        cierres=RepositorioCierresSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


SolicitarCierreDep = Annotated[SolicitarCierre, Depends(obtener_solicitar_cierre)]
AutorizarCierreDep = Annotated[AutorizarCierre, Depends(obtener_autorizar_cierre)]
ValidarCierreDep = Annotated[ValidarCierre, Depends(obtener_validar_cierre)]
RechazarCierreDep = Annotated[RechazarCierre, Depends(obtener_rechazar_cierre)]


def obtener_generar_estimacion(sesion: SesionRLS) -> GenerarEstimacion:
    return GenerarEstimacion(
        estimaciones=RepositorioEstimacionesSQL(sesion),
        calendario=RepositorioCalendarioSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_enviar_estimacion(sesion: SesionRLS) -> EnviarEstimacion:
    return EnviarEstimacion(
        estimaciones=RepositorioEstimacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def _bus_de_estimacion(sesion: SesionRLS, ctx: ContextoActual) -> BusEnProceso:
    """`EstimacionValidada` → notificar por Resend (§11.1, §11.3 E.5).

    Mismo cableado que `_bus_de_cierre` y `_bus_de_incidencia`: el borde
    decide qué reacciona al evento; el caso de uso de estimación no conoce a
    Resend ni al de notificación (§11.1).

    El **bloqueo del periodo** —el otro efecto que el §11.1 nombra en la misma
    línea— no está aquí: lo escribe `ValidarEstimacion` dentro de su
    transacción, porque el bus descarta los fallos de sus manejadores y un
    candado que se pierde deja cobrar dos veces la misma semana (ver el
    docstring de `IncidenciaDetiene` en `application/eventos.py`).
    """
    notificar = NotificarEstimacionValidada(
        estimaciones=RepositorioEstimacionesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        usuarios=RepositorioUsuariosSQL(sesion),
        correo=ClienteResend(),
        # Los dos canales del §12.2. Ninguno depende del otro: sin Expo
        # configurado, `ClienteExpoPush` registra y devuelve 0, y el correo
        # sale igual.
        push=ClienteExpoPush(),
    )

    async def _notificar(evento: EstimacionValidada) -> None:
        await notificar.ejecutar(evento)

    bus = BusEnProceso()
    bus.suscribir(EstimacionValidada, _notificar)
    return suscribir_avisos(bus, ctx=ctx, canal=canal_de_avisos)


def obtener_validar_estimacion(
    sesion: SesionRLS, ctx: ContextoActual
) -> ValidarEstimacion:
    return ValidarEstimacion(
        estimaciones=RepositorioEstimacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_estimacion(sesion, ctx),
    )


def obtener_armar_reporte_estimacion(sesion: SesionRLS) -> ArmarReporteDeEstimacion:
    return ArmarReporteDeEstimacion(
        estimaciones=RepositorioEstimacionesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
    )


GenerarEstimacionDep = Annotated[GenerarEstimacion, Depends(obtener_generar_estimacion)]
EnviarEstimacionDep = Annotated[EnviarEstimacion, Depends(obtener_enviar_estimacion)]
ValidarEstimacionDep = Annotated[ValidarEstimacion, Depends(obtener_validar_estimacion)]
ArmarReporteDeEstimacionDep = Annotated[
    ArmarReporteDeEstimacion, Depends(obtener_armar_reporte_estimacion)
]


def obtener_registrar_salida_almacen(sesion: SesionRLS) -> RegistrarSalidaAlmacen:
    return RegistrarSalidaAlmacen(
        materiales=RepositorioMaterialesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


RegistrarSalidaAlmacenDep = Annotated[
    RegistrarSalidaAlmacen, Depends(obtener_registrar_salida_almacen)
]


def _bus_de_incidencia(sesion: SesionRLS, ctx: ContextoActual) -> BusEnProceso:
    """`IncidenciaDetiene` → recalcular la ruta crítica de su obra (§11.3 F.5).

    Mismo cableado que `_bus_de_cierre`, y por la misma razón: el flujo de
    incidencias no conoce el de programación ni al revés (§11.1). Bloquear o
    desbloquear la actividad ya lo hizo el caso de uso dentro de su
    transacción, por el puerto `RepositorioActividades`; lo que falta después
    del commit es replanear el cronograma contra ese bloqueo —el "recalcular
    CPM (desfase)" del §11.3 F.5—, y eso es idempotente, así que da igual que
    el disparador sea el alta, el cierre o el rechazo.
    """
    recalcular = obtener_recalcular_ruta_critica(sesion)

    async def _recalcular_cpm(evento: IncidenciaDetiene) -> None:
        await recalcular.ejecutar(ComandoRecalcularRutaCritica(obra_id=evento.obra_id))

    bus = BusEnProceso()
    bus.suscribir(IncidenciaDetiene, _recalcular_cpm)
    return suscribir_avisos(bus, ctx=ctx, canal=canal_de_avisos)


def obtener_abrir_incidencia(
    sesion: SesionRLS, ctx: ContextoActual
) -> AbrirIncidencia:
    return AbrirIncidencia(
        actividades=RepositorioActividadesSQL(sesion),
        incidencias=RepositorioIncidenciasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_incidencia(sesion, ctx),
    )


def obtener_programar_incidencia(sesion: SesionRLS) -> ProgramarIncidencia:
    return ProgramarIncidencia(
        incidencias=RepositorioIncidenciasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_registrar_evento_incidencia(sesion: SesionRLS) -> RegistrarEventoIncidencia:
    return RegistrarEventoIncidencia(
        incidencias=RepositorioIncidenciasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_cerrar_incidencia(
    sesion: SesionRLS, ctx: ContextoActual
) -> CerrarIncidencia:
    return CerrarIncidencia(
        actividades=RepositorioActividadesSQL(sesion),
        incidencias=RepositorioIncidenciasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_incidencia(sesion, ctx),
    )


def obtener_rechazar_incidencia(
    sesion: SesionRLS, ctx: ContextoActual
) -> RechazarIncidencia:
    return RechazarIncidencia(
        actividades=RepositorioActividadesSQL(sesion),
        incidencias=RepositorioIncidenciasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_incidencia(sesion, ctx),
    )


AbrirIncidenciaDep = Annotated[AbrirIncidencia, Depends(obtener_abrir_incidencia)]
ProgramarIncidenciaDep = Annotated[
    ProgramarIncidencia, Depends(obtener_programar_incidencia)
]
RegistrarEventoIncidenciaDep = Annotated[
    RegistrarEventoIncidencia, Depends(obtener_registrar_evento_incidencia)
]
CerrarIncidenciaDep = Annotated[CerrarIncidencia, Depends(obtener_cerrar_incidencia)]
RechazarIncidenciaDep = Annotated[
    RechazarIncidencia, Depends(obtener_rechazar_incidencia)
]


def obtener_crear_evaluacion(sesion: SesionRLS) -> CrearEvaluacion:
    return CrearEvaluacion(
        evaluaciones=RepositorioEvaluacionesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_agregar_respuestas(sesion: SesionRLS) -> AgregarRespuestas:
    return AgregarRespuestas(
        evaluaciones=RepositorioEvaluacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


CrearEvaluacionDep = Annotated[CrearEvaluacion, Depends(obtener_crear_evaluacion)]
AgregarRespuestasDep = Annotated[AgregarRespuestas, Depends(obtener_agregar_respuestas)]


def obtener_registrar_revision_fisica(sesion: SesionRLS) -> RegistrarRevisionFisica:
    return RegistrarRevisionFisica(
        revisiones=RepositorioRevisionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


RegistrarRevisionFisicaDep = Annotated[
    RegistrarRevisionFisica, Depends(obtener_registrar_revision_fisica)
]


# --- Expediente (§7.9, §11.2) --------------------------------------------


def obtener_agregar_documento(sesion: SesionRLS) -> AgregarDocumento:
    return AgregarDocumento(
        expediente=RepositorioExpedienteSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_consultar_expediente(sesion: SesionRLS) -> ConsultarExpediente:
    return ConsultarExpediente(expediente=RepositorioExpedienteSQL(sesion))


def obtener_armar_expediente(sesion: SesionRLS) -> ArmarExpediente:
    """La vista agregada cruza cuatro contextos y cada uno entra por **su**
    repositorio: aquí se ve que ninguno lee las tablas de otro (§11.1)."""
    return ArmarExpediente(
        expediente=RepositorioExpedienteSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        cierres=RepositorioCierresSQL(sesion),
        estimaciones=RepositorioEstimacionesSQL(sesion),
        revisiones=RepositorioRevisionesSQL(sesion),
        incidencias=RepositorioIncidenciasSQL(sesion),
    )


AgregarDocumentoDep = Annotated[AgregarDocumento, Depends(obtener_agregar_documento)]
ConsultarExpedienteDep = Annotated[
    ConsultarExpediente, Depends(obtener_consultar_expediente)
]
ArmarExpedienteDep = Annotated[ArmarExpediente, Depends(obtener_armar_expediente)]


# --- Cuantificador (cerebro MODELO.md §1b, migración 0057) --------------


def obtener_registrar_plano(sesion: SesionRLS) -> RegistrarPlano:
    return RegistrarPlano(
        planos=RepositorioPlanosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_registrar_trazo_con_enlaces(sesion: SesionRLS) -> RegistrarTrazoConEnlaces:
    return RegistrarTrazoConEnlaces(
        trazos=RepositorioTrazosSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_reemplazar_enlace(sesion: SesionRLS) -> ReemplazarEnlace:
    return ReemplazarEnlace(
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_registrar_nota_plano(sesion: SesionRLS) -> RegistrarNotaPlano:
    return RegistrarNotaPlano(
        notas=RepositorioNotasPlanoSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


RegistrarPlanoDep = Annotated[RegistrarPlano, Depends(obtener_registrar_plano)]
RegistrarTrazoConEnlacesDep = Annotated[
    RegistrarTrazoConEnlaces, Depends(obtener_registrar_trazo_con_enlaces)
]
ReemplazarEnlaceDep = Annotated[ReemplazarEnlace, Depends(obtener_reemplazar_enlace)]
RegistrarNotaPlanoDep = Annotated[
    RegistrarNotaPlano, Depends(obtener_registrar_nota_plano)
]


# --- Cola de trabajos (§12.2, §11.2 "job") -------------------------------


def obtener_cola_de_trabajos() -> ColaDeTrabajos:
    """No depende de la sesión: la cola es Redis, no Postgres. El contexto
    RLS viaja en el payload del trabajo (`adapters/export/trabajos.py`)."""
    return ColaDeTrabajos()


ColaDeTrabajosDep = Annotated[ColaDeTrabajos, Depends(obtener_cola_de_trabajos)]


# --- Proyecto · Obra (§11.2) --------------------------------------------


def obtener_crear_proyecto(sesion: SesionRLS) -> CrearProyecto:
    return CrearProyecto(
        proyectos=RepositorioProyectosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_cluster(sesion: SesionRLS) -> CrearCluster:
    return CrearCluster(
        clusters=RepositorioClustersSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_prototipo(sesion: SesionRLS) -> CrearPrototipo:
    return CrearPrototipo(
        prototipos=RepositorioPrototiposSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


CrearProyectoDep = Annotated[CrearProyecto, Depends(obtener_crear_proyecto)]
CrearClusterDep = Annotated[CrearCluster, Depends(obtener_crear_cluster)]
CrearPrototipoDep = Annotated[CrearPrototipo, Depends(obtener_crear_prototipo)]


def obtener_crear_obra(sesion: SesionRLS) -> CrearObra:
    return CrearObra(
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_obras_en_lote(sesion: SesionRLS) -> CrearObrasEnLote:
    return CrearObrasEnLote(
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_actualizar_obra(sesion: SesionRLS) -> ActualizarObra:
    return ActualizarObra(
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_generar_obra(sesion: SesionRLS) -> GenerarObraDesdePrototipo:
    return GenerarObraDesdePrototipo(
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_revertir_generacion(sesion: SesionRLS) -> RevertirGeneracionDeObra:
    return RevertirGeneracionDeObra(
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


RevertirGeneracionDeObraDep = Annotated[
    RevertirGeneracionDeObra, Depends(obtener_revertir_generacion)
]


# --- Catálogos · APU (§11.2) ---------------------------------------------


def obtener_crear_unidad(sesion: SesionRLS) -> CrearUnidad:
    return CrearUnidad(
        unidades=RepositorioUnidadesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_familia(sesion: SesionRLS) -> CrearFamilia:
    return CrearFamilia(
        familias=RepositorioFamiliasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_cuadrilla(sesion: SesionRLS) -> CrearCuadrilla:
    return CrearCuadrilla(
        cuadrillas=RepositorioCuadrillasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_eliminar_version_de_cuadrilla(sesion: SesionRLS) -> EliminarVersionDeCuadrilla:
    return EliminarVersionDeCuadrilla(
        cuadrillas=RepositorioCuadrillasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_eliminar_version_de_cpu(sesion: SesionRLS) -> EliminarVersionDeCPU:
    return EliminarVersionDeCPU(
        conceptos=RepositorioConceptosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_insumo(sesion: SesionRLS) -> CrearInsumo:
    """Sirve a `POST /insumos` y a `POST /materiales`: `Material` es un
    `Insumo` con `tipo='material'` (§7.3)."""
    return CrearInsumo(
        insumos=RepositorioInsumosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_concepto(sesion: SesionRLS) -> CrearConcepto:
    return CrearConcepto(
        conceptos=RepositorioConceptosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_contratista(sesion: SesionRLS) -> CrearContratista:
    return CrearContratista(
        contratistas=RepositorioContratistasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_explotar_concepto(sesion: SesionRLS) -> ExplotarConcepto:
    return ExplotarConcepto(conceptos=RepositorioConceptosSQL(sesion))


def obtener_cpu(sesion: SesionRLS) -> ObtenerCPU:
    return ObtenerCPU(conceptos=RepositorioConceptosSQL(sesion))


def obtener_publicar_version_cpu(sesion: SesionRLS) -> PublicarVersionCPU:
    return PublicarVersionCPU(
        conceptos=RepositorioConceptosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


CrearUnidadDep = Annotated[CrearUnidad, Depends(obtener_crear_unidad)]
CrearFamiliaDep = Annotated[CrearFamilia, Depends(obtener_crear_familia)]
CrearCuadrillaDep = Annotated[CrearCuadrilla, Depends(obtener_crear_cuadrilla)]
EliminarVersionDeCuadrillaDep = Annotated[
    EliminarVersionDeCuadrilla, Depends(obtener_eliminar_version_de_cuadrilla)
]
EliminarVersionDeCPUDep = Annotated[
    EliminarVersionDeCPU, Depends(obtener_eliminar_version_de_cpu)
]
CrearInsumoDep = Annotated[CrearInsumo, Depends(obtener_crear_insumo)]
CrearConceptoDep = Annotated[CrearConcepto, Depends(obtener_crear_concepto)]
CrearContratistaDep = Annotated[CrearContratista, Depends(obtener_crear_contratista)]
ExplotarConceptoDep = Annotated[ExplotarConcepto, Depends(obtener_explotar_concepto)]
ObtenerCPUDep = Annotated[ObtenerCPU, Depends(obtener_cpu)]
PublicarVersionCPUDep = Annotated[
    PublicarVersionCPU, Depends(obtener_publicar_version_cpu)
]


# --- Insumos programados (§11.2) -----------------------------------------


def obtener_consultar_insumos_programados(
    sesion: SesionRLS,
) -> ConsultarInsumosProgramados:
    return ConsultarInsumosProgramados(
        actividades=RepositorioActividadesSQL(sesion),
        conceptos=RepositorioConceptosSQL(sesion),
        insumos=RepositorioInsumosSQL(sesion),
        unidades=RepositorioUnidadesSQL(sesion),
        calendario=RepositorioCalendarioSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        presupuestos=RepositorioPresupuestosSQL(sesion),
        materiales=RepositorioMaterialesSQL(sesion),
        nodos=RepositorioPrototipoNodoSQL(sesion),
        # Las fechas del CPM no se persisten (`guardar_resultado_cpm`), así que
        # la ventana de cada actividad se pide fresca a la ruta crítica.
        ruta=obtener_consultar_ruta_critica(sesion),
    )


ConsultarInsumosProgramadosDep = Annotated[
    ConsultarInsumosProgramados, Depends(obtener_consultar_insumos_programados)
]


# --- Planeación por obra (§8.3, §11.3) ------------------------------------


def obtener_consultar_planeacion(sesion: SesionRLS) -> ConsultarPlaneacion:
    return ConsultarPlaneacion(
        insumos=obtener_consultar_insumos_programados(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        planeacion=RepositorioPlaneacionSQL(sesion),
        frentes=RepositorioFrentesSQL(sesion),
        # El segundo eje (0047): con qué oficio se parte un frente que solo,
        # entero, es demasiado grueso para contratar.
        especialidades=RepositorioEspecialidadesSQL(sesion),
    )


def obtener_solicitar_control_de_cambio(
    sesion: SesionRLS,
) -> SolicitarControlDeCambio:
    return SolicitarControlDeCambio(
        controles=RepositorioControlCambioSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_resolver_control_de_cambio(sesion: SesionRLS) -> ResolverControlDeCambio:
    return ResolverControlDeCambio(
        controles=RepositorioControlCambioSQL(sesion),
        # Autorizar puede crear actividades —un trabajo fuera de catálogo, o la
        # nueva de una sustitución—, así que necesita el repo que las da de alta.
        actividades=RepositorioActividadesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_asignar_frente_de_obra(sesion: SesionRLS) -> AsignarFrenteDeObra:
    return AsignarFrenteDeObra(
        planeacion=RepositorioPlaneacionSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


ConsultarPlaneacionDep = Annotated[
    ConsultarPlaneacion, Depends(obtener_consultar_planeacion)
]
SolicitarControlDeCambioDep = Annotated[
    SolicitarControlDeCambio, Depends(obtener_solicitar_control_de_cambio)
]
ResolverControlDeCambioDep = Annotated[
    ResolverControlDeCambio, Depends(obtener_resolver_control_de_cambio)
]
AsignarFrenteDeObraDep = Annotated[
    AsignarFrenteDeObra, Depends(obtener_asignar_frente_de_obra)
]


# --- Programación · CPM (§11.2) ------------------------------------------


def obtener_crear_programa_base(sesion: SesionRLS) -> CrearProgramaBase:
    return CrearProgramaBase(
        programas=RepositorioProgramasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_consultar_ruta_critica(sesion: SesionRLS) -> ConsultarRutaCritica:
    return ConsultarRutaCritica(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
    )


def obtener_recalcular_ruta_critica(sesion: SesionRLS) -> RecalcularRutaCritica:
    return RecalcularRutaCritica(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_instanciar_programa(sesion: SesionRLS) -> InstanciarProgramaObra:
    return InstanciarProgramaObra(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_replicar_programa(sesion: SesionRLS) -> ReplicarProgramaEnObras:
    """La replicación masiva se arma **sobre** la instanciación individual, no
    al lado: es la misma operación repetida, y montarla sobre el caso de uso ya
    probado es lo que garantiza que una obra del lote quede exactamente igual
    que si se hubiera instanciado a mano (§11.2)."""
    return ReplicarProgramaEnObras(
        instanciar=obtener_instanciar_programa(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
    )


def obtener_consultar_arbol_programa(sesion: SesionRLS) -> ConsultarArbolPrograma:
    """El Gantt jerárquico (§7.4). Mismos repos que la ruta crítica: las barras
    resumen se derivan de las mismas actividades, no de una tabla propia."""
    return ConsultarArbolPrograma(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
    )


def obtener_programar_nodo(sesion: SesionRLS) -> ProgramarNodoDelArbol:
    return ProgramarNodoDelArbol(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_editar_programacion(sesion: SesionRLS) -> EditarProgramacionActividad:
    return EditarProgramacionActividad(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


CrearProgramaBaseDep = Annotated[
    CrearProgramaBase, Depends(obtener_crear_programa_base)
]
ConsultarRutaCriticaDep = Annotated[
    ConsultarRutaCritica, Depends(obtener_consultar_ruta_critica)
]
RecalcularRutaCriticaDep = Annotated[
    RecalcularRutaCritica, Depends(obtener_recalcular_ruta_critica)
]
InstanciarProgramaObraDep = Annotated[
    InstanciarProgramaObra, Depends(obtener_instanciar_programa)
]
EditarProgramacionActividadDep = Annotated[
    EditarProgramacionActividad, Depends(obtener_editar_programacion)
]
ReplicarProgramaEnObrasDep = Annotated[
    ReplicarProgramaEnObras, Depends(obtener_replicar_programa)
]
ConsultarArbolProgramaDep = Annotated[
    ConsultarArbolPrograma, Depends(obtener_consultar_arbol_programa)
]
ProgramarNodoDelArbolDep = Annotated[
    ProgramarNodoDelArbol, Depends(obtener_programar_nodo)
]


CrearObraDep = Annotated[CrearObra, Depends(obtener_crear_obra)]
CrearObrasEnLoteDep = Annotated[CrearObrasEnLote, Depends(obtener_crear_obras_en_lote)]
ActualizarObraDep = Annotated[ActualizarObra, Depends(obtener_actualizar_obra)]
GenerarObraDesdePrototipoDep = Annotated[
    GenerarObraDesdePrototipo, Depends(obtener_generar_obra)
]


# --- Cargas (§11.2 "Cargas", §11.3 G) ------------------------------------


def obtener_consultar_carga(sesion: SesionRLS) -> ConsultarCarga:
    return ConsultarCarga(cargas=RepositorioCargasSQL(sesion))


def obtener_revertir_carga(sesion: SesionRLS) -> RevertirCarga:
    return RevertirCarga(
        cargas=RepositorioCargasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_revertir_carga_en_cadena(sesion: SesionRLS) -> RevertirCargaEnCadena:
    return RevertirCargaEnCadena(
        cargas=RepositorioCargasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_eliminar_carga(sesion: SesionRLS) -> EliminarCarga:
    return EliminarCarga(
        cargas=RepositorioCargasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_resolver_pendiente(sesion: SesionRLS) -> ResolverPendiente:
    return ResolverPendiente(
        cargas=RepositorioCargasSQL(sesion),
        conceptos=RepositorioConceptosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_reiniciar_organizacion(sesion: SesionRLS) -> ReiniciarOrganizacion:
    return ReiniciarOrganizacion(
        organizacion=RepositorioOrganizacionSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


ConsultarCargaDep = Annotated[ConsultarCarga, Depends(obtener_consultar_carga)]
RevertirCargaDep = Annotated[RevertirCarga, Depends(obtener_revertir_carga)]
RevertirCargaEnCadenaDep = Annotated[
    RevertirCargaEnCadena, Depends(obtener_revertir_carga_en_cadena)
]
EliminarCargaDep = Annotated[EliminarCarga, Depends(obtener_eliminar_carga)]
ResolverPendienteDep = Annotated[ResolverPendiente, Depends(obtener_resolver_pendiente)]
ReiniciarOrganizacionDep = Annotated[
    ReiniciarOrganizacion, Depends(obtener_reiniciar_organizacion)
]


class FabricaDeCargas:
    """Arma el caso de uso de carga que corresponde al tipo pedido.

    El tipo llega en el **cuerpo** de la petición (`POST /cargas`), no en la
    ruta, así que no puede resolverse como una dependencia normal de FastAPI:
    el router pide la fábrica y le pasa el tipo ya validado. Sigue siendo el
    borde el que ensambla —el caso de uso no conoce `adapters.repos` ni
    `adapters.excel` (§12.11)—, solo que en dos tiempos.
    """

    _IVA_TASA = "iva_tasa"
    _IVA_DEFAULT = Decimal("0.16")
    """Default canónico del §3.5. En runtime manda Configuración (§8.7): el
    valor del código es solo el fallback."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def para(self, tipo: TipoCarga) -> EjecutarCarga:
        return EjecutarCarga(
            cargas=RepositorioCargasSQL(self._sesion),
            lector=cargador_para(tipo),
            aplicador=await self._aplicador(tipo),
            uow=UnidadDeTrabajoSQL(self._sesion),
        )

    async def _aplicador(self, tipo: TipoCarga) -> AplicadorDeCarga:
        sesion = self._sesion
        cargas = RepositorioCargasSQL(sesion)

        if tipo is TipoCarga.MATERIALES:
            return AplicadorMateriales(
                insumos=RepositorioInsumosSQL(sesion),
                unidades=RepositorioUnidadesSQL(sesion),
                familias=RepositorioFamiliasSQL(sesion),
                cargas=cargas,
            )
        if tipo is TipoCarga.MANO_DE_OBRA:
            return AplicadorManoObra(
                insumos=RepositorioInsumosSQL(sesion),
                unidades=RepositorioUnidadesSQL(sesion),
                familias=RepositorioFamiliasSQL(sesion),
                cuadrillas=RepositorioCuadrillasSQL(sesion),
                cargas=cargas,
            )
        if tipo is TipoCarga.SUBCONTRATOS:
            return AplicadorManoObra(
                insumos=RepositorioInsumosSQL(sesion),
                unidades=RepositorioUnidadesSQL(sesion),
                familias=RepositorioFamiliasSQL(sesion),
                cuadrillas=RepositorioCuadrillasSQL(sesion),
                cargas=cargas,
                tipo=TipoInsumo.SUBCONTRATO,
            )
        if tipo is TipoCarga.TRABAJOS:
            return AplicadorTrabajos(
                insumos=RepositorioInsumosSQL(sesion),
                unidades=RepositorioUnidadesSQL(sesion),
                familias=RepositorioFamiliasSQL(sesion),
                cuadrillas=RepositorioCuadrillasSQL(sesion),
                cargas=cargas,
            )
        if tipo is TipoCarga.CUADRILLAS:
            return AplicadorCuadrillas(
                cuadrillas=RepositorioCuadrillasSQL(sesion),
                insumos=RepositorioInsumosSQL(sesion),
                unidades=RepositorioUnidadesSQL(sesion),
                cargas=cargas,
            )
        if tipo is TipoCarga.CATALOGO_CONCEPTOS:
            return AplicadorConceptosBase(
                conceptos=RepositorioConceptosSQL(sesion),
                unidades=RepositorioUnidadesSQL(sesion),
                cargas=cargas,
                # El oficio con el que se ejecuta el concepto (0047). Se pasa
                # solo aquí: un concepto auxiliar no se contrata por oficio.
                especialidades=RepositorioEspecialidadesSQL(sesion),
            )
        if tipo is TipoCarga.CONCEPTOS_AUXILIARES:
            return AplicadorConceptosBase(
                conceptos=RepositorioConceptosSQL(sesion),
                unidades=RepositorioUnidadesSQL(sesion),
                cargas=cargas,
                tipo=TipoConcepto.AUXILIAR,
                prefijo_clave="AUX",
            )
        if tipo is TipoCarga.NIVELES:
            return AplicadorNiveles(niveles_etapas=RepositorioNivelesEtapasSQL(sesion))
        if tipo is TipoCarga.ETAPAS_CONSTRUCTIVAS:
            return AplicadorEtapasConstructivas(
                niveles_etapas=RepositorioNivelesEtapasSQL(sesion),
                # El frente de cada etapa (0045). El catálogo se lee para
                # resolverlo por nombre y para crear el que no exista: el
                # archivo del cliente es la autoridad sobre su vocabulario.
                frentes=RepositorioFrentesSQL(sesion),
                cargas=cargas,
            )
        if tipo is TipoCarga.UNIDADES:
            return AplicadorUnidades(unidades=RepositorioUnidadesSQL(sesion), cargas=cargas)
        if tipo is TipoCarga.FAMILIAS:
            return AplicadorFamilias(familias=RepositorioFamiliasSQL(sesion), cargas=cargas)
        if tipo is TipoCarga.CONTRATISTAS:
            return AplicadorContratistas(
                contratistas=RepositorioContratistasSQL(sesion),
                # Los frentes se leen para resolver las claves del archivo a
                # ids: el cargador habla en claves porque es lo que una persona
                # escribe en un Excel.
                frentes=RepositorioFrentesSQL(sesion),
                cargas=cargas,
                # El otro eje: qué oficios sabe hacer (0047).
                especialidades=RepositorioEspecialidadesSQL(sesion),
            )
        if tipo is TipoCarga.CPU:
            return AplicadorCPU(
                conceptos=RepositorioConceptosSQL(sesion),
                insumos=RepositorioInsumosSQL(sesion),
                unidades=RepositorioUnidadesSQL(sesion),
                familias=RepositorioFamiliasSQL(sesion),
                cargas=cargas,
            )
        if tipo is TipoCarga.ALMACEN:
            tasa = await RepositorioConfiguracionSQL(sesion).decimal(
                self._IVA_TASA, self._IVA_DEFAULT
            )
            return AplicadorAlmacen(
                materiales=RepositorioMaterialesSQL(sesion),
                insumos=RepositorioInsumosSQL(sesion),
                obras=RepositorioObrasSQL(sesion),
                contratistas=RepositorioContratistasSQL(sesion),
                conceptos=RepositorioConceptosSQL(sesion),
                familias=RepositorioFamiliasSQL(sesion),
                cargas=cargas,
                tasa_iva=tasa,
            )
        if tipo in (TipoCarga.PROTOTIPOS, TipoCarga.PRESUPUESTO):
            # Un solo tipo de carga en la pantalla, dos formatos de archivo:
            # el alta plana y la ingeniería por prototipo. `CargadorPrototipos`
            # ya distinguió cuál llegó; `AplicadorDePrototipos` lo despacha.
            # `PRESUPUESTO` sigue aceptándose por si alguien lo pide por API,
            # pero el árbol y el plano funcionan igual en cualquiera de los dos.
            return AplicadorDePrototipos(
                plano=AplicadorPrototipos(
                    prototipos=RepositorioPrototiposSQL(sesion),
                    proyectos=RepositorioProyectosSQL(sesion),
                ),
                ingenieria=AplicadorPresupuesto(
                    conceptos=RepositorioConceptosSQL(sesion),
                    insumos=RepositorioInsumosSQL(sesion),
                    unidades=RepositorioUnidadesSQL(sesion),
                    prototipos=RepositorioPrototiposSQL(sesion),
                    prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
                    niveles_etapas=RepositorioNivelesEtapasSQL(sesion),
                    presupuestos=RepositorioPresupuestosSQL(sesion),
                    cargas=cargas,
                ),
            )
        if tipo is TipoCarga.INGENIERIA_LOTE:
            return AplicadorIngenieriaLote(
                obras=RepositorioObrasSQL(sesion),
                prototipos=RepositorioPrototiposSQL(sesion),
                prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
                conceptos=RepositorioConceptosSQL(sesion),
                desviaciones=RepositorioDesviacionesSQL(sesion),
                cargas=cargas,
            )
        # `cargador_para` ya rechazó los tipos sin cargador; llegar aquí
        # significa que se agregó uno y se olvidó su aplicador.
        raise TipoDeCargaSinCargador(
            f"El tipo {tipo!r} tiene cargador pero no aplicador (§10.6)."
        )


def obtener_fabrica_de_cargas(sesion: SesionRLS) -> FabricaDeCargas:
    return FabricaDeCargas(sesion)


FabricaDeCargasDep = Annotated[FabricaDeCargas, Depends(obtener_fabrica_de_cargas)]


# --- Identidad y equipo (§5.1) -------------------------------------------
#
# El proveedor de auth se construye aquí, igual que un repositorio: para el
# caso de uso es un puerto más. Se instancia por petición y no una vez al
# arranque porque no guarda estado —abre su cliente HTTP en cada llamada— y así
# un cambio de variables de entorno no exige redesplegar para tomar efecto.


def obtener_crear_usuario(sesion: SesionRLS) -> CrearUsuario:
    return CrearUsuario(
        usuarios=RepositorioUsuariosSQL(sesion),
        auth=AdminDeSupabase(),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_actualizar_usuario(sesion: SesionRLS) -> ActualizarUsuario:
    return ActualizarUsuario(
        usuarios=RepositorioUsuariosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_resetear_contrasena(sesion: SesionRLS) -> ResetearContrasena:
    return ResetearContrasena(
        usuarios=RepositorioUsuariosSQL(sesion),
        auth=AdminDeSupabase(),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_asignar_alcance(sesion: SesionRLS) -> AsignarAlcance:
    return AsignarAlcance(
        usuarios=RepositorioUsuariosSQL(sesion),
        asignaciones=RepositorioAsignacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


CrearUsuarioDep = Annotated[CrearUsuario, Depends(obtener_crear_usuario)]
ActualizarUsuarioDep = Annotated[
    ActualizarUsuario, Depends(obtener_actualizar_usuario)
]
ResetearContrasenaDep = Annotated[
    ResetearContrasena, Depends(obtener_resetear_contrasena)
]
AsignarAlcanceDep = Annotated[AsignarAlcance, Depends(obtener_asignar_alcance)]


def obtener_dar_de_alta_extra(sesion: SesionRLS) -> DarDeAltaExtra:
    return DarDeAltaExtra(
        actividades=RepositorioActividadesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


DarDeAltaExtraDep = Annotated[DarDeAltaExtra, Depends(obtener_dar_de_alta_extra)]


# --- Cierre de obra final (§11.3 D) --------------------------------------


def obtener_abrir_cierre_de_obra(sesion: SesionRLS) -> AbrirCierreDeObra:
    return AbrirCierreDeObra(
        cierres=RepositorioCierresDeObraSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_participar_en_cierre(sesion: SesionRLS, ctx: ContextoActual) -> Participar:
    return Participar(
        cierres=RepositorioCierresDeObraSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        # Ya no está vacío: desde la Fase 16, `CierreDeObraCompletado` se
        # anuncia en vivo (§11.2). Sigue sin tener manejadores de negocio —lo
        # que el cierre debía congelar lo escribe `Participar` dentro de su
        # unidad de trabajo—, y ese sigue siendo el motivo de que el bus se
        # inyecte siempre: suscribir el primero es agregar una línea aquí.
        eventos=suscribir_avisos(BusEnProceso(), ctx=ctx, canal=canal_de_avisos),
    )


def obtener_consultar_cierre_de_obra(sesion: SesionRLS) -> ConsultarCierreDeObra:
    return ConsultarCierreDeObra(cierres=RepositorioCierresDeObraSQL(sesion))


AbrirCierreDeObraDep = Annotated[
    AbrirCierreDeObra, Depends(obtener_abrir_cierre_de_obra)
]
ParticiparEnCierreDep = Annotated[Participar, Depends(obtener_participar_en_cierre)]
ConsultarCierreDeObraDep = Annotated[
    ConsultarCierreDeObra, Depends(obtener_consultar_cierre_de_obra)
]
