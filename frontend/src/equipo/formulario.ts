/**
 * Traducción entre el formulario de alta/edición (todo `string`) y los DTOs
 * del contrato (`CrearUsuarioPeticion`, `ActualizarUsuarioPeticion`).
 *
 * Puro y sin reglas: no decide quién puede otorgar qué rol —eso es `reglas.ts`
 * para la UX y el backend para la verdad—.
 */

import type {
  ActualizarUsuarioPeticion,
  CrearUsuarioPeticion,
  UsuarioRespuesta,
} from '@/api/generado/modelo';
import type { Rol } from '@/shell/navegacion';

export interface FormularioUsuario {
  readonly nombre: string;
  readonly email: string;
  readonly rol: Rol;
  readonly cedula: string;
  readonly telefono: string;
  readonly contrasenaTemporal: string;
}

export function formularioUsuarioVacio(
  rol: Rol,
  contrasenaTemporal: string,
): FormularioUsuario {
  return { nombre: '', email: '', rol, cedula: '', telefono: '', contrasenaTemporal };
}

export function formularioDesdeUsuario(usuario: UsuarioRespuesta): FormularioUsuario {
  return {
    nombre: usuario.nombre,
    email: usuario.email,
    rol: usuario.rol as Rol,
    cedula: usuario.cedula ?? '',
    telefono: usuario.telefono ?? '',
    contrasenaTemporal: '',
  };
}

function textoOpcional(valor: string): string | undefined {
  const limpio = valor.trim();
  return limpio === '' ? undefined : limpio;
}

export function altaCompleta(formulario: FormularioUsuario, minimo: number): boolean {
  return (
    formulario.nombre.trim() !== '' &&
    formulario.email.trim() !== '' &&
    formulario.contrasenaTemporal.length >= minimo
  );
}

export function peticionDeAlta(formulario: FormularioUsuario): CrearUsuarioPeticion {
  return {
    nombre: formulario.nombre.trim(),
    // En minúsculas porque `uq_usuario_email_org` distingue mayúsculas: sin
    // esto, "Ana@obra.mx" y "ana@obra.mx" serían dos personas. El dominio
    // vuelve a normalizarlo; aquí es para que la pantalla muestre lo mismo que
    // se va a guardar.
    email: formulario.email.trim().toLowerCase(),
    rol: formulario.rol,
    contrasena_temporal: formulario.contrasenaTemporal,
    cedula: textoOpcional(formulario.cedula),
    telefono: textoOpcional(formulario.telefono),
  };
}

/**
 * Solo lo que cambió respecto de la fila actual.
 *
 * Mandar el cuerpo entero funcionaría —el backend hace `coalesce`— pero
 * enviaría `rol` en cada edición de teléfono, y el trigger de la 0025 vigila
 * los cambios de rol: un PATCH que reenvía el mismo rol pasa, pero deja el
 * campo en el cuerpo de una petición que no tenía por qué llevarlo.
 */
export function cambiosDeUsuario(
  formulario: FormularioUsuario,
  original: UsuarioRespuesta,
): ActualizarUsuarioPeticion {
  const cambios: ActualizarUsuarioPeticion = {};
  if (formulario.nombre.trim() !== original.nombre) {
    cambios.nombre = formulario.nombre.trim();
  }
  if (formulario.cedula.trim() !== (original.cedula ?? '')) {
    cambios.cedula = formulario.cedula.trim();
  }
  if (formulario.telefono.trim() !== (original.telefono ?? '')) {
    cambios.telefono = formulario.telefono.trim();
  }
  if (formulario.rol !== original.rol) {
    cambios.rol = formulario.rol;
  }
  return cambios;
}

export function hayCambios(cambios: ActualizarUsuarioPeticion): boolean {
  return Object.keys(cambios).length > 0;
}
