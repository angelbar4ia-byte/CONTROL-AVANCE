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
 * Qué puente de alcance le corresponde a un rol (§4, cadena de mando 0042).
 *
 * `null` para Control de obra: es la raíz, ve toda la organización y no
 * cuelga de nadie. `clusters` (supervisor↔cluster) y `proyectos`
 * (control↔proyecto) quedaron inertes desde la 0042 — ya no deciden alcance,
 * así que esta pantalla ya no los ofrece.
 */
export function puenteDe(rol: string): 'gente' | 'obras' | null {
  if (rol === 'super_intendente') return 'gente'; // superintendente_usuario
  if (rol === 'supervisor') return 'gente'; // supervisor_residente
  if (rol === 'residente') return 'obras'; // residente_obra: decide su alcance real
  return null;
}

/**
 * Roles que cuelgan de `rolJefe` en el organigrama (§4, 0042).
 *
 * Espejo de `roles_que_cuelgan_de` (`domain/identidad/reglas.py`): de un
 * super intendente cuelgan supervisores y residentes; de un supervisor,
 * solo residentes.
 */
export function rolesQueCuelganDe(rolJefe: Rol): readonly Rol[] {
  if (rolJefe === 'super_intendente') return ['supervisor', 'residente'];
  if (rolJefe === 'supervisor') return ['residente'];
  return [];
}

/**
 * ¿`quien` puede cambiar el alcance de alguien con `rolDestino`? (§4, 0042)
 *
 * Espejo de `puede_asignar_alcance_de`: Control arma la gente de un super
 * intendente; Control o el super intendente (dentro de su propia cadena)
 * arman la de un supervisor; Control, el super intendente o el supervisor
 * arman las obras de un residente.
 */
export function puedeAsignarAlcanceDe(quien: Rol, rolDestino: string): boolean {
  if (rolDestino === 'super_intendente') return quien === 'control_obra';
  if (rolDestino === 'supervisor') return quien === 'control_obra' || quien === 'super_intendente';
  if (rolDestino === 'residente') {
    return quien === 'control_obra' || quien === 'super_intendente' || quien === 'supervisor';
  }
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
