/**
 * Cómo se lee el estado de una obra en la Torre (§5.1, §5.3).
 *
 * Sin lógica de negocio: los conteos los calcula el backend en una consulta
 * (`adapters/repos/torre_sql.py`). Aquí solo se decide **qué mirar primero** y
 * cómo nombrarlo, que es de lo que va esta pantalla: tres de los cuatro roles
 * la abren al entrar y lo que necesitan no es un reporte, es saber qué les toca
 * hoy.
 */

import type { EstadoDeObraRespuesta } from '@/api/generado/modelo';
import type { Rol } from '@/shell/navegacion';

/** Cómo se llama la Torre en el sidebar de cada rol (§5.1). */
const TITULO_POR_ROL: Record<string, string> = {
  supervisor: 'Torre de control',
  control_obra: 'Torre de control',
  super_intendente: 'Torre de control',
  residente: 'Mis obras',
};

export function tituloDeTorre(rol: Rol): string {
  return TITULO_POR_ROL[rol] ?? 'Torre de control';
}

/**
 * Lo que esta persona puede hacer con lo que ve, dicho en una línea.
 *
 * No es decoración: la misma tabla significa cosas distintas según quién la
 * abra —el supervisor autoriza cierres, control los valida (§4)— y sin decirlo
 * la pantalla es un tablero de números sin verbo.
 */
export function subtituloDeTorre(rol: Rol): string {
  if (rol === 'supervisor') {
    return 'Tus obras por cluster. Los cierres solicitados esperan tu autorización (§11.3 C).';
  }
  if (rol === 'control_obra') {
    return 'Las obras de tus proyectos. Los cierres autorizados esperan tu validación (§11.3 C).';
  }
  if (rol === 'super_intendente') {
    return 'Toda la organización. Lo que estorba aparece primero.';
  }
  return 'Las obras donde eres residente.';
}

export type Urgencia = 'detenida' | 'pendiente' | 'al-corriente';

/**
 * Tres estados, no cinco.
 *
 * · `detenida` — hay una actividad bloqueada o una incidencia que detiene
 *   (§11.3 F). Es lo único que **impide trabajar**, así que va aparte.
 * · `pendiente` — hay algo esperando a una persona: un cierre por resolver o
 *   una incidencia abierta que no detiene.
 * · `al-corriente` — nada esperando. No significa "terminada".
 *
 * Se resiste la tentación de meter el avance en esta clasificación: una obra
 * al 20 % puede ir perfectamente en tiempo, y teñirla de rojo por el número
 * enseñaría a ignorar los rojos.
 */
export function urgenciaDe(obra: EstadoDeObraRespuesta): Urgencia {
  if (obra.bloqueadas > 0 || obra.incidencias_detienen > 0) return 'detenida';
  if (obra.cierres_pendientes > 0 || obra.incidencias_abiertas > 0) return 'pendiente';
  return 'al-corriente';
}

const TONO_URGENCIA: Record<Urgencia, string> = {
  detenida: 'danger',
  pendiente: 'warn',
  'al-corriente': 'ok',
};

export function tonoUrgencia(urgencia: Urgencia): string {
  return TONO_URGENCIA[urgencia];
}

const ETIQUETA_URGENCIA: Record<Urgencia, string> = {
  detenida: 'Detenida',
  pendiente: 'Pendiente',
  'al-corriente': 'Al corriente',
};

export function etiquetaUrgencia(urgencia: Urgencia): string {
  return ETIQUETA_URGENCIA[urgencia];
}

/** Resumen de la cabecera: cuántas obras hay en cada estado. */
export interface ResumenDeTorre {
  readonly obras: number;
  readonly detenidas: number;
  readonly pendientes: number;
  readonly alCorriente: number;
  readonly cierresPendientes: number;
  readonly incidenciasAbiertas: number;
}

export function resumirTorre(
  obras: readonly EstadoDeObraRespuesta[],
): ResumenDeTorre {
  let detenidas = 0;
  let pendientes = 0;
  let cierresPendientes = 0;
  let incidenciasAbiertas = 0;

  for (const obra of obras) {
    const urgencia = urgenciaDe(obra);
    if (urgencia === 'detenida') detenidas += 1;
    else if (urgencia === 'pendiente') pendientes += 1;
    cierresPendientes += obra.cierres_pendientes;
    incidenciasAbiertas += obra.incidencias_abiertas;
  }

  return {
    obras: obras.length,
    detenidas,
    pendientes,
    alCorriente: obras.length - detenidas - pendientes,
    cierresPendientes,
    incidenciasAbiertas,
  };
}

/**
 * Filtra por texto sobre lo que identifica una obra.
 *
 * Sobre clave de obra, de cluster, de proyecto y nombre del residente: con
 * ochenta obras, «FRESNO 01» y «CEDRO 01» se parecen lo bastante como para que
 * buscar por el nombre de quien la lleva sea a veces lo más rápido.
 */
export function filtrarObras(
  obras: readonly EstadoDeObraRespuesta[],
  texto: string,
): readonly EstadoDeObraRespuesta[] {
  const busqueda = texto.trim().toLowerCase();
  if (busqueda === '') return obras;
  return obras.filter((obra) =>
    [obra.obra_clave, obra.cluster_clave, obra.proyecto_clave, obra.residente_nombre]
      .filter((campo): campo is string => typeof campo === 'string')
      .some((campo) => campo.toLowerCase().includes(busqueda)),
  );
}

const ETIQUETA_ESTATUS_ACTIVIDAD: Record<string, string> = {
  programada: 'Programada',
  en_proceso: 'En proceso',
  casi: 'Casi',
  pendiente_cierre: 'Pendiente de cierre',
  concluida: 'Concluida',
  retrasada: 'Retrasada',
  extra_catalogo: 'Extra catálogo',
};

export function etiquetaEstatusActividad(estatus: string): string {
  return ETIQUETA_ESTATUS_ACTIVIDAD[estatus] ?? estatus;
}

export function tonoEstatusActividad(estatus: string): string {
  if (estatus === 'concluida') return 'ok';
  if (estatus === 'retrasada') return 'danger';
  if (estatus === 'en_proceso' || estatus === 'casi') return 'info';
  return 'neutral';
}
