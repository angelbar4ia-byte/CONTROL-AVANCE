/**
 * Conector de PowerSync — el puente entre la réplica SQLite local y Postgres.
 *
 * Spec §12.5 (offline y sincronización) · §12.4 (RLS) · §11.3 workflow B.
 *
 * ## Por qué la subida va contra Postgres y no contra la API
 *
 * El workflow B del §11.3 separa explícitamente las dos rutas:
 *
 *   > 3. PowerSync concilia contra Postgres (respetando RLS).
 *   >    **En web:** `PATCH /actividades/{id}/avance`.
 *
 * Es decir: la ruta web pasa por el caso de uso de FastAPI; la ruta móvil
 * concilia contra Postgres a través de PowerSync, y **RLS** es la frontera
 * que la mantiene honesta (§12.4). Por eso `uploadData` escribe con el
 * cliente de Supabase autenticado con el JWT del usuario: las mismas
 * políticas de `database/migrations/0012_rls_policies.sql` que protegen la
 * web protegen esta escritura, y los `CHECK`/triggers del §6 que viven en la
 * BD (`app.actividad_recalcular`) se siguen ejecutando.
 *
 * ## Qué NO sube
 *
 * `actividad` es **servidor-manda** (ver `ESTRATEGIA_CONFLICTOS` en
 * `powersync.ts`): la pantalla de captura la actualiza local solo como
 * reflejo optimista para que el residente vea su número al instante. Subir
 * ese reflejo pisaría el total canónico, así que sus operaciones se
 * descartan de la cola. Lo que sí viaja es `registro_avance`, que guarda el
 * **delta** y por eso se acumula sin conflicto entre dispositivos.
 *
 * ## Sin URL de PowerSync configurada
 *
 * `connect()` no se llama (ver `ProveedorSync.tsx`). Las escrituras locales
 * se siguen encolando en `ps_crud` y suben en cuanto exista la URL; la UI lo
 * dice con todas sus letras en vez de fingir que sincronizó.
 */

import {
  UpdateType,
  type AbstractPowerSyncDatabase,
  type CrudEntry,
  type PowerSyncBackendConnector,
  type PowerSyncCredentials,
} from '@powersync/react-native';

import { URL_POWERSYNC } from '@/lib/entorno';
import { supabase } from '@/lib/supabase';

/**
 * Tablas que se escriben local pero **nunca** se suben: el servidor es la
 * autoridad sobre ellas (§11.1). Ver la nota de arriba.
 */
const TABLAS_SOLO_REFLEJO: ReadonlySet<string> = new Set(['actividad']);

/**
 * Códigos de error de Postgres que no se arreglan reintentando: violan una
 * restricción o un permiso. Reintentarlos para siempre dejaría la cola
 * bloqueada y el residente sin poder sincronizar nada más (§12.5).
 */
const CODIGOS_NO_REINTENTABLES: ReadonlySet<string> = new Set([
  '22P02', // texto mal formado para el tipo
  '23502', // not null
  '23503', // llave foránea
  '23505', // llave duplicada
  '23514', // CHECK — incluye los topes del §6
  '42501', // permiso denegado / RLS
  '42703', // columna inexistente
]);

interface ErrorPostgrest {
  readonly message: string;
  readonly code?: string;
}

/** Falla de una operación de la cola de subida. */
export class ErrorDeSubida extends Error {
  readonly codigo: string | undefined;
  readonly reintentable: boolean;

  constructor(tabla: string, error: ErrorPostgrest) {
    super(`[${tabla}] ${error.message}`);
    this.name = 'ErrorDeSubida';
    this.codigo = error.code;
    this.reintentable = !(error.code !== undefined && CODIGOS_NO_REINTENTABLES.has(error.code));
  }
}

/**
 * Campos que el cliente no decide y el servidor sí.
 *
 * `registro_avance.sync_status` se escribe local como `pendiente` (§7.6) y
 * pasa a `sincronizado` al subir; el valor del servidor baja después por
 * sync y limpia la bandera local sin lógica extra en la pantalla.
 */
function camposDelServidor(tabla: string): Record<string, unknown> {
  if (tabla === 'registro_avance' || tabla === 'revision_fisica') {
    return { sync_status: 'sincronizado' };
  }
  return {};
}

/**
 * Columnas `jsonb` en Postgres que SQLite guarda como texto (el esquema
 * local solo tiene text/real/integer). Si se subieran tal cual, Postgres
 * guardaría la cadena `"[]"` en vez del arreglo `[]`.
 */
const COLUMNAS_JSON: Readonly<Record<string, readonly string[]>> = {
  registro_avance: ['evidencias'],
  revision_fisica: ['fotos'],
  incidencia: ['evidencias'],
};

function normalizar(tabla: string, fila: Record<string, unknown>): Record<string, unknown> {
  const columnas = COLUMNAS_JSON[tabla];
  if (!columnas) return fila;

  const salida = { ...fila };
  for (const columna of columnas) {
    const valor = salida[columna];
    if (typeof valor !== 'string') continue;
    try {
      salida[columna] = JSON.parse(valor);
    } catch {
      // Texto que no es JSON: se manda como arreglo vacío antes que romper
      // la cola entera por una fila mal formada.
      salida[columna] = [];
    }
  }
  return salida;
}

async function aplicarOperacion(operacion: CrudEntry): Promise<void> {
  const tabla = supabase.from(operacion.table);

  switch (operacion.op) {
    case UpdateType.PUT: {
      const fila = normalizar(operacion.table, {
        ...(operacion.opData ?? {}),
        id: operacion.id,
        ...camposDelServidor(operacion.table),
      });
      const { error } = await tabla.upsert(fila);
      if (error) throw new ErrorDeSubida(operacion.table, error);
      return;
    }

    case UpdateType.PATCH: {
      const cambios = normalizar(operacion.table, {
        ...(operacion.opData ?? {}),
        ...camposDelServidor(operacion.table),
      });
      const { error } = await tabla.update(cambios).eq('id', operacion.id);
      if (error) throw new ErrorDeSubida(operacion.table, error);
      return;
    }

    case UpdateType.DELETE: {
      const { error } = await tabla.delete().eq('id', operacion.id);
      if (error) throw new ErrorDeSubida(operacion.table, error);
      return;
    }
  }
}

export class ConectorObraCtrl implements PowerSyncBackendConnector {
  /**
   * Credenciales frescas en cada conexión: el token es el mismo JWT de
   * Supabase Auth que lleva `org_id`/`rol` (§12.4), así que las sync rules
   * ven exactamente al mismo usuario que RLS.
   */
  async fetchCredentials(): Promise<PowerSyncCredentials | null> {
    if (!URL_POWERSYNC) return null;

    const { data, error } = await supabase.auth.getSession();
    if (error) throw error;
    if (!data.session) return null;

    return {
      endpoint: URL_POWERSYNC,
      token: data.session.access_token,
      expiresAt: data.session.expires_at ? new Date(data.session.expires_at * 1000) : undefined,
    };
  }

  /**
   * Sube una transacción de la cola local. Un error lanzado hace que
   * PowerSync reintente más tarde (es lo que queremos al perder señal); un
   * error de restricción se descarta con registro en consola, porque
   * reintentarlo nunca va a funcionar y dejaría la cola atorada.
   */
  async uploadData(base: AbstractPowerSyncDatabase): Promise<void> {
    const transaccion = await base.getNextCrudTransaction();
    if (!transaccion) return;

    try {
      for (const operacion of transaccion.crud) {
        if (TABLAS_SOLO_REFLEJO.has(operacion.table)) continue;
        await aplicarOperacion(operacion);
      }
      await transaccion.complete();
    } catch (e) {
      if (e instanceof ErrorDeSubida && !e.reintentable) {
        console.error(
          '[sync] Cambio local rechazado por Postgres; se descarta de la cola ' +
            `(código ${e.codigo ?? 'sin código'}): ${e.message}`,
        );
        await transaccion.complete();
        return;
      }
      throw e;
    }
  }
}

export const conector = new ConectorObraCtrl();
