/**
 * Acciones de autenticación — auth administrado por Supabase (§12.4).
 *
 * Sin endpoint `/login` propio: `signInWithPassword` habla directo con
 * Supabase Auth. `useSesion` (`sesion.ts`) reacciona al cambio de sesión y
 * decide el redirect por rol en `app/index.tsx`.
 */
import { supabase } from './supabase';

export interface ErrorInicioSesion {
  readonly mensaje: string;
}

function mensajeAmigable(mensajeOriginal: string): string {
  const m = mensajeOriginal.toLowerCase();
  if (m.includes('invalid login credentials')) {
    return 'Correo o contraseña incorrectos.';
  }
  if (m.includes('email not confirmed')) {
    return 'Tu correo aún no está confirmado. Contacta a Control de obra.';
  }
  if (m.includes('network') || m.includes('fetch')) {
    return 'Sin conexión: revisa tu señal e intenta de nuevo.';
  }
  return mensajeOriginal;
}

/** Devuelve `null` si el login fue exitoso, o el error a mostrar en la UI. */
export async function iniciarSesion(correo: string, contrasena: string): Promise<ErrorInicioSesion | null> {
  const { error } = await supabase.auth.signInWithPassword({
    email: correo.trim(),
    password: contrasena,
  });

  if (error) {
    return { mensaje: mensajeAmigable(error.message) };
  }

  return null;
}

export async function cerrarSesion(): Promise<void> {
  await supabase.auth.signOut();
}
