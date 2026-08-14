/**
 * Formato de números, moneda y fechas.
 *
 * Spec §12.10 · DESIGN_SYSTEM.md §4.
 *
 * Moneda **MXN es-MX**, fechas `dd mmm aa`. Todo lo numérico se muestra con
 * `--f-mono` + `tabular-nums` para que las columnas alineen (§12.10).
 *
 * Los `Intl.*Format` se crean una vez a nivel de módulo: construirlos en cada
 * celda es caro en tablas de miles de renglones (§12.9).
 */

const MXN = new Intl.NumberFormat('es-MX', {
  style: 'currency',
  currency: 'MXN',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const NUM = new Intl.NumberFormat('es-MX', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const NUM_ENTERO = new Intl.NumberFormat('es-MX', { maximumFractionDigits: 0 });

const PCT = new Intl.NumberFormat('es-MX', {
  style: 'percent',
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const MESES = [
  'ene', 'feb', 'mar', 'abr', 'may', 'jun',
  'jul', 'ago', 'sep', 'oct', 'nov', 'dic',
] as const;

/** Importe en MXN: `$1,234.50`. */
export function fmtMXN(valor: number | string | null | undefined): string {
  if (valor === null || valor === undefined || valor === '') return '—';
  const n = typeof valor === 'string' ? Number(valor) : valor;
  return Number.isFinite(n) ? MXN.format(n) : '—';
}

/** Cantidad con 2 decimales: `1,234.50`. */
export function fmtNum(valor: number | string | null | undefined): string {
  if (valor === null || valor === undefined || valor === '') return '—';
  const n = typeof valor === 'string' ? Number(valor) : valor;
  return Number.isFinite(n) ? NUM.format(n) : '—';
}

export function fmtEntero(valor: number | null | undefined): string {
  return valor === null || valor === undefined ? '—' : NUM_ENTERO.format(valor);
}

/**
 * Porcentaje. Recibe el valor **como se guarda en BD** (0–100), no 0–1:
 * `avance_pct` es `numeric(5,2)` en el rango 0–100 (§7.6).
 */
export function fmtPct(pct: number | string | null | undefined): string {
  if (pct === null || pct === undefined || pct === '') return '—';
  const n = typeof pct === 'string' ? Number(pct) : pct;
  return Number.isFinite(n) ? PCT.format(n / 100) : '—';
}

const SOLO_FECHA = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Fecha corta `dd mmm aa` (§12.10). Acepta `Date` o ISO de Postgres. */
export function fmtFecha(valor: Date | string | null | undefined): string {
  if (!valor) return '—';

  // Postgres devuelve fechas puras (`date`, sin hora) como `YYYY-MM-DD`.
  // `new Date('YYYY-MM-DD')` las interpreta como medianoche UTC, así que en
  // cualquier huso al oeste de Greenwich (incluida toda la República
  // Mexicana, §1) el día local queda un día atrás. Se parsean a mano como
  // fecha local para evitar el corrimiento.
  let d: Date;
  if (valor instanceof Date) {
    d = valor;
  } else {
    const m = SOLO_FECHA.exec(valor);
    d = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(valor);
  }

  if (Number.isNaN(d.getTime())) return '—';

  const dia = String(d.getDate()).padStart(2, '0');
  const mes = MESES[d.getMonth()] ?? '';
  const anio = String(d.getFullYear()).slice(-2);
  return `${dia} ${mes} ${anio}`;
}

/** Etiqueta de semana de obra: `S21 · 2026` (§3.1). */
export function fmtSemana(semana: number, anio: number): string {
  return `S${String(semana).padStart(2, '0')} · ${anio}`;
}

/**
 * Color semántico de una barra de avance (DESIGN_SYSTEM.md §4):
 * `≥ 90 → ok` · `< 25 → danger` · resto neutro.
 */
export function colorAvance(pct: number): 'ok' | 'danger' | 'accent' {
  if (pct >= 90) return 'ok';
  if (pct < 25) return 'danger';
  return 'accent';
}
