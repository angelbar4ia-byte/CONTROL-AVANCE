/**
 * Decodificación mínima del payload de un JWT.
 *
 * No verifica la firma —eso ya lo hizo Supabase Auth al emitir el token, y el
 * backend la vuelve a verificar contra el JWKS del proyecto (§12.4)—. Aquí
 * solo se lee para conocer el alcance del usuario y pintar la interfaz.
 *
 * ## Por qué no basta `session.user.app_metadata`
 *
 * El hook `custom_access_token_hook` (migración 0015) copia `org_id`, `rol`,
 * `usuario_id` y `nombre` al **nivel raíz** de los claims, no dentro de
 * `app_metadata` —que solo trae `{provider, providers}`—. Leerlos de
 * `app_metadata` devuelve `undefined` siempre, aunque el token sea correcto.
 *
 * Es el mismo criterio que `mobile/src/lib/jwt.ts`: ambos clientes leen los
 * claims de la raíz, igual que `adapters/api/dependencias.py`.
 */

/** Payload del JWT como objeto, o `{}` si no se pudo decodificar. */
export function decodificarClaimsJwt(token: string): Record<string, unknown> {
  const partes = token.split('.');
  if (partes.length < 2) return {};

  try {
    const base64 = partes[1]!.replace(/-/g, '+').replace(/_/g, '/');
    const relleno = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');

    // `atob` da bytes crudos; el nombre de la organización puede llevar
    // acentos, así que se reinterpretan como UTF-8 en vez de latin-1.
    const bytes = Uint8Array.from(atob(relleno), (c) => c.charCodeAt(0));
    const payload = JSON.parse(new TextDecoder().decode(bytes));

    return typeof payload === 'object' && payload !== null
      ? (payload as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}
