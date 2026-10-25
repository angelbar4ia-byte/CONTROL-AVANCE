#!/usr/bin/env node
/**
 * Auth falsa para los E2E de workflows: imita lo mínimo de GoTrue (Supabase
 * Auth) que usa supabase-js, para poder correr la web y la API sin un proyecto
 * de Supabase.
 *
 *   POST /auth/v1/token?grant_type=password|refresh_token
 *   GET  /auth/v1/user
 *
 * Emite el JWT que emitiría el `custom_access_token_hook` (migración 0015):
 * `org_id`, `rol`, `usuario_id` y `nombre` en la raíz de los claims, firmado
 * HS256 con `JWT_SECRET`, que es lo que el backend verifica cuando no hay JWKS.
 *
 * Quién es el usuario sale de la tabla `usuario` por correo. La contraseña es
 * la misma para todos (`E2E_PASSWORD`): esto es un arnés de pruebas, no auth.
 *
 *   DATABASE_URL=postgresql://... JWT_SECRET=... E2E_PASSWORD=... \
 *     node e2e/soporte/auth-falsa.mjs [puerto]
 */
import { execFileSync } from 'node:child_process';
import { createHmac, randomUUID } from 'node:crypto';
import { createServer } from 'node:http';

const PUERTO = Number(process.argv[2] ?? process.env.AUTH_FALSA_PUERTO ?? 54321);
const DATABASE_URL = process.env.DATABASE_URL;
const JWT_SECRET = process.env.JWT_SECRET;
const PASSWORD = process.env.E2E_PASSWORD;

if (!DATABASE_URL || !JWT_SECRET || !PASSWORD) {
  console.error('Faltan DATABASE_URL, JWT_SECRET o E2E_PASSWORD.');
  process.exit(1);
}

const b64 = (o) => Buffer.from(typeof o === 'string' ? o : JSON.stringify(o)).toString('base64url');

function firmar(claims) {
  const cuerpo = `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64(claims)}`;
  const firma = createHmac('sha256', JWT_SECRET).update(cuerpo).digest('base64url');
  return `${cuerpo}.${firma}`;
}

/** `usuario` por correo, vía psql: sin dependencias de Node. */
function buscarUsuario(correo) {
  const sql =
    "select row_to_json(u) from (select id, org_id, nombre, email, rol from usuario " +
    `where lower(email) = lower('${correo.replace(/'/g, "''")}') limit 1) u`;
  const salida = execFileSync('psql', [DATABASE_URL, '-tAX', '-c', sql], {
    encoding: 'utf8',
  }).trim();
  return salida ? JSON.parse(salida) : null;
}

function sesionDe(usuario) {
  const ahora = Math.floor(Date.now() / 1000);
  const expira = ahora + 3600;
  const claims = {
    sub: usuario.id,
    aud: 'authenticated',
    role: 'authenticated',
    email: usuario.email,
    iat: ahora,
    exp: expira,
    org_id: usuario.org_id,
    rol: usuario.rol,
    usuario_id: usuario.id,
    nombre: usuario.nombre,
  };
  return {
    access_token: firmar(claims),
    token_type: 'bearer',
    expires_in: 3600,
    expires_at: expira,
    // El refresh lleva el correo para poder re-emitir sin guardar estado.
    refresh_token: b64({ correo: usuario.email, n: randomUUID() }),
    user: {
      id: usuario.id,
      aud: 'authenticated',
      role: 'authenticated',
      email: usuario.email,
      app_metadata: { provider: 'email', providers: ['email'] },
      user_metadata: {},
      created_at: new Date().toISOString(),
    },
  };
}

function responder(res, estado, cuerpo) {
  res.writeHead(estado, {
    'content-type': 'application/json',
    'access-control-allow-origin': '*',
    'access-control-allow-headers': '*',
    'access-control-allow-methods': 'GET,POST,OPTIONS',
  });
  res.end(JSON.stringify(cuerpo));
}

async function leerJson(req) {
  const partes = [];
  for await (const p of req) partes.push(p);
  try {
    return JSON.parse(Buffer.concat(partes).toString() || '{}');
  } catch {
    return {};
  }
}

createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PUERTO}`);
  if (req.method === 'OPTIONS') return responder(res, 204, {});

  if (url.pathname === '/auth/v1/token' && req.method === 'POST') {
    const cuerpo = await leerJson(req);
    const tipo = url.searchParams.get('grant_type');

    if (tipo === 'password') {
      const usuario = buscarUsuario(cuerpo.email ?? '');
      if (!usuario || cuerpo.password !== PASSWORD) {
        return responder(res, 400, {
          error: 'invalid_grant',
          error_description: 'Invalid login credentials',
        });
      }
      return responder(res, 200, sesionDe(usuario));
    }

    if (tipo === 'refresh_token') {
      try {
        const { correo } = JSON.parse(Buffer.from(cuerpo.refresh_token, 'base64url'));
        const usuario = buscarUsuario(correo);
        if (usuario) return responder(res, 200, sesionDe(usuario));
      } catch {
        /* cae al error */
      }
      return responder(res, 400, { error: 'invalid_grant' });
    }
  }

  if (url.pathname === '/auth/v1/user') {
    return responder(res, 200, { id: 'x', aud: 'authenticated', role: 'authenticated' });
  }

  responder(res, 404, { error: 'no existe en la auth falsa', ruta: url.pathname });
}).listen(PUERTO, '127.0.0.1', () => {
  console.log(`auth falsa en http://127.0.0.1:${PUERTO}`);
});
