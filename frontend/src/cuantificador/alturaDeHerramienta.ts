/**
 * La altura estándar del muro que propone el plano (driver `altura_estandar`, Paramétrico 4B; Ola 4C).
 *
 * Antes el plano proponía 2.6 m fijos al trazar. Ahora la propone el driver vigente de la obra (el de la obra si es ajustable y la
 * obra lo cambió; si no, el global; si no, 3.00 m). Q1: solo lo que NACE sin altura la toma de aquí; un trazo ya guardado conserva
 * la suya y nada guardado se recalcula al cambiar el driver.
 */

/** El valor de partida del driver (M-9). Solo vale mientras la obra no responde: el servidor da el vigente. */
export const ALTURA_ESTANDAR_DE_PARTIDA_M = 3;
export const DRIVER_ALTURA_ESTANDAR = 'altura_estandar';

interface DriverVigente {
  readonly clave: string;
  readonly valor_vigente: string | number;
}

/** La altura estándar de una lista de drivers de la obra; la de partida si no viene o no vale. */
export function alturaEstandarDe(drivers: readonly DriverVigente[] | null | undefined): number {
  const d = drivers?.find((x) => x.clave === DRIVER_ALTURA_ESTANDAR);
  const n = d ? Number(String(d.valor_vigente).replace(',', '.')) : NaN;
  return Number.isFinite(n) && n > 0 ? n : ALTURA_ESTANDAR_DE_PARTIDA_M;
}
