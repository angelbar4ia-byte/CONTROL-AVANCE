/**
 * Cómo se lee un cierre de obra en la pantalla — workflow D (§11.3 D).
 *
 * Sin lógica de negocio: qué aporta cada rol al acta, cómo se nombra cada
 * pendiente y si al usuario en sesión ya le tocó firmar. Quién puede qué lo
 * deciden el dominio y RLS.
 */

import type { CierreDeObraRespuesta } from '@/api/generado/modelo';
import type { Rol } from '@/shell/navegacion';

/**
 * Qué aporta cada rol (§11.3 D.2).
 *
 * Espejo de `APORTACION_POR_ROL` del dominio. Se nombra porque «participar» no
 * dice nada: el residente **entrega**, el supervisor da su **visto bueno**,
 * control responde por **calidad y expediente** y el super intendente **firma**.
 */
const APORTACION: Record<string, string> = {
  residente: 'Entrega',
  supervisor: 'Visto bueno',
  control_obra: 'Calidad y expediente',
  super_intendente: 'Firma',
};

export function aportacionDe(rol: string): string {
  return APORTACION[rol] ?? 'Participación';
}

const ETIQUETA_ROL: Record<string, string> = {
  residente: 'Residente',
  supervisor: 'Supervisor',
  control_obra: 'Control de obra',
  super_intendente: 'Super intendente',
};

export function etiquetaRol(rol: string): string {
  return ETIQUETA_ROL[rol] ?? rol;
}

/** ¿Solo el Super intendente abre el acta? (§11.2) */
export function puedeAbrirCierre(rol: Rol): boolean {
  return rol === 'super_intendente';
}

/**
 * ¿A esta persona todavía le toca firmar?
 *
 * La pregunta es por **rol**, no por persona: `uq_cierre_obra_participacion` es
 * por `(cierre, rol)`, así que si otro residente ya firmó, este no vuelve a
 * hacerlo. La pantalla tiene que decirlo así para que nadie espere un botón que
 * no va a aparecer.
 */
export function leTocaFirmar(cierre: CierreDeObraRespuesta, rol: Rol): boolean {
  return cierre.estatus === 'en_proceso' && cierre.faltan.includes(rol);
}

export type EstadoDeActa = 'cerrada' | 'lista-para-firmar' | 'esperando-firmas' | 'con-pendientes';

/**
 * En qué punto está el acta.
 *
 * Cuatro estados y no dos, porque «en proceso» junta tres situaciones que piden
 * acciones distintas: falta resolver trabajo, falta que alguien firme, o ya
 * está todo y solo falta el último clic.
 */
export function estadoDeActa(cierre: CierreDeObraRespuesta): EstadoDeActa {
  if (cierre.estatus === 'cerrada') return 'cerrada';
  if (cierre.pendientes.some((p) => p.bloquea)) return 'con-pendientes';
  if (cierre.faltan.length > 0) return 'esperando-firmas';
  return 'lista-para-firmar';
}

const ETIQUETA_ESTADO: Record<EstadoDeActa, string> = {
  cerrada: 'Obra entregada',
  'lista-para-firmar': 'Lista para firmar',
  'esperando-firmas': 'Esperando firmas',
  'con-pendientes': 'Con pendientes',
};

export function etiquetaEstado(estado: EstadoDeActa): string {
  return ETIQUETA_ESTADO[estado];
}

const TONO_ESTADO: Record<EstadoDeActa, string> = {
  cerrada: 'ok',
  'lista-para-firmar': 'info',
  'esperando-firmas': 'warn',
  'con-pendientes': 'danger',
};

export function tonoEstado(estado: EstadoDeActa): string {
  return TONO_ESTADO[estado];
}

/**
 * Los pendientes, separados por si impiden entregar.
 *
 * La pantalla los muestra en dos bloques: mezclarlos haría que un expediente
 * vacío se viera igual de grave que una estimación sin validar, y entonces
 * nadie miraría ninguno.
 */
export function separarPendientes(cierre: CierreDeObraRespuesta): {
  readonly bloqueantes: CierreDeObraRespuesta['pendientes'];
  readonly avisos: CierreDeObraRespuesta['pendientes'];
} {
  return {
    bloqueantes: cierre.pendientes.filter((p) => p.bloquea),
    avisos: cierre.pendientes.filter((p) => !p.bloquea),
  };
}
