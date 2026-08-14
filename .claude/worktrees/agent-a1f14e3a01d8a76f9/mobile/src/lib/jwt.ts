/**
 * Decodificación mínima del payload de un JWT.
 *
 * No verifica firma — eso ya lo hizo Supabase Auth al emitir el token; aquí
 * solo se lee para extraer los claims custom `org_id`/`rol` (§12.4) del lado
 * cliente, sin depender de `atob`/`Buffer` (no garantizados en Hermes sin
 * polyfill).
 */

const BASE64_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

function base64UrlDecode(segmento: string): string {
  const base64 = segmento.replace(/-/g, '+').replace(/_/g, '/');
  let buffer = 0;
  let bits = 0;
  let salida = '';

  for (const c of base64) {
    const idx = BASE64_CHARS.indexOf(c);
    if (idx === -1) continue; // ignora '=' de relleno y caracteres inválidos
    buffer = (buffer << 6) | idx;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      salida += String.fromCharCode((buffer >> bits) & 0xff);
    }
  }

  return salida;
}

/** Devuelve el payload del JWT como objeto, o `{}` si no se pudo decodificar. */
export function decodificarClaimsJwt(token: string): Record<string, unknown> {
  const partes = token.split('.');
  if (partes.length < 2) return {};

  try {
    const payload = JSON.parse(base64UrlDecode(partes[1]!));
    return typeof payload === 'object' && payload !== null ? (payload as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}
