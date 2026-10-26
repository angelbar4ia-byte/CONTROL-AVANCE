/**
 * Textos del cuantificador.
 *
 * No hay aquí reglas de permiso: los cuatro roles que existen en ObraCtrl
 * trazan (cerebro MODELO.md §1b, «Quién puede trazar»), así que ningún botón
 * del visor se esconde por rol. Si alguna vez deja de ser cierto, la frontera
 * real sigue siendo el RBAC del backend y RLS (§12.4).
 */

import type { MedidaDeTrazo } from './geometria';

const ETIQUETA_MEDIDA: Record<MedidaDeTrazo, string> = {
  area: 'Área',
  perimetro: 'Perímetro',
  longitud: 'Longitud',
  conteo: 'Conteo',
};

export function etiquetaMedida(medida: string): string {
  return ETIQUETA_MEDIDA[medida as MedidaDeTrazo] ?? medida;
}
