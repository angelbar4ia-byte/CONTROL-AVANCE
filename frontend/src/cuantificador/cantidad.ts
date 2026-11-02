/**
 * La cantidad de un componente por unidad de su concepto, formada por piezas comerciales (espejo de
 * `backend/.../domain/catalogos/cantidad.py`): `piezas ÷ largo × (1 + desperdicio %)`, a seis decimales.
 *
 * Ejemplo, el castillo K2: 4 varillas del no. 3 de 12 ml → 4 ÷ 12 = 0.333333 por ml, más 0.5 % de desperdicio = 0.335.
 * El servidor la vuelve a calcular; esto es la vista previa mientras se escribe.
 *
 * Funciones puras, sin DOM ni React.
 */

export interface FormulaDePiezas {
  readonly piezas: number;
  readonly largo: number;
  readonly desperdicioPct: number;
}

/** `null` si la fórmula no tiene sentido (piezas o largo no positivos, desperdicio fuera de 0 a 100). */
export function cantidadPorPiezas({ piezas, largo, desperdicioPct }: FormulaDePiezas): number | null {
  if (!(piezas > 0) || !(largo > 0) || !(desperdicioPct >= 0 && desperdicioPct <= 100)) return null;
  const valor = (piezas / largo) * (1 + desperdicioPct / 100);
  return Math.round(valor * 1e6 + Number.EPSILON) / 1e6;
}

/** Un número escrito a mano (con coma o punto); `NaN` si no lo es. */
export function numeroDeTexto(texto: string): number {
  const t = texto.trim().replace(',', '.');
  return t === '' ? Number.NaN : Number(t);
}
