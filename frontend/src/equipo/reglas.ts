/**
 * Reflejo en el front de las reglas del §4 sobre usuarios.
 *
 * Spec §4 (roles y alcance) · §5.1 (el alta la hace Control de obra).
 *
 * **Esto no autoriza nada.** Es UX: sirve para no ofrecer un botón que va a
 * responder 403. La regla de verdad vive tres veces —el dominio
 * (`domain/identidad/reglas.py`), el trigger de la migración 0025 y RLS—, y
 * este archivo es un cuarto reflejo, el más barato y el menos confiable. Si
 * discrepa, manda el backend.
 */

import type { Rol } from '@/shell/navegacion';

export const ROLES: readonly Rol[] = [
  'residente',
  'supervisor',
  'control_obra',
  'super_intendente',
];

const ETIQUETA: Record<Rol, string> = {
  residente: 'Residente',
  supervisor: 'Supervisor',
  control_obra: 'Control de obra',
  super_intendente: 'Super intendente',
};

export function etiquetaRol(rol: string): string {
  return ETIQUETA[rol as Rol] ?? rol;
}

/** Tono del badge del rol. El de más privilegio se distingue a propósito. */
export function tonoRol(rol: string): string {
  if (rol === 'super_intendente') return 'warn';
  if (rol === 'control_obra') return 'info';
  return 'neutral';
}

/** ¿Este rol administra el equipo? (§5.1) */
export function administraEquipo(rol: Rol): boolean {
  return rol === 'control_obra' || rol === 'super_intendente';
}

/**
 * Roles que `quien` puede otorgar en un alta o en un cambio (§4).
 *
 * Control de obra arma su equipo pero **no** puede fabricar un Super
 * intendente: sería darse a sí mismo un cómplice con más privilegios. Por eso
 * la lista se filtra en vez de deshabilitar la opción — una opción visible que
 * siempre falla es peor que no ofrecerla.
 */
export function rolesQuePuedeOtorgar(quien: Rol): readonly Rol[] {
  if (!administraEquipo(quien)) return [];
  if (quien === 'super_intendente') return ROLES;
  return ROLES.filter((r) => r !== 'super_intendente');
}

/**
 * ¿`quien` puede editar a esta persona? (§4)
 *
 * Las dos prohibiciones son las del trigger de la 0025: nadie se edita el rol
 * ni el estatus a sí mismo, y solo un Super intendente toca a otro Super
 * intendente.
 */
export function puedeEditar(quien: Rol, esUnoMismo: boolean, rolDestino: string): boolean {
  if (!administraEquipo(quien)) return false;
  if (esUnoMismo) return false;
  if (rolDestino === 'super_intendente') return quien === 'super_intendente';
  return true;
}

/**
 * Qué puente de alcance le corresponde a un rol (§4).
 *
 * `null` para el residente: llega a su obra por `obra.residente_id`, que se
 * asigna desde la obra y no desde Asignaciones. Asignarle un cluster no le
 * daría alcance, solo una fila que nadie lee.
 */
export function puenteDe(rol: string): 'clusters' | 'proyectos' | null {
  if (rol === 'supervisor') return 'clusters';
  if (rol === 'control_obra') return 'proyectos';
  return null;
}

/** ¿`quien` puede cambiar el alcance de alguien con `rolDestino`? (§4) */
export function puedeAsignarAlcanceDe(quien: Rol, rolDestino: string): boolean {
  // `control_proyecto` decide qué proyectos ve un Control de obra, o sea el
  // alcance de quien administra: si Control pudiera editarlo se ampliaría el
  // suyo. Es la política `control_proyecto_*` de la migración 0012.
  if (rolDestino === 'control_obra') return quien === 'super_intendente';
  if (rolDestino === 'supervisor') return administraEquipo(quien);
  return false;
}

/** Largo mínimo de la contraseña temporal — espejo de `LARGO_MINIMO_CONTRASENA`. */
export const LARGO_MINIMO_CONTRASENA = 12;

/**
 * Sugiere una contraseña temporal legible.
 *
 * Legible a propósito: alguien la va a dictar por teléfono o escribirla en un
 * papel, y una cadena de base64 con símbolos se transcribe mal. La seguridad
 * viene del largo, no de los símbolos — y de que la persona está obligada a
 * cambiarla en cuanto entra.
 */
export function sugerirContrasena(): string {
  const silabas = [
    'ba', 'ce', 'di', 'fo', 'gu', 'la', 'me', 'ni', 'po', 'ra',
    'sa', 'te', 'vi', 'zo', 'mu', 'lo', 'pe', 'ta', 'ri', 'no',
  ];
  const azar = (max: number) => {
    const buffer = new Uint32Array(1);
    globalThis.crypto.getRandomValues(buffer);
    return (buffer[0] ?? 0) % max;
  };
  let palabra = '';
  while (palabra.length < LARGO_MINIMO_CONTRASENA + 2) {
    palabra += silabas[azar(silabas.length)] ?? 'xa';
  }
  return `${palabra}-${100 + azar(900)}`;
}
