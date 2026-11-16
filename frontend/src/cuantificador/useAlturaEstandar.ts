/** El hook de la altura estándar de la obra (driver `altura_estandar`); lo puro vive en `alturaEstandar.ts`. */

import { useDriversDeObraApiV1ObrasObraIdDriversGet } from '@/api/generado/parametrico/parametrico';
import { alturaEstandarDe } from './alturaEstandar';

/** La altura estándar vigente de la obra. Mientras carga (o si falla) vale la de partida. */
export function useAlturaEstandar(obraId: string): number {
  const drivers = useDriversDeObraApiV1ObrasObraIdDriversGet(obraId, { query: { enabled: obraId !== '' } });
  return alturaEstandarDe(drivers.data);
}
