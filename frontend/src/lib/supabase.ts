/**
 * Cliente de Supabase para la **ruta directa de catálogos**.
 *
 * Spec §10.7 (acceso directo a catálogos) · §12.4 (RLS).
 *
 * Dos rutas de acceso a datos, y no se mezclan:
 *
 *   1. **Catálogos** (selects, tablas, filtros) → directo a Supabase con
 *      supabase-js + RLS. Rápido y con realtime opcional.
 *   2. **Lógica de dominio** (cargas/ETL, CPM, estimaciones, cierres,
 *      auditoría) → siempre por la API FastAPI.
 *
 * ## Seguridad (crítico)
 *
 * Como el front toca la BD directo, **RLS es la única frontera** de esta ruta.
 * Se usa la **anon key**; la *service key* nunca llega al cliente. Si algún
 * día una consulta de aquí devuelve datos de otra organización, el problema
 * está en las políticas de `database/migrations/0012`, no aquí.
 */

import { createClient, type SupabaseClient } from '@supabase/supabase-js';

/**
 * Sufijos que el Dashboard de Supabase muestra pegados a la URL del proyecto.
 *
 * La etiqueta que ve el operador dice "API URL" y el valor termina en
 * `/rest/v1/`, así que copiarlo tal cual es el camino natural. Pero
 * supabase-js espera la URL **base** y le agrega la ruta del servicio: con el
 * sufijo incluido, el login pega contra `/rest/v1/auth/v1/token` y devuelve
 * 404. Se normaliza aquí en vez de exigir que alguien recuerde recortarlo.
 */
const SUFIJOS_DE_SERVICIO = ['/rest/v1', '/auth/v1', '/storage/v1', '/realtime/v1'];

function baseDeProyecto(valor: string): string {
  const base = valor.trim().replace(/\/+$/, '');
  const sufijo = SUFIJOS_DE_SERVICIO.find((s) => base.endsWith(s));
  return sufijo ? base.slice(0, -sufijo.length).replace(/\/+$/, '') : base;
}

const url = baseDeProyecto(import.meta.env.VITE_SUPABASE_URL ?? '');
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  throw new Error(
    'Faltan VITE_SUPABASE_URL o VITE_SUPABASE_ANON_KEY. ' +
      'Revisa .env.example y las variables del proyecto en Vercel (§12.8).',
  );
}

if (/service_role/.test(anonKey)) {
  // Un JWT de service_role salta RLS por completo: en el navegador expondría
  // toda la base a cualquiera que abra las herramientas de desarrollo.
  throw new Error(
    'VITE_SUPABASE_ANON_KEY parece ser una service key. ' +
      'La service key NUNCA va al cliente (§10.7). Usa la anon key.',
  );
}

export const supabase: SupabaseClient = createClient(url, anonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
  global: {
    headers: { 'x-cliente': 'obractrl-web' },
  },
});

/**
 * Tablas que se pueden leer por esta ruta.
 *
 * Es una lista blanca deliberada: mantiene la separación del §10.7 explícita
 * en el código y evita que una pantalla operativa termine consultando la BD
 * directo cuando debería pasar por un caso de uso del backend.
 */
export const CATALOGOS = [
  'unidad',
  'familia',
  'insumo',
  'concepto',
  'cpu',
  'contratista',
  'cuadrilla',
  'frente',
  'nivel',
  'etapa_constructiva',
  'prototipo',
  'proyecto',
  'cluster',
  'criterio_evaluacion',
  'motivo_almacen',
] as const;

export type Catalogo = (typeof CATALOGOS)[number];
