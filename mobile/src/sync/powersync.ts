/**
 * Offline-first con PowerSync.
 *
 * Spec §12.5 (offline y sincronización) · §11.3 workflow B · §12.4 (RLS).
 *
 * PowerSync mantiene una réplica **SQLite** en el dispositivo: la app lee y
 * escribe local y sincroniza en segundo plano. La captura de avances del
 * Residente y la revisión física de Control de obra funcionan **sin señal**;
 * al reconectar se concilian contra Postgres.
 *
 * ## El requisito que no se puede fallar (§12.4)
 *
 * Las **sync rules de PowerSync deben reflejar el mismo `org_id` y rol que
 * las políticas RLS**, o el offline expondría datos de otra organización.
 * El espejo de `app.obra_visible()` vive en `sync-rules.yaml`; si cambia el
 * alcance de un rol en `database/migrations/0011`, hay que cambiarlo ahí.
 *
 * ## Fotos
 *
 * No viajan por PowerSync ni por la API: se guardan local y se suben directo
 * a R2 en segundo plano con una presigned URL (§12.5).
 */

import { column, Schema, Table } from '@powersync/react-native';

/**
 * Esquema local. Es un **subconjunto** del esquema de Postgres (§7): solo lo
 * que se necesita en campo. Meter todo el catálogo de conceptos en cada
 * teléfono sería inútil y pesado.
 *
 * Los cambios de esquema deben ser compatibles con clientes que aún tienen
 * datos locales viejos y **cola de cambios sin sincronizar** (§12.12).
 */
export const esquemaLocal = new Schema({
  obra: new Table({
    org_id: column.text,
    cluster_id: column.text,
    clave: column.text,
    estatus: column.text,
    avance_pct: column.real,
    residente_id: column.text,
    fecha_inicio: column.text,
  }),

  actividad: new Table({
    org_id: column.text,
    obra_id: column.text,
    concepto_id: column.text,
    frente_id: column.text,
    descripcion: column.text,
    cant_base: column.real,
    cant_programada: column.real,
    cant_ejecutada: column.real,
    avance_pct: column.real,
    estatus: column.text,
    precio_unitario: column.real,
    precio_destajo: column.real,
    modo_pago: column.text,
    es_critica: column.integer,
    holgura: column.real,
    bloqueada: column.integer,
    fecha_inicio: column.text,
    fecha_termino: column.text,
  }),

  // Bitácora de captura diaria: es la tabla que más se escribe offline (§7.6)
  registro_avance: new Table({
    org_id: column.text,
    // Derivada de `actividad.obra_id` por trigger (migración 0021). El
    // cliente **no** la manda al capturar: el servidor la pisa. Está aquí
    // porque las data queries de las sync rules no admiten subconsulta y sin
    // ella esta tabla no se puede acotar a la obra del bucket (§12.5).
    obra_id: column.text,
    actividad_id: column.text,
    fecha: column.text,
    delta_ejecutado: column.real,
    usuario_id: column.text,
    evidencias: column.text,
    comentario: column.text,
    sync_status: column.text,
    device_id: column.text,
    capturado_en: column.text,
  }),

  incidencia: new Table({
    org_id: column.text,
    obra_id: column.text,
    frente_id: column.text,
    tipo: column.text,
    impacto: column.text,
    titulo: column.text,
    descripcion: column.text,
    estatus: column.text,
    creada_por: column.text,
    fecha_creada: column.text,
    fecha_limite: column.text,
  }),

  // Revisión física de Control de obra en campo (§7.8)
  revision_fisica: new Table({
    org_id: column.text,
    obra_id: column.text,
    actividad_id: column.text,
    usuario_id: column.text,
    fecha: column.text,
    fotos: column.text,
    comentario: column.text,
    calidad: column.integer,
    sync_status: column.text,
  }),

  // Catálogos mínimos para poder capturar sin señal
  frente: new Table({
    org_id: column.text,
    clave: column.text,
    nombre: column.text,
    orden: column.integer,
    color: column.text,
  }),

  concepto: new Table({
    org_id: column.text,
    clave: column.text,
    descripcion: column.text,
    unidad_id: column.text,
  }),
});

export type EsquemaLocal = (typeof esquemaLocal)['types'];

/**
 * Resolución de conflictos.
 *
 * Default: last-write-wins (§12.5). Pero el avance **no** puede resolverse
 * así: dos capturas del mismo día desde dispositivos distintos deben sumar
 * sus deltas, no pisarse. Por eso `registro_avance` guarda
 * `delta_ejecutado` y no un total: los deltas se acumulan sin conflicto, y
 * `actividad.cant_ejecutada` se deriva de su suma en el servidor.
 */
export const ESTRATEGIA_CONFLICTOS = {
  registro_avance: 'acumular-deltas',
  revision_fisica: 'acumular',
  actividad: 'servidor-manda',
  incidencia: 'last-write-wins',
} as const;
