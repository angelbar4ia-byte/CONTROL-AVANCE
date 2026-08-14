/**
 * Tono visual compartido por los `.badge`/`.bar` del sistema de diseño
 * (DESIGN_SYSTEM.md §4). Cada feature mapea sus propios estatus a un tono;
 * este tipo es lo único que comparten, para no acoplar un feature a otro.
 */
export type TonoBadge = 'ok' | 'warn' | 'danger' | 'info' | 'accent' | 'outline';
