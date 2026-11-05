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
from obractrl.adapters.repos.arbol_de_obra_sql import RepositorioArbolDeObraSQL
from obractrl.adapters.repos.arbol_sql import RepositorioArbolSQL
from obractrl.adapters.repos.asignaciones_sql import RepositorioAsignacionesSQL
from obractrl.adapters.repos.calendario_sql import RepositorioCalendarioSQL
from obractrl.adapters.repos.cambio_de_unidad_sql import RepositorioCambioDeUnidadSQL
from obractrl.adapters.repos.cargas_sql import RepositorioCargasSQL
from obractrl.adapters.repos.cierres_frente_sql import RepositorioCierresDeFrenteSQL
from obractrl.adapters.repos.cierres_obra_sql import RepositorioCierresDeObraSQL
from obractrl.adapters.repos.cierres_sql import RepositorioCierresSQL
from obractrl.adapters.repos.clusters_sql import RepositorioClustersSQL
from obractrl.adapters.repos.comprobacion_sql import RepositorioComprobacionesSQL
from obractrl.adapters.repos.conceptos_sql import RepositorioConceptosSQL
from obractrl.adapters.repos.configuracion_sql import RepositorioConfiguracionSQL
from obractrl.adapters.repos.confirmaciones_sql import RepositorioConfirmacionesSQL
from obractrl.adapters.repos.contratistas_sql import RepositorioContratistasSQL
from obractrl.adapters.repos.control_cambio_sql import RepositorioControlCambioSQL
from obractrl.adapters.repos.cuadrillas_sql import RepositorioCuadrillasSQL
from obractrl.adapters.repos.cuantificacion_sql import (
    RepositorioElementosSQL,
    RepositorioEnlacesCuantificacionSQL,
    RepositorioEnlacesDeHojaSQL,
    RepositorioMatricesSQL,
    RepositorioMedicionesSQL,
    RepositorioNotasPlanoSQL,
    RepositorioPlanosSQL,
    RepositorioTrazosSQL,
)
from obractrl.adapters.repos.desviaciones_sql import RepositorioDesviacionesSQL
from obractrl.adapters.repos.ediciones_de_programa_sql import (
    RepositorioEdicionesDeProgramaSQL,
)
from obractrl.adapters.repos.elementos_parametricos_sql import (
    RepositorioElementosParametricosSQL,
)
from obractrl.adapters.repos.ensambles_sql import RepositorioEnsamblesSQL
from obractrl.adapters.repos.especialidades_sql import (
    RepositorioEspecialidadesSQL,
)
from obractrl.adapters.repos.estimaciones_sql import RepositorioEstimacionesSQL
from obractrl.adapters.repos.evaluaciones_sql import RepositorioEvaluacionesSQL
from obractrl.adapters.repos.expediente_sql import RepositorioExpedienteSQL
from obractrl.adapters.repos.familias_sql import RepositorioFamiliasSQL
from obractrl.adapters.repos.frentes_sql import RepositorioFrentesSQL
from obractrl.adapters.repos.generacion_ensamble_sql import (
    RepositorioGeneracionDePresupuestoSQL,
)
from obractrl.adapters.repos.incidencias_sql import RepositorioIncidenciasSQL
from obractrl.adapters.repos.ingenieria_lote_insumos_sql import (
    RepositorioIngenieriaLoteInsumosSQL,
)
from obractrl.adapters.repos.insumos_sql import RepositorioInsumosSQL
from obractrl.adapters.repos.mano_de_obra_opus_sql import RepositorioManoDeObraOpusSQL
from obractrl.adapters.repos.materiales_sql import RepositorioMaterialesSQL
from obractrl.adapters.repos.niveles_etapas_sql import RepositorioNivelesEtapasSQL
from obractrl.adapters.repos.obras_sql import RepositorioObrasSQL
from obractrl.adapters.repos.organizacion_sql import RepositorioOrganizacionSQL
from obractrl.adapters.repos.partes_sql import RepositorioPartesSQL
from obractrl.adapters.repos.planeacion_sql import RepositorioPlaneacionSQL
from obractrl.adapters.repos.presupuestos_sql import RepositorioPresupuestosSQL
from obractrl.adapters.repos.programas_sql import RepositorioProgramasSQL
from obractrl.adapters.repos.prototipo_nodo_sql import RepositorioPrototipoNodoSQL
from obractrl.adapters.repos.prototipos_sql import RepositorioPrototiposSQL
from obractrl.adapters.repos.proyectos_sql import RepositorioProyectosSQL
from obractrl.adapters.repos.reprogramaciones_sql import RepositorioReprogramacionesSQL
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
    AplicadorProgramaBase,
    AplicadorPrototipos,
    AplicadorTrabajos,
    AplicadorUnidades,
)
from obractrl.application.casos_uso.aplicar_catalogo_mano_de_obra import (
    AplicadorCatalogoManoDeObra,
    AplicadorSemillaCuadrillas,
)
from obractrl.application.casos_uso.arbol import ArmarArbol
from obractrl.application.casos_uso.arbol_de_obra import ArbolDeObra
from obractrl.application.casos_uso.calcular_cpu import (
    ExplotarConcepto,
    ObtenerCPU,
    PublicarVersionCPU,
)
from obractrl.application.casos_uso.cambio_de_unidad import CambioDeUnidad
from obractrl.application.casos_uso.capturar_avance import CapturarAvance
from obractrl.application.casos_uso.comprobar_excedente import (
    ConsultarComprobaciones,
    DeclararPerdidaDeExcedente,
    ValidarExcedente,
)
from obractrl.application.casos_uso.conceptos_en_obra import CrearConceptoEnObra
from obractrl.application.casos_uso.confirmar_avance import (
    ConfirmarAvance,
    ConsultarConfirmaciones,
)
from obractrl.application.casos_uso.consultar_insumos_programados import (
    ConsultarInsumosProgramados,
)
from obractrl.application.casos_uso.consultar_planeacion import (
    AsignarFrenteDeObra,
    ConsultarPlaneacion,
)
from obractrl.application.casos_uso.cotizacion_al_cliente import (
    ConsultarCotizaciones,
    CotizarLoModificado,
    ResponderCotizacion,
)
from obractrl.application.casos_uso.crear_obra_desde_catalogo_base import (
    ConsultarCatalogosBase,
    CrearObraDesdeCatalogoBase,
    CrearObraDesdeCero,
)
from obractrl.application.casos_uso.cuantificar import (
    AgregarHuecoATrazo,
    AprobarTrazo,
    CalibrarEscalaDePlano,
    ConsultarCuantificacion,
    ConsultarMatrices,
    ConversionDelEnlace,
    EliminarTrazo,
    FijarVistaDePlano,
    GestionarVanos,
    MatrizQueCuenta,
    QuitarHueco,
    ReemplazarEnlace,
    RegistrarNotaPlano,
    RegistrarPlano,
    RegistrarTrazoConEnlaces,
    TraerTrazoAOtraVersion,
    TransformarTrazos,
)
from obractrl.application.casos_uso.dar_de_alta_extra import DarDeAltaExtra
from obractrl.application.casos_uso.elementos import GestionarElementos
from obractrl.application.casos_uso.elementos_parametricos import (
    GestionarElementosParametricos,
)
from obractrl.application.casos_uso.enlaces_de_hoja import GestionarEnlacesDeHoja
from obractrl.application.casos_uso.exportar_estimacion import (
    ArmarReporteDeEstimacion,
)
from obractrl.application.casos_uso.generar_obra_desde_prototipo import (
    GenerarObraDesdePrototipo,
    RevertirGeneracionDeObra,
)
from obractrl.application.casos_uso.gestionar_carga import (
    AprobarPendientesEnLote,
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
from obractrl.application.casos_uso.gestionar_cierre_de_frente import (
    AprobarCierreDeFrente,
    ConsultarFrentesDeObra,
    RechazarCierreDeFrente,
    SolicitarCierreDeFrente,
    ValidarCierreDeFrente,
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
from obractrl.application.casos_uso.gestionar_desviaciones import (
    CapturarCausaDeDesviacion,
    ConsultarDesviaciones,
)
from obractrl.application.casos_uso.gestionar_ensamble import (
    ExplotarEnsamble,
    ExtraerEnsamble,
    GenerarDesdeEnsamble,
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
from obractrl.application.casos_uso.gestionar_partes import (
    AgregarActividadNueva,
    CambiarEstadoDePartes,
    ConsultarAlertasDePartes,
    ConsultarArranque,
    ConsultarBitacoraDePartes,
    ConsultarCargaDePartes,
    ConsultarDesfaseDePartes,
    ConsultarModificaciones,
    ConsultarPartes,
    FijarCandadoDeAsignar,
    FijarDesfaseDePartes,
    FijarPlantasDeObra,
    FijarPlantasDePrototipo,
    MarcarParteIndependiente,
    ModificarActividad,
)
from obractrl.application.casos_uso.gestionar_programacion import (
    ComandoRecalcularRutaCritica,
    ConsultarArbolPrograma,
    ConsultarEdicionesDePrograma,
    ConsultarRutaCritica,
    CrearProgramaBase,
    EditarProgramacionActividad,
    IniciarObra,
    InstanciarProgramaObra,
    ProgramarNodoDelArbol,
    RecalcularRutaCritica,
    ReplicarProgramaEnObras,
)
from obractrl.application.casos_uso.gestionar_proyecto import (
    CrearCluster,
    CrearPrototipo,
    CrearProyecto,
    EditarNivelesYRecamaras,
)
from obractrl.application.casos_uso.gestionar_reprogramacion import (
    AplicarReprogramacion,
    ConsultarReprogramaciones,
    ObservarReprogramacion,
    ProponerReprogramacion,
    RechazarReprogramacion,
    RevisarReprogramacion,
    ValidarReprogramacion,
)
from obractrl.application.casos_uso.gestionar_usuarios import (
    ActualizarUsuario,
    AsignarAlcance,
    CrearUsuario,
    ResetearContrasena,
)
from obractrl.application.casos_uso.matrices_de_concepto import (
    GestionarMatricesDeConcepto,
)
from obractrl.application.casos_uso.mediciones import GestionarMediciones
from obractrl.application.casos_uso.notificar_estimacion import (
    NotificarEstimacionValidada,
)
from obractrl.application.casos_uso.notificar_partes import NotificarPartes
from obractrl.application.casos_uso.notificar_reprogramacion import (
    NotificarReprogramacion,
)
from obractrl.application.casos_uso.preparar_obra_nueva import PrepararObraNueva
from obractrl.application.casos_uso.propuestas import (
    AceptarPropuestas,
    ProponerTrazos,
    RechazarPropuestas,
)
from obractrl.application.casos_uso.registrar_revision_fisica import (
    RegistrarRevisionFisica,
)
from obractrl.application.casos_uso.registrar_salida_almacen import RegistrarSalidaAlmacen
from obractrl.application.casos_uso.valuacion_de_partes import (
    ConsultarValuacion,
    RedisenarParte,
)
from obractrl.application.eventos import (
    ActividadCerrada,
    BusEnProceso,
    EstimacionValidada,
    IncidenciaDetiene,
    PartesCambiaronDeEstado,
    ReprogramacionAplicada,
    ReprogramacionObservada,
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
    "AceptarPropuestasDep",
    "ActualizarObraDep",
    "ActualizarUsuarioDep",
    "AgregarActividadNuevaDep",
    "AgregarDocumentoDep",
    "AgregarHuecoDep",
    "AgregarRespuestasDep",
    "AplicarReprogramacionDep",
    "AprobarCierreDeFrenteDep",
    "AprobarPendientesEnLoteDep",
    "AprobarTrazoDep",
    "ArbolDeObraDep",
    "ArmarArbolDep",
    "ArmarExpedienteDep",
    "ArmarReporteDeEstimacionDep",
    "AsignarAlcanceDep",
    "AsignarFrenteDeObraDep",
    "AutorizarCierreDep",
    "CalibrarEscalaDePlanoDep",
    "CambiarEstadoDePartesDep",
    "CambioDeUnidadDep",
    "CapturarAvanceDep",
    "CapturarCausaDeDesviacionDep",
    "CerrarIncidenciaDep",
    "ColaDeTrabajosDep",
    "ConfirmarAvanceDep",
    "ConsultarAlertasDePartesDep",
    "ConsultarArbolProgramaDep",
    "ConsultarArranqueDep",
    "ConsultarBitacoraDePartesDep",
    "ConsultarCargaDePartesDep",
    "ConsultarCargaDep",
    "ConsultarCatalogosBaseDep",
    "ConsultarCierreDeObraDep",
    "ConsultarComprobacionesDep",
    "ConsultarConfirmacionesDep",
    "ConsultarCotizacionesDep",
    "ConsultarCuantificacionDep",
    "ConsultarDesfaseDePartesDep",
    "ConsultarDesviacionesDep",
    "ConsultarEdicionesDeProgramaDep",
    "ConsultarExpedienteDep",
    "ConsultarFrentesDeObraDep",
    "ConsultarInsumosProgramadosDep",
    "ConsultarMatricesDep",
    "ConsultarModificacionesDep",
    "ConsultarPartesDep",
    "ConsultarPlaneacionDep",
    "ConsultarReprogramacionesDep",
    "ConsultarRutaCriticaDep",
    "ConsultarValuacionDep",
    "ConversionDelEnlaceDep",
    "CotizarLoModificadoDep",
    "CrearClusterDep",
    "CrearConceptoDep",
    "CrearConceptoEnObraDep",
    "CrearContratistaDep",
    "CrearCuadrillaDep",
    "CrearEvaluacionDep",
    "CrearFamiliaDep",
    "CrearInsumoDep",
    "CrearObraDep",
    "CrearObraDesdeCatalogoBaseDep",
    "CrearObraDesdeCeroDep",
    "CrearObrasEnLoteDep",
    "CrearProgramaBaseDep",
    "CrearPrototipoDep",
    "CrearProyectoDep",
    "CrearUnidadDep",
    "CrearUsuarioDep",
    "DarDeAltaExtraDep",
    "DeclararPerdidaDeExcedenteDep",
    "EditarNivelesYRecamarasDep",
    "EditarProgramacionActividadDep",
    "EliminarCargaDep",
    "EliminarTrazoDep",
    "EliminarVersionDeCPUDep",
    "EliminarVersionDeCuadrillaDep",
    "EnviarEstimacionDep",
    "ExplotarConceptoDep",
    "ExplotarEnsambleDep",
    "ExtraerEnsambleDep",
    "FabricaDeCargasDep",
    "FijarCandadoDeAsignarDep",
    "FijarDesfaseDePartesDep",
    "FijarPlantasDeObraDep",
    "FijarPlantasDePrototipoDep",
    "FijarVistaDePlanoDep",
    "GenerarDesdeEnsambleDep",
    "GenerarEstimacionDep",
    "GenerarObraDesdePrototipoDep",
    "GestionarElementosDep",
    "GestionarElementosParametricosDep",
    "GestionarEnlacesDeHojaDep",
    "GestionarMatricesDeConceptoDep",
    "GestionarMedicionesDep",
    "GestionarVanosDep",
    "IniciarObraDep",
    "InstanciarProgramaObraDep",
    "MarcarParteIndependienteDep",
    "MatrizQueCuentaDep",
    "ModificarActividadDep",
    "ObservarReprogramacionDep",
    "ObtenerCPUDep",
    "ParticiparEnCierreDep",
    "PrepararObraNuevaDep",
    "ProgramarIncidenciaDep",
    "ProgramarNodoDelArbolDep",
    "ProponerReprogramacionDep",
    "ProponerTrazosDep",
    "PublicarVersionCPUDep",
    "QuitarHuecoDep",
    "RecalcularRutaCriticaDep",
    "RechazarCierreDeFrenteDep",
    "RechazarCierreDep",
    "RechazarIncidenciaDep",
    "RechazarPropuestasDep",
    "RechazarReprogramacionDep",
    "RedisenarParteDep",
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
    "ResponderCotizacionDep",
    "RevertirCargaDep",
    "RevertirCargaEnCadenaDep",
    "RevertirGeneracionDeObraDep",
    "RevisarReprogramacionDep",
    "SolicitarCierreDeFrenteDep",
    "SolicitarCierreDep",
    "TraerTrazoDep",
    "TransformarTrazosDep",
    "ValidarCierreDeFrenteDep",
    "ValidarCierreDep",
    "ValidarEstimacionDep",
    "ValidarExcedenteDep",
    "ValidarReprogramacionDep",
]


def obtener_capturar_avance(sesion: SesionRLS) -> CapturarAvance:
    return CapturarAvance(
        actividades=RepositorioActividadesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        cierres_de_frente=RepositorioCierresDeFrenteSQL(sesion),
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


def obtener_consultar_cuantificacion(sesion: SesionRLS) -> ConsultarCuantificacion:
    return ConsultarCuantificacion(
        planos=RepositorioPlanosSQL(sesion),
        trazos=RepositorioTrazosSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        notas=RepositorioNotasPlanoSQL(sesion),
    )


def obtener_consultar_matrices(sesion: SesionRLS) -> ConsultarMatrices:
    return ConsultarMatrices(matrices=RepositorioMatricesSQL(sesion))


def obtener_registrar_plano(sesion: SesionRLS) -> RegistrarPlano:
    return RegistrarPlano(
        planos=RepositorioPlanosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_registrar_trazo_con_enlaces(sesion: SesionRLS, ctx: ContextoActual) -> RegistrarTrazoConEnlaces:
    return RegistrarTrazoConEnlaces(
        mediciones=RepositorioMedicionesSQL(sesion),
        trazos=RepositorioTrazosSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
        matrices=RepositorioMatricesSQL(sesion),
    )


def obtener_agregar_hueco(sesion: SesionRLS, ctx: ContextoActual) -> AgregarHuecoATrazo:
    return AgregarHuecoATrazo(
        trazos=RepositorioTrazosSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
        matrices=RepositorioMatricesSQL(sesion),
    )


def obtener_gestionar_vanos(sesion: SesionRLS, ctx: ContextoActual) -> GestionarVanos:
    return GestionarVanos(
        trazos=RepositorioTrazosSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
        matrices=RepositorioMatricesSQL(sesion),
    )


def obtener_matriz_que_cuenta(sesion: SesionRLS, ctx: ContextoActual) -> MatrizQueCuenta:
    return MatrizQueCuenta(
        trazos=RepositorioTrazosSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
        matrices=RepositorioMatricesSQL(sesion),
    )


def obtener_eliminar_trazo(sesion: SesionRLS, ctx: ContextoActual) -> EliminarTrazo:
    return EliminarTrazo(
        trazos=RepositorioTrazosSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
        matrices=RepositorioMatricesSQL(sesion),
    )


def obtener_transformar_trazos(sesion: SesionRLS) -> TransformarTrazos:
    return TransformarTrazos(
        trazos=RepositorioTrazosSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_quitar_hueco(sesion: SesionRLS, ctx: ContextoActual) -> QuitarHueco:
    return QuitarHueco(
        trazos=RepositorioTrazosSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
        matrices=RepositorioMatricesSQL(sesion),
    )


def obtener_calibrar_escala(sesion: SesionRLS, ctx: ContextoActual) -> CalibrarEscalaDePlano:
    return CalibrarEscalaDePlano(
        planos=RepositorioPlanosSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
        matrices=RepositorioMatricesSQL(sesion),
    )


def obtener_gestionar_elementos_parametricos(sesion: SesionRLS) -> GestionarElementosParametricos:
    return GestionarElementosParametricos(
        elementos=RepositorioElementosParametricosSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
    )


def obtener_gestionar_elementos(sesion: SesionRLS, ctx: ContextoActual) -> GestionarElementos:
    return GestionarElementos(
        elementos=RepositorioElementosSQL(sesion),
        mediciones=RepositorioMedicionesSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
        matrices=RepositorioMatricesSQL(sesion),
    )


def obtener_gestionar_mediciones(sesion: SesionRLS, ctx: ContextoActual) -> GestionarMediciones:
    return GestionarMediciones(
        elementos=RepositorioElementosSQL(sesion),
        mediciones=RepositorioMedicionesSQL(sesion),
        planos=RepositorioPlanosSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
        matrices=RepositorioMatricesSQL(sesion),
    )


def obtener_fijar_vista(sesion: SesionRLS) -> FijarVistaDePlano:
    return FijarVistaDePlano(planos=RepositorioPlanosSQL(sesion), uow=UnidadDeTrabajoSQL(sesion))


def obtener_reemplazar_enlace(sesion: SesionRLS, ctx: ContextoActual) -> ReemplazarEnlace:
    return ReemplazarEnlace(
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
        matrices=RepositorioMatricesSQL(sesion),
    )


def obtener_conversion_del_enlace(sesion: SesionRLS, ctx: ContextoActual) -> ConversionDelEnlace:
    return ConversionDelEnlace(
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion), reemplazar=obtener_reemplazar_enlace(sesion, ctx)
    )


def obtener_traer_trazo(sesion: SesionRLS, ctx: ContextoActual) -> TraerTrazoAOtraVersion:
    return TraerTrazoAOtraVersion(
        trazos=RepositorioTrazosSQL(sesion),
        planos=RepositorioPlanosSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
        matrices=RepositorioMatricesSQL(sesion),
    )


def obtener_gestionar_enlaces_de_hoja(sesion: SesionRLS) -> GestionarEnlacesDeHoja:
    return GestionarEnlacesDeHoja(
        planos=RepositorioPlanosSQL(sesion),
        enlaces=RepositorioEnlacesDeHojaSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_proponer_trazos(sesion: SesionRLS) -> ProponerTrazos:
    return ProponerTrazos(
        trazos=RepositorioTrazosSQL(sesion),
        planos=RepositorioPlanosSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_aceptar_propuestas(sesion: SesionRLS, ctx: ContextoActual) -> AceptarPropuestas:
    return AceptarPropuestas(
        trazos=RepositorioTrazosSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
        matrices=RepositorioMatricesSQL(sesion),
    )


def obtener_rechazar_propuestas(sesion: SesionRLS) -> RechazarPropuestas:
    return RechazarPropuestas(trazos=RepositorioTrazosSQL(sesion), uow=UnidadDeTrabajoSQL(sesion))


def obtener_arbol_de_obra(sesion: SesionRLS) -> ArbolDeObra:
    return ArbolDeObra(arbol=RepositorioArbolDeObraSQL(sesion), partes=RepositorioPartesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion))


def obtener_preparar_obra_nueva(sesion: SesionRLS) -> PrepararObraNueva:
    return PrepararObraNueva(arbol=obtener_arbol_de_obra(sesion), generar=obtener_generar_obra(sesion))


def obtener_cambio_de_unidad(sesion: SesionRLS) -> CambioDeUnidad:
    return CambioDeUnidad(
        arbol=RepositorioArbolSQL(sesion),
        cambios=RepositorioCambioDeUnidadSQL(sesion),
        partes=RepositorioPartesSQL(sesion),
        enlaces=RepositorioEnlacesCuantificacionSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        desviaciones=RepositorioDesviacionesSQL(sesion),
        matrices=RepositorioMatricesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_armar_arbol(sesion: SesionRLS) -> ArmarArbol:
    return ArmarArbol(
        arbol=RepositorioArbolSQL(sesion),
        partes=RepositorioPartesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_confirmar_avance(sesion: SesionRLS) -> ConfirmarAvance:
    return ConfirmarAvance(
        actividades=RepositorioActividadesSQL(sesion),
        confirmaciones=RepositorioConfirmacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_consultar_confirmaciones(sesion: SesionRLS) -> ConsultarConfirmaciones:
    return ConsultarConfirmaciones(
        confirmaciones=RepositorioConfirmacionesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
    )


def obtener_consultar_frentes_de_obra(sesion: SesionRLS) -> ConsultarFrentesDeObra:
    return ConsultarFrentesDeObra(
        cierres=RepositorioCierresDeFrenteSQL(sesion), obras=RepositorioObrasSQL(sesion)
    )


def obtener_solicitar_cierre_de_frente(sesion: SesionRLS) -> SolicitarCierreDeFrente:
    return SolicitarCierreDeFrente(
        cierres=RepositorioCierresDeFrenteSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
    )


def obtener_aprobar_cierre_de_frente(sesion: SesionRLS) -> AprobarCierreDeFrente:
    return AprobarCierreDeFrente(
        cierres=RepositorioCierresDeFrenteSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
    )


def obtener_validar_cierre_de_frente(sesion: SesionRLS) -> ValidarCierreDeFrente:
    return ValidarCierreDeFrente(
        cierres=RepositorioCierresDeFrenteSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
    )


def obtener_rechazar_cierre_de_frente(sesion: SesionRLS) -> RechazarCierreDeFrente:
    return RechazarCierreDeFrente(
        cierres=RepositorioCierresDeFrenteSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
    )


def obtener_consultar_desviaciones(sesion: SesionRLS) -> ConsultarDesviaciones:
    return ConsultarDesviaciones(
        desviaciones=RepositorioDesviacionesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
    )


def obtener_capturar_causa(sesion: SesionRLS) -> CapturarCausaDeDesviacion:
    return CapturarCausaDeDesviacion(
        desviaciones=RepositorioDesviacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_consultar_comprobaciones(sesion: SesionRLS) -> ConsultarComprobaciones:
    return ConsultarComprobaciones(comprobaciones=RepositorioComprobacionesSQL(sesion))


def obtener_validar_excedente(sesion: SesionRLS) -> ValidarExcedente:
    return ValidarExcedente(
        comprobaciones=RepositorioComprobacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_declarar_perdida_de_excedente(sesion: SesionRLS) -> DeclararPerdidaDeExcedente:
    return DeclararPerdidaDeExcedente(
        comprobaciones=RepositorioComprobacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_aprobar_trazo(sesion: SesionRLS) -> AprobarTrazo:
    return AprobarTrazo(
        trazos=RepositorioTrazosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_registrar_nota_plano(sesion: SesionRLS) -> RegistrarNotaPlano:
    return RegistrarNotaPlano(
        notas=RepositorioNotasPlanoSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


ConsultarComprobacionesDep = Annotated[
    ConsultarComprobaciones, Depends(obtener_consultar_comprobaciones)
]
ValidarExcedenteDep = Annotated[ValidarExcedente, Depends(obtener_validar_excedente)]
DeclararPerdidaDeExcedenteDep = Annotated[
    DeclararPerdidaDeExcedente, Depends(obtener_declarar_perdida_de_excedente)
]
AprobarTrazoDep = Annotated[AprobarTrazo, Depends(obtener_aprobar_trazo)]
AgregarHuecoDep = Annotated[AgregarHuecoATrazo, Depends(obtener_agregar_hueco)]
EliminarTrazoDep = Annotated[EliminarTrazo, Depends(obtener_eliminar_trazo)]
TransformarTrazosDep = Annotated[TransformarTrazos, Depends(obtener_transformar_trazos)]
QuitarHuecoDep = Annotated[QuitarHueco, Depends(obtener_quitar_hueco)]
ConsultarMatricesDep = Annotated[ConsultarMatrices, Depends(obtener_consultar_matrices)]
ConsultarCuantificacionDep = Annotated[
    ConsultarCuantificacion, Depends(obtener_consultar_cuantificacion)
]
RegistrarPlanoDep = Annotated[RegistrarPlano, Depends(obtener_registrar_plano)]
RegistrarTrazoConEnlacesDep = Annotated[
    RegistrarTrazoConEnlaces, Depends(obtener_registrar_trazo_con_enlaces)
]
ReemplazarEnlaceDep = Annotated[ReemplazarEnlace, Depends(obtener_reemplazar_enlace)]
ConversionDelEnlaceDep = Annotated[ConversionDelEnlace, Depends(obtener_conversion_del_enlace)]
GestionarEnlacesDeHojaDep = Annotated[GestionarEnlacesDeHoja, Depends(obtener_gestionar_enlaces_de_hoja)]
ProponerTrazosDep = Annotated[ProponerTrazos, Depends(obtener_proponer_trazos)]
AceptarPropuestasDep = Annotated[AceptarPropuestas, Depends(obtener_aceptar_propuestas)]
RechazarPropuestasDep = Annotated[RechazarPropuestas, Depends(obtener_rechazar_propuestas)]
GestionarElementosParametricosDep = Annotated[
    GestionarElementosParametricos, Depends(obtener_gestionar_elementos_parametricos)
]
GestionarVanosDep = Annotated[GestionarVanos, Depends(obtener_gestionar_vanos)]
MatrizQueCuentaDep = Annotated[MatrizQueCuenta, Depends(obtener_matriz_que_cuenta)]
PrepararObraNuevaDep = Annotated[PrepararObraNueva, Depends(obtener_preparar_obra_nueva)]
ArbolDeObraDep = Annotated[ArbolDeObra, Depends(obtener_arbol_de_obra)]
CambioDeUnidadDep = Annotated[CambioDeUnidad, Depends(obtener_cambio_de_unidad)]
ArmarArbolDep = Annotated[ArmarArbol, Depends(obtener_armar_arbol)]
TraerTrazoDep = Annotated[TraerTrazoAOtraVersion, Depends(obtener_traer_trazo)]
CalibrarEscalaDePlanoDep = Annotated[
    CalibrarEscalaDePlano, Depends(obtener_calibrar_escala)
]
GestionarElementosDep = Annotated[GestionarElementos, Depends(obtener_gestionar_elementos)]
GestionarMedicionesDep = Annotated[GestionarMediciones, Depends(obtener_gestionar_mediciones)]
FijarVistaDePlanoDep = Annotated[FijarVistaDePlano, Depends(obtener_fijar_vista)]
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


def obtener_editar_niveles_y_recamaras(sesion: SesionRLS) -> EditarNivelesYRecamaras:
    return EditarNivelesYRecamaras(
        prototipos=RepositorioPrototiposSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


EditarNivelesYRecamarasDep = Annotated[
    EditarNivelesYRecamaras, Depends(obtener_editar_niveles_y_recamaras)
]
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


# --- Ensambles paramétricos (skill erp-parametrico, §11.2) ----------------


def obtener_explotar_ensamble(sesion: SesionRLS) -> ExplotarEnsamble:
    return ExplotarEnsamble(
        ensambles=RepositorioEnsamblesSQL(sesion),
        conceptos=RepositorioConceptosSQL(sesion),
    )


def obtener_extraer_ensamble(sesion: SesionRLS) -> ExtraerEnsamble:
    return ExtraerEnsamble(
        ensambles=RepositorioEnsamblesSQL(sesion),
        conceptos=RepositorioConceptosSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_generar_desde_ensamble(sesion: SesionRLS) -> GenerarDesdeEnsamble:
    return GenerarDesdeEnsamble(
        ensambles=RepositorioEnsamblesSQL(sesion),
        conceptos=RepositorioConceptosSQL(sesion),
        generacion=RepositorioGeneracionDePresupuestoSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


ExplotarEnsambleDep = Annotated[ExplotarEnsamble, Depends(obtener_explotar_ensamble)]
ExtraerEnsambleDep = Annotated[ExtraerEnsamble, Depends(obtener_extraer_ensamble)]
GenerarDesdeEnsambleDep = Annotated[
    GenerarDesdeEnsamble, Depends(obtener_generar_desde_ensamble)
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
        ediciones=RepositorioEdicionesDeProgramaSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_iniciar_obra(sesion: SesionRLS) -> IniciarObra:
    return IniciarObra(
        actividades=RepositorioActividadesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        programas=RepositorioProgramasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_consultar_ediciones_de_programa(
    sesion: SesionRLS,
) -> ConsultarEdicionesDePrograma:
    return ConsultarEdicionesDePrograma(
        obras=RepositorioObrasSQL(sesion),
        ediciones=RepositorioEdicionesDeProgramaSQL(sesion),
    )


def _bus_de_reprogramacion(sesion: SesionRLS, ctx: ContextoActual) -> BusEnProceso:
    """`ReprogramacionAplicada` y `ReprogramacionObservada` → avisar (D-533): correo +
    push, y el aviso en vivo. Mismo cableado que `_bus_de_estimacion`."""
    notificar = NotificarReprogramacion(
        reprogramaciones=RepositorioReprogramacionesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        usuarios=RepositorioUsuariosSQL(sesion),
        correo=ClienteResend(),
        push=ClienteExpoPush(),
    )

    async def _avisar_aplicada(evento: ReprogramacionAplicada) -> None:
        await notificar.aplicada(evento)

    async def _avisar_observada(evento: ReprogramacionObservada) -> None:
        await notificar.observada(evento)

    bus = BusEnProceso()
    bus.suscribir(ReprogramacionAplicada, _avisar_aplicada)
    bus.suscribir(ReprogramacionObservada, _avisar_observada)
    return suscribir_avisos(bus, ctx=ctx, canal=canal_de_avisos)


def obtener_consultar_reprogramaciones(sesion: SesionRLS) -> ConsultarReprogramaciones:
    return ConsultarReprogramaciones(
        reprogramaciones=RepositorioReprogramacionesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
    )


def obtener_proponer_reprogramacion(sesion: SesionRLS) -> ProponerReprogramacion:
    return ProponerReprogramacion(
        reprogramaciones=RepositorioReprogramacionesSQL(sesion),
        actividades=RepositorioActividadesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_revisar_reprogramacion(sesion: SesionRLS) -> RevisarReprogramacion:
    return RevisarReprogramacion(
        reprogramaciones=RepositorioReprogramacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_validar_reprogramacion(sesion: SesionRLS) -> ValidarReprogramacion:
    return ValidarReprogramacion(
        reprogramaciones=RepositorioReprogramacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_rechazar_reprogramacion(sesion: SesionRLS) -> RechazarReprogramacion:
    return RechazarReprogramacion(
        reprogramaciones=RepositorioReprogramacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_observar_reprogramacion(
    sesion: SesionRLS, ctx: ContextoActual
) -> ObservarReprogramacion:
    return ObservarReprogramacion(
        reprogramaciones=RepositorioReprogramacionesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_reprogramacion(sesion, ctx),
    )


def obtener_aplicar_reprogramacion(
    sesion: SesionRLS, ctx: ContextoActual
) -> AplicarReprogramacion:
    return AplicarReprogramacion(
        reprogramaciones=RepositorioReprogramacionesSQL(sesion),
        editar=obtener_editar_programacion(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_reprogramacion(sesion, ctx),
    )


def obtener_consultar_partes(sesion: SesionRLS) -> ConsultarPartes:
    return ConsultarPartes(
        partes=RepositorioPartesSQL(sesion), obras=RepositorioObrasSQL(sesion)
    )


def obtener_consultar_carga_de_partes(sesion: SesionRLS) -> ConsultarCargaDePartes:
    return ConsultarCargaDePartes(
        partes=RepositorioPartesSQL(sesion), obras=RepositorioObrasSQL(sesion)
    )


def obtener_crear_obra_desde_catalogo_base(sesion: SesionRLS) -> CrearObraDesdeCatalogoBase:
    return CrearObraDesdeCatalogoBase(
        obras=RepositorioObrasSQL(sesion),
        clusters=RepositorioClustersSQL(sesion),
        prototipos=RepositorioPrototiposSQL(sesion),
        prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
        partes=RepositorioPartesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_crear_obra_desde_cero(sesion: SesionRLS) -> CrearObraDesdeCero:
    return CrearObraDesdeCero(
        obras=RepositorioObrasSQL(sesion),
        clusters=RepositorioClustersSQL(sesion),
        prototipos=RepositorioPrototiposSQL(sesion),
        partes=RepositorioPartesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_consultar_valuacion(sesion: SesionRLS) -> ConsultarValuacion:
    return ConsultarValuacion(
        partes=RepositorioPartesSQL(sesion), obras=RepositorioObrasSQL(sesion)
    )


def obtener_redisenar_parte(sesion: SesionRLS, ctx: ContextoActual) -> RedisenarParte:
    return RedisenarParte(
        partes=RepositorioPartesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        explotar=ExplotarEnsamble(
            ensambles=RepositorioEnsamblesSQL(sesion), conceptos=RepositorioConceptosSQL(sesion)
        ),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
    )


def obtener_cotizar_lo_modificado(sesion: SesionRLS) -> CotizarLoModificado:
    return CotizarLoModificado(
        partes=RepositorioPartesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        configuracion=RepositorioConfiguracionSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_consultar_cotizaciones(sesion: SesionRLS) -> ConsultarCotizaciones:
    return ConsultarCotizaciones(
        partes=RepositorioPartesSQL(sesion), obras=RepositorioObrasSQL(sesion)
    )


def obtener_responder_cotizacion(sesion: SesionRLS) -> ResponderCotizacion:
    return ResponderCotizacion(partes=RepositorioPartesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion))


def obtener_consultar_catalogos_base(sesion: SesionRLS) -> ConsultarCatalogosBase:
    return ConsultarCatalogosBase(partes=RepositorioPartesSQL(sesion))


def obtener_modificar_actividad(sesion: SesionRLS, ctx: ContextoActual) -> ModificarActividad:
    return ModificarActividad(
        partes=RepositorioPartesSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
    )


def obtener_agregar_actividad_nueva(sesion: SesionRLS, ctx: ContextoActual) -> AgregarActividadNueva:
    return AgregarActividadNueva(
        partes=RepositorioPartesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
    )


def obtener_gestionar_matrices_de_concepto(sesion: SesionRLS) -> GestionarMatricesDeConcepto:
    return GestionarMatricesDeConcepto(
        conceptos=RepositorioConceptosSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
    )


def obtener_crear_concepto_en_obra(sesion: SesionRLS) -> CrearConceptoEnObra:
    return CrearConceptoEnObra(
        conceptos=RepositorioConceptosSQL(sesion),
        partes=RepositorioPartesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
    )


def obtener_consultar_modificaciones(sesion: SesionRLS) -> ConsultarModificaciones:
    return ConsultarModificaciones(
        partes=RepositorioPartesSQL(sesion), obras=RepositorioObrasSQL(sesion)
    )


def obtener_marcar_parte_independiente(sesion: SesionRLS) -> MarcarParteIndependiente:
    return MarcarParteIndependiente(
        partes=RepositorioPartesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
    )


def obtener_fijar_plantas_de_obra(sesion: SesionRLS) -> FijarPlantasDeObra:
    return FijarPlantasDeObra(partes=RepositorioPartesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion))


def obtener_fijar_plantas_de_prototipo(sesion: SesionRLS) -> FijarPlantasDePrototipo:
    return FijarPlantasDePrototipo(
        partes=RepositorioPartesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
    )


def _bus_de_partes(sesion: SesionRLS, ctx: ContextoActual) -> BusEnProceso:
    """`PartesCambiaronDeEstado` → avisar por correo y push a quien da el siguiente paso, y el
    aviso en vivo (D-571, §8.6)."""
    notificar = NotificarPartes(
        partes=RepositorioPartesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        usuarios=RepositorioUsuariosSQL(sesion),
        correo=ClienteResend(),
        push=ClienteExpoPush(),
    )

    async def _avisar(evento: PartesCambiaronDeEstado) -> None:
        await notificar.ejecutar(evento)

    bus = BusEnProceso()
    bus.suscribir(PartesCambiaronDeEstado, _avisar)
    return suscribir_avisos(bus, ctx=ctx, canal=canal_de_avisos)


def obtener_cambiar_estado_de_partes(
    sesion: SesionRLS, ctx: ContextoActual
) -> CambiarEstadoDePartes:
    return CambiarEstadoDePartes(
        partes=RepositorioPartesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        uow=UnidadDeTrabajoSQL(sesion),
        eventos=_bus_de_partes(sesion, ctx),
    )


def obtener_consultar_bitacora_de_partes(sesion: SesionRLS) -> ConsultarBitacoraDePartes:
    return ConsultarBitacoraDePartes(
        partes=RepositorioPartesSQL(sesion), obras=RepositorioObrasSQL(sesion)
    )


def obtener_consultar_alertas_de_partes(sesion: SesionRLS) -> ConsultarAlertasDePartes:
    return ConsultarAlertasDePartes(
        partes=RepositorioPartesSQL(sesion),
        obras=RepositorioObrasSQL(sesion),
        configuracion=RepositorioConfiguracionSQL(sesion),
    )


def obtener_consultar_arranque(sesion: SesionRLS) -> ConsultarArranque:
    return ConsultarArranque(partes=RepositorioPartesSQL(sesion), obras=RepositorioObrasSQL(sesion))


def obtener_fijar_candado_de_asignar(sesion: SesionRLS) -> FijarCandadoDeAsignar:
    return FijarCandadoDeAsignar(partes=RepositorioPartesSQL(sesion), uow=UnidadDeTrabajoSQL(sesion))


def obtener_consultar_desfase_de_partes(sesion: SesionRLS) -> ConsultarDesfaseDePartes:
    return ConsultarDesfaseDePartes(configuracion=RepositorioConfiguracionSQL(sesion))


def obtener_fijar_desfase_de_partes(sesion: SesionRLS) -> FijarDesfaseDePartes:
    return FijarDesfaseDePartes(
        configuracion=RepositorioConfiguracionSQL(sesion), uow=UnidadDeTrabajoSQL(sesion)
    )


ConsultarAlertasDePartesDep = Annotated[
    ConsultarAlertasDePartes, Depends(obtener_consultar_alertas_de_partes)
]
ConsultarArranqueDep = Annotated[ConsultarArranque, Depends(obtener_consultar_arranque)]
FijarCandadoDeAsignarDep = Annotated[
    FijarCandadoDeAsignar, Depends(obtener_fijar_candado_de_asignar)
]
ConsultarDesfaseDePartesDep = Annotated[
    ConsultarDesfaseDePartes, Depends(obtener_consultar_desfase_de_partes)
]
FijarDesfaseDePartesDep = Annotated[
    FijarDesfaseDePartes, Depends(obtener_fijar_desfase_de_partes)
]
CambiarEstadoDePartesDep = Annotated[
    CambiarEstadoDePartes, Depends(obtener_cambiar_estado_de_partes)
]
ConsultarBitacoraDePartesDep = Annotated[
    ConsultarBitacoraDePartes, Depends(obtener_consultar_bitacora_de_partes)
]
ConsultarPartesDep = Annotated[ConsultarPartes, Depends(obtener_consultar_partes)]
CrearObraDesdeCatalogoBaseDep = Annotated[
    CrearObraDesdeCatalogoBase, Depends(obtener_crear_obra_desde_catalogo_base)
]
CrearObraDesdeCeroDep = Annotated[CrearObraDesdeCero, Depends(obtener_crear_obra_desde_cero)]
ConsultarValuacionDep = Annotated[ConsultarValuacion, Depends(obtener_consultar_valuacion)]
RedisenarParteDep = Annotated[RedisenarParte, Depends(obtener_redisenar_parte)]
CotizarLoModificadoDep = Annotated[CotizarLoModificado, Depends(obtener_cotizar_lo_modificado)]
ConsultarCotizacionesDep = Annotated[
    ConsultarCotizaciones, Depends(obtener_consultar_cotizaciones)
]
ResponderCotizacionDep = Annotated[ResponderCotizacion, Depends(obtener_responder_cotizacion)]
ConsultarCatalogosBaseDep = Annotated[
    ConsultarCatalogosBase, Depends(obtener_consultar_catalogos_base)
]
ModificarActividadDep = Annotated[ModificarActividad, Depends(obtener_modificar_actividad)]
GestionarMatricesDeConceptoDep = Annotated[
    GestionarMatricesDeConcepto, Depends(obtener_gestionar_matrices_de_concepto)
]
CrearConceptoEnObraDep = Annotated[CrearConceptoEnObra, Depends(obtener_crear_concepto_en_obra)]
AgregarActividadNuevaDep = Annotated[
    AgregarActividadNueva, Depends(obtener_agregar_actividad_nueva)
]
ConsultarModificacionesDep = Annotated[
    ConsultarModificaciones, Depends(obtener_consultar_modificaciones)
]
ConsultarCargaDePartesDep = Annotated[
    ConsultarCargaDePartes, Depends(obtener_consultar_carga_de_partes)
]
MarcarParteIndependienteDep = Annotated[
    MarcarParteIndependiente, Depends(obtener_marcar_parte_independiente)
]
FijarPlantasDeObraDep = Annotated[FijarPlantasDeObra, Depends(obtener_fijar_plantas_de_obra)]
FijarPlantasDePrototipoDep = Annotated[
    FijarPlantasDePrototipo, Depends(obtener_fijar_plantas_de_prototipo)
]

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
ConfirmarAvanceDep = Annotated[ConfirmarAvance, Depends(obtener_confirmar_avance)]
ConsultarConfirmacionesDep = Annotated[
    ConsultarConfirmaciones, Depends(obtener_consultar_confirmaciones)
]
ConsultarFrentesDeObraDep = Annotated[
    ConsultarFrentesDeObra, Depends(obtener_consultar_frentes_de_obra)
]
SolicitarCierreDeFrenteDep = Annotated[
    SolicitarCierreDeFrente, Depends(obtener_solicitar_cierre_de_frente)
]
AprobarCierreDeFrenteDep = Annotated[
    AprobarCierreDeFrente, Depends(obtener_aprobar_cierre_de_frente)
]
ValidarCierreDeFrenteDep = Annotated[
    ValidarCierreDeFrente, Depends(obtener_validar_cierre_de_frente)
]
RechazarCierreDeFrenteDep = Annotated[
    RechazarCierreDeFrente, Depends(obtener_rechazar_cierre_de_frente)
]
ConsultarDesviacionesDep = Annotated[
    ConsultarDesviaciones, Depends(obtener_consultar_desviaciones)
]
CapturarCausaDeDesviacionDep = Annotated[
    CapturarCausaDeDesviacion, Depends(obtener_capturar_causa)
]
IniciarObraDep = Annotated[IniciarObra, Depends(obtener_iniciar_obra)]
ConsultarEdicionesDeProgramaDep = Annotated[
    ConsultarEdicionesDePrograma, Depends(obtener_consultar_ediciones_de_programa)
]
ConsultarReprogramacionesDep = Annotated[
    ConsultarReprogramaciones, Depends(obtener_consultar_reprogramaciones)
]
ProponerReprogramacionDep = Annotated[
    ProponerReprogramacion, Depends(obtener_proponer_reprogramacion)
]
RevisarReprogramacionDep = Annotated[
    RevisarReprogramacion, Depends(obtener_revisar_reprogramacion)
]
ValidarReprogramacionDep = Annotated[
    ValidarReprogramacion, Depends(obtener_validar_reprogramacion)
]
RechazarReprogramacionDep = Annotated[
    RechazarReprogramacion, Depends(obtener_rechazar_reprogramacion)
]
AplicarReprogramacionDep = Annotated[
    AplicarReprogramacion, Depends(obtener_aplicar_reprogramacion)
]
ObservarReprogramacionDep = Annotated[
    ObservarReprogramacion, Depends(obtener_observar_reprogramacion)
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


def obtener_aprobar_pendientes_en_lote(sesion: SesionRLS) -> AprobarPendientesEnLote:
    return AprobarPendientesEnLote(
        cargas=RepositorioCargasSQL(sesion),
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
AprobarPendientesEnLoteDep = Annotated[
    AprobarPendientesEnLote, Depends(obtener_aprobar_pendientes_en_lote)
]
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

        if tipo in (TipoCarga.MATERIALES, TipoCarga.FLETES):
            return AplicadorMateriales(
                insumos=RepositorioInsumosSQL(sesion),
                unidades=RepositorioUnidadesSQL(sesion),
                familias=RepositorioFamiliasSQL(sesion),
                cargas=cargas,
            )
        if tipo is TipoCarga.MANO_DE_OBRA:
            return AplicadorCatalogoManoDeObra(
                insumos=RepositorioInsumosSQL(sesion),
                cuadrillas=RepositorioCuadrillasSQL(sesion),
                unidades=RepositorioUnidadesSQL(sesion),
                familias=RepositorioFamiliasSQL(sesion),
                detalle=RepositorioManoDeObraOpusSQL(sesion),
                cargas=cargas,
            )
        if tipo is TipoCarga.SEMILLA_CUADRILLA_RENDIMIENTO:
            return AplicadorSemillaCuadrillas(
                insumos=RepositorioInsumosSQL(sesion),
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
                cuadrillas=RepositorioCuadrillasSQL(sesion),
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
        if tipo is TipoCarga.PROGRAMA_BASE:
            return AplicadorProgramaBase(
                prototipos=RepositorioPrototiposSQL(sesion),
                prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
                crear_programa_base=CrearProgramaBase(
                    programas=RepositorioProgramasSQL(sesion),
                    uow=UnidadDeTrabajoSQL(sesion),
                ),
            )
        if tipo is TipoCarga.INGENIERIA_LOTE:
            return AplicadorIngenieriaLote(
                obras=RepositorioObrasSQL(sesion),
                prototipos=RepositorioPrototiposSQL(sesion),
                prototipo_nodos=RepositorioPrototipoNodoSQL(sesion),
                conceptos=RepositorioConceptosSQL(sesion),
                desviaciones=RepositorioDesviacionesSQL(sesion),
                ingenieria_insumos=RepositorioIngenieriaLoteInsumosSQL(sesion),
                cargas=cargas,
                arbol=obtener_arbol_de_obra(sesion),
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
