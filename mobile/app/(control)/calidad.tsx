/**
 * Calidad — promedio de las revisiones físicas (§7.8).
 *
 * La pantalla vive en `src/pantallas/Calidad.tsx`: es compartida entre roles
 * (§5.3) y esta ruta solo la monta para Control de obra.
 */

import { Calidad } from '@/pantallas/Calidad';

export default function Pantalla() {
  return <Calidad />;
}
